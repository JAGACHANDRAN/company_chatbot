import json
from app.database import get_database
from app.config import COLLECTION_NAME

def inspect_merged():
    db = get_database()
    col = db[COLLECTION_NAME]
    
    merged_samples = list(col.find({
        "$or": [
            {"Records Merged": {"$gt": 1}},
            {"Sources": {"$regex": r"\|"}}
        ]
    }, {"embedding": 0}).limit(5))
    
    print("\n--- SAMPLE 5 MERGED/SOURCES DOCUMENTS ---")
    for idx, d in enumerate(merged_samples, 1):
        print(f"\nDoc {idx}:")
        print(f"  company: {d.get('company')}")
        print(f"  source_file: {d.get('source_file')}")
        print(f"  Source File: {d.get('Source File')}")
        print(f"  Sources: {d.get('Sources')}")
        print(f"  Source Sheet: {d.get('Source Sheet')}")
        print(f"  sheet_name: {d.get('sheet_name')}")
        print(f"  Records Merged: {d.get('Records Merged')}")

if __name__ == "__main__":
    inspect_merged()
