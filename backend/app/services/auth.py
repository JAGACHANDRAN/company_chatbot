import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Union, Dict, Any
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pymongo import ASCENDING
from ..database import get_database

# Authentication Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "calispec-secure-jwt-auth-key-2026-prod-secret-token")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days

# Unified MongoDB user collection for both uploaders and chat users
USER_COLLECTION = "user"
USERS_COLLECTION = "users"
UPLOADERS_COLLECTION = "uploaders"

# Valid Role Definitions
ROLE_DATA_UPLOADER = "DATA_UPLOADER"
ROLE_CHAT_USER = "CHAT_USER"
ALLOWED_ROLES = [ROLE_DATA_UPLOADER, ROLE_CHAT_USER]

oauth2_scheme = HTTPBearer(auto_error=False)


def get_user_collection():
    """Returns PyMongo collection reference for the 'user' collection."""
    db = get_database()
    return db[USER_COLLECTION]


def get_uploaders_collection():
    """Compatibility alias pointing to user collection."""
    return get_user_collection()


def get_users_collection():
    """Compatibility alias pointing to user collection."""
    return get_user_collection()


def ensure_user_indexes():
    """Ensures unique index on email for the 'user' collection in MongoDB."""
    try:
        db = get_database()
        user_col = db[USER_COLLECTION]
        user_col.create_index([("email", ASCENDING)], unique=True, background=True)

        # Also maintain index on 'users' collection
        usr_col = db[USERS_COLLECTION]
        usr_col.create_index([("email", ASCENDING)], unique=True, background=True)
    except Exception as e:
        print(f"[User Indexes Warning] {e}")


def ensure_default_users():
    """Ensures user indexes and default collections setup."""
    ensure_user_indexes()


def get_user_by_email(email: str) -> Optional[dict]:
    """Finds user by email in the user collection."""
    try:
        db = get_database()
        return db[USER_COLLECTION].find_one({"email": email.strip().lower()})
    except Exception:
        return None


