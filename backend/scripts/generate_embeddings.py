import os
import sys
import argparse
import asyncio
import time
from typing import List, Dict, Any
from dotenv import load_dotenv
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

# Ensure backend root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.database import get_database, get_collections, check_db_connection
from app.services.vector_search import (
    build_record_search_text,
    get_embedding,
    generate_local_embedding,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    VECTOR_DIMENSIONS
)
from app.services.mongo_dataset import DATASET_RECORDS_COLLECTION


async def process_collection_embeddings(collection, force: bool = False, batch_size: int = 50):
    col_name = collection.name
    try:
        total_docs = collection.estimated_document_count()
    except Exception:
        total_docs = collection.count_documents({})

    print(f"\n📂 Scanning collection: '{col_name}' ({total_docs:,} total documents)...")

    # Correct filter condition: find documents missing valid embeddings or search_text
    query = {} if force else {
        "$or": [
            {"embedding": {"$exists": False}},
            {"embedding": None},
            {"embedding": []},
            {"search_text": {"$exists": False}},
            {"search_text": ""},
            {"search_text": None}
        ]
    }

    try:
        docs_to_update_count = collection.count_documents(query)
    except Exception as count_err:
        print(f"  ⚠️ Could not count query matches in '{col_name}': {count_err}")
        docs_to_update_count = total_docs

    skipped_count = total_docs - docs_to_update_count
    if docs_to_update_count == 0 and not force:
        print(f"  ✓ All {total_docs:,} records in '{col_name}' already have embeddings. (Skipped)")
        return 0, skipped_count

    print(f"  Found {docs_to_update_count:,} records needing embeddings ({skipped_count:,} already indexed)...")

    cursor = collection.find(query)
    batch_ops: List[UpdateOne] = []
    processed_count = 0
    sample_dim = None

    for doc in cursor:
        search_text = build_record_search_text(doc)
        if not search_text:
            search_text = doc.get("search_text") or "company contact"

        embedding = await get_embedding(search_text)
        if not sample_dim and isinstance(embedding, list) and len(embedding) > 0:
            sample_dim = len(embedding)

        op = UpdateOne(
            {"_id": doc["_id"]},
            {"$set": {
                "search_text": search_text,
                "embedding": embedding
            }}
        )
        batch_ops.append(op)

        if len(batch_ops) >= batch_size:
            collection.bulk_write(batch_ops, ordered=False)
            processed_count += len(batch_ops)
            batch_ops.clear()
            print(f"  ... Updated {processed_count:,} / {docs_to_update_count:,} in '{col_name}'")

    if batch_ops:
        collection.bulk_write(batch_ops, ordered=False)
        processed_count += len(batch_ops)
        batch_ops.clear()

    dim_str = f"{sample_dim}-dim" if sample_dim else f"{VECTOR_DIMENSIONS}-dim"
    print(f"  ✓ Completed '{col_name}': {processed_count:,} records updated with {dim_str} embeddings.")
    return processed_count, skipped_count


async def generate_and_update_embeddings(force: bool = False, batch_size: int = 50):
    start_time = time.time()
    print("=" * 70)
    print("Calispec RAG Embedding Indexing & Migration Tool")
    print(f"Provider        : {EMBEDDING_PROVIDER}")
    print(f"Model           : {EMBEDDING_MODEL}")
    print(f"Base Dimensions : {VECTOR_DIMENSIONS}")
    print(f"Force Re-index  : {force}")
    print(f"Batch Size      : {batch_size}")
    print("=" * 70)

    # 1. Verify DB Connection
    is_connected, msg = check_db_connection()
    if not is_connected:
        print(f"\n❌ MongoDB Connection Error: {msg}")
        print("Please check your MONGODB_URI in backend/.env and network access whitelist.")
        return

    db = get_database()
    print(f"✅ Connected to MongoDB Database: '{db.name}'")

    total_updated = 0
    total_skipped = 0

    # 2. Process dataset_records (dynamic uploaded files)
    try:
        ds_col = db[DATASET_RECORDS_COLLECTION]
        u_cnt, s_cnt = await process_collection_embeddings(ds_col, force=force, batch_size=batch_size)
        total_updated += u_cnt
        total_skipped += s_cnt
    except Exception as err:
        print(f"⚠️ Error processing '{DATASET_RECORDS_COLLECTION}': {err}")

    # 3. Process all configured business collections
    try:
        collections = get_collections()
        for col in collections:
            u_cnt, s_cnt = await process_collection_embeddings(col, force=force, batch_size=batch_size)
            total_updated += u_cnt
            total_skipped += s_cnt
    except Exception as err:
        print(f"⚠️ Error processing collections: {err}")

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "=" * 70)
    print("Embedding Generation Summary:")
    print(f"  - Total Records Updated : {total_updated:,}")
    print(f"  - Total Records Skipped : {total_skipped:,}")
    print(f"  - Elapsed Time          : {elapsed} seconds")
    print("✓ All records indexed with search_text and embedding vectors.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for MongoDB records.")
    parser.add_argument("--force", action="store_true", help="Re-generate embeddings even if they already exist.")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for processing.")
    args = parser.parse_args()

    asyncio.run(generate_and_update_embeddings(force=args.force, batch_size=args.batch_size))


if __name__ == "__main__":
    main()

