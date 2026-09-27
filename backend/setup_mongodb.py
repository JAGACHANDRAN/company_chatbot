"""
MongoDB Cloud (Atlas) Setup & Index Script
Creates high-performance search indexes for the 11 company columns:
1. Company Name
2. Group
3. Contact Person
4. Mobile No.
5. Email 1
6. Email 2
7. Telephone 1
8. Telephone 2
9. Address
10. PIN
11. Remarks

Supports multiple collections (e.g., all 6 collections configured in backend/.env).
"""

import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, TEXT

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", os.getenv("DATABASE_URL", "")).strip()
DB_NAME = os.getenv("MONGODB_DB_NAME", "calispec").strip()
MONGODB_COLLECTIONS_RAW = os.getenv("MONGODB_COLLECTIONS", os.getenv("MONGODB_COLLECTION_NAMES", "")).strip()
DEFAULT_COLLECTION_NAME = os.getenv("MONGODB_COLLECTION_NAME", "metrology").strip()


def setup_indexes():
    if not MONGODB_URI or MONGODB_URI.startswith("postgresql"):
        print("❌ Error: MONGODB_URI is not set in backend/.env")
        print("Please paste your MongoDB Cloud Atlas connection string into backend/.env")
        return

    print("=" * 60)
    print("Connecting to MongoDB Cloud...")
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        print("✅ Successfully connected to MongoDB Cloud!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nTroubleshooting tips for MongoDB Atlas:")
        print("1. In MongoDB Atlas, go to 'Network Access' -> Add IP Address -> 'Allow Access from Anywhere' (0.0.0.0/0) or add your current IP.")
        print("2. Check that your database username and password in the URI are correct (and percent-encode special characters like @ or #).")
        return

    # Resolve database
    try:
        db = client.get_default_database()
        if db is None:
            db = client[DB_NAME]
    except Exception:
        db = client[DB_NAME]

    print(f"Target Database: {db.name}")

    # Determine collections to index
    target_collection_names = []
    if MONGODB_COLLECTIONS_RAW:
        for c in MONGODB_COLLECTIONS_RAW.split(","):
            c_clean = c.strip()
            if c_clean and c_clean not in target_collection_names:
                target_collection_names.append(c_clean)

    for key, val in os.environ.items():
        if key.startswith("MONGODB_COLLECTION_") or key.startswith("MONGODB_COLLECTION_NAME_"):
            for part in val.split(","):
                c_clean = part.strip()
                if c_clean and c_clean not in target_collection_names:
                    target_collection_names.append(c_clean)

    if DEFAULT_COLLECTION_NAME and DEFAULT_COLLECTION_NAME not in target_collection_names:
        target_collection_names.append(DEFAULT_COLLECTION_NAME)

    # If empty, query the database for all user collections
    if not target_collection_names:
        try:
            target_collection_names = [c for c in db.list_collection_names() if not c.startswith("system.")]
        except Exception:
            target_collection_names = ["metrology"]

    print(f"Collections to index ({len(target_collection_names)}): {', '.join(target_collection_names)}")

    indexes_to_create = [
        # Canonical columns
        ("company_name", ASCENDING),
        ("contact_person", ASCENDING),
        ("designation", ASCENDING),
        ("mobile_no", ASCENDING),
        ("landline_telephone", ASCENDING),
        ("landline_other_no", ASCENDING),
        ("telephone_1", ASCENDING),
        ("telephone_2", ASCENDING),
        ("email", ASCENDING),
        ("email_1", ASCENDING),
        ("email_2", ASCENDING),
        ("address", ASCENDING),
        ("city", ASCENDING),
        ("state", ASCENDING),
        ("pin", ASCENDING),
        ("group", ASCENDING),
        ("records_merged", ASCENDING),
        ("review_required", ASCENDING),
        ("sources", ASCENDING),
        ("remarks", ASCENDING),
        # Verbatim header columns from collections
        ("Company Name", ASCENDING),
        ("Contact Person", ASCENDING),
        ("Designation", ASCENDING),
        ("Mobile No.", ASCENDING),
        ("Landline / Telephone", ASCENDING),
        ("Landline / Other No.", ASCENDING),
        ("Telephone 1", ASCENDING),
        ("Telephone 2", ASCENDING),
        ("Email", ASCENDING),
        ("Email 1", ASCENDING),
        ("Email 2", ASCENDING),
        ("Address", ASCENDING),
        ("City", ASCENDING),
        ("State", ASCENDING),
        ("PIN", ASCENDING),
        ("Group", ASCENDING),
        ("Records Merged", ASCENDING),
        ("Review Required", ASCENDING),
        ("Sources", ASCENDING),
        ("Remarks", ASCENDING),
    ]

    for col_name in target_collection_names:
        collection = db[col_name]
        try:
            count = collection.estimated_document_count()
        except Exception:
            count = 0
        print(f"\n📂 Indexing collection: '{col_name}' ({count:,} documents)...")

        for field, direction in indexes_to_create:
            try:
                idx_name = f"idx_{field.lower().replace(' ', '_').replace('.', '')}"
                collection.create_index([(field, direction)], name=idx_name, background=True)
                print(f"  ✓ Index created: {field}")
            except Exception as err:
                print(f"  ⚠️ Index {field}: {err}")

        # Optional full text index for multi-field search acceleration
        try:
            collection.create_index([
                ("company_name", TEXT),
                ("group", TEXT),
                ("contact_person", TEXT),
                ("address", TEXT),
                ("remarks", TEXT)
            ], name="idx_company_text_search", background=True)
            print("  ✓ Compound text index created.")
        except Exception:
            pass

    print("\n" + "=" * 60)
    print(f"🎉 MongoDB Cloud index setup complete across all {len(target_collection_names)} collections!")
    print("=" * 60)


if __name__ == "__main__":
    setup_indexes()
