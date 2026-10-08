import pytest
from app.services.source_resolver import (
    get_record_sources,
    get_record_source_display,
    get_company_sources_summary
)
from app.services.query_understanding import (
    detect_followup_availability_filter,
    FollowupFilter,
    fallback_query_understanding
)
from app.services.session_cache import (
    store_last_result_set,
    get_last_result_set,
    update_current_result_set,
    reset_session_filter,
    clear_session
)
from app.services.response_generator import (
    format_followup_answer,
    format_strict_company_records
)
from app.routes.chat import matches_followup_filter


def test_source_resolver_single_and_merged():
    # 1. Single non-merged record
    rec1 = {"company": "Alpha Corp", "person": "Alice", "dataset_name": "Alpha_Database"}
    assert get_record_sources(rec1) == ["Alpha_Database"]
    assert get_record_source_display(rec1) == "Alpha_Database"

    # 2. Merged record with pipe-separated Sources
    rec2 = {
        "company": "Beta Corp",
        "person": "Bob",
        "dataset_name": "ACMEE 2023 | ACMEE 15 - 19 | ACMEE 2023"
    }
    assert get_record_sources(rec2) == ["ACMEE 2023", "ACMEE 15 - 19"]
    assert get_record_source_display(rec2) == "ACMEE 2023, ACMEE 15 - 19"

    # 3. Missing / empty source
    rec3 = {"company": "Gamma Corp", "person": "Charlie"}
    assert get_record_sources(rec3) == ["Not available"]
    assert get_record_source_display(rec3) == "Not available"

    # 4. Company level sources summary (clean comma-separated dataset names, NO counts)
    summary = get_company_sources_summary([rec1, rec2, rec3])
    assert summary == "Alpha_Database, ACMEE 2023, ACMEE 15 - 19"


def test_detect_followup_availability_filters():
    # Email required
    f1 = detect_followup_availability_filter("from those TVS companies, show only the ones that have an email")
    assert f1 is not None
    assert f1.is_followup is True
    assert any(c["field"] == "email" and c["required"] is True for c in f1.conditions)

    # Alternate synonym
    f2 = detect_followup_availability_filter("give the ones having mail id")
    assert f2 is not None
    assert any(c["field"] == "email" and c["required"] is True for c in f2.conditions)

    # Without email (complement)
    f3 = detect_followup_availability_filter("those without email")
    assert f3 is not None
    assert any(c["field"] == "email" and c["required"] is False for c in f3.conditions)

    # Compound AND condition
    f4 = detect_followup_availability_filter("with email and phone")
    assert f4 is not None
    assert f4.operator == "AND"
    assert any(c["field"] == "email" and c["required"] is True for c in f4.conditions)
    assert any(c["field"] == "phone" and c["required"] is True for c in f4.conditions)

    # Compound OR condition
    f5 = detect_followup_availability_filter("with email or phone")
    assert f5 is not None
    assert f5.operator == "OR"

    # Location narrowing
    f6 = detect_followup_availability_filter("now only those in Chennai")
    assert f6 is not None
    assert f6.city_filter == "Chennai" or f6.location_filter == "Chennai"

    # Count queries
    f7 = detect_followup_availability_filter("how many of them have email")
    assert f7 is not None
    assert f7.is_count_query is True

    # Reset command
    f8 = detect_followup_availability_filter("reset")
    assert f8 is not None
    assert f8.is_reset is True

    f9 = detect_followup_availability_filter("show all again")
    assert f9 is not None
    assert f9.is_reset is True


def test_session_cache_and_filter_stacking():
    test_sid = "test_session_123"
    clear_session(test_sid)

    # Synthetic documents
    mock_records = [
        {"_id": "doc1", "company": "TVS Motor", "person": "P1", "email": "p1@tvs.com", "phone": "9876543210", "city": "Chennai"},
        {"_id": "doc2", "company": "TVS Electronics", "person": "P2", "email": "p2@tvs.com", "phone": "", "city": "Bangalore"},
        {"_id": "doc3", "company": "TVS Supply", "person": "P3", "email": "", "phone": "9876543212", "city": "Chennai"},
        {"_id": "doc4", "company": "TVS Credit", "person": "P4", "email": "", "phone": "", "city": "Mumbai"},
        {"_id": "doc5", "company": "TVS Training", "person": "P5", "email": "p5@tvs.com", "phone": "9876543214", "city": "Chennai"},
    ]

    store_last_result_set(
        session_id=test_sid,
        records=mock_records,
        company="TVS",
        columns_shown=["email", "phone"]
    )

    state = get_last_result_set(test_sid)
    assert state is not None
    assert len(state["original_ids"]) == 5
    assert len(state["current_ids"]) == 5

    # 1. Filter: "with email"
    followup_email = detect_followup_availability_filter("show only the ones having email")
    matched_with_email = [r for r in mock_records if matches_followup_filter(r, followup_email)]
    assert len(matched_with_email) == 3
    assert set(r["_id"] for r in matched_with_email) == {"doc1", "doc2", "doc5"}

    # 2. Filter: "without email" (Complement test: with + without = N)
    followup_no_email = detect_followup_availability_filter("those without email")
    matched_no_email = [r for r in mock_records if matches_followup_filter(r, followup_no_email)]
    assert len(matched_no_email) == 2
    assert set(r["_id"] for r in matched_no_email) == {"doc3", "doc4"}
    assert len(matched_with_email) + len(matched_no_email) == len(mock_records)

    # 3. Filter stacking: Update current_ids to matched_with_email, then filter by "now only Chennai"
    update_current_result_set(test_sid, [r["_id"] for r in matched_with_email], "having email")
    state_after_step1 = get_last_result_set(test_sid)
    assert len(state_after_step1["current_ids"]) == 3

    followup_chennai = detect_followup_availability_filter("now only those in Chennai")
    narrowed = [r for r in matched_with_email if matches_followup_filter(r, followup_chennai)]
    assert len(narrowed) == 2
    assert set(r["_id"] for r in narrowed) == {"doc1", "doc5"}

    # 4. Reset: Restores original 5 records
    restored_ids = reset_session_filter(test_sid)
    assert len(restored_ids) == 5
    state_after_reset = get_last_result_set(test_sid)
    assert len(state_after_reset["current_ids"]) == 5


def test_followup_answer_formatting():
    # Synthetic records
    mock_records = [
        {"_id": "doc1", "company": "TVS Motor", "person": "Ravi", "email": "ravi@tvs.com", "dataset_name": "ACMEE 2023"}
    ]
    followup = detect_followup_availability_filter("give the ones having mail id")
    ans = format_followup_answer(
        records=mock_records,
        total_prev_count=5,
        followup_filter=followup,
        company_name="TVS"
    )
    assert "1 of 5 previous TVS results have an email. 4 excluded." in ans
    assert "Source File: ACMEE 2023" in ans
    assert "Company Name: TVS Motor" in ans

    # 0 match case
    ans_zero = format_followup_answer(
        records=[],
        total_prev_count=5,
        followup_filter=followup,
        company_name="TVS"
    )
    assert "0 of 5 previous TVS results have an email. All 5 records were excluded." in ans_zero
