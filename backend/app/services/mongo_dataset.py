import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pymongo import ASCENDING
from ..database import get_database


DATASETS_COLLECTION = "datasets"
DATASET_RECORDS_COLLECTION = "dataset_records"


def ensure_dataset_indexes():
    """Ensures indexes exist on datasets and dataset_records collections."""
    try:
        db = get_database()
        db[DATASETS_COLLECTION].create_index([("dataset_id", ASCENDING)], unique=True, background=True)
        db[DATASETS_COLLECTION].create_index([("created_at", ASCENDING)], background=True)
        
        db[DATASET_RECORDS_COLLECTION].create_index([("dataset_id", ASCENDING)], background=True)
        db[DATASET_RECORDS_COLLECTION].create_index([("dataset_id", ASCENDING), ("record_index", ASCENDING)], background=True)

        # Field-level search indexes
        for field in [
            "data.Company Name", "data.Person Name", "data.Designation", "data.Department",
            "data.State", "data.City", "data.Country", "data.Location",
            "normalized_data.company_name", "normalized_data.person_name", "normalized_data.designation",
            "normalized_data.state", "normalized_data.city"
        ]:
            try:
                db[DATASET_RECORDS_COLLECTION].create_index([(field, ASCENDING)], background=True)
            except Exception:
                pass
    except Exception as e:
        print(f"[Mongo Dataset Warning] Could not create dataset indexes: {e}")


def save_dataset(
    filename: str,
    original_type: str,
    original_fields: List[str],
    normalized_fields: List[str],
    field_mapping: Dict[str, str],
    field_types: Dict[str, str],
    normalized_records: List[Dict[str, Any]],
    sheet_name: Optional[str] = None,
    size_bytes: int = 0
) -> Dict[str, Any]:
    """
    Saves dataset metadata and all normalized records into MongoDB.
    Uses batched insert_many for high performance with large datasets.
    """
    db = get_database()
    ensure_dataset_indexes()

    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat() + "Z"

    dataset_meta = {
        "dataset_id": dataset_id,
        "filename": filename,
        "original_type": original_type,
        "sheet_name": sheet_name,
        "created_at": created_at,
        "record_count": len(normalized_records),
        "fields": original_fields,
        "normalized_fields": normalized_fields,
        "field_mapping": field_mapping,
        "field_types": field_types,
        "size_bytes": size_bytes
    }

    # 1. Insert dataset metadata
    db[DATASETS_COLLECTION].insert_one(dataset_meta)

    # 2. Insert records in chunks of 1000
    if normalized_records:
        docs_to_insert = []
        for rec in normalized_records:
            doc = {
                "dataset_id": dataset_id,
                "record_index": rec["record_index"],
                "data": rec["data"],
                "normalized_data": rec["normalized_data"]
            }
            docs_to_insert.append(doc)

            if len(docs_to_insert) >= 1000:
                db[DATASET_RECORDS_COLLECTION].insert_many(docs_to_insert, ordered=False)
                docs_to_insert = []

        if docs_to_insert:
            db[DATASET_RECORDS_COLLECTION].insert_many(docs_to_insert, ordered=False)

    # Safe log without recording any sensitive user record contents
    print(f"[Dataset Saved] ID: {dataset_id} | File: {filename} | Records: {len(normalized_records):,} | Fields: {len(original_fields)}")

    # Return clean copy without MongoDB _id
    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "original_type": original_type,
        "sheet_name": sheet_name,
        "created_at": created_at,
        "record_count": len(normalized_records),
        "fields": original_fields,
        "normalized_fields": normalized_fields
    }


def list_datasets() -> List[Dict[str, Any]]:
    """Returns list of all stored datasets."""
    db = get_database()
    cursor = db[DATASETS_COLLECTION].find({}, {"_id": 0}).sort("created_at", -1)
    return list(cursor)


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    """Returns metadata for a specific dataset."""
    if not dataset_id:
        return None
    db = get_database()
    return db[DATASETS_COLLECTION].find_one({"dataset_id": dataset_id}, {"_id": 0})


def delete_dataset(dataset_id: str) -> bool:
    """Deletes a dataset and all associated records from MongoDB."""
    if not dataset_id:
        return False
    db = get_database()
    db[DATASETS_COLLECTION].delete_one({"dataset_id": dataset_id})
    db[DATASET_RECORDS_COLLECTION].delete_many({"dataset_id": dataset_id})
    print(f"[Dataset Deleted] ID: {dataset_id}")
    return True


def get_dataset_sample(dataset_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Fetches a sample of records from the dataset (for UI preview)."""
    db = get_database()
    cursor = db[DATASET_RECORDS_COLLECTION].find({"dataset_id": dataset_id}, {"_id": 0, "data": 1}).limit(limit)
    return [doc.get("data", {}) for doc in cursor]
