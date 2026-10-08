import pytest
from app.services.query_understanding import (
    fallback_query_understanding,
    resolve_followup_context,
    detect_field_requests,
    StructuredQuery
)
from app.services.response_generator import format_field_specific_answer, format_strict_company_records


def test_field_detection_emails_alone():
    """Verify detection of 'emails alone' / 'only emails'."""
    sq = fallback_query_understanding("tvs companies emails alone")
    assert "email" in sq.requested_fields
    assert sq.is_only_fields is True
    assert sq.companies == ["TVS"]


def test_field_detection_emails_of_tvs_companies_list_alsone():
    """Verify detection of 'the emails of tvs companies list alsone' with typos."""
    sq = fallback_query_understanding("the emails of tvs companies list alsone")
    assert "email" in sq.requested_fields
    assert sq.is_only_fields is True
    assert sq.companies == ["TVS"]


def test_field_detection_emails_of_tvs():
    """Verify detection of 'give me emails of tvs companies'."""
    sq = fallback_query_understanding("give me emails of tvs companies")
    assert "email" in sq.requested_fields
    assert sq.companies == ["TVS"]


def test_field_detection_contact_numbers():
    """Verify detection of phone / contact number queries."""
    sq = fallback_query_understanding("Show me TVS contact numbers")
    assert "phone" in sq.requested_fields
    assert sq.companies == ["TVS"]


def test_field_detection_multi_fields():
    """Verify detection of multiple requested fields (city, state, phone)."""
    sq = fallback_query_understanding("TVS company city, state and phone numbers")
    assert "city" in sq.requested_fields
    assert "state" in sq.requested_fields
    assert "phone" in sq.requested_fields


def test_full_details_override():
    """Verify 'all details' resets requested_fields to empty (full view)."""
    sq = fallback_query_understanding("Show TVS company all details")
    assert sq.requested_fields == []
    assert sq.is_only_fields is False


def test_missing_data_query():
    """Verify missing data query detection: 'which tvs companies have no email'."""
    sq = fallback_query_understanding("which tvs companies have no email")
    assert sq.missing_filter == "email"
    assert sq.email_required is False
    assert sq.companies == ["TVS"]


def test_count_query():
    """Verify count query detection: 'how many tvs companies have linkedin'."""
    sq = fallback_query_understanding("how many tvs companies have linkedin")
    assert sq.is_count_query is True
    assert "linkedin" in sq.requested_fields or sq.linkedin_required is True
    assert sq.companies == ["TVS"]


def test_followup_field_switch():
    """Verify follow-up replaces requested field when user asks 'now their phone numbers'."""
    history = [
        {"user": "tvs companies emails alone", "assistant": "Found 2 companies matching 'TVS'..."}
    ]
    sq2 = fallback_query_understanding("now their phone numbers")
    resolved = resolve_followup_context(sq2, history=history)

    assert resolved.companies == ["TVS"]
    assert "phone" in resolved.requested_fields


def test_followup_add_column():
    """Verify follow-up appends column when user asks 'add address'."""
    history = [
        {"user": "tvs companies emails alone", "assistant": "Found 2 companies matching 'TVS'..."}
    ]
    sq2 = fallback_query_understanding("add address")
    resolved = resolve_followup_context(sq2, history=history)

    assert resolved.companies == ["TVS"]
    assert "email" in resolved.requested_fields
    assert "address" in resolved.requested_fields


def test_format_field_specific_answer_synthetic():
    """Verify response format has exact header and 'Not Available' values for missing fields."""
    synthetic_records = [
        {
            "Company Name": "TVS Synthetic Motor 1",
            "source_file": "synthetic_mock_1.csv",
            "Email": "info@synthetic-motor1.test",
            "Contact Number": "+91 99999 11111"
        },
        {
            "Company Name": "TVS Synthetic Motor 2",
            "source_file": "synthetic_mock_2.csv",
            "Email": "",
            "Contact Number": "+91 99999 22222"
        }
    ]

    sq = StructuredQuery(
        intent="company_search",
        companies=["TVS"],
        requested_fields=["email"]
    )

    formatted = format_field_specific_answer(synthetic_records, sq)

    assert "Found 2 companies matching 'TVS'. 1 have an email, 1 do not." in formatted
    assert "Company Name: TVS Synthetic Motor 1" in formatted
    assert "info@synthetic-motor1.test" in formatted
    assert "Company Name: TVS Synthetic Motor 2" in formatted
    assert "Email 1: Not Available" in formatted


def test_format_missing_field_answer_synthetic():
    """Verify missing field query shows only records missing that field."""
    synthetic_records = [
        {
            "Company Name": "TVS Synthetic With Email",
            "source_file": "mock.csv",
            "Email": "active@synthetic.test"
        },
        {
            "Company Name": "TVS Synthetic No Email",
            "source_file": "mock.csv",
            "Email": ""
        }
    ]

    sq = StructuredQuery(
        intent="company_search",
        companies=["TVS"],
        missing_filter="email"
    )

    formatted = format_field_specific_answer(synthetic_records, sq)
    assert "Found 1 companies matching 'TVS' with no email." in formatted
    assert "TVS Synthetic No Email" in formatted


def test_format_field_specific_answer_nested_containers():
    """Verify field-specific extraction works across MongoDB raw_data, data, and normalized_data sub-dictionaries."""
    synthetic_nested = [
        {
            "_id": "doc1",
            "source_file": "nested_records.xlsx",
            "data": {
                "company": "TVS Synthetic Motors Pvt Ltd",
                "email": "contact@synthetic-motors.test",
                "phone": "+91 98888 77777"
            },
            "raw_data": {
                "Company Name": "TVS Synthetic Motors Pvt Ltd",
                "Email ID": "contact@synthetic-motors.test",
                "Mobile": "+91 98888 77777"
            }
        }
    ]

    sq = StructuredQuery(
        intent="company_search",
        companies=["TVS"],
        requested_fields=["email", "phone"]
    )

    formatted = format_field_specific_answer(synthetic_nested, sq)
    assert "Company Name: TVS Synthetic Motors Pvt Ltd" in formatted
    assert "contact@synthetic-motors.test" in formatted
    assert "+91 98888 77777" in formatted
