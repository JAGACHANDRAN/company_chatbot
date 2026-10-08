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

# Single MongoDB user collection for both uploaders and chat users
USERS_COLLECTION = "users"
USER_COLLECTION = USERS_COLLECTION
UPLOADERS_COLLECTION = USERS_COLLECTION

# Valid Role Definitions
ROLE_DATA_UPLOADER = "DATA_UPLOADER"
ROLE_CHAT_USER = "CHAT_USER"
ALLOWED_ROLES = [ROLE_DATA_UPLOADER, ROLE_CHAT_USER]

oauth2_scheme = HTTPBearer(auto_error=False)


def get_user_collection():
    """Returns PyMongo collection reference for the single 'users' collection."""
    db = get_database()
    return db[USERS_COLLECTION]


def get_uploaders_collection():
    """Compatibility alias pointing to users collection."""
    return get_user_collection()


def get_users_collection():
    """Returns PyMongo collection reference for the single 'users' collection."""
    return get_user_collection()


def ensure_user_indexes():
    """Ensures unique index on email for the 'users' collection in MongoDB."""
    try:
        db = get_database()
        user_col = db[USERS_COLLECTION]
        user_col.create_index([("email", ASCENDING)], unique=True, background=True)

        # If a legacy separate 'user' collection exists, migrate records and drop it
        if "user" in db.list_collection_names() and USERS_COLLECTION != "user":
            legacy_col = db["user"]
            for doc in legacy_col.find():
                email = doc.get("email")
                if email and not user_col.find_one({"email": email}):
                    doc_copy = dict(doc)
                    doc_copy.pop("_id", None)
                    user_col.insert_one(doc_copy)
            legacy_col.drop()
    except Exception as e:
        print(f"[User Indexes Warning] {e}")


def ensure_default_users():
    """Ensures user indexes and default collections setup."""
    ensure_user_indexes()


