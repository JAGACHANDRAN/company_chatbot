import pytest
from app.services.query_understanding import fallback_query_understanding
from app.services.mongo_search import build_structured_mongo_filter
from app.services.retrieval_service import validate_record_relevance
from app.services.response_generator import generate_no_data_message, generate_deterministic_answer


def test_case_1_show_me_tvs_companies():
    q = "Show me TVS companies"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.email_required is None


def test_case_2_show_tvs_companies_with_email():
    q = "Show TVS companies with email"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.email_required is True


def test_case_3_which_tvs_companies_have_email_ids():
    q = "Which TVS companies have email IDs?"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.email_required is True


def test_case_4_give_me_tvs_companies_without_email():
    q = "Give me TVS companies without email"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.email_required is False


def test_case_5_find_quality_managers_in_chennai():
    q = "Find quality managers in Chennai"
    sq = fallback_query_understanding(q)
    assert sq.designation and "quality manager" in sq.designation.lower()
    assert sq.city and "chennai" in sq.city.lower()


def test_case_6_find_quality_managers_in_chennai_who_have_email():
    q = "Find quality managers in Chennai who have email"
    sq = fallback_query_understanding(q)
    assert sq.designation and "quality manager" in sq.designation.lower()
    assert sq.city and "chennai" in sq.city.lower()
    assert sq.email_required is True


def test_case_7_which_companies_in_tamil_nadu_have_phone_numbers():
    q = "Which companies in Tamil Nadu have phone numbers?"
    sq = fallback_query_understanding(q)
    assert sq.state and "tamil nadu" in sq.state.lower()
    assert sq.phone_required is True


def test_case_8_who_is_quality_manager_at_tvs_in_chennai():
    q = "Who is the Quality Manager at TVS in Chennai?"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.designation and "quality manager" in sq.designation.lower()
    assert sq.city and "chennai" in sq.city.lower()


def test_case_9_show_abc_company_no_data():
    q = "Show ABC company"
    sq = fallback_query_understanding(q)
    msg = generate_no_data_message(q, sq)
    assert "No data available for ABC company." in msg


def test_case_10_show_tvs_companies_with_email_no_data():
    q = "Show TVS companies with email"
    sq = fallback_query_understanding(q)
    msg = generate_no_data_message(q, sq)
    assert "No data available for TVS companies with an available email address." in msg


def test_case_11_emial_availble_tvs_companis():
    q = "emial availble tvs companis"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.email_required is True


def test_case_12_give_me_all_companies_of_tvs_having_mail_id():
    q = "give me all companies of tvs which are having mail id"
    sq = fallback_query_understanding(q)
    assert "TVS" in sq.companies
    assert sq.email_required is True


def test_relevance_guard_filters_missing_email():
    sq = fallback_query_understanding("Show TVS companies with email")
    rec_with_email = {
        "company_name": "TVS Motor Company",
        "email": "contact@tvs.com",
        "person_name": "Ravi Kumar"
    }
    rec_without_email = {
        "company_name": "TVS Motor Company",
        "email": None,
        "person_name": "Ravi Kumar"
    }
    rec_with_placeholder_email = {
        "company_name": "TVS Motor Company",
        "email": "Not Available",
        "person_name": "Ravi Kumar"
    }

    assert validate_record_relevance(rec_with_email, sq) is True
    assert validate_record_relevance(rec_without_email, sq) is False
    assert validate_record_relevance(rec_with_placeholder_email, sq) is False


def test_case_tvs_company_email_available_list():
    q = "tvs company email available list"
    sq = fallback_query_understanding(q)
    assert sq.companies == ["TVS"]
    assert sq.email_required is True


def test_format_strict_company_records_filters_contacts_without_email():
    from app.services.response_generator import format_strict_company_records
    sq = fallback_query_understanding("tvs company email available list")
    records = [
        {
            "company_name": "TVS Motor Company",
            "person_name": "Ravi Kumar",
            "email": "ravi@tvs.com",
            "source_file": "file1.xlsx"
        },
        {
            "company_name": "TVS Motor Company",
            "person_name": "Arun NoEmail",
            "email": None,
            "source_file": "file1.xlsx"
        }
    ]
    formatted = format_strict_company_records(records, structured_query=sq)
    assert "Ravi Kumar" in formatted
    assert "ravi@tvs.com" in formatted
    assert "Arun NoEmail" not in formatted

