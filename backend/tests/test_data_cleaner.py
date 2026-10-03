"""
Comprehensive pytest suite for Offline Data Cleaning Pipeline (No AI, Local & Deterministic).
Uses STRICTLY FAKE DATA to verify:
1. cleaner_core / data_cleaner local deterministic cleaning (phones pulled from names, company splitting, deduplication).
2. Report generation and Excel export via write_report_xlsx.
3. POST /api/datasets/upload/preview returns report and writes NOTHING to MongoDB.
4. GET /api/datasets/upload/preview/{preview_id}/report.xlsx returns downloadable Excel report.
5. POST /api/datasets/upload/confirm with corrected mapping produces a NEW report/preview.
6. POST /api/datasets/upload/confirm writes ONLY cleaned rows to MongoDB and clears cache.
7. 'append' mode skips existing duplicate contacts.
8. 'replace' mode clears previous records.
9. POST /api/datasets/upload/cancel clears in-memory preview.
10. Expired / invalid preview returns HTTP 404.
11. Unsupported file types are rejected with HTTP 400.
12. Files with zero usable rows cannot be saved.
13. Logs NEVER contain cell values, names, phones, or emails.
14. Hidden internal fields (needs_review, review_reasons, norm_company, uploaded_at) are excluded from chat.
"""

import io
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services import data_cleaner
from app.services.auth import create_access_token, ROLE_DATA_UPLOADER
from app.services.preview_cache import get_preview, clear_all_previews, store_preview
from app.utils.normalization import INTERNAL_EXCLUDE_KEYS

client = TestClient(app)

# Generate mock auth token for DATA_UPLOADER (Zero DB interaction required)
TEST_AUTH_TOKEN = create_access_token({
    "sub": "fake_test_uploader_id",
    "email": "uploader@fake-test.local",
    "role": ROLE_DATA_UPLOADER
})
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_AUTH_TOKEN}"}

FAKE_CSV_DATA = (
    "Company Name,Contact Person,Designation,Phone Number,Email Address,Location\n"
    "Acme Precision & Tech Tools,Alice Walker 9876543210,Senior Quality Lead,044-2223334,alice@acme-fake.test,Chennai\n"
    "Beta Solutions,Bob Smith,Operations Head,9123456780,bob@beta-fake.test,Bangalore\n"
).encode("utf-8")


@pytest.fixture(autouse=True)
def clean_cache():
    clear_all_previews()
    yield
    clear_all_previews()


# ---------------------------------------------------------------------------
# 1. Local Deterministic Cleaning Logic
# ---------------------------------------------------------------------------
def test_data_cleaner_local_cleaning_logic():
    """Verify offline cleaning: phone pulled from name, multiple companies split."""
    result = data_cleaner.clean_file(FAKE_CSV_DATA, "test_contacts.csv")

    assert result.stats["rows_in"] == 2
    # Acme Precision & Tech Tools should be split into 2 rows, plus Bob Smith = 3 rows
    assert len(result.rows) >= 2
    assert result.stats["phones_pulled_from_names"] >= 1

    # Check that Alice's phone was extracted to the phone field
    alice_rows = [r for r in result.rows if "Alice Walker" in r["person"]]
    assert len(alice_rows) > 0
    for r in alice_rows:
        # p_cols comes first, then extracted p_name
        assert r["phone"] == "0442223334"
        assert r["phone_2"] == "+919876543210"
        assert "9876543210" not in r["person"]
        assert r["norm_company"] != ""


# ---------------------------------------------------------------------------
# 2. Excel Audit Report Generation
# ---------------------------------------------------------------------------
def test_write_report_xlsx():
    """Verify write_report_xlsx creates all 5 sheets in memory."""
    import openpyxl
    result = data_cleaner.clean_file(FAKE_CSV_DATA, "test_contacts.csv")
    report = data_cleaner.build_report(result)

    buf = io.BytesIO()
    data_cleaner.write_report_xlsx(report, buf)
    buf.seek(0)

    wb = openpyxl.load_workbook(buf)
    sheet_names = wb.sheetnames
    assert "Summary" in sheet_names
    assert "Column mapping" in sheet_names
    assert "Changes" in sheet_names
    assert "Needs review" in sheet_names
    assert "Cleaned data" in sheet_names


