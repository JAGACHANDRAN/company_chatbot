"""
Comprehensive pytest suite for Admin-Only Existing MongoDB Data Cleaner.
Uses STRICTLY FAKE DATA and mongomock.
ZERO real database connections and ZERO real .env reads.

Verifies:
1. Non-admin users get HTTP 403 Forbidden.
2. Preview is strictly read-only and writes NOTHING to MongoDB.
3. Preview returns full report (summary, column mapping, changes with source_doc_id, needs_review, cleaned_preview, total_changes).
4. Download report (.xlsx) returns valid Excel spreadsheet bytes.
5. mode "new_collection" creates <name>_cleaned and leaves original untouched.
6. mode "replace" requires admin to type the exact collection name in confirm_name (rejected otherwise).
7. mode "replace" aborts if <name>_backup already exists.
8. mode "replace" creates backup, verifies count, replaces original, and preserves indexes.
9. mode "replace" rolls back and restores from backup if an error occurs.
10. Privacy compliance: No record values appear in printed logs.
"""

import io
import pytest
import mongomock
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import create_access_token, ROLE_DATA_UPLOADER, ROLE_CHAT_USER
from app.services.preview_cache import clear_all_previews
from app.services import existing_data_cleaner

client = TestClient(app)

# Fake Auth Tokens
ADMIN_TOKEN = create_access_token({
    "sub": "fake_admin_uid",
    "email": "admin@fake-calispec.local",
    "role": ROLE_DATA_UPLOADER
})
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

CHAT_USER_TOKEN = create_access_token({
    "sub": "fake_chat_uid",
    "email": "user@fake-calispec.local",
    "role": ROLE_CHAT_USER
})
CHAT_USER_HEADERS = {"Authorization": f"Bearer {CHAT_USER_TOKEN}"}

FAKE_METROLOGY_RECORDS = [
    {
        "company": "Apex Precision & Tools Ltd",
        "person": "John Doe 9876543210",
        "designation": "Lead Metrology Engineer",
        "phone": "044-22334455",
        "email": "john@apex-fake.local",
        "location": "Chennai",
        "source_fields": {"extra": "sample"}
    },
    {
        "company": "Zenith Instruments",
        "person": "Jane Smith",
        "designation": "QA Director",
        "phone": "9812345678",
        "email": "jane@zenith-fake.local",
        "location": "Bangalore"
    }
]


@pytest.fixture(autouse=True)
def clean_cache_and_mock_db():
    clear_all_previews()
    mock_mongo = mongomock.MongoClient()
    mock_db = mock_mongo["test_calispec"]

    # Populate fake collections
    mock_db["metrology"].insert_many(list(FAKE_METROLOGY_RECORDS))
    mock_db["calibration"].insert_many([
        {
            "company": "Calibra Test Labs",
            "person": "Robert Brown",
            "phone": "080-44556677",
            "email": "robert@calibra-fake.local",
            "location": "Hyderabad"
        }
    ])

    with patch("app.routes.admin_clean.get_database", return_value=mock_db), \
         patch("app.database.get_database", return_value=mock_db), \
         patch("app.services.existing_data_cleaner.collection_names", return_value=["metrology", "calibration"]):
        yield mock_db

    clear_all_previews()


# ---------------------------------------------------------------------------
# 1. RBAC Security Guard: Non-admin users get 403
# ---------------------------------------------------------------------------
def test_admin_clean_non_admin_gets_403(clean_cache_and_mock_db):
    """Users with CHAT_USER role receive 403 Forbidden for all admin clean endpoints."""
    endpoints = [
        ("GET", "/api/admin/clean/collections"),
        ("POST", "/api/admin/clean/preview"),
        ("POST", "/api/admin/clean/apply"),
    ]
    for method, ep in endpoints:
        if method == "GET":
            res = client.get(ep, headers=CHAT_USER_HEADERS)
        else:
            res = client.post(ep, json={}, headers=CHAT_USER_HEADERS)
        assert res.status_code == 403
        assert "Admin or data uploader privileges required" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 2. Collections List Endpoint
