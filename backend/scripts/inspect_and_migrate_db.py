import os
import sys
from dotenv import load_dotenv
from pymongo import UpdateOne
from app.database import get_database
from app.utils.normalization import normalize_company_name

load_dotenv()


def inspect_and_migrate():
    db = get_database()
    print(f"Connected to database: '{db.name}'", flush=True)

    cols = db.list_collection_names()
    print(f"Collections: {cols}", flush=True)

    # 1. Migrate dataset_records
    if "dataset_records" in cols:
        print("Inspecting dataset_records...", flush=True)
        bulk_ops = []
        for doc in db.dataset_records.find():
            raw = doc.get("data") or doc.get("raw_data") or {}
            orig_comp = raw.get("Company Name") or raw.get("company_name") or doc.get("company_name") or ""
            if orig_comp:
                correct_norm_comp = normalize_company_name(str(orig_comp))
                existing_norm = doc.get("normalized_data") or {}
                existing_norm_comp = existing_norm.get("company_name") or doc.get("norm_company_name")

                updates = {}
                if existing_norm_comp != correct_norm_comp:
                    existing_norm["company_name"] = correct_norm_comp
                    updates["normalized_data"] = existing_norm
                    updates["norm_company_name"] = correct_norm_comp

                if not doc.get("database_source"):
                    updates["database_source"] = "MongoDB Atlas"
                if not doc.get("source_collection") and doc.get("dataset_name"):
                    updates["source_collection"] = doc.get("dataset_name")

                if updates:
                    bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": updates}))

        if bulk_ops:
            res = db.dataset_records.bulk_write(bulk_ops)
            print(f"dataset_records: modified {res.modified_count} docs.", flush=True)
        else:
            print("dataset_records: all records already up-to-date.", flush=True)

    # 2. Add norm_company_name to named collections if needed
    for c_name in cols:
        if c_name in ("dataset_records", "datasets", "system.views"):
            continue
        print(f"Checking {c_name}...", flush=True)
        bulk_ops = []
        # Find docs missing norm_company_name or database_source
        missing_cursor = db[c_name].find({
            "$or": [
                {"norm_company_name": {"$exists": False}},
                {"database_source": {"$exists": False}}
            ]
        }).limit(2000)

        for doc in missing_cursor:
            comp_val = doc.get("Company Name") or doc.get("Company") or doc.get("company_name")
            upd = {
                "database_source": "MongoDB Atlas",
                "source_collection": c_name
            }
            if comp_val:
                upd["norm_company_name"] = normalize_company_name(str(comp_val))
            if not doc.get("source_file"):
                upd["source_file"] = f"{c_name}.xlsx"

            bulk_ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": upd}))

        if bulk_ops:
            res = db[c_name].bulk_write(bulk_ops)
            print(f"{c_name}: updated {res.modified_count} docs.", flush=True)
        else:
            print(f"{c_name}: already up-to-date.", flush=True)

    print("Migration finished successfully.", flush=True)


if __name__ == "__main__":
    inspect_and_migrate()
