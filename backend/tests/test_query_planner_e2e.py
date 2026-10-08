import pytest
from unittest.mock import patch, MagicMock
from app.services.query_planner import (
    QueryPlan,
    split_pasted_companies,
    rule_based_plan,
    plan_query_execution,
    execute_planned_retrieval
)
from app.services.source_resolver import (
    get_dataset_name,
    get_record_sources,
    get_record_source_display,
    get_company_sources_summary,
    _DATASET_ID_TO_NAME
)
from app.services.response_generator import (
    format_strict_company_records,
    format_followup_answer
)


def test_split_pasted_companies_various_delimiters():
    # 1. Newlines and numbered lists
    pasted_1 = """1. Ashok Leyland
2. TVS Motor Company
3. Bosch India
4. Premier CNC
5. Sundram Fasteners"""
    companies = split_pasted_companies(pasted_1)
    assert len(companies) == 5
    assert companies[0] == "Ashok Leyland"
    assert companies[1] == "TVS Motor Company"
    assert companies[2] == "Bosch India"
    assert companies[3] == "Premier CNC"
    assert companies[4] == "Sundram Fasteners"

    # 2. Comma separated list
    pasted_2 = "Ashok Leyland, TVS Motor Company, Bosch India, Premier CNC"
    companies2 = split_pasted_companies(pasted_2)
    assert len(companies2) == 4
    assert "Ashok Leyland" in companies2
    assert "Premier CNC" in companies2

    # 3. Semicolon and bullet separated
    pasted_3 = "- Bharat Heavy Electricals; - BHEL Trichy; * Larsen & Toubro"
    companies3 = split_pasted_companies(pasted_3)
    assert len(companies3) == 3
    assert "Bharat Heavy Electricals" in companies3
    assert "BHEL Trichy" in companies3
    assert "Larsen & Toubro" in companies3


def test_rule_based_planner_fallback():
    # 1. Email filter
    plan1 = rule_based_plan("give the list of ashok leyland companies where emails available only")
    assert plan1.intent == "lookup"
    assert "ashok leyland" in [c.lower() for c in plan1.companies]
    assert "email" in plan1.must_have
    assert plan1.only_requested_fields is True
    assert "email" in plan1.fields

    # 2. TVS Quality persons alone
    plan2 = rule_based_plan("give me tvs quality dept persons alone")
    assert plan2.intent == "lookup"
    assert "tvs" in [c.lower() for c in plan2.companies]
    assert "designation" in plan2.must_have or "contact_person" in plan2.fields
    assert any(k in ["quality", "qa", "qc"] for k in plan2.designation_keywords)
    assert plan2.only_requested_fields is True

    # 3. Followup availability filter
    plan3 = rule_based_plan("from those TVS companies, show only the ones that have an email")
    assert plan3.intent == "filter_previous"
    assert plan3.use_previous_results is True
    assert "email" in plan3.must_have

    # 4. Count query
    plan4 = rule_based_plan("how many of them have phone number")
    assert plan4.intent == "count"
    assert plan4.use_previous_results is True
    assert "phone" in plan4.must_have


import asyncio
from app.services.query_understanding import StructuredQuery
from app.services.source_resolver import set_cached_dataset_map


def test_llm_planner_fallback_on_error():
    # When LLM fails, times out, or returns bad data, plan_query_execution must fallback safely
    with patch("httpx.AsyncClient.post", side_effect=Exception("Connection refused")):
        plan = asyncio.run(plan_query_execution("ashok leyland with email only"))
        assert isinstance(plan, QueryPlan)
        assert "ashok leyland" in [c.lower() for c in plan.companies]
        assert "email" in plan.must_have