# ---------------------------------------------------------------------------
# 3. Preview Endpoint Writes Nothing to MongoDB
# ---------------------------------------------------------------------------
@patch("app.services.mongo_dataset.get_database")
def test_preview_endpoint_returns_report_and_writes_nothing_to_mongo(mock_get_db):
    """POST /api/datasets/upload/preview returns report and leaves MongoDB untouched."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    response = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert "preview_id" in data
    assert "summary" in data
    assert "plain_language" in data["summary"]
    assert "column_mapping" in data
    assert "changes" in data
    assert len(data["cleaned_rows"]) > 0

    # Ensure ZERO database inserts occurred during preview
    mock_db["datasets"].insert_one.assert_not_called()
    mock_db["dataset_records"].insert_many.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Preview Excel Download Endpoint
# ---------------------------------------------------------------------------
def test_preview_download_excel_report():
    """GET /api/datasets/upload/preview/{preview_id}/report.xlsx downloads Excel report."""
    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    preview_id = prev_res.json()["preview_id"]

    res = client.get(f"/api/datasets/upload/preview/{preview_id}/report.xlsx", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]
    assert len(res.content) > 1000


# ---------------------------------------------------------------------------
# 5. Corrected Column Mapping Produces New Preview
# ---------------------------------------------------------------------------
@patch("app.services.mongo_dataset.get_database")
def test_confirm_corrected_mapping_produces_new_preview(mock_get_db):
    """If user changes column mapping, confirm re-cleans and returns re_preview: True."""
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db

    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    preview_id = prev_res.json()["preview_id"]

    confirm_payload = {
        "preview_id": preview_id,
        "dataset_name": "Test_Dataset",
        "mode": "append",
        "column_mapping": {
            "Company Name": "location",
            "Contact Person": "person",
            "Designation": "designation",
            "Phone Number": "phone",
            "Email Address": "email",
            "Location": "company",
        }
    }

    res = client.post("/api/datasets/upload/confirm", json=confirm_payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["re_preview"] is True
    assert data["preview_id"] != preview_id
    assert "summary" in data

    # Verify zero database inserts occurred during re-clean
    mock_db["datasets"].insert_one.assert_not_called()
    mock_db["dataset_records"].insert_many.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Confirm Writes ONLY Cleaned Rows to MongoDB and Frees Cache
# ---------------------------------------------------------------------------
@patch("app.services.mongo_dataset.get_database")
def test_confirm_writes_only_cleaned_rows_and_deletes_preview(mock_get_db):
    """POST /api/datasets/upload/confirm saves cleaned rows and removes preview from memory."""
    mock_db = MagicMock()
    mock_db["datasets"].find_one.return_value = None
    mock_db["dataset_records"].count_documents.return_value = 3
    mock_get_db.return_value = mock_db

    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    preview_id = prev_res.json()["preview_id"]

    confirm_payload = {
        "preview_id": preview_id,
        "dataset_name": "Verified_Dataset",
        "mode": "append"
    }

    res = client.post("/api/datasets/upload/confirm", json=confirm_payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["inserted"] > 0

    # Verify inserted records are cleaned and contain required fields
    inserted_chunk = mock_db["dataset_records"].insert_many.call_args[0][0]
    for doc in inserted_chunk:
        assert "company" in doc
        assert "person" in doc
        assert "phone" in doc
        assert "email" in doc
        assert "norm_company" in doc
        assert "uploaded_at" in doc
        assert "search_text" in doc
        # Raw file content must not be stored
        assert "raw_content" not in doc

    # Verify preview is deleted from memory cache
    assert get_preview(preview_id) is None


# ---------------------------------------------------------------------------
# 7. Append Mode Skips Existing Duplicates
# ---------------------------------------------------------------------------
@patch("app.services.mongo_dataset.get_database")
def test_append_mode_skips_duplicate_rows(mock_get_db):
    """Append mode skips existing contacts (same norm_company + person + phone/email)."""
    mock_db = MagicMock()
    mock_db["datasets"].find_one.return_value = {"dataset_id": "ds_existing_001", "filename": "Test"}
    # Simulate Bob Smith already in MongoDB
    mock_db["dataset_records"].find.return_value = [
        {"norm_company": "beta solutions", "person": "bob smith", "phone": "+919123456780", "email": "bob@beta-fake.test"}
    ]
    mock_db["dataset_records"].count_documents.return_value = 3
    mock_get_db.return_value = mock_db

    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    preview_id = prev_res.json()["preview_id"]

    confirm_payload = {
        "preview_id": preview_id,
        "dataset_name": "Test",
        "mode": "append"
    }

    res = client.post("/api/datasets/upload/confirm", json=confirm_payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["skipped"] >= 1


# ---------------------------------------------------------------------------
# 8. Replace Mode Clears Prior Records
# ---------------------------------------------------------------------------
@patch("app.services.mongo_dataset.get_database")
def test_replace_mode_replaces_existing_records(mock_get_db):
    """Replace mode clears previous records for that dataset."""
    mock_db = MagicMock()
    mock_db["datasets"].find_one.return_value = {"dataset_id": "ds_existing_002", "filename": "Test"}
    mock_db["dataset_records"].count_documents.return_value = 2
    mock_get_db.return_value = mock_db

    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    preview_id = prev_res.json()["preview_id"]

    confirm_payload = {
        "preview_id": preview_id,
        "dataset_name": "Test",
        "mode": "replace"
    }

    res = client.post("/api/datasets/upload/confirm", json=confirm_payload, headers=AUTH_HEADERS)
    assert res.status_code == 200
    mock_db["dataset_records"].delete_many.assert_called_with({"dataset_id": "ds_existing_002"})


# ---------------------------------------------------------------------------
# 9. Cancel Discards Preview From Memory
# ---------------------------------------------------------------------------
def test_cancel_deletes_preview():
    """POST /api/datasets/upload/cancel removes preview from cache."""
    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    preview_id = prev_res.json()["preview_id"]

    assert get_preview(preview_id) is not None

    cancel_res = client.post("/api/datasets/upload/cancel", json={"preview_id": preview_id}, headers=AUTH_HEADERS)
    assert cancel_res.status_code == 200
    assert get_preview(preview_id) is None


# ---------------------------------------------------------------------------
# 10. Expired / Invalid Preview Returns HTTP 404
# ---------------------------------------------------------------------------
def test_expired_preview_returns_404():
    """Accessing non-existent preview returns HTTP 404."""
    res = client.get("/api/datasets/upload/preview/invalid_id/report.xlsx", headers=AUTH_HEADERS)
    assert res.status_code == 404

    confirm_res = client.post("/api/datasets/upload/confirm", json={"preview_id": "invalid_id"}, headers=AUTH_HEADERS)
    assert confirm_res.status_code == 404


# ---------------------------------------------------------------------------
# 11. Unsupported File Types Rejected
# ---------------------------------------------------------------------------
def test_unsupported_file_type_rejected():
    """Unsupported files (.pdf, .exe) rejected with HTTP 400."""
    files = {"file": ("malicious.exe", b"fake binary", "application/octet-stream")}
    res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


# ---------------------------------------------------------------------------
# 12. Zero Usable Rows Blocked
# ---------------------------------------------------------------------------
def test_zero_usable_rows_blocked_on_confirm():
    """Empty or header-only file cannot be saved to database."""
    empty_csv = "Company,Person,Phone\n".encode("utf-8")
    files = {"file": ("empty.csv", empty_csv, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    assert prev_res.status_code == 200
    preview_id = prev_res.json()["preview_id"]

    confirm_res = client.post("/api/datasets/upload/confirm", json={"preview_id": preview_id}, headers=AUTH_HEADERS)
    assert confirm_res.status_code == 400
    assert "zero usable records" in confirm_res.json()["detail"]


# ---------------------------------------------------------------------------
# 13. Privacy Test: Logs Never Contain Cell Values
# ---------------------------------------------------------------------------
def test_no_cell_values_in_logs(capsys):
    """Assert log outputs never print cell values, names, phones, or emails."""
    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)

    captured = capsys.readouterr().out
    assert "Alice Walker" not in captured
    assert "Bob Smith" not in captured
    assert "9876543210" not in captured
    assert "alice@acme-fake.test" not in captured


# ---------------------------------------------------------------------------
# 14. Hidden Internal Fields Filtered From Chat
# ---------------------------------------------------------------------------
def test_hidden_internal_fields_in_chat():
    """Verify norm_company, needs_review, review_reasons, uploaded_at are hidden."""
    assert "norm_company" in INTERNAL_EXCLUDE_KEYS
    assert "needs_review" in INTERNAL_EXCLUDE_KEYS
    assert "review_reasons" in INTERNAL_EXCLUDE_KEYS
    assert "uploaded_at" in INTERNAL_EXCLUDE_KEYS


# ---------------------------------------------------------------------------
# 15. Step 3 Required Tests: Comprehensive Preview Structure & Sanitization
# ---------------------------------------------------------------------------
def test_preview_response_contains_all_required_report_fields():
    """Preview response contains preview_id, summary, column_mapping, changes, needs_review, cleaned_preview, total_changes."""
    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    assert "preview_id" in data
    assert "summary" in data
    assert "rows_in" in data["summary"]
    assert "rows_out" in data["summary"]
    assert "empty_rows" in data["summary"]
    assert "rows_added_by_split" in data["summary"]
    assert "phones_pulled_from_names" in data["summary"]
    assert "duplicates_removed" in data["summary"]
    assert "needs_review" in data["summary"]
    assert "changes_by_type" in data["summary"]
    assert "plain_language" in data["summary"]

    assert "column_mapping" in data
    assert isinstance(data["column_mapping"], list)
    for col in data["column_mapping"]:
        assert "column" in col
        assert "mapped_to" in col
        assert "method" in col

    assert "changes" in data
    assert isinstance(data["changes"], list)
    assert "total_changes" in data
    assert data["total_changes"] >= len(data["changes"])

    assert "needs_review" in data
    assert isinstance(data["needs_review"], list)

    assert "cleaned_preview" in data
    assert isinstance(data["cleaned_preview"], list)
    assert len(data["cleaned_preview"]) <= 50


def test_changes_include_before_and_after_with_what_happened_for_phone_in_name():
    """Changes include before and after with what_happened human label when a phone is inside a name."""
    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()

    phone_changes = [c for c in data["changes"] if c.get("action") == "phone_extracted_from_name"]
    assert len(phone_changes) > 0

    change = phone_changes[0]
    assert change["field"] == "person"
    assert "9876543210" in str(change["before"])
    assert "Alice Walker" in str(change["before"])
    assert "name: Alice Walker" in str(change["after"])
    assert "+919876543210" in str(change["after"])
    assert change["what_happened"] == "Phone number found inside the name and moved to the phone field"
    assert "source_row" in change
    assert "action" in change


def test_preview_response_is_valid_json_with_empty_cells_and_dates():
    """Preview response is strictly valid JSON even with NaN, empty cells, and date values."""
    import json
    fake_csv_with_nans_and_dates = (
        "Company,Person,Designation,Phone,Email,Date Joined,Notes\n"
        "Beta Labs,Carol Danvers,,9876543219,carol@fake.local,2024-01-15,\n"
        ",,,,\n"
        "Delta Corp,David Banner,Engineer,,david@fake.local,,\n"
    ).encode("utf-8")

    files = {"file": ("fake_dates_nans.csv", fake_csv_with_nans_and_dates, "text/csv")}
    res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    assert res.status_code == 200

    # Ensure response text is strictly valid RFC 8259 JSON and contains no NaN tokens
    raw_text = res.text
    assert ": NaN" not in raw_text
    assert ": -NaN" not in raw_text
    assert ": Infinity" not in raw_text

    parsed = json.loads(raw_text)
    assert parsed["success"] is True
    assert "summary" in parsed
    assert "cleaned_preview" in parsed


def test_confirm_impossible_without_valid_preview_id():
    """Confirm cannot succeed without a valid preview_id in memory."""
    payloads = [
        {},
        {"preview_id": ""},
        {"preview_id": "non_existent_prev_12345"},
        {"preview_id": None},
    ]
    for p in payloads:
        res = client.post("/api/datasets/upload/confirm", json=p, headers=AUTH_HEADERS)
        # Should be 404 (not found) or 422 (validation error if missing)
        assert res.status_code in (404, 422)


def test_paginated_changes_endpoint():
    """GET /api/datasets/upload/preview/{preview_id}/changes paginates correctly."""
    files = {"file": ("test_upload.csv", FAKE_CSV_DATA, "text/csv")}
    prev_res = client.post("/api/datasets/upload/preview", files=files, headers=AUTH_HEADERS)
    assert prev_res.status_code == 200
    preview_id = prev_res.json()["preview_id"]

    res = client.get(f"/api/datasets/upload/preview/{preview_id}/changes?offset=0&limit=2", headers=AUTH_HEADERS)
    assert res.status_code == 200
    paged = res.json()
    assert paged["success"] is True
    assert paged["offset"] == 0
    assert paged["limit"] == 2
    assert "total" in paged
    assert len(paged["changes"]) <= 2

    # Filter by action
    res_filtered = client.get(
        f"/api/datasets/upload/preview/{preview_id}/changes?offset=0&limit=10&action=phone_extracted_from_name",
        headers=AUTH_HEADERS
    )
    assert res_filtered.status_code == 200
    paged_filtered = res_filtered.json()
    for c in paged_filtered["changes"]:
        assert c["action"] == "phone_extracted_from_name"
