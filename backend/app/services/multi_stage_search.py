import os
import re
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from threading import Lock

import rapidfuzz
from rapidfuzz import process, fuzz
from bson import ObjectId

from ..database import get_database, get_configured_collection_names
from ..config import VECTOR_INDEX_NAME, RETRIEVE_K, FINAL_K, RRF_K, EMBEDDING_DIM
from ..services.embeddings import embed_query, strip_embedding
from ..utils.normalization import normalize_company

logger = logging.getLogger("calispec.multi_stage_search")

_NAME_CACHE_LOCK = Lock()
_COMPANY_NAME_CACHE: List[str] = []
_LAST_CACHE_TIME: float = 0
_CACHE_TTL: float = 600  # 10 minutes

VECTOR_SIMILARITY_THRESHOLD = 0.82


def extract_core_company_name(query: str) -> str:
    """Extracts core normalized company name from query string."""
    from ..services.query_understanding import clean_company_name
    from ..utils.normalization import normalize_company
    cleaned = clean_company_name(query)
    return normalize_company(cleaned)


def generate_query_variants(query: str) -> List[str]:
    """Generates acronym and space variants of a query string."""
    q = query.strip().lower()
    variants = [q]
    if len(q) <= 4 and " " not in q:
        spaced = " ".join(list(q))
        variants.append(spaced)
    elif len(q) <= 7 and " " in q and all(len(p) == 1 for p in q.split()):
        collapsed = q.replace(" ", "")
        variants.append(collapsed)
    return list(dict.fromkeys(variants))


def _calculate_fuzzy_score(query: str, target: str) -> float:
    """Calculates rapidfuzz ratio score between two strings."""
    return float(fuzz.ratio(query.lower().strip(), target.lower().strip()))


def get_cached_company_names() -> List[str]:
    """Returns in-memory cached distinct company names from database."""
    global _COMPANY_NAME_CACHE, _LAST_CACHE_TIME
    with _NAME_CACHE_LOCK:
        if not _COMPANY_NAME_CACHE or (time.time() - _LAST_CACHE_TIME > _CACHE_TTL):
            _build_company_name_cache()
        return list(_COMPANY_NAME_CACHE)


def refresh_company_name_cache() -> None:
    """Forces rebuild of company names cache (e.g. after upload)."""
    with _NAME_CACHE_LOCK:
        _build_company_name_cache()


def _build_company_name_cache() -> None:
    """Internal builder of unique normalized company names for Did You Mean."""
    global _COMPANY_NAME_CACHE, _LAST_CACHE_TIME
    try:
        db = get_database()
        cols = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))
        names_set: Set[str] = set()

        for c_name in cols:
            try:
                norm_vals = db[c_name].distinct("norm_company")
                for v in norm_vals:
                    if v and len(str(v).strip()) >= 2:
                        names_set.add(str(v).strip().lower())

                raw_vals = db[c_name].distinct("company")
                for v in raw_vals:
                    if v and len(str(v).strip()) >= 2:
                        n = normalize_company(str(v).strip())
                        if n and len(n) >= 2:
                            names_set.add(n)
            except Exception as e:
                logger.warning(f"Error caching company names from {c_name}: {e}")

        _COMPANY_NAME_CACHE = sorted([n for n in names_set if len(n) >= 2])
        _LAST_CACHE_TIME = time.time()
        logger.info(f"Loaded {len(_COMPANY_NAME_CACHE)} unique company names into memory cache.")
    except Exception as e:
        logger.error(f"Failed to build company name cache: {e}")


