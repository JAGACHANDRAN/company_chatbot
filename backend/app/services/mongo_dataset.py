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
            "norm_company", "person", "phone", "email", "company", "location", "designation", "dataset_name",
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
        from .vector_search import build_record_search_text, generate_local_embedding
        docs_to_insert = []
        for rec in normalized_records:
            search_text = build_record_search_text(rec)
            embedding = generate_local_embedding(search_text)
            doc = {
                "dataset_id": dataset_id,
                "record_index": rec["record_index"],
                "data": rec["data"],
                "normalized_data": rec["normalized_data"],
                "search_text": search_text,
                "embedding": embedding
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


def save_cleaned_dataset(
    filename: str,
    cleaned_rows: List[Dict[str, Any]],
    dataset_name: Optional[str] = None,
    mode: str = "append",
) -> Dict[str, Any]:
    """
    Saves cleaned contact records into MongoDB.
    
    Document shape:
      company, person, designation, phone, phone_2, email, email_2, location,
      linkedin, any extra columns, norm_company, source_file, sheet_name,
      source_row, needs_review, review_reasons, uploaded_at, search_text.
    
    Modes:
      - 'replace': deletes previous records for this dataset and inserts all cleaned rows.
      - 'append': skips rows already in the collection (matching norm_company + person + phone/email).
    """
    import re
    from .data_cleaner import STANDARD_ORDER

    db = get_database()
    ensure_dataset_indexes()

    clean_name = (dataset_name or filename or "uploaded_dataset").strip()
    uploaded_at = datetime.utcnow().isoformat() + "Z"

    # Find if dataset entry already exists
    existing = db[DATASETS_COLLECTION].find_one({"filename": clean_name}) or db[DATASETS_COLLECTION].find_one({"dataset_name": clean_name})
    if existing:
        dataset_id = existing["dataset_id"]
        if mode == "replace":
            db[DATASET_RECORDS_COLLECTION].delete_many({"dataset_id": dataset_id})
    else:
        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"

    # If append mode, build lookup of existing records for deduplication
    existing_keys = set()
    if mode == "append" and existing:
        cursor = db[DATASET_RECORDS_COLLECTION].find(
            {"dataset_id": dataset_id},
            {"norm_company": 1, "person": 1, "phone": 1, "email": 1, "_id": 0}
        )
        for doc in cursor:
            nc = str(doc.get("norm_company") or "").strip().lower()
            p = str(doc.get("person") or "").strip().lower()
            ph = re.sub(r"\D", "", str(doc.get("phone") or ""))
            em = str(doc.get("email") or "").strip().lower()
            if nc and p:
                if ph:
                    existing_keys.add((nc, p, f"p:{ph}"))
                if em:
                    existing_keys.add((nc, p, f"e:{em}"))
                if not ph and not em:
                    existing_keys.add((nc, p, "none"))

    inserted_docs = []
    skipped_count = 0

    standard_keys = {
        "company", "person", "designation", "phone", "phone_2",
        "email", "email_2", "location", "linkedin", "norm_company",
        "source_file", "sheet_name", "source_row", "needs_review",
        "review_reasons", "uploaded_at", "search_text", "dataset_id", "dataset_name"
    }

    for row in cleaned_rows:
        nc = str(row.get("norm_company") or "").strip().lower()
        p = str(row.get("person") or "").strip().lower()
        ph = re.sub(r"\D", "", str(row.get("phone") or ""))
        em = str(row.get("email") or "").strip().lower()

        if mode == "append" and existing_keys and nc and p:
            is_dup = False
            if ph and (nc, p, f"p:{ph}") in existing_keys:
                is_dup = True
            elif em and (nc, p, f"e:{em}") in existing_keys:
                is_dup = True
            elif not ph and not em and (nc, p, "none") in existing_keys:
                is_dup = True

            if is_dup:
                skipped_count += 1
                continue

        # Add to existing_keys to deduplicate within this upload batch
        if nc and p:
            if ph:
                existing_keys.add((nc, p, f"p:{ph}"))
            if em:
                existing_keys.add((nc, p, f"e:{em}"))
            if not ph and not em:
                existing_keys.add((nc, p, "none"))

        search_text = " ".join(str(row.get(k, "")) for k in
                               ("company", "person", "designation", "phone", "email", "location") if row.get(k))

        doc = {
            "dataset_id": dataset_id,
            "dataset_name": clean_name,
            "company": row.get("company") or "",
            "person": row.get("person") or "",
            "designation": row.get("designation") or "",
            "phone": row.get("phone") or "",
            "phone_2": row.get("phone_2") or "",
            "email": row.get("email") or "",
            "email_2": row.get("email_2") or "",
            "location": row.get("location") or "",
            "linkedin": row.get("linkedin") or "",
            "norm_company": row.get("norm_company") or "",
            "source_file": row.get("source_file", filename),
            "sheet_name": str(row.get("sheet_name", "")),
            "source_row": int(row.get("source_row", 0)) if str(row.get("source_row", "")).isdigit() else 0,
            "needs_review": bool(row.get("needs_review", False)),
            "review_reasons": str(row.get("review_reasons", "")),
            "uploaded_at": uploaded_at,
            "search_text": search_text,
            "embedding_status": "pending",
        }

        # Any extra columns from row
        for k, v in row.items():
            if k not in standard_keys and not k.startswith("_"):
                doc[k] = v

        # Sub-payloads for backward compatibility with mongo search
        doc["data"] = {
            "Company Name": doc["company"],
            "Person Name": doc["person"],
            "Designation": doc["designation"],
            "Contact Number": doc["phone"],
            "Phone 2": doc["phone_2"],
            "Email": doc["email"],
            "Email 2": doc["email_2"],
            "Location": doc["location"],
            "LinkedIn": doc["linkedin"],
            **{k: doc[k] for k in doc if k not in standard_keys and k not in ("data", "normalized_data")}
        }
        doc["normalized_data"] = {
            "company_name": doc["company"],
            "person_name": doc["person"],
            "designation": doc["designation"],
            "contact_number": doc["phone"],
            "email": doc["email"],
            "location": doc["location"],
        }
        inserted_docs.append(doc)

    # Insert docs in chunks of 1000
    if inserted_docs:
        for i in range(0, len(inserted_docs), 1000):
            chunk = inserted_docs[i:i + 1000]
            db[DATASET_RECORDS_COLLECTION].insert_many(chunk, ordered=False)

    # Update or insert dataset metadata
    total_in_db = db[DATASET_RECORDS_COLLECTION].count_documents({"dataset_id": dataset_id})
    all_fields = list(STANDARD_ORDER) + ["needs_review", "review_reasons"]
    
    meta_doc = {
        "dataset_id": dataset_id,
        "filename": filename,
        "dataset_name": clean_name,
        "original_type": filename.split(".")[-1].lower() if "." in filename else "data",
        "created_at": uploaded_at,
        "updated_at": uploaded_at,
        "record_count": total_in_db,
        "fields": all_fields,
        "normalized_fields": all_fields,
        "is_cleaned": True,
    }
    db[DATASETS_COLLECTION].update_one(
        {"dataset_id": dataset_id},
        {"$set": meta_doc},
        upsert=True
    )

    # Safe log without logging any cell values
    print(f"[Cleaned Dataset Saved] ID: {dataset_id} | Name: {clean_name} | Inserted: {len(inserted_docs)} | Skipped: {skipped_count}")

    return {
        "success": True,
        "dataset_id": dataset_id,
        "dataset_name": clean_name,
        "filename": filename,
        "inserted": len(inserted_docs),
        "skipped": skipped_count,
        "total_records": total_in_db,
        "message": f"Successfully processed {len(cleaned_rows)} records: {len(inserted_docs)} inserted, {skipped_count} skipped duplicates."
    }
