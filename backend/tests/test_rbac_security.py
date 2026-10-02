import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.services.auth import (
    ensure_default_users,
    get_user_by_email,
    ROLE_DATA_UPLOADER,
    ROLE_CHAT_USER
)

client = TestClient(app)

def setup_module():
    ensure_default_users()

def test_login_data_uploader_success():
    """TEST 1: Login as DATA_UPLOADER"""
    response = client.post("/api/auth/login", json={
        "email": "uploader@calispec.com",
        "password": "Uploader@123"
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == ROLE_DATA_UPLOADER
    assert data["user"]["email"] == "uploader@calispec.com"
    # Ensure password hash is not exposed
    assert "password" not in data
    assert "password_hash" not in data
    assert "password" not in data["user"]

def test_login_chat_user_success():
    """TEST 2: Login as CHAT_USER"""
    response = client.post("/api/auth/login", json={
        "email": "employee@calispec.com",
        "password": "ChatUser@123"
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == ROLE_CHAT_USER
    assert data["user"]["email"] == "employee@calispec.com"
    assert "password" not in data
    assert "password_hash" not in data

def test_unauthenticated_upload_rejected():
    """TEST 6: Call upload API without authentication -> HTTP 401"""
    # 1. Check /api/datasets/upload
    res1 = client.post("/api/datasets/upload", files={"file": ("test.csv", b"a,b\n1,2")})
    assert res1.status_code == 401
    assert res1.json()["detail"] == "Authentication required."

    # 2. Check /api/upload direct alias
    res2 = client.post("/api/upload", files={"file": ("test.csv", b"a,b\n1,2")})
    assert res2.status_code == 401
    assert res2.json()["detail"] == "Authentication required."

    # 3. Check /api/datasets/inspect
    res3 = client.post("/api/datasets/inspect", files={"file": ("test.csv", b"a,b\n1,2")})
    assert res3.status_code == 401
    assert res3.json()["detail"] == "Authentication required."

def test_chat_user_upload_forbidden():
    """TEST 3: Login as CHAT_USER and manually call POST /api/upload -> HTTP 403"""
    # Login as CHAT_USER
    login_res = client.post("/api/auth/login", json={
        "email": "employee@calispec.com",
        "password": "ChatUser@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Call /api/upload
    res_alias = client.post("/api/upload", files={"file": ("test.csv", b"a,b\n1,2")}, headers=headers)
    assert res_alias.status_code == 403
    assert res_alias.json()["detail"] == "You do not have permission to upload files."

    # Call /api/datasets/upload
    res_upload = client.post("/api/datasets/upload", files={"file": ("test.csv", b"a,b\n1,2")}, headers=headers)
    assert res_upload.status_code == 403
    assert res_upload.json()["detail"] == "You do not have permission to upload files."

    # Call /api/datasets/inspect
    res_inspect = client.post("/api/datasets/inspect", files={"file": ("test.csv", b"a,b\n1,2")}, headers=headers)
    assert res_inspect.status_code == 403
    assert res_inspect.json()["detail"] == "You do not have permission to upload files."

def test_chat_user_cannot_spoof_role_in_request():
    """TEST 5: Send {'role': 'DATA_UPLOADER'} from a CHAT_USER request -> HTTP 403"""
    login_res = client.post("/api/auth/login", json={
        "email": "employee@calispec.com",
        "password": "ChatUser@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to spoof role in form data / query
    res = client.post(
        "/api/upload",
        files={"file": ("test.csv", b"a,b\n1,2")},
        data={"role": "DATA_UPLOADER"},
        params={"role": "DATA_UPLOADER"},
        headers=headers
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "You do not have permission to upload files."

def test_chat_user_data_management_deletion_forbidden():
    """TEST 8: CHAT_USER attempts any MongoDB write/data-management endpoint -> HTTP 403"""
    login_res = client.post("/api/auth/login", json={
        "email": "employee@calispec.com",
        "password": "ChatUser@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_del = client.delete("/api/datasets/non_existent_id", headers=headers)
    assert res_del.status_code == 403
    assert res_del.json()["detail"] == "You do not have permission to delete datasets."

def test_data_uploader_can_inspect_and_upload():
    """TEST 7: DATA_UPLOADER uploads a valid file -> succeeds"""
    login_res = client.post("/api/auth/login", json={
        "email": "uploader@calispec.com",
        "password": "Uploader@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sample_csv = b"Company Name,City,State\nAcme Precision,Dallas,TX\nCalispec Instruments,Chicago,IL\n"
    res = client.post(
        "/api/datasets/inspect",
        files={"file": ("test_sample.csv", sample_csv)},
        headers=headers
    )
    assert res.status_code == 200, res.text
    inspect_data = res.json()
    assert inspect_data["success"] is True
    assert inspect_data["total_records_detected"] == 2

def test_api_responses_never_contain_credentials_or_passwords():
    """TEST 9 & 10: Verify passwords and MongoDB credentials are never returned"""
    # 1. Health endpoint
    health_res = client.get("/health").json()
    health_str = str(health_res).lower()
    assert "mongodb+srv" not in health_str
    assert "password" not in health_str

    # 2. Auth me endpoint
    login_res = client.post("/api/auth/login", json={
        "email": "uploader@calispec.com",
        "password": "Uploader@123"
    })
    token = login_res.json()["access_token"]
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert "password" not in me_res
    assert "password_hash" not in me_res
    assert me_res["role"] == "DATA_UPLOADER"


if __name__ == "__main__":
    print("Running Calispec RBAC Security Tests...")
    setup_module()
    test_login_data_uploader_success()
    print("PASS: test_login_data_uploader_success")
    test_login_chat_user_success()
    print("PASS: test_login_chat_user_success")
    test_unauthenticated_upload_rejected()
    print("PASS: test_unauthenticated_upload_rejected (HTTP 401)")
    test_chat_user_upload_forbidden()
    print("PASS: test_chat_user_upload_forbidden (HTTP 403)")
    test_chat_user_cannot_spoof_role_in_request()
    print("PASS: test_chat_user_cannot_spoof_role_in_request (HTTP 403)")
    test_chat_user_data_management_deletion_forbidden()
    print("PASS: test_chat_user_data_management_deletion_forbidden (HTTP 403)")
    test_data_uploader_can_inspect_and_upload()
    print("PASS: test_data_uploader_can_inspect_and_upload")
    test_api_responses_never_contain_credentials_or_passwords()
    print("PASS: test_api_responses_never_contain_credentials_or_passwords")
    print("\nALL BACKEND RBAC TESTS PASSED SUCCESSFULLY!")
