import pytest
import asyncio
import re
from app.database import get_database
from app.routes.chat import execute_rag_pipeline
from app.services.response_generator import get_contact_fields

NULL_VALUES = {"", "none", "null", "nan", "n/a", "na", "-", "--", "undefined", "not available", "not_available", "no data available"}

def raw_has_email(raw_doc):
    containers = [
        raw_doc,
        raw_doc.get("data") if isinstance(raw_doc.get("data"), dict) else {},
        raw_doc.get("normalized_data") if isinstance(raw_doc.get("normalized_data"), dict) else {},
        raw_doc.get("source_fields") if isinstance(raw_doc.get("source_fields"), dict) else {}
    ]
    for c in containers:
        for k, v in c.items():
            if any(x in k.lower() for x in ["email", "mail"]):
                s = str(v).strip().lower()
                if s and s not in NULL_VALUES and "@" in s:
                    return True
    return False

def raw_has_phone(raw_doc):
    containers = [
        raw_doc,
        raw_doc.get("data") if isinstance(raw_doc.get("data"), dict) else {},
        raw_doc.get("normalized_data") if isinstance(raw_doc.get("normalized_data"), dict) else {},
        raw_doc.get("source_fields") if isinstance(raw_doc.get("source_fields"), dict) else {}
    ]
    for c in containers:
        for k, v in c.items():
            if any(x in k.lower() for x in ["phone", "mobile", "tel", "contact number", "contact_no"]):
                s = str(v).strip().lower()
                digits = re.sub(r"\D", "", s)
                if len(digits) >= 5 and s not in NULL_VALUES:
                    return True
    return False


def test_tvs_display_values_raw_db_consistency():
    """
    1. For all TVS records: if raw DB has email in ANY candidate key, the returned record must contain it.
    """
    db = get_database()
    raw_docs = list(db["dataset_records"].find({"norm_company": {"$regex": r"\btvs\b"}}, {"embedding": 0}))
    res = asyncio.run(execute_rag_pipeline("tvs"))
    assert res.found is True
    assert res.count == len(raw_docs)

    raw_map = {str(d.get("_id")): d for d in raw_docs}
    for item in res.data:
        rid = str(item.get("_id") or item.get("id"))
        if rid in raw_map:
            raw_d = raw_map[rid]
            has_em = raw_has_email(raw_d)
            item_email = item.get("email") or item.get("Email")
            if has_em:
                assert item_email and item_email != "No data available", f"Record {rid} has raw email but displayed '{item_email}'"
            else:
                assert item_email == "No data available", f"Record {rid} has no raw email but displayed '{item_email}'"


def test_tvs_no_data_available_counts_match_header():
    """
    2. Number of cards showing 'No data available' for email == number of records with no email in raw DB.
    Must equal the header's count.
    """
    db = get_database()
    raw_docs = list(db["dataset_records"].find({"norm_company": {"$regex": r"\btvs\b"}}, {"embedding": 0}))
    raw_no_email_count = sum(1 for d in raw_docs if not raw_has_email(d))
    raw_with_email_count = len(raw_docs) - raw_no_email_count

    res = asyncio.run(execute_rag_pipeline("tvs"))
    cards_no_email = sum(1 for item in res.data if item.get("email") == "No data available")
    cards_with_email = sum(1 for item in res.data if item.get("email") != "No data available")

    assert cards_no_email == raw_no_email_count
    assert cards_with_email == raw_with_email_count
    assert f"{raw_with_email_count} contacts have an email" in res.message


def test_tvs_with_emails_only_real_emails():
    """
    3. 'tvs with emails' shows ONLY cards that display a real email (no 'No data available').
    """
    res = asyncio.run(execute_rag_pipeline("tvs with emails"))
    assert res.found is True
    assert res.count > 0
    for item in res.data:
        em = item.get("email")
        assert em and em != "No data available" and "@" in em


def test_tvs_without_emails_only_no_data_available():
    """
    4. 'tvs without emails' shows ONLY cards whose email is 'No data available'.
    """
    res = asyncio.run(execute_rag_pipeline("tvs without emails"))
    assert res.found is True
    assert res.count > 0
    for item in res.data:
        em = item.get("email")
        assert em == "No data available"