def test_source_resolver_dataset_name_cleanliness():
    # Populate mock cache
    set_cached_dataset_map({
        "ds_101": "Metrology_5000_2628_Cleaned_R1.0",
        "ds_102": "Cleaned_Met_Sales_Unique_R1.0"
    })

    rec1 = {"_id": "r1", "dataset_id": "ds_101", "company": "Alpha Corp"}
    rec2 = {"_id": "r2", "dataset_id": "ds_102", "company": "Alpha Corp"}
    rec_merged = {"_id": "r3", "dataset_id": "ds_101", "dataset_name": "Metrology_5000_2628_Cleaned_R1.0 | Cleaned_Met_Sales_Unique_R1.0"}

    # 1. Strips .xlsx extension and returns mapped name
    assert get_dataset_name(rec1) == "Metrology_5000_2628_Cleaned_R1.0"
    assert get_dataset_name(rec2) == "Cleaned_Met_Sales_Unique_R1.0"

    # 2. Merged dataset names
    assert get_record_source_display(rec_merged) == "Metrology_5000_2628_Cleaned_R1.0, Cleaned_Met_Sales_Unique_R1.0"

    # 3. Summary list format
    summary = get_company_sources_summary([rec1, rec2])
    assert summary == "Metrology_5000_2628_Cleaned_R1.0, Cleaned_Met_Sales_Unique_R1.0"
    # Ensure NO sheet names or counts like Sheet1 or (8) are present
    assert "Sheet" not in summary
    assert "(" not in summary and ")" not in summary


def test_embedding_field_shielded_from_output():
    # Test that format_strict_company_records and formatting helpers never leak "embedding"
    test_records = [
        {
            "_id": "rec_001",
            "company": "TVS Motor Company",
            "contact_person": "Sundar",
            "designation": "Head Quality",
            "email": "sundar@tvs.in",
            "phone": "+91 9876543210",
            "dataset_name": "Automotive_OEM_Directory",
            "embedding": [0.123, -0.456, 0.789] * 256 # 768-d vector
        }
    ]

    sq = StructuredQuery(
        companies=["TVS Motor Company"],
        requested_fields=["email", "contact_person"],
        is_only_fields=True
    )
    formatted_text = format_strict_company_records(test_records, structured_query=sq)
    assert "embedding" not in formatted_text.lower()
    assert "0.123" not in formatted_text
    assert "Automotive_OEM_Directory" in formatted_text
    assert "sundar@tvs.in" in formatted_text


def test_selective_field_formatting_quality_and_email():
    # Scenario A: Email only
    records_email = [
        {
            "company": "Ashok Leyland Ltd",
            "contact_person": "Ramesh Kumar",
            "email": "ramesh@ashokleyland.com",
            "phone": "9840011223",
            "dataset_name": "Commercial_Vehicles_DB"
        },
        {
            "company": "Ashok Leyland Defense",
            "contact_person": "Suresh",
            "email": "suresh@defense.ashokleyland.com",
            "phone": "9840011224",
            "dataset_name": "Commercial_Vehicles_DB"
        }
    ]
    sq_email = StructuredQuery(
        companies=["Ashok Leyland"],
        requested_fields=["email"],
        is_only_fields=True
    )
    res_email = format_strict_company_records(records_email, structured_query=sq_email)
    assert "Ashok Leyland Ltd" in res_email
    assert "ramesh@ashokleyland.com" in res_email
    # Phone should be excluded when selective field is email only
    assert "9840011223" not in res_email

    # Scenario B: Quality persons alone
    records_quality = [
        {
            "company": "TVS Motor Company Ltd",
            "contact_person": "Venkatesh Rao",
            "designation": "Quality Assurance Manager",
            "email": "venkatesh@tvsmotor.com",
            "dataset_name": "Automotive_Directory"
        }
    ]
    sq_quality = StructuredQuery(
        companies=["TVS Motor Company Ltd"],
        requested_fields=["person", "designation"],
        is_only_fields=True
    )
    res_quality = format_strict_company_records(records_quality, structured_query=sq_quality)
    assert "TVS Motor Company Ltd" in res_quality
    assert "Venkatesh Rao" in res_quality
    assert "Quality Assurance Manager" in res_quality

