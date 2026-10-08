"""
Resumable script to generate 768-d embeddings for records in dataset_records
using local Ollama (nomic-embed-text).

Usage:
  python scripts/reembed_all.py [--force] [--limit N] [--batch 32]
"""
import os
import sys
import time
import argparse
from typing import List
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure backend root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.config import (
    MONGODB_URI,
    DB_NAME,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    OLLAMA_LOCAL_URL,
)
from app.services.embeddings import build_record_text, embed_documents, is_ollama_available


def reembed_all(force: bool = False, limit: int = 0, batch_size: int = 32):
    print("=" * 70)
    print("Calispec Local Re-embedding Tool (nomic-embed-text 768-d)")
    print(f"Database         : {DB_NAME}")
    print(f"Collection       : {COLLECTION_NAME}")
    print(f"Model            : {EMBEDDING_MODEL} ({EMBEDDING_DIM}-d)")
    print(f"Local Ollama URL : {OLLAMA_LOCAL_URL}")
    print(f"Force re-embed   : {force}")
    print(f"Batch size       : {batch_size}")
    if limit > 0:
        print(f"Doc Limit        : {limit}")
    print("=" * 70)

    if not is_ollama_available():
        print(f"❌ Error: Local Ollama is not reachable at {OLLAMA_LOCAL_URL} or missing model '{EMBEDDING_MODEL}'")
        print("Please ensure Ollama is running and run: ollama pull nomic-embed-text")
        return

    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    total_docs = collection.estimated_document_count()
    print(f"\n📂 Total documents in '{COLLECTION_NAME}': {total_docs:,}")

    # Resumable query filter: find docs missing embedding or where length != 768
    if force:
        query = {}
    else:
        query = {
            "$or": [
                {"embedding": {"$exists": False}},
                {"embedding": None},
                {"embedding": {"$size": 0}},
                {"embedding": {"$not": {"$size": EMBEDDING_DIM}}}
            ]
        }

    docs_to_process = collection.count_documents(query)
    already_indexed = total_docs - docs_to_process

    if limit > 0:
        docs_to_process = min(docs_to_process, limit)

    if docs_to_process == 0 and not force:
        print(f"  ✓ All {total_docs:,} documents already have valid {EMBEDDING_DIM}-d embeddings!")
        return

    print(f"  Found {docs_to_process:,} documents needing embeddings ({already_indexed:,} already indexed).")
    print("  Starting embedding process...\n")

    cursor = collection.find(query)
    if limit > 0:
        cursor = cursor.limit(limit)

    batch_docs = []
    batch_texts = []
    processed_count = 0
    skipped_empty = 0
    t_start = time.time()

    for doc in cursor:
        rec_text = build_record_text(doc)
        if not rec_text or not rec_text.strip():
            skipped_empty += 1
            continue

        batch_docs.append(doc)
        batch_texts.append(rec_text)

        if len(batch_docs) >= batch_size:
            # Embed batch
            embeddings = embed_documents(batch_texts, batch_size=batch_size)
            ops = []
            for d, emb, txt in zip(batch_docs, embeddings, batch_texts):
                ops.append(
                    UpdateOne(
                        {"_id": d["_id"]},
                        {"$set": {
                            "embedding": emb,
                            "search_text": txt
                        }}
                    )
                )

            if ops:
                collection.bulk_write(ops, ordered=False)

            processed_count += len(batch_docs)
            batch_docs.clear()
            batch_texts.clear()

            elapsed = max(time.time() - t_start, 0.001)
            docs_per_sec = processed_count / elapsed
            remaining = docs_to_process - processed_count
            eta_secs = remaining / docs_per_sec if docs_per_sec > 0 else 0
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_secs))

            percent = (processed_count / docs_to_process) * 100
            print(f"  [{processed_count:,}/{docs_to_process:,}] ({percent:.1f}%) | {docs_per_sec:.1f} docs/s | ETA: {eta_str}")

    # Process final remaining batch
    if batch_docs:
        embeddings = embed_documents(batch_texts, batch_size=batch_size)
        ops = []
        for d, emb, txt in zip(batch_docs, embeddings, batch_texts):
            ops.append(
                UpdateOne(
                    {"_id": d["_id"]},
                    {"$set": {
                        "embedding": emb,
                        "search_text": txt
                    }}
                )
            )
        if ops:
            collection.bulk_write(ops, ordered=False)
        processed_count += len(batch_docs)

    elapsed_total = round(time.time() - t_start, 2)
    valid_count = collection.count_documents({"embedding": {"$size": EMBEDDING_DIM}})

    print("\n" + "=" * 70)
    print("Re-embedding Complete!")
    print(f"  - Processed in this run : {processed_count:,}")
    print(f"  - Skipped empty texts   : {skipped_empty:,}")
    print(f"  - Time elapsed          : {elapsed_total}s")
    print(f"  - Total valid 768-d docs: {valid_count:,} / {total_docs:,}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Re-embed database records with local nomic-embed-text (768-d).")
    parser.add_argument("--force", action="store_true", help="Re-embed all records even if 768-d embedding exists.")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N documents (useful for testing).")
    parser.add_argument("--batch", type=int, default=32, help="Batch size for embedding generation (default: 32).")
    args = parser.parse_args()

    reembed_all(force=args.force, limit=args.limit, batch_size=args.batch)


if __name__ == "__main__":
    main()
