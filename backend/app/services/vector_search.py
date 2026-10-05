import os
import re
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import httpx
from ..config import (
    PRIVACY_MODE,
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    VECTOR_INDEX_NAME,
    OLLAMA_BASE_URL,
    OLLAMA_API_KEY,
)
from ..database import get_database, get_collections, get_database_name
from ..utils.normalization import normalize_record_fields, normalize_text
from .mongo_dataset import list_datasets, DATASET_RECORDS_COLLECTION

VECTOR_DIMENSIONS = 256


def generate_local_embedding(text: str, dim: int = VECTOR_DIMENSIONS) -> List[float]:
    """
    High-performance, zero-dependency deterministic semantic feature vector generator.
    Produces unit-normalized dense vectors for search_text comparison when external
    embedding APIs are unavailable or offline.
    Uses n-gram hashing and subword frequency distribution.
    """
    clean = normalize_text(text)
    if not clean:
        return [0.0] * dim

    vector = [0.0] * dim
    words = clean.split()

    for word in words:
        # Word-level hash feature
        w_hash = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % dim
        vector[w_hash] += 2.0

        # Subword n-grams (3-character and 4-character chunks)
        for n in (3, 4):
            for i in range(len(word) - n + 1):
                ngram = word[i:i + n]
                ng_hash = int(hashlib.md5(ngram.encode("utf-8")).hexdigest(), 16) % dim
                vector[ng_hash] += 1.0

    # L2 unit normalization
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0.0:
        return [round(v / norm, 5) for v in vector]
    return vector


async def get_embedding(text: str) -> List[float]:
    """
    Retrieves dense vector embedding for text using configured provider.
    When PRIVACY_MODE is true or external API is offline/unavailable, uses local deterministic embedding.
    """
    clean = text.strip() if text else ""
    if not clean:
        return [0.0] * VECTOR_DIMENSIONS

    if PRIVACY_MODE:
        return generate_local_embedding(clean)

    if EMBEDDING_PROVIDER in ("ollama", "cloud"):
        try:
            headers = {"Content-Type": "application/json"}
            if OLLAMA_API_KEY:
                headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

            payload = {
                "model": EMBEDDING_MODEL,
                "prompt": clean,
            }

            endpoint = f"{OLLAMA_BASE_URL}/api/embeddings"
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    emb = data.get("embedding")
                    if emb and isinstance(emb, list) and len(emb) > 0:
                        return emb
        except Exception:
            # Fallback to deterministic local embedding
            pass

    return generate_local_embedding(clean)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two numeric vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_record_search_text(record: Dict[str, Any]) -> str:
    """
    Constructs comprehensive search_text for a record from all meaningful text fields:
    Company Name, Person Name, Designation, Department, Location, City, State, Country,
    Address, Phone, Email, Remarks, Group, Source File.
    Supports top-level document fields, 'data', 'normalized_data', and 'raw_data'.
    """
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    norm_data = record.get("normalized_data") if isinstance(record.get("normalized_data"), dict) else {}
    raw_data = record.get("raw_data") if isinstance(record.get("raw_data"), dict) else {}

    def get_field_val(*keys: str) -> Optional[str]:
        for k in keys:
            for src in (record, data, norm_data, raw_data):
                if isinstance(src, dict) and k in src:
                    val = src.get(k)
                    if val and not isinstance(val, (dict, list)):
                        s = str(val).strip()
                        if s and s.lower() not in ("none", "null", "not available", "n/a", "-", "nan", "undefined"):
                            return s
        return None

    fields = [
        get_field_val("company", "Company Name", "company_name", "business_name", "Firm", "Organization", "Company", "Client", "norm_company"),
        get_field_val("person", "Contact Person", "person_name", "name", "Name", "Full Name", "Employee Name", "first_name"),
        get_field_val("designation", "Designation", "role", "Role", "Job Title", "Position", "Title"),
        get_field_val("department", "Department", "division", "Division"),
        get_field_val("city", "City", "Town"),
        get_field_val("state", "State", "Province"),
        get_field_val("country", "Country"),
        get_field_val("location", "Location", "Address", "Company Address", "address", "PIN", "pin"),
        get_field_val("phone", "phone_2", "Mobile No.", "mobile_no", "telephone_1", "telephone_2", "contact_number", "Tel"),
        get_field_val("email", "email_2", "Email 1", "Email 2", "personal_mail_id", "Email"),
        get_field_val("linkedin", "LinkedIn", "LinkedIn URL", "linkedin_url"),
        get_field_val("group", "Group"),
        get_field_val("remarks", "Remarks"),
        get_field_val("source_file", "Source File", "source_filename", "filename"),
    ]

    clean_parts = [f for f in fields if f]
    return " ".join(clean_parts).strip()


