import os
import sys
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.services.auth import (
    ensure_default_users,
    get_or_create_google_user,
    get_user_by_email,
    decode_access_token,
    ROLE_DATA_UPLOADER,
    ROLE_CHAT_USER
)

client = TestClient(app)


def setup_module():
    ensure_default_users()


def test_google_login_redirect():
    """Verify that /auth/google/login redirects to Google OAuth endpoint."""
    with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client-id-123.apps.googleusercontent.com"}):
        response = client.get("/auth/google/login", follow_redirects=False)
        assert response.status_code == 307
        location = response.headers.get("location", "")
        assert "accounts.google.com/o/oauth2/v2/auth" in location
        assert "client_id=test-client-id-123.apps.googleusercontent.com" in location
        assert "response_type=code" in location
        assert "scope=openid+email+profile" in location or "scope=openid%20email%20profile" in location


def test_google_login_redirect_api_alias():
    """Verify that /api/auth/google/login works identically."""
    with patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "test-client-id-123.apps.googleusercontent.com"}):
        response = client.get("/api/auth/google/login", follow_redirects=False)
        assert response.status_code == 307
        assert "accounts.google.com/o/oauth2/v2/auth" in response.headers.get("location", "")


def test_get_or_create_google_user_new_and_existing():
    """Verify creation and subsequent login of a Google user without duplication."""
    test_google_data = {
        "sub": "google-sub-998877",
        "email": "newgoogleuser@example.com",
        "name": "Google Test User",
        "picture": "https://lh3.googleusercontent.com/a/test-avatar"
    }

    # 1. First login -> Creates user
    user1 = get_or_create_google_user(test_google_data)
    assert user1["email"] == "newgoogleuser@example.com"
    assert user1["role"] == ROLE_CHAT_USER
    assert user1["name"] == "Google Test User"
    assert user1["user_id"].startswith("usr_")

    # 2. Second login with same email -> Returns same user_id, no duplicate
    user2 = get_or_create_google_user(test_google_data)
    assert user2["user_id"] == user1["user_id"]
    assert user2["email"] == "newgoogleuser@example.com"
    assert user2["role"] == ROLE_CHAT_USER


def test_get_or_create_google_user_preserves_uploader_role():
    """Verify that if an existing uploader logs in via Google, role is maintained."""
    uploader_google_data = {
        "sub": "google-uploader-112233",
        "email": "jagachandrans@gmail.com",
        "name": "Admin Uploader",
        "picture": "https://lh3.googleusercontent.com/a/admin-avatar"
    }

    with patch.dict(os.environ, {"UPLOADER_EMAIL": "jagachandrans@gmail.com"}):
        user = get_or_create_google_user(uploader_google_data)
        assert user["role"] == ROLE_DATA_UPLOADER
        assert user["email"] == "jagachandrans@gmail.com"


def test_google_callback_error_handling():
    """Verify callback handles Google error parameters gracefully."""
    response = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert "auth_error=access_denied" in location


def test_google_callback_success_flow():
    """Verify end-to-end token exchange and JWT minting in Google OAuth callback."""
    from unittest.mock import MagicMock

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "mock-google-access-token-xyz",
        "expires_in": 3599,
        "token_type": "Bearer"
    }

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "sub": "google-sub-445566",
        "email": "verifiedgoogle@company.com",
        "name": "Verified Employee",
        "picture": "https://lh3.googleusercontent.com/a/photo.jpg"
    }


    async def mock_post(*args, **kwargs):
        return mock_token_resp

    async def mock_get(*args, **kwargs):
        return mock_userinfo_resp

    with patch.dict(os.environ, {
        "GOOGLE_CLIENT_ID": "mock-client-id",
        "GOOGLE_CLIENT_SECRET": "mock-client-secret",
        "GOOGLE_REDIRECT_URI": "http://127.0.0.1:8000/auth/google/callback",
        "FRONTEND_URL": "http://localhost:5173"
    }):
        with patch("httpx.AsyncClient.post", side_effect=mock_post), \
             patch("httpx.AsyncClient.get", side_effect=mock_get):
            
            response = client.get("/auth/google/callback?code=mock-auth-code-123", follow_redirects=False)
            assert response.status_code == 307
            location = response.headers.get("location", "")
            assert "http://localhost:5173/?" in location
            assert "token=" in location
            assert "email=verifiedgoogle%40company.com" in location or "email=verifiedgoogle@company.com" in location
            assert "role=CHAT_USER" in location

            # Extract minted JWT token from redirect location
            import urllib.parse
            parsed_query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
            jwt_token = parsed_query["token"][0]

            # Verify token works on protected /api/auth/me
            me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
            assert me_resp.status_code == 200
            me_data = me_resp.json()
            assert me_data["email"] == "verifiedgoogle@company.com"
            assert me_data["role"] == ROLE_CHAT_USER
