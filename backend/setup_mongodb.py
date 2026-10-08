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
import time
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.operations import SearchIndexModel

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", os.getenv("DATABASE_URL", "")).strip()
DB_NAME = os.getenv("MONGODB_DB_NAME", "calispec").strip()
MONGODB_COLLECTIONS_RAW = os.getenv("MONGODB_COLLECTIONS", os.getenv("MONGODB_COLLECTION_NAMES", "")).strip()
DEFAULT_COLLECTION_NAME = os.getenv("MONGODB_COLLECTION_NAME", "dataset_records").strip()
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index").strip()
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


def setup_vector_search_index(collection, index_name: str = VECTOR_INDEX_NAME, dim: int = EMBEDDING_DIM):
    """
    Drops any existing index named `index_name` and creates a vectorSearch index
    with 768 dimensions and cosine similarity, plus filter fields.
    Polls until status is READY / queryable.
    """
    col_name = collection.name
    print(f"\n🔍 Configuring Atlas Vector Search Index on '{col_name}'...")
    print(f"  - Index Name    : {index_name}")
    print(f"  - Dimensions    : {dim}")
    print(f"  - Similarity    : cosine")
    print(f"  - Filter Fields : city, company, dataset_id")

    # 1. Check existing search indexes and drop if exists
    try:
        existing_indexes = list(collection.list_search_indexes())
        for idx in existing_indexes:
            if idx.get("name") == index_name:
                print(f"  Found existing search index '{index_name}' (status: {idx.get('status', 'unknown')}). Dropping it...")
                try:
                    collection.drop_search_index(index_name)
                    print(f"  ✓ Dropped existing index '{index_name}'.")
                    time.sleep(3)
                except Exception as drop_err:
                    print(f"  ⚠️ Notice while dropping index: {drop_err}")
    except Exception as list_err:
        print(f"  ⚠️ Could not list search indexes via driver: {list_err}")

    # 2. Create the SearchIndexModel
    definition = {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": dim,
                "similarity": "cosine"
            },
            {"type": "filter", "path": "city"},
            {"type": "filter", "path": "company"},
            {"type": "filter", "path": "dataset_id"}
        ]
    }

    try:
        model = SearchIndexModel(
            definition=definition,
            name=index_name,
            type="vectorSearch"
        )
        created_name = collection.create_search_index(model=model)
        print(f"  ✓ Initiated search index creation: '{created_name}'")
    except Exception as create_err:
        print(f"  ❌ Error creating SearchIndexModel: {create_err}")
        return False

    # 3. Poll until queryable (status == READY or queryable == True, max 5 min timeout)
    print(f"  ⏳ Waiting for index '{index_name}' to become queryable (timeout: 5 min)...")
    start_time = time.time()
    timeout_secs = 300
    is_ready = False

    while time.time() - start_time < timeout_secs:
        try:
            indexes = list(collection.list_search_indexes())
            target_idx = next((i for i in indexes if i.get("name") == index_name), None)
            if target_idx:
                status = target_idx.get("status", "BUILDING").upper()
                queryable = target_idx.get("queryable", False)
                print(f"    ... Status: {status} | Queryable: {queryable} (Elapsed: {int(time.time() - start_time)}s)")
                if status == "READY" or queryable is True:
                    print(f"  🎉 Atlas Vector Search Index '{index_name}' is READY and queryable!")
                    is_ready = True
                    break
                elif status in ("FAILED", "DOES_NOT_EXIST"):
                    print(f"  ❌ Index creation failed with status: {status}")
                    break
        except Exception as poll_err:
            print(f"    ... Polling check: {poll_err}")

        time.sleep(10)

    if not is_ready:
        print(f"  ⚠️ Index creation is still building in Atlas background. It will become ready shortly.")

    return is_ready


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
    target_collection_names = ["dataset_records"]
    if MONGODB_COLLECTIONS_RAW:
        for c in MONGODB_COLLECTIONS_RAW.split(","):
            c_clean = c.strip()
            if c_clean and c_clean not in target_collection_names:
                target_collection_names.append(c_clean)

    indexes_to_create = [
        # Canonical columns
        ("company", ASCENDING),
        ("company_name", ASCENDING),
        ("person", ASCENDING),
        ("contact_person", ASCENDING),
        ("designation", ASCENDING),
        ("phone", ASCENDING),
        ("mobile_no", ASCENDING),
        ("email", ASCENDING),
        ("city", ASCENDING),
        ("location", ASCENDING),
        ("dataset_id", ASCENDING),
        ("search_text", ASCENDING),
    ]

    for col_name in target_collection_names:
        collection = db[col_name]
        try:
            count = collection.estimated_document_count()
        except Exception:
            count = 0
        print(f"\n📂 Indexing B-tree and text fields on: '{col_name}' ({count:,} documents)...")

        for field, direction in indexes_to_create:
            try:
                idx_name = f"idx_{field.lower().replace(' ', '_').replace('.', '')}"
                collection.create_index([(field, direction)], name=idx_name, background=True)
                print(f"  ✓ Index created: {field}")
            except Exception as err:
                print(f"  ⚠️ Index {field}: {err}")

        # Text index for lexical search
        try:
            collection.create_index([
                ("company", TEXT),
                ("person", TEXT),
                ("designation", TEXT),
                ("location", TEXT),
                ("search_text", TEXT)
            ], name="idx_text_search", background=True)
            print("  ✓ Compound text index created.")
        except Exception:
            pass

    # Setup Atlas Vector Search index on dataset_records
    setup_vector_search_index(db["dataset_records"])

    print("\n" + "=" * 60)
    print(f"🎉 MongoDB Cloud index setup complete!")
    print("=" * 60)


if __name__ == "__main__":
    setup_indexes()

