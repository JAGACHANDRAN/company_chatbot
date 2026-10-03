import io
import re
import pytest
import mongomock
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import pandas as pd

from app.main import app
from app.database import get_database, get_collections
from app.services import data_cleaner
from app.services.contact_search import (
    build_vocab,
    parse_query,
    search,
    format_markdown,
    get_or_build_vocab,
    invalidate_vocab,
    ensure_contact_indexes,
    check_uncleaned_collections
)

# Sample Raw Data for testing
RAW_TEST_ROWS = [
    {
        "company": "Tata Motors Ltd",
        "person": "Rajesh Sharma",
        "designation": "Quality Manager",
        "phone": "+91 9876543210",
        "email": "rajesh@tatamotors.com",
        "location": "Pune",
    },
    {
        "company": "Tata Motors Ltd",
        "person": "Anil Deshmukh",
        "designation": "Purchase Head",
        "phone": "+91 9876543211",
        "email": "anil@tatamotors.com",
        "location": "Pune",
    },
    {
        "company": "JBM Group",
        "person": "Suresh Gupta",
        "designation": "Plant Head",
        "phone": "+91 9876543212",
        "email": "suresh@jbmgroup.com",
        "location": "Delhi",
    },
    {
        "company": "Kappa Motors Pvt Ltd",
        "person": "Vikas Patil",
        "designation": "Quality Manager",
        "phone": "+91 9876543213",
        "email": "vikas@kappamotors.com",
        "location": "Pune",
    },
    {
        "company": "Kappa Motors Pvt Ltd",
        "person": "Pooja Verma",
        "designation": "Director",
        "phone": "+91 9876543214",
        "email": "pooja@kappamotors.com",
        "location": "Mumbai",
    },
    {
        "company": "ABC Engineering Pvt Ltd",
        "person": "Kiran Rao",
        "designation": "Design Engineer",
        "phone": "+91 9876543215",
        "email": "kiran@abcengg.com",
        "location": "Bangalore",
    },
    {
        "company": "XYZ Tools Ltd",
        "person": "Ramesh Kumar",
        "designation": "Sales Executive",
        "phone": "+91 9876543216",
        "email": "ramesh@xyztools.com",
        "location": "Chennai",
    },
]


@pytest.fixture
def mock_db():
    """Builds a mongomock database populated with cleaned test records."""
    client = mongomock.MongoClient()
    db = client["calispec_test"]
    invalidate_vocab()

    # Clean the fake data using cleaner_core (clean_records)
    df = pd.DataFrame(RAW_TEST_ROWS)
    clean_result = data_cleaner.clean_records(df, "test_file.xlsx")
    cleaned_rows = clean_result.rows

    # Populate metrology collection
    col = db["metrology"]
    col.insert_many(cleaned_rows)
    ensure_contact_indexes(db, ["metrology"])
    return db


def test_tata_jbm_kappa_three_groups(mock_db):
    """'Tata Motors, JBM Group, Kappa Motors' -> 3 groups"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("Tata Motors, JBM Group, Kappa Motors", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] == 3
    found_companies = {g["company"] for g in res["groups"]}
    assert any("Tata Motors" in c for c in found_companies)
    assert any("JBM Group" in c for c in found_companies)
    assert any("Kappa Motors" in c for c in found_companies)


def test_abc_engineering_and_xyz_tools_two_groups(mock_db):
    """'abc engineering and xyz tools' -> 2 groups"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("abc engineering and xyz tools", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] == 2
    found_companies = {g["company"] for g in res["groups"]}
    assert any("ABC Engineering" in c for c in found_companies)
    assert any("XYZ Tools" in c for c in found_companies)


def test_partial_names_resolved(mock_db):
    """'tata, jbm, kappa' -> partial names resolved"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("tata, jbm, kappa", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] == 3
    found_companies = {g["company"] for g in res["groups"]}
    assert any("Tata Motors" in c for c in found_companies)
    assert any("JBM Group" in c for c in found_companies)
    assert any("Kappa Motors" in c for c in found_companies)


def test_typo_resolved_to_tata_motors(mock_db):
    """'tata motars' -> typo resolved to Tata Motors"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("tata motars", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] >= 1
    found_companies = {g["company"] for g in res["groups"]}
    assert any("Tata Motors" in c for c in found_companies)