async def execute_vector_search(
    query_text: str,
    dataset_id: Optional[str] = "all",
    limit: int = 50,
    min_similarity: float = 0.15
) -> List[Dict[str, Any]]:
    """
    Executes vector/semantic search across database records.
    1. Generates query vector embedding.
    2. Checks if MongoDB Atlas Vector Search index ($vectorSearch) is available.
    3. If not, performs in-memory cosine similarity against stored or computed record embeddings.
    Returns normalized records sorted by descending relevance.
    """
    if not query_text or not query_text.strip():
        return []

    query_embedding = await get_embedding(query_text)
    db = get_database()
    results: List[Tuple[float, Dict[str, Any]]] = []
    seen_ids = set()

    # 1. Attempt MongoDB Atlas $vectorSearch pipeline on dataset_records
    atlas_vector_success = False
    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 2,
                    "limit": limit
                }
            }
        ]
        cursor = db[DATASET_RECORDS_COLLECTION].aggregate(pipeline)
        for doc in cursor:
            doc_id = str(doc.get("_id", ""))
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                norm_rec = normalize_record_fields(doc)
                results.append((1.0, norm_rec))
        if results:
            atlas_vector_success = True
    except Exception:
        atlas_vector_success = False

    # 1b. Also attempt $vectorSearch on configured collections if Atlas Vector Search is available
    if atlas_vector_success:
        try:
            collections = get_collections()
            for col in collections:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": VECTOR_INDEX_NAME,
                            "path": "embedding",
                            "queryVector": query_embedding,
                            "numCandidates": limit * 2,
                            "limit": limit
                        }
                    }
                ]
                cursor = col.aggregate(pipeline)
                for doc in cursor:
                    doc_id = str(doc.get("_id", ""))
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        doc_copy = dict(doc)
                        doc_copy["source_collection"] = col.name
                        norm_rec = normalize_record_fields(doc_copy)
                        results.append((1.0, norm_rec))
        except Exception:
            pass

    # 2. Local Vector Similarity Fallback (when Atlas Vector Search index is not present or unsupported)
    if not atlas_vector_success:
        # Retrieve candidate records from dataset_records
        try:
            ds_col = db[DATASET_RECORDS_COLLECTION]
            ds_query = {}
            if dataset_id and dataset_id not in ("all", "default", "*", "companies"):
                ds_query["dataset_id"] = dataset_id

            uploaded_datasets = list_datasets()
            ds_name_map = {ds.get("dataset_id"): ds.get("filename", "Uploaded Dataset") for ds in uploaded_datasets}

            cursor = ds_col.find(ds_query).limit(300)
            for doc in cursor:
                rec_embedding = doc.get("embedding")
                search_text = doc.get("search_text") or build_record_search_text(doc)

                if not rec_embedding or not isinstance(rec_embedding, list) or len(rec_embedding) != len(query_embedding):
                    rec_embedding = generate_local_embedding(search_text, dim=len(query_embedding))

                sim = cosine_similarity(query_embedding, rec_embedding)
                if sim >= min_similarity:
                    ds_name = ds_name_map.get(doc.get("dataset_id"), "Uploaded Dataset")
                    norm_rec = normalize_record_fields(doc, source_file=ds_name)
                    doc_id = str(doc.get("_id", ""))
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        results.append((sim, norm_rec))
        except Exception as e:
            pass

        # Search across configured MongoDB collections
        try:
            collections = get_collections()
            db_name = get_database_name()
            for col in collections:
                col_cursor = col.find().limit(200)
                for raw_doc in col_cursor:
                    rec_embedding = raw_doc.get("embedding")
                    search_text = raw_doc.get("search_text") or build_record_search_text(raw_doc)

                    if not rec_embedding or not isinstance(rec_embedding, list) or len(rec_embedding) != len(query_embedding):
                        rec_embedding = generate_local_embedding(search_text, dim=len(query_embedding))

                    sim = cosine_similarity(query_embedding, rec_embedding)
                    if sim >= min_similarity:
                        doc_copy = dict(raw_doc)
                        col_db = db_name
                        doc_copy["database_source"] = col_db
                        doc_copy["database"] = col_db
                        doc_copy["source_collection"] = col.name
                        s_file_col = (
                            raw_doc.get("source_file")
                            or raw_doc.get("Source File")
                            or raw_doc.get("source_filename")
                            or raw_doc.get("Source_File")
                            or None
                        )
                        doc_copy["source_file"] = s_file_col
                        norm_rec = normalize_record_fields(doc_copy, source_file=s_file_col)
                        doc_id = str(raw_doc.get("_id", ""))
                        if doc_id not in seen_ids:
                            seen_ids.add(doc_id)
                            results.append((sim, norm_rec))
        except Exception as e:
            pass

    # Sort by descending similarity score
    results.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in results[:limit]]