@pytest.mark.parametrize("company_name", ["ashok leyland", "bosch", "premier cnc", "mahindra"])
def test_other_large_companies_display_values_integrity(company_name):
    """
    5. Repeat 1 to 4 for 'ashok leyland' and 3 other large companies.
    """
    db = get_database()
    raw_docs = list(db["dataset_records"].find({"norm_company": {"$regex": rf"\b{re.escape(company_name)}\b"}}, {"embedding": 0}))
    res = asyncio.run(execute_rag_pipeline(company_name))
    assert res.found is True
    assert res.count == len(raw_docs)

    raw_with_emails = sum(1 for d in raw_docs if raw_has_email(d))
    cards_with_emails = sum(1 for d in res.data if d.get("email") != "No data available")
    assert cards_with_emails == raw_with_emails

    # Test with emails filter
    res_with_em = asyncio.run(execute_rag_pipeline(f"{company_name} with emails"))
    assert res_with_em.count == raw_with_emails
    for d in res_with_em.data:
        assert d.get("email") != "No data available"


def test_record_with_multiple_emails_and_phones():
    """
    6. A record with 2 emails and 2 phones shows all of them.
    """
    sample_rec = {
        "company": "Test Multi Auto Ltd",
        "data": {
            "Company Name": "Test Multi Auto Ltd",
            "Person Name": "John Doe",
            "Designation": "VP Engg",
            "Contact Number": "+919876543210",
            "Phone 2": "+919876543211",
            "Email": "john1@test.com",
            "Email 2": "john2@test.com",
            "Location": "Chennai, Tamil Nadu"
        },
        "dataset_id": "mock_id"
    }

    fields = get_contact_fields(sample_rec)
    assert len(fields["emails"]) == 2
    assert "john1@test.com" in fields["emails"]
    assert "john2@test.com" in fields["emails"]
    assert len(fields["phones"]) == 2


def test_final_rendered_response_structure():
    """
    7. Check the final rendered response (the actual API JSON/text the frontend gets).
    """
    res = asyncio.run(execute_rag_pipeline("tvs"))
    assert res.success is True
    assert isinstance(res.data, list)
    assert len(res.data) > 0
    assert "Delphi" in res.message or "TVS" in res.message
    first_item = res.data[0]
    assert "Company Name" in first_item or "company" in first_item
    assert "Source File" in first_item or "source_file" in first_item
    assert "Contact Person" in first_item or "person" in first_item


def test_group_and_deduplicate_contacts_same_company_same_location():
    """
    8. Records with same company & same location combine contacts.
    Records with different location stay separated.
    Exact duplicates are eliminated.
    """
    from app.services.response_generator import group_and_deduplicate_records, format_strict_company_records

    records = [
        {
            "company": "TVS Motor Company",
            "data": {
                "Company Name": "TVS Motor Company",
                "Person Name": "Ravi Kumar",
                "Designation": "Quality Manager",
                "Email": "ravi@tvs.in",
                "Contact Number": "+919876543210",
                "Location": "Hosur, Tamil Nadu"
            },
            "dataset_id": "test_ds"
        },
        # Duplicate of record 1
        {
            "company": "TVS Motor Company",
            "data": {
                "Company Name": "TVS Motor Company",
                "Person Name": "Ravi Kumar",
                "Designation": "Quality Manager",
                "Email": "ravi@tvs.in",
                "Contact Number": "+919876543210",
                "Location": "Hosur, Tamil Nadu"
            },
            "dataset_id": "test_ds"
        },
        # Same company & same location, but different contact person
        {
            "company": "TVS Motor Company",
            "data": {
                "Company Name": "TVS Motor Company",
                "Person Name": "Priya Sharma",
                "Designation": "Purchase Head",
                "Email": "priya@tvs.in",
                "Contact Number": "+919876543211",
                "Location": "Hosur, Tamil Nadu"
            },
            "dataset_id": "test_ds"
        },
        # Same company, but DIFFERENT location (Chennai)
        {
            "company": "TVS Motor Company",
            "data": {
                "Company Name": "TVS Motor Company",
                "Person Name": "Anand R",
                "Designation": "Plant Head",
                "Email": "anand@tvs.in",
                "Contact Number": "+919876543212",
                "Location": "Chennai, Tamil Nadu"
            },
            "dataset_id": "test_ds"
        }
    ]

    grouped = group_and_deduplicate_records(records)
    # Total distinct company entries: Hosur group + Chennai group = 2
    assert len(grouped) == 2, f"Expected 2 groups, got {len(grouped)}"
    
    # Hosur group has 2 contacts (Ravi and Priya, duplicate Ravi removed)
    hosur_group = next(g for g in grouped if "hosur" in g["address"].lower())
    assert len(hosur_group["contacts"]) == 2
    assert hosur_group["contacts"][0]["name"] == "Ravi Kumar"
    assert hosur_group["contacts"][1]["name"] == "Priya Sharma"

    # Formatted markdown output has 2 Contact Persons under Hosur
    rendered = format_strict_company_records(records)
    assert "Contact Person 1:" in rendered
    assert "Contact Person 2:" in rendered
    assert "Ravi Kumar" in rendered
    assert "Priya Sharma" in rendered
    assert "Anand R" in rendered


