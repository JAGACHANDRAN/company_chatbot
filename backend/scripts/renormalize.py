import argparse
import sys
import re
from pathlib import Path

# Add project root and backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_database
from app.utils.normalization import normalize_company


def main():
    parser = argparse.ArgumentParser(description="Renormalize norm_company in dataset_records.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database (default is dry run)")
    args = parser.parse_args()

    db = get_database()
    collection = db["dataset_records"]
    cursor = collection.find({}, {"_id": 1, "company": 1, "norm_company": 1, "data.company": 1, "data.Company": 1, "data.Company Name": 1})
    
    total = 0
    changed = 0
    examples = []

    print(f"Scanning records in {collection.name}...")
    ops = []
    for doc in cursor:
        total += 1
        raw_company = (
            doc.get("company")
            or (doc.get("data", {}).get("company") if isinstance(doc.get("data"), dict) else None)
            or (doc.get("data", {}).get("Company") if isinstance(doc.get("data"), dict) else None)
            or (doc.get("data", {}).get("Company Name") if isinstance(doc.get("data"), dict) else None)
            or ""
        )
        current_norm = doc.get("norm_company", "")
        new_norm = normalize_company(raw_company)
        
        if current_norm != new_norm:
            changed += 1
            if len(examples) < 10:
                examples.append({
                    "_id": str(doc["_id"]),
                    "raw": raw_company,
                    "current": current_norm,
                    "new": new_norm
                })
            if args.apply:
                from pymongo import UpdateOne
                ops.append(UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"norm_company": new_norm, "needs_reembedding": True}}
                ))
                if len(ops) >= 1000:
                    collection.bulk_write(ops, ordered=False)
                    ops = []

    if args.apply and ops:
        from pymongo import UpdateOne
        collection.bulk_write(ops, ordered=False)
        ops = []

    print(f"\n--- Renormalization Summary ---")
    print(f"Total documents: {total}")
    print(f"Documents differing: {changed} ({(changed/total*100):.1f}%)" if total > 0 else "0")
    print(f"Mode: {'APPLIED TO DB' if args.apply else 'DRY RUN (use --apply to write)'}")
    
    if examples:
        print("\nSample differences:")
        for ex in examples:
            print(f"  Raw: '{ex['raw']}' -> Current: '{ex['current']}' -> New: '{ex['new']}'")


if __name__ == "__main__":
    main()