def get_user_by_email(email: str) -> Optional[dict]:
    """Finds user by email in the users collection."""
    try:
        db = get_database()
        return db[USERS_COLLECTION].find_one({"email": email.strip().lower()})
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
    Authenticates user credentials against the single MongoDB 'users' collection.
    - Uploader user (configured via .env or role DATA_UPLOADER): stored in 'users' collection with role DATA_UPLOADER.
    - Normal chat user: stored in 'users' collection with role CHAT_USER.
    """
    clean_email = email.strip().lower()
    clean_pwd = password.strip()
    now_iso = datetime.utcnow().isoformat() + "Z"

    db = get_database()
    user_col = db[USERS_COLLECTION]

    # 1. Check configured specific uploader from .env (e.g. UPLOADER_EMAIL & UPLOADER_PASSWORD)
    uploader_env_email = os.getenv("UPLOADER_EMAIL", "").strip().lower()
    uploader_env_pwd = os.getenv("UPLOADER_PASSWORD", "").strip()

    if uploader_env_email and clean_email == uploader_env_email and clean_pwd == uploader_env_pwd:
        existing = user_col.find_one({"email": clean_email})
        user_id = existing.get("user_id") if existing else f"usr_{uuid.uuid4().hex[:10]}"

        # Store or update details in the single 'users' collection
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

        return {
            "user_id": user_id,
            "email": clean_email,
            "role": ROLE_DATA_UPLOADER
        }

    # 2. Check existing user in MongoDB 'users' collection
    user_doc = user_col.find_one({"email": clean_email})

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
            return {
                "user_id": user_id,
                "email": clean_email,
                "role": user_role
            }
        else:
            # Existing user password mismatch
            return None

    # 3. New normal chat user login/registration: store in single 'users' collection as CHAT_USER
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
    user_col.insert_one(new_user_doc)

    return {
        "user_id": new_user_id,
        "email": clean_email,
        "role": ROLE_CHAT_USER
    }


def create_user(email: str, password: str, role: str = ROLE_CHAT_USER) -> dict:
    """Creates or updates a user in the 'users' collection with hashed password."""
    clean_email = email.strip().lower()
    clean_pwd = password.strip()
    role_clean = role.strip().upper()
    if role_clean not in ALLOWED_ROLES:
        role_clean = ROLE_CHAT_USER
    
    db = get_database()
    user_col = db[USERS_COLLECTION]
    now_iso = datetime.utcnow().isoformat() + "Z"
    
    existing = user_col.find_one({"email": clean_email})
    user_id = existing.get("user_id") if existing else f"usr_{uuid.uuid4().hex[:10]}"
    hashed_pwd = hash_password(clean_pwd)
    
    user_doc = {
        "user_id": user_id,
        "email": clean_email,
        "password_hash": hashed_pwd,
        "role": role_clean,
        "user_type": "uploader" if role_clean == ROLE_DATA_UPLOADER else "chat_user",
        "last_login": now_iso
    }
    user_col.update_one(
        {"email": clean_email},
        {
            "$set": user_doc,
            "$setOnInsert": {"created_at": now_iso}
        },
        upsert=True
    )
    return {
        "user_id": user_id,
        "email": clean_email,
        "role": role_clean
    }


def get_or_create_google_user(google_info: dict) -> dict:
    """
    Finds existing user by email or creates a new user from verified Google OAuth profile data.
    Preserves existing roles and links Google profile metadata.
    """
    raw_email = google_info.get("email", "")
    if not raw_email:
        raise ValueError("Google profile did not provide an email address.")
    
    clean_email = raw_email.strip().lower()
    google_id = google_info.get("sub", "")
    name = google_info.get("name", "")
    picture = google_info.get("picture", "")
    now_iso = datetime.utcnow().isoformat() + "Z"

    db = get_database()
    user_col = db[USERS_COLLECTION]

    # Check if this email matches the configured uploader email from .env
    uploader_env_email = os.getenv("UPLOADER_EMAIL", "").strip().lower()
    is_env_uploader = bool(uploader_env_email and clean_email == uploader_env_email)

    existing = user_col.find_one({"email": clean_email})

    if existing:
        user_id = existing.get("user_id") or f"usr_{uuid.uuid4().hex[:10]}"
        user_role = existing.get("role", ROLE_DATA_UPLOADER if is_env_uploader else ROLE_CHAT_USER)
        
        update_fields: Dict[str, Any] = {
            "last_login": now_iso,
            "last_auth_provider": "google"
        }
        if google_id and not existing.get("google_id"):
            update_fields["google_id"] = google_id
        if picture and not existing.get("picture"):
            update_fields["picture"] = picture
        if name and not existing.get("name"):
            update_fields["name"] = name
        if is_env_uploader and user_role != ROLE_DATA_UPLOADER:
            update_fields["role"] = ROLE_DATA_UPLOADER
            user_role = ROLE_DATA_UPLOADER

        user_col.update_one(
            {"email": clean_email},
            {"$set": update_fields}
        )

        return {
            "user_id": user_id,
            "email": clean_email,
            "role": user_role,
            "name": existing.get("name") or name,
            "picture": existing.get("picture") or picture
        }
    else:
        # Create a new user record in the MongoDB users collection
        new_user_id = f"usr_{uuid.uuid4().hex[:10]}"
        assigned_role = ROLE_DATA_UPLOADER if is_env_uploader else ROLE_CHAT_USER
        
        new_user_doc = {
            "user_id": new_user_id,
            "email": clean_email,
            "name": name,
            "picture": picture,
            "google_id": google_id,
            "role": assigned_role,
            "user_type": "uploader" if assigned_role == ROLE_DATA_UPLOADER else "chat_user",
            "auth_provider": "google",
            "created_at": now_iso,
            "last_login": now_iso
        }
        user_col.insert_one(new_user_doc)

        return {
            "user_id": new_user_id,
            "email": clean_email,
            "role": assigned_role,
            "name": name,
            "picture": picture
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
