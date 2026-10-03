"""
Debug script: inspect source_file field in MongoDB documents.
Run from backend/ directory: python scripts/debug_source_file.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import get_mongo_client, DEFAULT_DB_NAME

client = get_mongo_client()
db = client[DEFAULT_DB_NAME]

print(f"\n=== Connected to DB: {DEFAULT_DB_NAME} ===")

print(f"Collections: {db.list_collection_names()}\n")

for col_name in db.list_collection_names():
    if col_name.startswith("system.") or col_name in {"user","users","uploaders","datasets","fs.files","fs.chunks"}:
        continue
    col = db[col_name]
    count = col.count_documents({})
    if count == 0:
        continue
    print(f"--- Collection: {col_name} ({count} docs) ---")
    # Check first 5 docs for source_file field
    for doc in col.find({}, {"source_file": 1, "dataset_name": 1, "company": 1, "_id": 0}).limit(5):
        sf = doc.get("source_file", "[MISSING]")
        ds = doc.get("dataset_name", "[MISSING]")
        co = doc.get("company", "[MISSING]")
        print(f"  company={co!r:40s}  source_file={sf!r:50s}  dataset_name={ds!r}")
    print()
