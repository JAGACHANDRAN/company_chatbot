import os
import sys
import argparse
import asyncio
from typing import List, Dict, Any
from dotenv import load_dotenv

# Ensure backend root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.database import get_database, get_collections
from app.services.vector_search import (
    build_record_search_text,
    get_embedding,
    generate_local_embedding,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL
)
from app.services.mongo_dataset import DATASET_RECORDS_COLLECTION


async def generate_and_update_embeddings(force: bool = False, batch_size: int = 50):
    db = get_database()
    print("=" * 60)
    print("Calispec RAG Embedding Indexing & Migration Tool")
    print(f"Provider: {EMBEDDING_PROVIDER} | Model: {EMBEDDING_MODEL}")
    print(f"Force re-index: {force}")
    print("=" * 60)

    # 1. Process dataset_records
    ds_col = db[DATASET_RECORDS_COLLECTION]
    total_ds_records = ds_col.count_documents({})
    print(f"\nScanning '{DATASET_RECORDS_COLLECTION}' ({total_ds_records:,} documents)...")

    query = {} if force else {
        "$or": [
            {"embedding": {"$exists": False}},
            {"embedding": None},
            {"embedding": []},
            {"search_text": {"$exists": False}}
        ]
    }

    cursor = ds_col.find(query)
    updated_count = 0
    skipped_count = total_ds_records - ds_col.count_documents(query)

    batch_ops = []
    for doc in cursor:
        search_text = doc.get("search_text") or build_record_search_text(doc)
        embedding = await get_embedding(search_text)

        ds_col.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "search_text": search_text,
                "embedding": embedding
            }}
        )
        updated_count += 1
        if updated_count % 25 == 0:
            print(f"  Processed {updated_count:,} records in dataset_records...")

    print(f"✓ '{DATASET_RECORDS_COLLECTION}': {updated_count} records indexed, {skipped_count} skipped.")

    # 2. Process configured MongoDB collections
    collections = get_collections()
    for col in collections:
        total_col_docs = col.estimated_document_count()
        print(f"\nScanning '{col.name}' ({total_col_docs:,} documents)...")

        col_query = {} if force else {
            "$or": [
                {"embedding": {"$exists": False}},
                {"embedding": None},
                {"embedding": []},
                {"search_text": {"$exists": False}}
            ]
        }

        col_cursor = col.find(col_query)
        col_updated = 0
        for doc in col_cursor:
            search_text = doc.get("search_text") or build_record_search_text(doc)
            embedding = await get_embedding(search_text)

            col.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "search_text": search_text,
                    "embedding": embedding
                }}
            )
            col_updated += 1
            if col_updated % 50 == 0:
                print(f"  Processed {col_updated:,} in {col.name}...")

        print(f"✓ '{col.name}': {col_updated} records indexed.")

    print("\n" + "=" * 60)
    print("Embedding generation and migration complete!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for MongoDB records.")
    parser.add_argument("--force", action="store_true", help="Re-generate embeddings even if they already exist.")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for processing.")
    args = parser.parse_args()

    asyncio.run(generate_and_update_embeddings(force=args.force, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
