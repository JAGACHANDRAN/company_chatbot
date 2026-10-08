"""
MongoDB Atlas Vector Search Service.
Executes $vectorSearch with local Ollama query embeddings (nomic-embed-text 768-d).
Falls back to in-memory cosine similarity if Atlas search index is unavailable.
"""
import math
import logging
from typing import List, Dict, Any, Optional, Tuple

from ..config import (
    VECTOR_INDEX_NAME,
    EMBEDDING_DIM,
    NUM_CANDIDATES,
    RETRIEVE_K,
    COLLECTION_NAME,
)
from .embeddings import embed_query, build_record_text, embed_record
from ..database import get_database, get_collections
from ..utils.normalization import normalize_record_fields

logger = logging.getLogger("calispec.vector_search")


# Backwards compatibility aliases
build_record_search_text = build_record_text
generate_local_embedding = embed_record
VECTOR_DIMENSIONS = EMBEDDING_DIM


async def get_embedding(text: str) -> List[float]:
    """Alias for embed_query for backwards compatibility."""
    return await embed_query(text)

# Global tracking for health check reporting
FALLBACK_USED_RECENTLY: bool = False


def get_fallback_used_recently() -> bool:
    """Returns whether the in-memory fallback was triggered recently."""
    global FALLBACK_USED_RECENTLY
    return FALLBACK_USED_RECENTLY


def reset_fallback_flag() -> None:
    """Resets the fallback tracking flag."""
    global FALLBACK_USED_RECENTLY
    FALLBACK_USED_RECENTLY = False


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_atlas_vector_filter(
    city: Optional[str] = None,
    company: Optional[str] = None,
    companies: Optional[List[str]] = None,
    dataset_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Constructs an Atlas $vectorSearch filter object using declared filter paths:
    'city', 'dataset_id'.
    Note: Exact $eq on company is avoided here because vector search is semantic,
    and partial entity queries (e.g. 'TVS') would otherwise be blocked by $eq from
    matching 'TVS MOTORS', 'Delphi TVS', etc.
    """
    filter_clauses = []

    if city and city.strip():
        filter_clauses.append({"city": {"$eq": city.strip()}})

    if dataset_id and dataset_id not in ("all", "*", "default", None):
        filter_clauses.append({"dataset_id": {"$eq": dataset_id.strip()}})

    if not filter_clauses:
        return None
    if len(filter_clauses) == 1:
        return filter_clauses[0]
    return {"$and": filter_clauses}


async def execute_vector_search(
    query_text: str,
    dataset_id: Optional[str] = "all",
    city: Optional[str] = None,
    company: Optional[str] = None,
    companies: Optional[List[str]] = None,
    limit: int = RETRIEVE_K,
    num_candidates: int = NUM_CANDIDATES,
    min_similarity: float = 0.15
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Executes Atlas $vectorSearch on dataset_records.
    1. Embeds the user query via local nomic-embed-text (768-d).
    2. Runs MongoDB Atlas $vectorSearch aggregation pipeline with declared filters.
    3. Projects out 'embedding' field and includes 'score' ($meta: vectorSearchScore).
    4. Falls back to in-memory cosine if $vectorSearch is unavailable, logging a warning.

    Returns:
      (results: List[Dict[str, Any]], fallback_used: bool)
    """
    global FALLBACK_USED_RECENTLY

    clean_query = query_text.strip() if query_text else ""
    if not clean_query:
        return [], False

    query_embedding = await embed_query(clean_query)
    if not query_embedding or len(query_embedding) != EMBEDDING_DIM:
        logger.warning(f"[Vector Search] Invalid query embedding generated: {len(query_embedding)}d")
        return [], False

    db = get_database()
    col = db[COLLECTION_NAME]
    results: List[Dict[str, Any]] = []
    fallback_used = False

    # 1. Attempt Atlas $vectorSearch aggregation pipeline
    atlas_filter = build_atlas_vector_filter(
        city=city,
        company=company,
        companies=companies,
        dataset_id=dataset_id
    )

    def _run_pipeline(filter_obj: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        spec: Dict[str, Any] = {
            "index": VECTOR_INDEX_NAME,
            "path": "embedding",
            "queryVector": query_embedding,
            "numCandidates": max(num_candidates, limit * 2),
            "limit": limit
        }
        if filter_obj:
            spec["filter"] = filter_obj
        pipeline = [
            {"$vectorSearch": spec},
            {
                "$project": {
                    "embedding": 0,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        docs = []
        for doc in col.aggregate(pipeline):
            norm_rec = normalize_record_fields(doc)
            norm_rec["_id"] = str(doc.get("_id", ""))
            norm_rec["company"] = norm_rec.get("company_name") or doc.get("company")
            norm_rec["person"] = norm_rec.get("person_name") or doc.get("person")
            norm_rec["phone"] = norm_rec.get("contact_number") or doc.get("phone")
            norm_rec["email"] = norm_rec.get("personal_mail_id") or doc.get("email")
            norm_rec["city"] = norm_rec.get("city") or doc.get("city") or doc.get("location")
            norm_rec["retrieval_score"] = float(doc.get("score", 0.0))
            docs.append(norm_rec)
        return docs

    try:
        results = _run_pipeline(atlas_filter)
        if not results:
            logger.warning(f"[Vector Search EMPTY] filter={atlas_filter} index={VECTOR_INDEX_NAME}")
            # Retry ONCE without filter before falling back if a filter was originally applied
            if atlas_filter is not None:
                try:
                    retry_results = _run_pipeline(None)
                    if retry_results:
                        results = retry_results
                    else:
                        logger.warning(f"[Vector Search EMPTY] filter=None index={VECTOR_INDEX_NAME}")
                except Exception as retry_err:
                    logger.error(
                        f"[Vector Search ERROR] {type(retry_err).__name__}: {retry_err} (index={VECTOR_INDEX_NAME}, filter=None)"
                    )
    except Exception as vs_err:
        logger.error(
            f"[Vector Search ERROR] {type(vs_err).__name__}: {vs_err} (index={VECTOR_INDEX_NAME}, filter={atlas_filter})"
        )
        results = []

    # 2. Only if both fail, use the in-memory fallback and log "[Vector Search Fallback]"
    if not results:
        fallback_used = True
        FALLBACK_USED_RECENTLY = True
        logger.warning(f"[Vector Search Fallback]")

        sample_query: Dict[str, Any] = {"embedding": {"$exists": True, "$ne": None}}
        if dataset_id and dataset_id not in ("all", "*", "default", None):
            sample_query["dataset_id"] = dataset_id

        scored = []
        try:
            cursor = col.find(sample_query, {"embedding": 1, "company": 1, "person": 1, "designation": 1, "location": 1, "city": 1, "phone": 1, "email": 1, "data": 1, "normalized_data": 1, "raw_data": 1, "source_file": 1}).limit(300)
            for doc in cursor:
                rec_emb = doc.get("embedding")
                if rec_emb and isinstance(rec_emb, list) and len(rec_emb) == EMBEDDING_DIM:
                    sim = cosine_similarity(query_embedding, rec_emb)
                    if sim >= min_similarity:
                        norm_rec = normalize_record_fields(doc)
                        norm_rec["_id"] = str(doc.get("_id", ""))
                        norm_rec["retrieval_score"] = sim
                        scored.append((sim, norm_rec))
        except Exception as fb_err:
            logger.error(f"[Vector Search Fallback Error] In-memory scan failed: {fb_err}")

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]

    return results, fallback_used