def test_multi_company_query_does_not_bleed_previous_session():
    """
    9. Entering multiple company names in a new query searches those companies
    and is not treated as a follow-up to a previous search session.
    """
    session_id = "test_multi_company_isolation_session"
    
    # 1. First search TVS
    res1 = asyncio.run(execute_rag_pipeline("tvs", session_id=session_id))
    assert res1.found is True

    # 2. Search multiple new companies
    res2 = asyncio.run(execute_rag_pipeline("ashok leyland and bosch", session_id=session_id))
    assert res2.found is True
    # Verify that results are for Ashok Leyland and Bosch, not filtering previous TVS
    comp_names = [d.get("company", "").lower() for d in res2.data]
    assert any("ashok" in c for c in comp_names)
    assert any("bosch" in c for c in comp_names)


def test_another_company_query_does_not_return_previous_company():
    """
    10. Searching TVS, then asking for 'another company list which having email alone'
    must NOT return TVS records, but must return a distinct company from the DB with emails.
    Subsequent 'another company' request must return yet another distinct company.
    """
    session_id = "test_another_company_session"

    # Step 1: Search TVS
    res1 = asyncio.run(execute_rag_pipeline("tvs company list", session_id=session_id))
    assert res1.found is True
    assert res1.count > 0
    tvs_comps = {d.get("company", "").lower() for d in res1.data}
    assert any("tvs" in c for c in tvs_comps)

    # Step 2: Ask for another company with typo in 'aanothe rcompany'
    history = [
        {"role": "user", "content": "tvs company list"},
        {"role": "assistant", "content": f"Found {res1.count} records for TVS"}
    ]
    res2 = asyncio.run(execute_rag_pipeline(
        "give me aanothe rcompany list which having email alone",
        history=history,
        session_id=session_id
    ))
    assert res2.found is True
    assert res2.count > 0
    comps2 = {d.get("company", "").lower() for d in res2.data}
    assert not any("tvs" in c for c in comps2), f"TVS should not be returned in turn 2, got {comps2}"
    for d in res2.data:
        em = d.get("email") or d.get("Email")
        assert em and em != "No data available" and "@" in em

    # Step 3: Ask for another company again
    history.extend([
        {"role": "user", "content": "give me aanothe rcompany list which having email alone"},
        {"role": "assistant", "content": f"Found {res2.count} records"}
    ])
    res3 = asyncio.run(execute_rag_pipeline(
        "give me another company list which having email alone",
        history=history,
        session_id=session_id
    ))
    assert res3.found is True
    assert res3.count > 0
    comps3 = {d.get("company", "").lower() for d in res3.data}
    assert not any("tvs" in c for c in comps3), f"TVS should not be returned in turn 3, got {comps3}"
    assert not any(any(c2_sub in c3 for c2_sub in ["brakes"]) for c3 in comps3), f"Turn 2 company should not repeat in turn 3, got {comps3}"
    for d in res3.data:
        em = d.get("email") or d.get("Email")
        assert em and em != "No data available" and "@" in em


