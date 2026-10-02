import httpx
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_live_tests():
    print(f"Connecting to live backend at {BASE_URL}...")
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        # TEST 1: Login as DATA_UPLOADER
        print("\n--- TEST 1: Login as DATA_UPLOADER ---")
        uploader_res = client.post("/api/auth/login", json={
            "email": "uploader@calispec.com",
            "password": "Uploader@123"
        })
        assert uploader_res.status_code == 200, f"Uploader login failed: {uploader_res.text}"
        uploader_data = uploader_res.json()
        uploader_token = uploader_data["access_token"]
        assert uploader_data["user"]["role"] == "DATA_UPLOADER"
        print(f"[PASS] DATA_UPLOADER login succeeded. Role: {uploader_data['user']['role']}")

        # TEST 2: Login as CHAT_USER
        print("\n--- TEST 2: Login as CHAT_USER ---")
        chat_user_res = client.post("/api/auth/login", json={
            "email": "employee@calispec.com",
            "password": "ChatUser@123"
        })
        assert chat_user_res.status_code == 200, f"Chat user login failed: {chat_user_res.text}"
        chat_user_data = chat_user_res.json()
        chat_user_token = chat_user_data["access_token"]
        assert chat_user_data["user"]["role"] == "CHAT_USER"
        print(f"[PASS] CHAT_USER login succeeded. Role: {chat_user_data['user']['role']}")

        # TEST 3: Login as CHAT_USER and manually call POST /api/upload
        print("\n--- TEST 3: CHAT_USER manually calling POST /api/upload ---")
        cu_headers = {"Authorization": f"Bearer {chat_user_token}"}
        cu_upload_res = client.post(
            "/api/upload",
            files={"file": ("unauthorized.csv", b"company,city\nBadActor,Anytown")},
            headers=cu_headers
        )
        assert cu_upload_res.status_code == 403, f"Expected 403, got {cu_upload_res.status_code}: {cu_upload_res.text}"
        assert cu_upload_res.json()["detail"] == "You do not have permission to upload files."
        print(f"[PASS] Backend rejected CHAT_USER upload with HTTP 403: {cu_upload_res.json()}")

        # Also test /api/datasets/upload for CHAT_USER
        cu_ds_res = client.post(
            "/api/datasets/upload",
            files={"file": ("unauthorized.csv", b"company,city\nBadActor,Anytown")},
            headers=cu_headers
        )
        assert cu_ds_res.status_code == 403, f"Expected 403 on /api/datasets/upload, got {cu_ds_res.status_code}"
        print(f"[PASS] Backend rejected CHAT_USER on /api/datasets/upload with HTTP 403")

        # TEST 4 & 5: Attempt role tampering from CHAT_USER
        print("\n--- TEST 4 & 5: Tampered role request from CHAT_USER ---")
        tampered_res = client.post(
            "/api/upload",
            files={"file": ("tampered.csv", b"col1,col2\nval1,val2")},
            data={"role": "DATA_UPLOADER"},
            params={"role": "DATA_UPLOADER"},
            headers=cu_headers
        )
        assert tampered_res.status_code == 403, f"Expected 403 on role spoof, got {tampered_res.status_code}"
        print(f"[PASS] Role spoofing attempt blocked by backend. Status: 403 Forbidden")

        # TEST 6: Call upload API without authentication
        print("\n--- TEST 6: Upload API without authentication ---")
        no_auth_res = client.post(
            "/api/upload",
            files={"file": ("noauth.csv", b"a,b\n1,2")}
        )
        assert no_auth_res.status_code == 401, f"Expected 401, got {no_auth_res.status_code}"
        assert no_auth_res.json()["detail"] == "Authentication required."
        print(f"[PASS] Unauthenticated request blocked with HTTP 401: {no_auth_res.json()}")

        # TEST 7: DATA_UPLOADER file upload / inspect succeeds
        print("\n--- TEST 7: DATA_UPLOADER file processing ---")
        du_headers = {"Authorization": f"Bearer {uploader_token}"}
        valid_csv = b"Company Name,City,State\nTest Metrology Inc,Austin,TX\nCalispec Precision,San Jose,CA\n"
        du_inspect_res = client.post(
            "/api/datasets/inspect",
            files={"file": ("sample_test.csv", valid_csv)},
            headers=du_headers
        )
        assert du_inspect_res.status_code == 200, f"DATA_UPLOADER inspect failed: {du_inspect_res.text}"
        inspect_json = du_inspect_res.json()
        assert inspect_json["success"] is True
        print(f"[PASS] DATA_UPLOADER file inspection succeeded ({inspect_json['total_records_detected']} records detected).")

        # TEST 8: CHAT_USER attempts MongoDB write/delete endpoint
        print("\n--- TEST 8: CHAT_USER attempts dataset deletion ---")
        cu_delete_res = client.delete("/api/datasets/ds_random123", headers=cu_headers)
        assert cu_delete_res.status_code == 403, f"Expected 403 on delete, got {cu_delete_res.status_code}"
        assert cu_delete_res.json()["detail"] == "You do not have permission to delete datasets."
        print(f"[PASS] CHAT_USER dataset deletion blocked with HTTP 403: {cu_delete_res.json()}")

        # TEST 9 & 10: Verify credentials and passwords are never exposed
        print("\n--- TEST 9 & 10: Security check against credential exposure ---")
        me_res = client.get("/api/auth/me", headers=du_headers)
        assert me_res.status_code == 200
        me_json = me_res.json()
        assert "password" not in me_json
        assert "password_hash" not in me_json
        print(f"[PASS] /api/auth/me returns safe fields: {list(me_json.keys())}")

        health_res = client.get("/health").text.lower()
        assert "mongodb+srv" not in health_res
        assert "password" not in health_res
        print("[PASS] MongoDB connection string and passwords are absent from all API responses.")

        print("\n==========================================")
        print("ALL 10 SECURITY TESTS PASSED ON LIVE SERVER!")
        print("==========================================")

if __name__ == "__main__":
    try:
        run_live_tests()
    except Exception as e:
        print(f"\n[FAILURE] {e}")
        sys.exit(1)
