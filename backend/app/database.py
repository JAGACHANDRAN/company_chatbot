import os
from typing import Optional, Tuple, List, Dict, Any, Generator
from urllib.parse import urlparse
import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv

load_dotenv()

# MongoDB Cloud / Atlas or Local URI
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    os.getenv("DATABASE_URL", "mongodb://localhost:27017")
).strip()

DEFAULT_DB_NAME = os.getenv("MONGODB_DB_NAME", "calispec").strip()
DEFAULT_COLLECTION_NAME = os.getenv("MONGODB_COLLECTION_NAME", "metrology").strip()

# Comma-separated list of collections (e.g., "metrology, calibration, testing, inspection, materials, instrumentation")
MONGODB_COLLECTIONS_RAW = os.getenv(
    "MONGODB_COLLECTIONS",
    os.getenv("MONGODB_COLLECTION_NAMES", "")
).strip()

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    """
    Returns a shared, pooled PyMongo client configured for MongoDB Cloud (Atlas) or local MongoDB.
    Uses a 5-second serverSelectionTimeoutMS so failures fail fast with clear diagnostics.
    """
    global _client
    if _client is None:
        if not MONGODB_URI:
            raise ValueError("MONGODB_URI is not set in backend/.env")
        
        _client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
            retryWrites=True
        )
    return _client


def get_database() -> Database:
    """
    Resolves the MongoDB database:
    1. If the MONGODB_URI specifies a database in its path, uses that default database.
    2. Otherwise, uses the MONGODB_DB_NAME environment variable (default: 'calispec').
    """
    client = get_mongo_client()
    try:
        default_db = client.get_default_database()
        if default_db is not None:
            return default_db
    except Exception:
        pass
    return client[DEFAULT_DB_NAME]


def get_database_name() -> str:
    """
    Returns the resolved database name from MongoDB connection or configuration.
    Never returns generic placeholders.
    """
    try:
        db = get_database()
        if db is not None:
            return str(db.name)
    except Exception:
        pass
    return DEFAULT_DB_NAME or "calispec"


def get_configured_collection_names() -> List[str]:
    """
    Returns the list of collection names configured for search.
    Supports:
    1. Comma-separated list: MONGODB_COLLECTIONS=col1, col2, col3, col4, col5, col6
    2. Numbered variables: MONGODB_COLLECTION_1, MONGODB_COLLECTION_2, ... MONGODB_COLLECTION_6
       or MONGODB_COLLECTION_NAME_1, MONGODB_COLLECTION_NAME_2, etc.
    3. Auto-discovering all non-system collections from the active MongoDB database if not specified.
    """
    found_names: List[str] = []

    # Check explicit comma-separated list
    raw_csv = os.getenv("MONGODB_COLLECTIONS", os.getenv("MONGODB_COLLECTION_NAMES", "")).strip()
    if raw_csv:
        for c in raw_csv.split(","):
            c_clean = c.strip()
            if c_clean and c_clean not in found_names:
                found_names.append(c_clean)

    # Check numbered or individual environment variables (e.g., MONGODB_COLLECTION_1, MONGODB_COLLECTION_NAME_1, etc.)
    for key, val in os.environ.items():
        if key.startswith("MONGODB_COLLECTION_") or key.startswith("MONGODB_COLLECTION_NAME_"):
            for part in val.split(","):
                c_clean = part.strip()
                if c_clean and c_clean not in found_names:
                    found_names.append(c_clean)

    # Check legacy single collection name
    single_name = os.getenv("MONGODB_COLLECTION_NAME", "").strip()
    if single_name and single_name not in found_names:
        for part in single_name.split(","):
            c_clean = part.strip()
            if c_clean and c_clean not in found_names:
                found_names.append(c_clean)

    if found_names:
        return found_names

    # Auto-discover non-system collections from the database
    try:
        db = get_database()
        internal_cols = {"user", "users", "uploaders", "dataset_records", "datasets"}
        existing = [c for c in db.list_collection_names() if not c.startswith("system.") and c.lower() not in internal_cols]
        if existing:
            return existing
    except Exception:
        pass

    return ["metrology"]


def get_collections() -> List[Collection]:
    """
    Returns a list of PyMongo Collection objects for all configured collections.
    If a collection does not yet exist, PyMongo will still instantiate a Collection reference.
    """
    db = get_database()
    col_names = get_configured_collection_names()
    
    # Try case-insensitive matching with existing database collections
    try:
        existing_cols = db.list_collection_names()
        case_map = {c.lower(): c for c in existing_cols}
    except Exception:
        case_map = {}

    resolved_collections: List[Collection] = []
    for name in col_names:
        matched_name = case_map.get(name.lower(), name)
        resolved_collections.append(db[matched_name])

    return resolved_collections


def get_companies_collection() -> Collection:
    """
    Backward-compatibility helper: returns the primary/first collection.
    """
    collections = get_collections()
    return collections[0] if collections else get_database()[DEFAULT_COLLECTION_NAME]


def get_db():
    """
    FastAPI dependency that provides the list of all active MongoDB collections.
    Allows searching across all configured collections simultaneously.
    """
    yield get_collections()


def check_db_connection() -> Tuple[bool, str]:
    """
    Pings MongoDB Cloud cluster to verify connectivity, credentials, and network access.
    Reports total and per-collection document counts across all 6 collections.
    Returns (is_connected: bool, message: str).
    """
    if not MONGODB_URI or MONGODB_URI.startswith("postgresql"):
        return False, "MONGODB_URI is not configured in backend/.env"

    try:
        client = get_mongo_client()
        client.admin.command("ping")
        
        db = get_database()
        cols = get_collections()
        col_stats = []
        total_docs = 0

        for col in cols:
            try:
                cnt = col.estimated_document_count()
            except Exception:
                cnt = 0
            total_docs += cnt
            col_stats.append(f"{col.name}: {cnt:,}")

        stats_str = ", ".join(col_stats) if col_stats else "no collections"
        return True, f"MongoDB Cloud connected ({db.name} | {len(cols)} collections | total {total_docs:,} docs | [{stats_str}])"
    except pymongo.errors.ServerSelectionTimeoutError:
        return False, "Could not reach MongoDB Cloud. Check internet connection and ensure your IP is whitelisted in Atlas Network Access."
    except pymongo.errors.OperationFailure as e:
        return False, f"MongoDB authentication failed: {e.details.get('errmsg', str(e))}"
    except Exception as e:
        return False, f"MongoDB connection error: {str(e)}"

