"""
Hybrid Retrieval Service.
Executes vector search ($vectorSearch) and structured MongoDB search in parallel,
merges results using Reciprocal Rank Fusion (k=60), and returns all matching and similar records.
"""
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple

from .query_understanding import StructuredQuery
from .query_router import SearchPlan, route_query
from .mongo_search import execute_structured_search
from .vector_search import execute_vector_search
from .reranker import reciprocal_rank_fusion
from ..utils.deduplication import deduplicate_records
from ..utils.normalization import (
    is_company_match,
    is_person_match,
    normalize_location_string,
    normalize_text,
)
from ..config import RETRIEVE_K, FINAL_K, RRF_K

logger = logging.getLogger("calispec.retrieval")


def validate_record_relevance(
    record: Dict[str, Any],
    structured_query: StructuredQuery,
    plan: Optional[SearchPlan] = None
) -> bool:
    """
    Guarantees that retrieved records satisfy explicit user constraints:
    - Target company match if explicit company requested (strict rejection of non-matching companies).
    - Target person match if explicit person requested.
    - Target location match if explicit city/state requested.
    - Availability filters (email_required, phone_required).
    - Missing filters (missing_filter).
    """
    from .response_generator import (
        extract_company_name,
        extract_person_info,
        extract_emails,
        extract_contact_numbers,
        extract_linkedin,
        extract_location
    )

    # 1. Company constraint (STRICT: Never return non-matching companies when company is specified)
    if structured_query.companies:
        rec_comp = extract_company_name(record)
        matched = False
        for target_comp in structured_query.companies:
            if is_company_match(target_comp, rec_comp):
                matched = True
                break
        if not matched:
            return False

    # 1b. Person constraint
    if structured_query.people:
        rec_person = extract_person_info(record).get("name") or ""
        matched_p = False
        for target_p in structured_query.people:
            if is_person_match(target_p, rec_person):
                matched_p = True
                break
        if not matched_p:
            return False

    # 2. Location constraint
    if structured_query.city:
        target_city = normalize_location_string(structured_query.city)
        rec_loc = extract_location(record)
        rec_city = normalize_location_string(rec_loc.get("city") or "")
        if rec_city and target_city not in rec_city:
            return False

    # 3. Contact availability
    if structured_query.email_required is True:
        if not extract_emails(record):
            return False

    if structured_query.phone_required is True:
        if not extract_contact_numbers(record):
            return False

    if structured_query.linkedin_required is True:
        if not extract_linkedin(record):
            return False

    # 4. Missing field filters
    if structured_query.missing_filter == "email" and extract_emails(record):
        return False
    elif structured_query.missing_filter == "phone" and extract_contact_numbers(record):
        return False
    elif structured_query.missing_filter == "linkedin" and extract_linkedin(record):
        return False

    return True


def group_records_by_source(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Groups retrieved records by source file or dataset while preserving original columns."""
    groups_dict: Dict[Tuple[str, Optional[str], Optional[str]], Dict[str, Any]] = {}

    for r in records:
        s_file = r.get("source_file") or r.get("Source File") or r.get("Sources") or None
        s_sheet = r.get("sheet_name") or r.get("Source Sheet") or None
        d_name = r.get("dataset_name") or r.get("dataset_id") or r.get("source_collection") or "dataset_records"
        s_col = r.get("source_collection") or "dataset_records"
        key = (str(s_file), str(s_sheet), str(d_name))

        if key not in groups_dict:
            groups_dict[key] = {
                "source_file": s_file,
                "source_sheet": s_sheet,
                "dataset_name": d_name,
                "source_collection": s_col,
                "records": [],
                "_seen": set()
            }

        rec_id = str(r.get("_id") or f"{r.get('company')}::{r.get('person')}")
        if rec_id not in groups_dict[key]["_seen"]:
            groups_dict[key]["_seen"].add(rec_id)
            groups_dict[key]["records"].append(r)

    result = []
    for g in groups_dict.values():
        del g["_seen"]
        if g["records"]:
            result.append(g)
    return result


async def execute_hybrid_retrieval(
    structured_query: StructuredQuery,
    plan: Optional[SearchPlan] = None,
    dataset_id: Optional[str] = "all",
    limit: int = FINAL_K
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Executes Multi-Stage Hybrid Retrieval:
    1. Runs parallel 5-stage keyword search (Stages A to E) + nomic-embed-text Atlas Vector Search.
    2. Merges with Weighted Reciprocal Rank Fusion (k=60).
    3. Validates relevance constraints (company, person, location, availability).
    4. Provides 'Did you mean: ...?' suggestions on 0 matches.
    """
    t_start = time.time()
    if plan is None:
        plan = route_query(structured_query)

    user_query = structured_query.original_query
    from .multi_stage_search import execute_multi_stage_retrieval

    # Execute Multi-Stage Retrieval
    multi_res = await execute_multi_stage_retrieval(
        raw_query=user_query,
        target_dataset=dataset_id or "all",
        city_filter=structured_query.city
    )

    retrieved_raw = multi_res.get("records", [])

    # Filter with relevance validation
    valid_records = [r for r in retrieved_raw if validate_record_relevance(r, structured_query, plan)]

    # If structured query has specific people or non-company constraints that multi_stage didn't capture,
    # fallback to structured search if valid_records is empty
    if not valid_records and (structured_query.people or structured_query.is_only_fields):
        try:
            struct_results = execute_structured_search(
                structured_query=structured_query,
                dataset_id=dataset_id,
                limit=max(RETRIEVE_K, limit)
            )
            for r in struct_results:
                if validate_record_relevance(r, structured_query, plan):
                    valid_records.append(r)
        except Exception as e:
            logger.warning(f"[Hybrid Retrieval] Structured fallback error: {e}")

    # Deduplicate and format records
    final_records = deduplicate_records(valid_records, preserve_source_separation=True)[:limit]
    source_groups = group_records_by_source(final_records)

    elapsed_ms = round((time.time() - t_start) * 1000, 2)
    logger.info(
        f"[Hybrid Retrieval] Strategy: {plan.search_strategy} | Stages: {multi_res.get('stages')} | "
        f"Retrieved: {len(final_records)} | Latency: {elapsed_ms}ms"
    )

    debug_info = {
        "search_strategy": plan.search_strategy,
        "stages": multi_res.get("stages", {}),
        "keyword_hits": multi_res.get("keyword_hits", 0),
        "vector_hits": multi_res.get("vector_hits", 0),
        "fallback_used": multi_res.get("fallback_used", False),
        "final_count": len(final_records),
        "suggestions": multi_res.get("suggestions", []),
        "latency_ms": elapsed_ms,
        "source_groups": source_groups
    }

    return final_records, debug_info