def execute_keyword_company_search(
    db,
    collections: List[str],
    raw_name: str,
    target_dataset: str = "all"
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Step 3A: Complete keyword retrieval on norm_company (fallback to company fields if norm_company empty).
    - Exact (Stage A)
    - Starts-with N then space or end (Stage B)
    - Whole-word phrase inside (Stage C)
    - All tokens as whole words (Stage D, only when N has 2+ tokens)
    - Short acronyms (<= 3 chars): whole-word match ONLY.
    - Strict deduplication by str(_id) immediately upon combining, BEFORE counting, filtering, or returning.
    """
    n_norm = normalize_company(raw_name)
    if not n_norm:
        return [], {"A": 0, "B": 0, "C": 0, "D": 0}

    tokens = [t for t in n_norm.split() if len(t) >= 1]
    stage_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    seen_ids = set()
    raw_records: List[Dict[str, Any]] = []

    def run_query(query_filter: Dict[str, Any], stage_label: str, stage_key: str):
        if target_dataset != "all":
            query_filter["dataset_id"] = target_dataset
        for c_name in collections:
            try:
                cursor = db[c_name].find(query_filter, {"embedding": 0}).limit(1000)
                for doc in cursor:
                    doc_id = str(doc.get("_id") or doc.get("id"))
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        doc["source_collection"] = c_name
                        doc["stage"] = stage_label
                        doc["_id"] = doc_id
                        raw_records.append(doc)
                        stage_counts[stage_key] += 1
            except Exception as e:
                logger.warning(f"Keyword search error in {c_name} for {stage_label}: {e}")

    # Case 1: Short acronyms (<= 3 characters, e.g. tvs, bhel, hvf)
    if len(n_norm) <= 3:
        word_regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"
        q = {
            "$or": [
                {"norm_company": {"$regex": word_regex, "$options": "i"}},
                {"$and": [
                    {"norm_company": {"$in": [None, ""]}},
                    {"company": {"$regex": word_regex, "$options": "i"}}
                ]}
            ]
        }
        run_query(q, "Stage C (Whole-Word Acronym)", "C")
    else:
        # Case 2: Standard company names (> 3 characters)
        # Stage A: Exact
        exact_regex = f"^{re.escape(n_norm)}$"
        q_a = {
            "$or": [
                {"norm_company": n_norm},
                {"norm_company": {"$regex": exact_regex, "$options": "i"}},
                {"$and": [
                    {"norm_company": {"$in": [None, ""]}},
                    {"company": {"$regex": exact_regex, "$options": "i"}}
                ]}
            ]
        }
        run_query(q_a, "Stage A (Exact)", "A")

        # Stage B: Starts-with
        start_regex = f"^{re.escape(n_norm)}(\\s|$)"
        q_b = {
            "$or": [
                {"norm_company": {"$regex": start_regex, "$options": "i"}},
                {"$and": [
                    {"norm_company": {"$in": [None, ""]}},
                    {"company": {"$regex": start_regex, "$options": "i"}}
                ]}
            ]
        }
        run_query(q_b, "Stage B (Starts-With)", "B")

        # Stage C: Whole-word phrase inside
        word_regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"
        q_c = {
            "$or": [
                {"norm_company": {"$regex": word_regex, "$options": "i"}},
                {"$and": [
                    {"norm_company": {"$in": [None, ""]}},
                    {"company": {"$regex": word_regex, "$options": "i"}}
                ]}
            ]
        }
        run_query(q_c, "Stage C (Whole-Word Phrase)", "C")

        # Stage D: All tokens as whole words (only when 2+ tokens)
        if len(tokens) >= 2:
            token_ands = [
                {"norm_company": {"$regex": rf"(^|\s){re.escape(t)}(\s|$)", "$options": "i"}}
                for t in tokens
            ]
            token_ands_fallback = [
                {"company": {"$regex": rf"(^|\s){re.escape(t)}(\s|$)", "$options": "i"}}
                for t in tokens
            ]
            q_d = {
                "$or": [
                    {"$and": token_ands},
                    {"$and": [
                        {"norm_company": {"$in": [None, ""]}},
                        {"$and": token_ands_fallback}
                    ]}
                ]
            }
            run_query(q_d, "Stage D (All Tokens Whole-Word)", "D")

    # Final immediate deduplication by str(_id)
    deduped_records: List[Dict[str, Any]] = []
    final_seen = set()
    for r in raw_records:
        rid = str(r.get("_id") or r.get("id"))
        if rid not in final_seen:
            final_seen.add(rid)
            deduped_records.append(r)

    return deduped_records, stage_counts


async def execute_vector_retrieval(
    db,
    original_query: str,
    target_dataset: str = "all",
    city_filter: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]], bool]:
    """
    Step 3B: Runs nomic-embed-text Vector Search with "search_query: " prefix.
    numCandidates=200, limit=30.
    Projects score via {"score": {"$meta": "vectorSearchScore"}}.
    Retries without filter if 0 results returned.
    Logs top 5 scores and company name + _id for top 10 hits.
    Returns (kept_vector_records, fallback_used, raw_vector_records, retried_without_filter).
    """
    query_text = original_query.strip()
    if not query_text:
        return [], False, [], False

    # Prefix query for nomic-embed-text
    formatted_query = f"search_query: {query_text}"
    try:
        query_vector = await embed_query(formatted_query)
    except Exception as e:
        logger.warning(f"[Vector Search] Could not generate embedding: {e}")
        query_vector = []

    if not query_vector or len(query_vector) != EMBEDDING_DIM:
        logger.warning("[Vector Search EMPTY] Could not generate embedding. Falling back to keyword search.")
        return [], True, [], False

    collections = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))
    raw_vector_records = []
    seen_ids = set()
    fallback_used = False
    retried_without_filter = False

    search_filter: Dict[str, Any] = {}
    if target_dataset != "all":
        search_filter["dataset_id"] = {"$eq": target_dataset}
    if city_filter:
        search_filter["city"] = {"$regex": city_filter, "$options": "i"}

    for c_name in collections:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_INDEX_NAME,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": 200,
                    "limit": 30,
                    **({"filter": search_filter} if search_filter else {})
                }
            },
            {
                "$project": {
                    "embedding": 0,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]

        try:
            cursor = db[c_name].aggregate(pipeline)
            docs = list(cursor)
            if not docs and search_filter:
                retried_without_filter = True
                logger.info(f"[Vector Search] 0 hits with filter, retrying without filter in {c_name}...")
                pipeline_no_filter = [
                    {
                        "$vectorSearch": {
                            "index": VECTOR_INDEX_NAME,
                            "path": "embedding",
                            "queryVector": query_vector,
                            "numCandidates": 200,
                            "limit": 30
                        }
                    },
                    {
                        "$project": {
                            "embedding": 0,
                            "score": {"$meta": "vectorSearchScore"}
                        }
                    }
                ]
                cursor = db[c_name].aggregate(pipeline_no_filter)
                docs = list(cursor)

            for d in docs:
                d_id = str(d.get("_id") or d.get("id"))
                raw_score = d.get("score")
                if raw_score is None:
                    logger.warning(f"[Vector Search BUG] Missing vectorSearchScore on document {d_id}")
                    score = 1.0
                else:
                    score = float(raw_score)

                if d_id not in seen_ids:
                    seen_ids.add(d_id)
                    d["source_collection"] = c_name
                    d["_id"] = d_id
                    d["vector_score"] = score
                    d["stage"] = "Vector ($vectorSearch)"
                    raw_vector_records.append(d)

        except Exception as e:
            logger.warning(f"[Vector Search ERROR] {type(e).__name__}: {e}")
            fallback_used = True

    # Sort all raw vector hits descending by score
    raw_vector_records.sort(key=lambda x: x.get("vector_score", 0.0), reverse=True)
    top_scores = [round(r.get("vector_score", 0.0), 4) for r in raw_vector_records[:5]]
    top_10_log = [
        {"_id": str(r.get("_id", "")), "company": str(r.get("company", "") or r.get("Company", "")), "score": round(r.get("vector_score", 0.0), 4)}
        for r in raw_vector_records[:10]
    ]
    logger.info(f"[Vector Search] Top 5 scores for '{query_text}': {top_scores} | Top 10 hits: {top_10_log}")

    # Threshold filtering
    kept_vector_records = [
        r for r in raw_vector_records
        if r.get("vector_score", 0.0) >= VECTOR_SIMILARITY_THRESHOLD
    ]
    dropped_count = len(raw_vector_records) - len(kept_vector_records)
    logger.info(f"[Vector Search] Total raw hits: {len(raw_vector_records)}, Passing threshold (>= {VECTOR_SIMILARITY_THRESHOLD}): {len(kept_vector_records)}, Dropped: {dropped_count}")

    return kept_vector_records, fallback_used, raw_vector_records, retried_without_filter


def get_did_you_mean_suggestions(core_name: str, limit: int = 3) -> List[str]:
    """
    Step 3: RapidFuzz score >= 85 on cached distinct company names for 0-result queries.
    """
    if not core_name or len(core_name) < 2:
        return []

    cached_names = get_cached_company_names()
    if not cached_names:
        return []

    q_lower = normalize_company(core_name)
    matches = process.extract(
        q_lower,
        cached_names,
        scorer=fuzz.ratio,
        limit=limit,
        score_cutoff=85.0
    )
    return [m[0].title() for m in matches]


async def execute_multi_stage_retrieval(
    raw_query: str,
    target_dataset: str = "all",
    city_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Step 3 Hybrid Retrieval:
    - Runs Keyword (Stage A-D) and Vector retrieval in parallel.
    - Merges with RRF (k=60), boosting keyword exact/phrase matches.
    - Keyword matches are the authoritative main list.
    - Vector-only hits that pass the threshold form a separate 'Related results' list.
    - Never replace, hide, or mix vector hits into keyword list.
    """
    t0 = time.time()
    db = get_database()
    collections = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))

    # 1. Run Keyword and Vector searches in parallel
    keyword_future = asyncio.to_thread(
        execute_keyword_company_search,
        db=db,
        collections=collections,
        raw_name=raw_query,
        target_dataset=target_dataset
    )
    vector_future = execute_vector_retrieval(
        db=db,
        original_query=raw_query,
        target_dataset=target_dataset,
        city_filter=city_filter
    )

    (keyword_records, stage_counts), (vector_records, fallback_used, raw_vector_records, retried_no_filter) = await asyncio.gather(
        keyword_future,
        vector_future
    )

    keyword_ids = {str(r.get("_id") or r.get("id")) for r in keyword_records}
    vector_only_records = [
        r for r in vector_records
        if str(r.get("_id") or r.get("id")) not in keyword_ids
    ]

    from ..services.response_generator import extract_company_name
    from ..utils.normalization import is_company_match

    filtered_kw = [r for r in keyword_records if is_company_match(raw_query, extract_company_name(r))]
    filtered_vec = [r for r in vector_records if is_company_match(raw_query, extract_company_name(r))]

    if filtered_kw:
        final_records = filtered_kw
    elif filtered_vec:
        final_records = filtered_vec
    else:
        final_records = []

    # Suggestions if 0 valid matches
    suggestions = []
    if not final_records:
        suggestions = get_did_you_mean_suggestions(raw_query)

    elapsed_ms = int((time.time() - t0) * 1000)
    logger.info(
        f"[RAG] tasks=1 keyword={len(keyword_records)} vector={len(vector_records)} "
        f"total={len(final_records)} fallback={'yes' if fallback_used else 'no'} {elapsed_ms}ms"
    )

    top_vector_scores = [r.get("vector_score", 0.0) for r in raw_vector_records[:10]]

    return {
        "records": final_records,
        "keyword_records": keyword_records,
        "vector_records": vector_records,
        "raw_vector_records": raw_vector_records,
        "vector_only_records": vector_only_records,
        "top_vector_scores": top_vector_scores,
        "stages": {**stage_counts, "vector": len(vector_records)},
        "keyword_hits": len(keyword_records),
        "vector_hits": len(vector_records),
        "vector_hits_raw": len(raw_vector_records),
        "vector_fallback_used": fallback_used,
        "filter_retried_without_filter": retried_no_filter,
        "suggestions": suggestions,
        "fallback_used": fallback_used,
        "latency_ms": elapsed_ms
    }