def hash_password(plain_password: str) -> str:
    """Hashes a password securely using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encodes a signed JWT access token containing trusted user data."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow()
    })
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT token using server secret."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def authenticate_user(email: str, password: str) -> Optional[dict]:
    """
    Authenticates user credentials against the MongoDB 'user' collection.
    - Uploader user (configured via .env or role DATA_UPLOADER): stored in 'user' collection with role DATA_UPLOADER.
    - Normal chat user: stored in 'user' collection with role CHAT_USER.
    - Only if they log in, their details are stored/updated in the 'user' collection.
    """
    clean_email = email.strip().lower()
    clean_pwd = password.strip()
    now_iso = datetime.utcnow().isoformat() + "Z"

    db = get_database()
    user_col = db[USER_COLLECTION]
    usr_mirror_col = db[USERS_COLLECTION]

    # 1. Check configured specific uploader from .env (e.g. UPLOADER_EMAIL & UPLOADER_PASSWORD)
    uploader_env_email = os.getenv("UPLOADER_EMAIL", "").strip().lower()
    uploader_env_pwd = os.getenv("UPLOADER_PASSWORD", "").strip()

    if uploader_env_email and clean_email == uploader_env_email and clean_pwd == uploader_env_pwd:
        existing = user_col.find_one({"email": clean_email})
        user_id = existing.get("user_id") if existing else f"usr_{uuid.uuid4().hex[:10]}"

        # ONLY if they log in, store details in the 'user' collection
        user_data = {
            "email": clean_email,
            "role": ROLE_DATA_UPLOADER,
            "user_type": "uploader",
            "last_login": now_iso
        }
        user_col.update_one(
            {"email": clean_email},
            {
                "$set": user_data,
                "$setOnInsert": {
                    "user_id": user_id,
                    "created_at": now_iso
                }
            },
            upsert=True
        )
        # Mirror to 'users' collection for backward compatibility
        usr_mirror_col.update_one(
            {"email": clean_email},
            {
                "$set": user_data,
                "$setOnInsert": {
                    "user_id": user_id,
                    "created_at": now_iso
                }
            },
            upsert=True
        )

        return {
            "user_id": user_id,
            "email": clean_email,
            "role": ROLE_DATA_UPLOADER
        }

    # 2. Check existing user in MongoDB 'user' (or 'users') collection
    user_doc = user_col.find_one({"email": clean_email})
    if not user_doc or (not user_doc.get("password_hash") and not user_doc.get("password")):
        fallback_doc = usr_mirror_col.find_one({"email": clean_email})
        if fallback_doc and (fallback_doc.get("password_hash") or fallback_doc.get("password")):
            user_doc = fallback_doc
            # Sync back to user collection
            user_col.update_one(
                {"email": clean_email},
                {"$set": {k: v for k, v in fallback_doc.items() if k != "_id"}},
                upsert=True
            )

    if user_doc:
        pwd_match = False
        if user_doc.get("password_hash") and verify_password(clean_pwd, user_doc["password_hash"]):
            pwd_match = True
        elif user_doc.get("password") and user_doc["password"] == clean_pwd:
            pwd_match = True

        if pwd_match:
            user_role = user_doc.get("role", ROLE_CHAT_USER)
            user_id = user_doc.get("user_id", f"usr_{uuid.uuid4().hex[:10]}")
            user_col.update_one(
                {"email": clean_email},
                {"$set": {"last_login": now_iso}},
                upsert=True
            )
            usr_mirror_col.update_one(
                {"email": clean_email},
                {"$set": {"last_login": now_iso}},
                upsert=True
            )
            return {
                "user_id": user_id,
                "email": clean_email,
                "role": user_role
            }
        else:
            # Existing user password mismatch
            return None

    # 3. New normal chat user login/registration: store in 'user' collection as CHAT_USER
    new_user_id = f"usr_{uuid.uuid4().hex[:10]}"
    hashed_pwd = hash_password(clean_pwd)
    new_user_doc = {
        "user_id": new_user_id,
        "email": clean_email,
        "password_hash": hashed_pwd,
        "role": ROLE_CHAT_USER,
        "user_type": "chat_user",
        "created_at": now_iso,
        "last_login": now_iso
    }
    user_col.insert_one(new_user_doc.copy())
    usr_mirror_col.insert_one(new_user_doc.copy())

    return {
        "user_id": new_user_id,
        "email": clean_email,
        "role": ROLE_CHAT_USER
    }


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme)
) -> dict:
    """
    FastAPI dependency to extract and authenticate the JWT Bearer token.
    Raises HTTP 401 with {"detail": "Authentication required."} if missing or invalid.
    Returns safe user dict: {"user_id": ..., "email": ..., "role": ...}.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required."
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        email: Optional[str] = payload.get("email")
        role: Optional[str] = payload.get("role")

        if not user_id or not role or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required."
            )

        return {
            "user_id": user_id,
            "email": email,
            "role": role
        }
    except (jwt.PyJWTError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required."
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(oauth2_scheme)
) -> Optional[dict]:
    """
    FastAPI dependency that extracts authenticated user if token is present,
    or returns None without raising 401.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_current_user(credentials)
    except Exception:
        return None


def require_role(
    allowed_role: Union[str, List[str]],
    forbidden_detail: str = "You do not have permission to upload files."
):
    """
    Factory dependency for Role-Based Access Control (RBAC).
    Checks that the authenticated user has the required role.
    If not, immediately returns HTTP 403 Forbidden with exact detail message.
    """
    allowed = [allowed_role] if isinstance(allowed_role, str) else allowed_role

    async def role_checker(
        current_user: dict = Depends(get_current_user)
    ) -> dict:
        user_role = current_user.get("role")
        if user_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=forbidden_detail
            )
        return current_user

    return role_checker
