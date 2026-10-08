import json
from app.database import get_database
from app.config import COLLECTION_NAME

def diagnose():
    db = get_database()
    col = db[COLLECTION_NAME]
    
    total = col.estimated_document_count()
    print(f"Total documents in {COLLECTION_NAME}: {total}")
    
    sample = list(col.find({}, {"embedding": 0}).limit(5))
    print("\n--- SAMPLE 5 DOCUMENTS (keys and source fields) ---")
    for idx, doc in enumerate(sample, 1):
        doc_id = str(doc.get("_id"))
        top_keys = list(doc.keys())
        raw_data_keys = list(doc.get("raw_data", {}).keys()) if isinstance(doc.get("raw_data"), dict) else []
        data_keys = list(doc.get("data", {}).keys()) if isinstance(doc.get("data"), dict) else []
        source_file = doc.get("source_file")
        raw_source_file = doc.get("raw_data", {}).get("Source File") if isinstance(doc.get("raw_data"), dict) else None
        sources = doc.get("Sources") or (doc.get("raw_data", {}).get("Sources") if isinstance(doc.get("raw_data"), dict) else None)
        records_merged = doc.get("Records Merged") or (doc.get("raw_data", {}).get("Records Merged") if isinstance(doc.get("raw_data"), dict) else None)
        
        print(f"Doc {idx} (_id={doc_id}):")
        print(f"  Top-level keys: {top_keys}")
        print(f"  raw_data keys: {raw_data_keys}")
        print(f"  source_file: {source_file}")
        print(f"  raw_data['Source File']: {raw_source_file}")
        print(f"  Sources: {sources}")
        print(f"  Records Merged: {records_merged}")

    # Aggregation & Analysis
    has_source_file = col.count_documents({"source_file": {"$exists": True, "$ne": None, "$ne": ""}})
    has_raw_source_file = col.count_documents({"raw_data.Source File": {"$exists": True, "$ne": None, "$ne": ""}})
    has_sources = col.count_documents({
        "$or": [
            {"Sources": {"$exists": True, "$ne": None, "$ne": ""}},
            {"raw_data.Sources": {"$exists": True, "$ne": None, "$ne": ""}}
        ]
    })
    
    # Check merged records
    merged_count = col.count_documents({
        "$or": [
            {"Records Merged": {"$gt": 1}},
            {"raw_data.Records Merged": {"$gt": 1}},
            {"Sources": {"$regex": r"\|"}},
            {"raw_data.Sources": {"$regex": r"\|"}}
        ]
    })
    
    # Check discrepancy between source_file and raw_data.Source File
    diff_count = 0
    all_sample_cursor = col.find({}, {"source_file": 1, "raw_data.Source File": 1, "Sources": 1, "raw_data.Sources": 1}).limit(5000)
    for d in all_sample_cursor:
        sf = d.get("source_file")
        raw_sf = d.get("raw_data", {}).get("Source File") if isinstance(d.get("raw_data"), dict) else None
        if sf and raw_sf and sf.strip().lower() != raw_sf.strip().lower():
            diff_count += 1

    print("\n--- AGGREGATE METRICS ---")
    print(f"Documents with 'source_file': {has_source_file}")
    print(f"Documents with 'raw_data.Source File': {has_raw_source_file}")
    print(f"Documents with 'Sources': {has_sources}")
    print(f"Merged records count: {merged_count}")
    print(f"Discrepancies (source_file != raw_data['Source File']): {diff_count}")

if __name__ == "__main__":
    diagnose()