def test_quality_managers_at_kappa_motors(mock_db):
    """'quality managers at Kappa Motors' -> Quality Manager returned"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("quality managers at Kappa Motors", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] == 1
    records = res["groups"][0]["records"]
    assert len(records) == 1
    assert "Quality Manager" in records[0]["designation"]
    assert records[0]["person"] == "Vikas Patil"


def test_quality_manager_designation(mock_db):
    """'quality manager' -> designation search alone"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("quality manager", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["total"] >= 2
    for g in res["groups"]:
        for r in g["records"]:
            assert "Quality Manager" in r["designation"]


def test_purchase_head_only(mock_db):
    """'purchase head' -> only purchase head titles"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("purchase head", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["total"] == 1
    rec = res["groups"][0]["records"][0]
    assert rec["designation"] == "Purchase Head"
    assert rec["person"] == "Anil Deshmukh"


def test_directors_designation(mock_db):
    """'directors' -> designation search alone"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("directors", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["total"] >= 1
    assert any("director" in r["designation"].lower() for g in res["groups"] for r in g["records"])


def test_foobar_and_kappa_motors(mock_db):
    """'Foobar Ltd, Kappa Motors' -> Kappa results + not found message"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("Foobar Ltd, Kappa Motors", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] == 1
    assert "Kappa Motors" in res["groups"][0]["company"]
    # Foobar is reported in unresolved / not_found
    missing = res["not_found"] + res["unresolved"]
    assert len(missing) >= 1
    assert any("foobar" in m.lower() for m in missing)
    md = format_markdown(res)
    assert 'no records found for "foobar"' in md.lower()


def test_company_typo_fuzzy_match(mock_db):
    """Typo in company name e.g. 'kapa motors' -> resolves to 'Kappa Motors'"""
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("kapa motors", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)
    assert res["companies_found"] >= 1
    assert any("Kappa" in g["company"] for g in res["groups"])


def test_privacy_mode_never_calls_llm_or_vector(mock_db, monkeypatch):
    """PRIVACY_MODE=true never calls llm.py or vector search (mock and assert)"""
    monkeypatch.setattr("app.routes.chat.get_database", lambda: mock_db)
    monkeypatch.setattr("app.routes.chat.get_configured_collection_names", lambda: ["metrology"])
    monkeypatch.setattr("app.routes.chat.PRIVACY_MODE", True)

    with patch("app.llm.call_llm") as mock_llm, \
         patch("app.services.vector_search.get_embedding") as mock_vec:

        client = TestClient(app)
        resp = client.post("/api/chat", json={"message": "Tata Motors"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["count"] >= 1

        mock_llm.assert_not_called()
        mock_vec.assert_not_called()

        client = TestClient(app)
        resp = client.post("/api/chat", json={"message": "Tata Motors"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["count"] >= 1

        mock_llm.assert_not_called()
        mock_vec.assert_not_called()


def test_no_query_text_in_logs(mock_db, monkeypatch, capsys):
    """Verify that no query text or cell values appear in printed logs"""
    secret_query = "Tata Motors special secret query 998877"
    monkeypatch.setattr("app.routes.chat.get_database", lambda: mock_db)
    monkeypatch.setattr("app.routes.chat.get_configured_collection_names", lambda: ["metrology"])
    monkeypatch.setattr("app.routes.chat.PRIVACY_MODE", True)

    client = TestClient(app)
    client.post("/api/chat", json={"message": secret_query})
    captured = capsys.readouterr()

    assert secret_query not in captured.out
    assert secret_query not in captured.err
    assert "998877" not in captured.out


def test_check_uncleaned_collections(mock_db):
    """Startup check warning on uncleaned collections"""
    # Insert an uncleaned collection without norm_company
    mock_db["uncleaned_col"].insert_one({"company": "Raw Co", "person": "John Doe"})
    uncleaned = check_uncleaned_collections(mock_db, ["metrology", "uncleaned_col"])
    assert "uncleaned_col" in uncleaned
    assert "metrology" not in uncleaned


def test_tvs_uncleaned_and_nested_schema(mock_db):
    """
    Validates that querying 'tvs' works properly when:
    1. The document is uncleaned with 'Company Name': 'TVS Motor Company' (no norm_company field).
    2. The document is in dataset_records with nested 'data.Company Name'.
    """
    invalidate_vocab()
    # Uncleaned collection with capitalised keys
    mock_db["tvs_col"].insert_one({
        "Company Name": "TVS Motor Company",
        "Person Name": "Shreethan Shetty",
        "Designation": "Quality Manager",
        "Phone Number": "+91 9876543299",
        "Email Address": "shetty@tvs.in",
        "Location": "Hosur"
    })
    # Dataset records with nested data
    mock_db["dataset_records"].insert_one({
        "dataset_id": "ds_test_1",
        "data": {
            "Company Name": "TVS Motor Company",
            "Person Name": "Anand R",
            "Designation": "Purchase Head",
            "Phone Number": "+91 9876543298",
            "Email Address": "anand@tvs.in",
            "Location": "Chennai"
        }
    })

    vocab = build_vocab(mock_db, ["metrology", "tvs_col", "dataset_records"])
    # 1. Query "tvs"
    parsed = parse_query("tvs", vocab)
    res = search(mock_db, ["metrology", "tvs_col", "dataset_records"], parsed, vocab)

    assert res["companies_found"] == 1
    assert any("TVS Motor Company" in g["company"] for g in res["groups"])
    assert res["total"] == 2
    md = format_markdown(res)
    assert "TVS Motor Company" in md
    assert "Shreethan Shetty" in md
    assert "Anand R" in md
    assert "+91 9876543299" in md
    assert "shetty@tvs.in" in md


def test_multiple_company_names_query(mock_db):
    """
    Validates querying multiple companies separated by commas, 'and', etc.:
    e.g. 'TVS, Tata Motors, JBM Group and ABC Engineering'
    """
    invalidate_vocab()
    mock_db["tvs_col"].insert_one({
        "Company Name": "TVS Motor Company",
        "Person Name": "Ravi K",
        "Designation": "Manager",
        "Phone Number": "+91 9876543200",
        "Location": "Hosur"
    })
    vocab = build_vocab(mock_db, ["metrology", "tvs_col"])

    parsed = parse_query("TVS, Tata Motors and JBM Group", vocab)
    assert len(parsed.companies) == 3

    res = search(mock_db, ["metrology", "tvs_col"], parsed, vocab)
    assert res["companies_found"] == 3
    found = {g["company"] for g in res["groups"]}
    assert any("TVS" in c for c in found)
    assert any("Tata Motors" in c for c in found)
    assert any("JBM" in c for c in found)

    md = format_markdown(res)
    assert "TVS Motor Company" in md
    assert "Tata Motors" in md
    assert "JBM Group" in md


def test_multiple_company_names_with_unknown(mock_db):
    """
    Querying multiple companies where one does not exist returns results for the existing
    ones and reports the missing one cleanly.
    """
    invalidate_vocab()
    vocab = build_vocab(mock_db, ["metrology"])
    parsed = parse_query("Tata Motors, NonExistentCorp, JBM Group", vocab)
    res = search(mock_db, ["metrology"], parsed, vocab)

    assert res["companies_found"] == 2
    found = {g["company"] for g in res["groups"]}
    assert any("Tata Motors" in c for c in found)
    assert any("JBM Group" in c for c in found)

    # Missing company reported
    missing = res["not_found"] + res["unresolved"]
    assert any("nonexistentcorp" in m.lower() for m in missing)
    md = format_markdown(res)
    assert 'no records found for "nonexistentcorp"' in md.lower()

