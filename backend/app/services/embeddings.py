"""
Local Embedding Service for Calispec Hybrid RAG.
SECURITY GUARANTEE: Embeddings are generated ONLY by local Ollama at http://localhost:11434.
Records are NEVER sent to any cloud embedding API.
"""
import logging
from typing import List, Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import (
    OLLAMA_LOCAL_URL,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
)
from ..database import get_database

logger = logging.getLogger("calispec.embeddings")


def is_ollama_available() -> bool:
    """Checks if local Ollama service is reachable and has the embedding model."""
    try:
        with httpx.Client(timeout=3.0) as client:
            res = client.get(f"{OLLAMA_LOCAL_URL}/api/tags")
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                model_base = EMBEDDING_MODEL.split(":")[0]
                return model_base in models or any(model_base in m for m in models)
    except Exception:
        return False
    return False


def build_record_text(doc: Dict[str, Any]) -> str:
    """
    Constructs normalized searchable record text:
    Format: 'Company: X | Person: Y | Designation: Z | City: C | State: S | Remarks: R'
    Uses real document fields. Skips empty/N/A values.
    SECURITY: NEVER includes phone numbers or emails in the embedding text.
    """
    raw = doc.get("raw_data") if isinstance(doc.get("raw_data"), dict) else {}
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    norm = doc.get("normalized_data") if isinstance(doc.get("normalized_data"), dict) else {}

    def get_field_val(*keys: str) -> Optional[str]:
        for k in keys:
            for src in (doc, raw, data, norm):
                if isinstance(src, dict) and k in src:
                    val = src.get(k)
                    if val is not None and not isinstance(val, (dict, list)):
                        s = str(val).strip()
                        if s and s.lower() not in ("none", "null", "not available", "n/a", "-", "nan", "undefined"):
                            return s
        return None

    company = get_field_val("company", "Company Name", "company_name", "business_name", "norm_company")
    person = get_field_val("person", "Contact Person", "person_name", "name")
    designation = get_field_val("designation", "Designation", "role", "Job Title")
    city = get_field_val("city", "City", "location", "Town")
    state = get_field_val("state", "State", "Province")
    remarks = get_field_val("remarks", "Remarks", "notes", "Product / Interest")

    parts = []
    if company:
        parts.append(f"Company: {company}")
    if person:
        parts.append(f"Person: {person}")
    if designation:
        parts.append(f"Designation: {designation}")
    if city:
        clean_city = city.split("/")[0].strip() if "/" in city else city
        parts.append(f"City: {clean_city}")
    if state:
        parts.append(f"State: {state}")
    if remarks:
        parts.append(f"Remarks: {remarks}")

    return " | ".join(parts) if parts else ""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    reraise=True
)
def _call_ollama_embed(inputs: List[str]) -> List[List[float]]:
    """Internal synchronous batch embedding call to local Ollama with retry backoff."""
    urls = [OLLAMA_LOCAL_URL]
    if "localhost" in OLLAMA_LOCAL_URL:
        urls.append(OLLAMA_LOCAL_URL.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in OLLAMA_LOCAL_URL:
        urls.append(OLLAMA_LOCAL_URL.replace("127.0.0.1", "localhost"))

    last_err = None
    for url in urls:
        endpoint = f"{url}/api/embed"
        payload = {
            "model": EMBEDDING_MODEL,
            "input": inputs
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(endpoint, json=payload)
                res.raise_for_status()
                data = res.json()
                embeddings = data.get("embeddings", [])
                if not embeddings or len(embeddings) != len(inputs):
                    raise ValueError(f"Expected {len(inputs)} embeddings, got {len(embeddings)}")
                for i, vec in enumerate(embeddings):
                    if len(vec) != EMBEDDING_DIM:
                        raise ValueError(f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(vec)} at index {i}")
                return embeddings
        except Exception as e:
            last_err = e
            continue

    raise last_err or RuntimeError("Failed to connect to local Ollama")


def _async_call_ollama_embed_sync_wrapper(inputs: List[str]) -> List[List[float]]:
    return _call_ollama_embed(inputs)


async def _async_call_ollama_embed(inputs: List[str]) -> List[List[float]]:
    """Internal asynchronous batch embedding call to local Ollama with retry backoff."""
    urls = [OLLAMA_LOCAL_URL]
    if "localhost" in OLLAMA_LOCAL_URL:
        urls.append(OLLAMA_LOCAL_URL.replace("localhost", "127.0.0.1"))
    elif "127.0.0.1" in OLLAMA_LOCAL_URL:
        urls.append(OLLAMA_LOCAL_URL.replace("127.0.0.1", "localhost"))

    last_err = None
    for url in urls:
        endpoint = f"{url}/api/embed"
        payload = {
            "model": EMBEDDING_MODEL,
            "input": inputs
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(endpoint, json=payload)
                res.raise_for_status()
                data = res.json()
                embeddings = data.get("embeddings", [])
                if not embeddings or len(embeddings) != len(inputs):
                    raise ValueError(f"Expected {len(inputs)} embeddings, got {len(embeddings)}")
                for i, vec in enumerate(embeddings):
                    if len(vec) != EMBEDDING_DIM:
                        raise ValueError(f"Embedding dimension mismatch: expected {EMBEDDING_DIM}, got {len(vec)} at index {i}")
                return embeddings
        except Exception as e:
            last_err = e
            continue

    raise last_err or RuntimeError("Failed to connect to local Ollama")


def embed_documents(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """
    Embeds a list of document texts in batches using nomic-embed-text via local Ollama.
    Prefixes each document with 'search_document: ' for optimal nomic retrieval.
    """
    if not texts:
        return []

    results: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        prefixed_batch = [f"search_document: {t.strip()}" if t and t.strip() else "search_document: empty" for t in batch]
        try:
            embeddings = _call_ollama_embed(prefixed_batch)
            results.extend(embeddings)
        except Exception as e:
            logger.warning(f"[embed_documents] Batch failed: {e}")
            results.extend([[0.0] * EMBEDDING_DIM for _ in batch])

    return results


async def embed_documents_async(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """Asynchronous batch document embedding with 'search_document: ' prefix."""
    if not texts:
        return []

    results: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        prefixed_batch = [f"search_document: {t.strip()}" if t and t.strip() else "search_document: empty" for t in batch]
        try:
            embeddings = await _async_call_ollama_embed(prefixed_batch)
            results.extend(embeddings)
        except Exception as e:
            logger.warning(f"[embed_documents_async] Batch failed: {e}")
            results.extend([[0.0] * EMBEDDING_DIM for _ in batch])

    return results


async def embed_query(text: str) -> List[float]:
    """
    Embeds a single search query using nomic-embed-text via local Ollama.
    Prefixes query with 'search_query: ' for optimal nomic retrieval.
    Safe: Never raises ConnectError; returns empty list on failure so search gracefully falls back to keyword matching.
    """
    clean = text.strip() if text else ""
    if not clean:
        return [0.0] * EMBEDDING_DIM

    prefixed = f"search_query: {clean}"
    try:
        embeddings = await _async_call_ollama_embed([prefixed])
        return embeddings[0]
    except Exception as e:
        logger.warning(f"[embed_query] Local Ollama embed unavailable ({e}). Continuing with keyword retrieval.")
        return []


def embed_query_sync(text: str) -> List[float]:
    """Synchronous single query embedding with 'search_query: ' prefix."""
    clean = text.strip() if text else ""
    if not clean:
        return [0.0] * EMBEDDING_DIM

    prefixed = f"search_query: {clean}"
    try:
        embeddings = _call_ollama_embed([prefixed])
        return embeddings[0]
    except Exception as e:
        logger.warning(f"[embed_query_sync] Local Ollama embed unavailable ({e}).")
        return []


def embed_record(record_or_text: Any) -> List[float]:
    """Generates local 768-d embedding for a document or text string."""
    if isinstance(record_or_text, dict):
        text = build_record_text(record_or_text)
    else:
        text = str(record_or_text)
    if not text:
        return [0.0] * EMBEDDING_DIM
    prefixed = f"search_document: {text}"
    embeddings = _call_ollama_embed([prefixed])
    return embeddings[0]


generate_local_embedding = embed_record


def strip_embedding(obj: Any) -> Any:
    """
    Recursively and thoroughly strips the 'embedding' key from documents, dicts, and lists.
    Guarantees embedding vectors are NEVER exposed in responses, UI, or exports.
    """
    if isinstance(obj, dict):
        return {k: strip_embedding(v) for k, v in obj.items() if k != "embedding"}
    if isinstance(obj, list):
        return [strip_embedding(item) for item in obj]
    return obj


async def embed_dataset_records_background(dataset_id: str, batch_size: int = 32) -> Dict[str, Any]:
    """
    Background job to embed newly uploaded records belonging to dataset_id in batches of 32.
    If Ollama is offline or unavailable, marks records 'pending' without crashing or blocking.
    """
    from pymongo import UpdateOne

    try:
        db = get_database()
        col = db["dataset_records"]
    except Exception as db_err:
        logger.warning(f"[Embedding Background] Database unavailable: {db_err}")
        return {"status": "error", "count": 0}

    if not is_ollama_available():
        count = col.count_documents({"dataset_id": dataset_id, "embedding_status": "pending"})
        print(f"[Embedding] Ollama unavailable, {count} pending")
        return {"status": "pending", "count": count}

    query = {
        "dataset_id": dataset_id,
        "$or": [
            {"embedding": {"$exists": False}},
            {"embedding": None},
            {"embedding_status": "pending"},
            {"$expr": {"$ne": [{"$size": {"$ifNull": ["$embedding", []]}}, EMBEDDING_DIM]}}
        ]
    }
    docs = list(col.find(query, {"_id": 1, "company": 1, "person": 1, "designation": 1, "location": 1, "data": 1, "raw_data": 1, "search_text": 1}))
    if not docs:
        return {"status": "completed", "count": 0}

    embedded_count = 0
    for i in range(0, len(docs), batch_size):
        batch_docs = docs[i : i + batch_size]
        texts = [build_record_text(d) for d in batch_docs]
        try:
            embeddings = await embed_documents_async(texts, batch_size=batch_size)
            updates = [
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": emb, "embedding_status": "completed"}}
                )
                for doc, emb in zip(batch_docs, embeddings)
            ]
            if updates:
                col.bulk_write(updates, ordered=False)
                embedded_count += len(updates)
        except Exception as err:
            logger.warning(f"[Embedding] Batch embedding error: {err}")
            col.update_many(
                {"_id": {"$in": [d["_id"] for d in batch_docs]}},
                {"$set": {"embedding_status": "pending"}}
            )

    print(f"[Embedding] Successfully embedded {embedded_count} records for dataset '{dataset_id}'")
    return {"status": "completed", "count": embedded_count}


async def backfill_missing_embeddings_job(batch_size: int = 32) -> Dict[str, Any]:
    """
    Periodic background job to find records with missing embedding (or length not 768, or status pending)
    and embed them in batches of 32.
    Logs count format: '[Embedding] backfill: embedded=X remaining=Y'
    """
    from pymongo import UpdateOne

    if not is_ollama_available():
        return {"embedded": 0, "remaining": 0}

    try:
        db = get_database()
        col = db["dataset_records"]
    except Exception:
        return {"embedded": 0, "remaining": 0}

    query = {
        "$or": [
            {"embedding": {"$exists": False}},
            {"embedding": None},
            {"embedding_status": "pending"},
            {"$expr": {"$ne": [{"$size": {"$ifNull": ["$embedding", []]}}, EMBEDDING_DIM]}}
        ]
    }
    total_pending = col.count_documents(query)
    if total_pending == 0:
        return {"embedded": 0, "remaining": 0}

    docs = list(col.find(query, {"_id": 1, "company": 1, "person": 1, "designation": 1, "location": 1, "data": 1, "raw_data": 1, "search_text": 1}).limit(320))
    embedded = 0
    for i in range(0, len(docs), batch_size):
        batch_docs = docs[i : i + batch_size]
        texts = [build_record_text(d) for d in batch_docs]
        try:
            embeddings = await embed_documents_async(texts, batch_size=batch_size)
            updates = [
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"embedding": emb, "embedding_status": "completed"}}
                )
                for doc, emb in zip(batch_docs, embeddings)
            ]
            if updates:
                col.bulk_write(updates, ordered=False)
                embedded += len(updates)
        except Exception as err:
            logger.warning(f"[Embedding Backfill Error] {err}")
            break

    remaining = max(0, total_pending - embedded)
    print(f"[Embedding] backfill: embedded={embedded} remaining={remaining}")
    return {"embedded": embedded, "remaining": remaining}
