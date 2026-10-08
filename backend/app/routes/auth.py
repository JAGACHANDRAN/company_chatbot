import os
import secrets
import urllib.parse
import httpx
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import RedirectResponse
from ..schemas import LoginRequest, LoginResponse, UserResponse
from ..services.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_or_create_google_user
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Access Control"])
google_router = APIRouter(prefix="/auth", tags=["Google OAuth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def get_oauth_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/auth/google/callback").strip()
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return client_id, client_secret, redirect_uri, frontend_url


async def handle_google_login(state: str = None):
    client_id, _, redirect_uri, frontend_url = get_oauth_config()
    if not client_id:
        # If Google OAuth is not configured, redirect back with descriptive error
        return RedirectResponse(
            url=f"{frontend_url}/?auth_error=google_oauth_not_configured",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    oauth_state = state or secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": oauth_state,
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


async def handle_google_callback(
    code: str = None,
    error: str = None,
    state: str = None
):
    client_id, client_secret, redirect_uri, frontend_url = get_oauth_config()

    if error or not code:
        err_code = error or "cancelled"
        return RedirectResponse(
            url=f"{frontend_url}/?auth_error={urllib.parse.quote(err_code)}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    if not client_id or not client_secret:
        return RedirectResponse(
            url=f"{frontend_url}/?auth_error=missing_server_oauth_credentials",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    try:
        # 1. Exchange authorization code with Google for tokens
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"}
            )

            if token_response.status_code != 200:
                print(f"[Google OAuth Token Error] {token_response.status_code}: {token_response.text}")
                return RedirectResponse(
                    url=f"{frontend_url}/?auth_error=token_exchange_failed",
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT
                )

            token_data = token_response.json()
            google_access_token = token_data.get("access_token")

            if not google_access_token:
                return RedirectResponse(
                    url=f"{frontend_url}/?auth_error=invalid_token_payload",
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT
                )

            # 2. Retrieve verified user profile from Google UserInfo endpoint
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {google_access_token}"}
            )

            if userinfo_response.status_code != 200:
                print(f"[Google OAuth UserInfo Error] {userinfo_response.status_code}: {userinfo_response.text}")
                return RedirectResponse(
                    url=f"{frontend_url}/?auth_error=userinfo_fetch_failed",
                    status_code=status.HTTP_307_TEMPORARY_REDIRECT
                )

            google_user_info = userinfo_response.json()

        # 3. Lookup existing user or create a new user in MongoDB users collection
        user_info = get_or_create_google_user(google_user_info)
        user_id = user_info.get("user_id", "")
        email = user_info.get("email", "")
        role = user_info.get("role", "CHAT_USER")

        # 4. Mint application's native JWT containing sub, email, and role
        access_token = create_access_token({
            "sub": user_id,
            "email": email,
            "role": role
        })

        # 5. Redirect back to React frontend with authentication details
        redirect_params = urllib.parse.urlencode({
            "token": access_token,
            "user_id": user_id,
            "email": email,
            "role": role
        })
        return RedirectResponse(
            url=f"{frontend_url}/?{redirect_params}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    except Exception as e:
        print(f"[Google OAuth Exception] {e}")
        return RedirectResponse(
            url=f"{frontend_url}/?auth_error=oauth_processing_error",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )


# Direct /auth/google endpoints matching Google Cloud Authorized Redirect URI
@google_router.get("/google/login")
async def google_login_direct(state: str = Query(None)):
    """Initiates Google OAuth 2.0 authentication flow."""
    return await handle_google_login(state)


@google_router.get("/google/callback")
async def google_callback_direct(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None)
):
    """Google OAuth 2.0 authorized callback handler."""
    return await handle_google_callback(code, error, state)


# API prefixed /api/auth/google endpoints for consistency
@router.get("/google/login")
async def google_login_api(state: str = Query(None)):
    """Initiates Google OAuth 2.0 authentication flow (/api/auth/google/login)."""
    return await handle_google_login(state)


@router.get("/google/callback")
async def google_callback_api(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None)
):
    """Google OAuth 2.0 authorized callback handler (/api/auth/google/callback)."""
    return await handle_google_callback(code, error, state)


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """
    Authenticates an authorized user and issues a signed JWT access token.
    Only authorized uploaders configured in .env or the database can sign in.
    Details are stored in MongoDB (uploaders or users collection) upon successful login.
    """
    user_info = authenticate_user(credentials.email, credentials.password)

    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Only authorized uploaders can sign in."
        )

    user_id = user_info.get("user_id", "")
    email = user_info.get("email", "")
    role = user_info.get("role", "CHAT_USER")

    # Mint JWT containing trusted role claim
    access_token = create_access_token({
        "sub": user_id,
        "email": email,
        "role": role
    })

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            user_id=user_id,
            email=email,
            role=role
        )
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user)
):
    """
    Returns the authenticated user profile and trusted role from the backend.
    """
    return UserResponse(
        user_id=current_user["user_id"],
        email=current_user["email"],
        role=current_user["role"]
    )


@router.post("/logout")
async def logout():
    """Client-side token invalidation acknowledgment."""
    return {"success": True, "message": "Logged out successfully."}

