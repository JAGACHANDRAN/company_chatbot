import os
import re
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
import httpx
from dotenv import load_dotenv
from ..database import get_database, get_collections, get_database_name
from ..utils.normalization import normalize_record_fields, normalize_text
from .mongo_dataset import list_datasets, DATASET_RECORDS_COLLECTION

load_dotenv()

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower().strip()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text").strip()
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", os.getenv("LLM_API_KEY", "")).strip()

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
    Tries Ollama embeddings first (if configured), then cleanly falls back to local embedding.
    """
    clean = text.strip()
    if not clean:
        return [0.0] * VECTOR_DIMENSIONS

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
    Company Name, Person Name, Designation, Department, State, City, Country, Address, Remarks.
    """
    data = record.get("data") if isinstance(record.get("data"), dict) else record

    fields = [
        data.get("company_name") or data.get("Company Name"),
        data.get("person_name") or data.get("Contact Person") or data.get("name"),
        data.get("designation") or data.get("Designation") or data.get("role"),
        data.get("department") or data.get("Department"),
        data.get("city") or data.get("City"),
        data.get("state") or data.get("State"),
        data.get("country") or data.get("Country"),
        data.get("location") or data.get("Location") or data.get("Address"),
        data.get("group") or data.get("Group"),
        data.get("remarks") or data.get("Remarks"),
    ]

    clean_parts = [str(f).strip() for f in fields if f and str(f).strip().lower() not in ("none", "null", "not available", "n/a", "-")]
    return " ".join(clean_parts).strip()


async def execute_vector_search(
    query_text: str,
    dataset_id: Optional[str] = "all",
    limit: int = 50,
    min_similarity: float = 0.25
) -> List[Dict[str, Any]]:
    """
    Executes vector/semantic search across database records.
    1. Checks if MongoDB Atlas Vector Search index ($vectorSearch) is available.
    2. If not, performs in-memory cosine similarity against stored or computed record embeddings.
    Returns normalized records sorted by descending relevance.
    """
    if not query_text or not query_text.strip():
        return []

    query_embedding = await get_embedding(query_text)
    db = get_database()
    results: List[Tuple[float, Dict[str, Any]]] = []

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
            norm_rec = normalize_record_fields(doc)
            results.append((1.0, norm_rec))
        if results:
            atlas_vector_success = True
    except Exception:
        # Atlas Vector Search index does not exist or is unsupported on cluster
        atlas_vector_success = False

    # 2. Local Vector Similarity Fallback
    if not atlas_vector_success:
        # Retrieve candidate records from dataset_records
        try:
            ds_col = db[DATASET_RECORDS_COLLECTION]
            ds_query = {}
            if dataset_id and dataset_id not in ("all", "default", "*", "companies"):
                ds_query["dataset_id"] = dataset_id

            uploaded_datasets = list_datasets()
            ds_name_map = {ds.get("dataset_id"): ds.get("filename", "Uploaded Dataset") for ds in uploaded_datasets}

            # Fetch sample / candidates (up to 300) for vector matching
            cursor = ds_col.find(ds_query).limit(300)
            for doc in cursor:
                rec_embedding = doc.get("embedding")
                search_text = doc.get("search_text") or build_record_search_text(doc)

                if not rec_embedding or len(rec_embedding) != len(query_embedding):
                    rec_embedding = generate_local_embedding(search_text, dim=len(query_embedding))

                sim = cosine_similarity(query_embedding, rec_embedding)
                if sim >= min_similarity:
                    ds_name = ds_name_map.get(doc.get("dataset_id"), "Uploaded Dataset")
                    norm_rec = normalize_record_fields(doc, source_file=ds_name)
                    results.append((sim, norm_rec))
        except Exception as e:
            print(f"[Local Vector Search Warning - datasets] {e}")

        # Search across collection candidates
        try:
            collections = get_collections()
            db_name = get_database_name()
            for col in collections:
                col_cursor = col.find().limit(50)
                for raw_doc in col_cursor:
                    search_text = build_record_search_text(raw_doc)
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
                        results.append((sim, norm_rec))
        except Exception as e:
            print(f"[Local Vector Search Warning - collections] {e}")

    # Sort by descending similarity score
    results.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in results[:limit]]