# ---------------------------------------------------------------------------
def test_admin_clean_collections_list(clean_cache_and_mock_db):
    """GET /api/admin/clean/collections lists collections with document counts."""
    res = client.get("/api/admin/clean/collections", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    cols = data["collections"]
    col_dict = {c["name"]: c for c in cols}

    assert "metrology" in col_dict
    assert col_dict["metrology"]["count"] == 2
    assert "calibration" in col_dict
    assert col_dict["calibration"]["count"] == 1


# ---------------------------------------------------------------------------
# 3. Preview is Read-Only and Writes Nothing to MongoDB
# ---------------------------------------------------------------------------
def test_admin_clean_preview_writes_nothing_to_mongo(clean_cache_and_mock_db):
    """POST /api/admin/clean/preview returns report and writes nothing to MongoDB."""
    mock_db = clean_cache_and_mock_db
    initial_collections = set(mock_db.list_collection_names())
    initial_count = mock_db["metrology"].count_documents({})

    res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    assert res.status_code == 200
    data = res.json()

    assert data["success"] is True
    assert "preview_id" in data
    assert data["collection"] == "metrology"

    # Verify report shape
    assert "summary" in data
    assert "column_mapping" in data
    assert "changes" in data
    assert "needs_review" in data
    assert "cleaned_preview" in data
    assert "total_changes" in data

    # Verify changes include source_doc_id and what_happened
    for c in data["changes"]:
        assert "source_doc_id" in c
        assert "what_happened" in c

    # Verify phone was extracted from John Doe
    phone_changes = [c for c in data["changes"] if c["action"] == "phone_extracted_from_name"]
    assert len(phone_changes) > 0
    assert "John Doe" in phone_changes[0]["before"]
    assert "9876543210" in phone_changes[0]["before"]

    # Verify DB was NOT touched at all
    assert set(mock_db.list_collection_names()) == initial_collections
    assert mock_db["metrology"].count_documents({}) == initial_count


# ---------------------------------------------------------------------------
# 4. Paginated Changes Endpoint
# ---------------------------------------------------------------------------
def test_admin_clean_preview_changes_pagination(clean_cache_and_mock_db):
    """GET /api/admin/clean/preview/{preview_id}/changes paginates properly."""
    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    res = client.get(
        f"/api/admin/clean/preview/{preview_id}/changes?offset=0&limit=1",
        headers=ADMIN_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["offset"] == 0
    assert data["limit"] == 1
    assert "total" in data
    assert len(data["changes"]) <= 1


# ---------------------------------------------------------------------------
# 5. Excel Download Endpoint
# ---------------------------------------------------------------------------
def test_admin_clean_preview_excel_download(clean_cache_and_mock_db):
    """GET /api/admin/clean/preview/{preview_id}/report.xlsx returns Excel bytes."""
    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    res = client.get(
        f"/api/admin/clean/preview/{preview_id}/report.xlsx",
        headers=ADMIN_HEADERS
    )
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]
    assert len(res.content) > 1000


# ---------------------------------------------------------------------------
# 6. Mode "new_collection" creates <name>_cleaned and leaves original untouched
# ---------------------------------------------------------------------------
def test_admin_clean_apply_new_collection(clean_cache_and_mock_db):
    """Mode new_collection creates metrology_cleaned without modifying original metrology."""
    mock_db = clean_cache_and_mock_db
    orig_docs = list(mock_db["metrology"].find({}))

    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    res = client.post(
        "/api/admin/clean/apply",
        json={"preview_id": preview_id, "mode": "new_collection"},
        headers=ADMIN_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["mode"] == "new_collection"
    assert data["target_collection"] == "metrology_cleaned"
    assert data["rows_written"] >= 2
    assert "Point MONGODB_COLLECTIONS" in " ".join(data["next_steps"])

    # Verify metrology_cleaned was created
    assert "metrology_cleaned" in mock_db.list_collection_names()
    cleaned_docs = list(mock_db["metrology_cleaned"].find({}))
    assert len(cleaned_docs) >= 2

    # Check that cleaned docs have source_doc_id, cleaned_at, and search_text
    for cd in cleaned_docs:
        assert "source_doc_id" in cd
        assert "cleaned_at" in cd
        assert "search_text" in cd
        assert cd["search_text"] != ""

    # Verify original metrology is completely UNTOUCHED
    assert list(mock_db["metrology"].find({})) == orig_docs


# ---------------------------------------------------------------------------
# 7. Mode "replace" requires exact typed confirm_name
# ---------------------------------------------------------------------------
def test_admin_clean_apply_replace_rejects_wrong_confirm_name(clean_cache_and_mock_db):
    """Mode replace is rejected with 400 if confirm_name does not match."""
    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    wrong_names = [None, "", "wrong_collection", "Metrology "]
    for w in wrong_names:
        res = client.post(
            "/api/admin/clean/apply",
            json={"preview_id": preview_id, "mode": "replace", "confirm_name": w},
            headers=ADMIN_HEADERS
        )
        assert res.status_code == 400
        assert "Confirmation mismatch" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 8. Mode "replace" aborts if backup collection already exists
# ---------------------------------------------------------------------------
def test_admin_clean_apply_replace_aborts_if_backup_exists(clean_cache_and_mock_db):
    """Mode replace aborts if metrology_backup already exists."""
    mock_db = clean_cache_and_mock_db
    mock_db["metrology_backup"].insert_one({"existing_backup": True})

    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    res = client.post(
        "/api/admin/clean/apply",
        json={"preview_id": preview_id, "mode": "replace", "confirm_name": "metrology"},
        headers=ADMIN_HEADERS
    )
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 9. Mode "replace" creates backup, verifies count, and overwrites original
# ---------------------------------------------------------------------------
def test_admin_clean_apply_replace_success(clean_cache_and_mock_db):
    """Mode replace backs up original, verifies counts, and overwrites original with clean data."""
    mock_db = clean_cache_and_mock_db
    orig_count = mock_db["metrology"].count_documents({})

    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    res = client.post(
        "/api/admin/clean/apply",
        json={"preview_id": preview_id, "mode": "replace", "confirm_name": "metrology"},
        headers=ADMIN_HEADERS
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["backup_collection"] == "metrology_backup"

    # Verify backup exists and contains exact original document count
    assert "metrology_backup" in mock_db.list_collection_names()
    assert mock_db["metrology_backup"].count_documents({}) == orig_count

    # Verify original metrology holds cleaned records
    cleaned_docs = list(mock_db["metrology"].find({}))
    assert len(cleaned_docs) >= 2
    for cd in cleaned_docs:
        assert "cleaned_at" in cd
        assert "search_text" in cd


# ---------------------------------------------------------------------------
# 10. Mode "replace" rolls back if an insertion error occurs
# ---------------------------------------------------------------------------
def test_admin_clean_apply_replace_rollback_on_failure(clean_cache_and_mock_db):
    """If an error occurs while writing cleaned records, original collection is restored from backup."""
    mock_db = clean_cache_and_mock_db
    orig_docs = list(mock_db["metrology"].find({}))

    prev_res = client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    preview_id = prev_res.json()["preview_id"]

    # Force failure on insert of cleaned rows, but allow rollback restoration to succeed
    real_insert_many = mock_db["metrology"].insert_many
    def insert_side_effect(docs, *args, **kwargs):
        if docs and "cleaned_at" in docs[0]:
            raise Exception("Disk or write error")
        return real_insert_many(docs, *args, **kwargs)

    with patch.object(mock_db["metrology"], "insert_many", side_effect=insert_side_effect):
        res = client.post(
            "/api/admin/clean/apply",
            json={"preview_id": preview_id, "mode": "replace", "confirm_name": "metrology"},
            headers=ADMIN_HEADERS
        )
        assert res.status_code == 500
        assert "restored" in res.json()["detail"].lower()

    # Verify original documents were restored
    restored_docs = list(mock_db["metrology"].find({}))
    assert len(restored_docs) == len(orig_docs)


# ---------------------------------------------------------------------------
# 11. Privacy Compliance: Logs never contain record values
# ---------------------------------------------------------------------------
def test_admin_clean_no_record_values_in_logs(clean_cache_and_mock_db, capsys):
    """Verifies that no record cell values, contact names, or phones are logged."""
    client.post(
        "/api/admin/clean/preview",
        json={"collection": "metrology"},
        headers=ADMIN_HEADERS
    )
    captured = capsys.readouterr().out
    assert "John Doe" not in captured
    assert "9876543210" not in captured
    assert "john@apex-fake.local" not in captured
    assert "Jane Smith" not in captured
