import json
from typing import List, Dict, Any, Optional, Tuple
from .query_understanding import StructuredQuery
from .query_router import SearchPlan, route_query
from .mongo_search import execute_structured_search
from .vector_search import execute_vector_search
from ..utils.deduplication import deduplicate_records
from ..utils.normalization import (
    is_company_match,
    is_person_match,
    normalize_location_string,
    normalize_text,
)
from .reranker import rerank_records


def validate_record_relevance(
    record: Dict[str, Any],
    structured_query: StructuredQuery,
    plan: Optional[SearchPlan] = None
) -> bool:
    """
    RESULT RELEVANCE GUARD:
    Guarantees that records meet hard user constraints before proceeding.
    1. Explicit company query: record must match requested company (is_company_match).
       Rejects unrelated companies (e.g. ACCUMEN AUTOMATION for 2D INC).
    2. Explicit person query: record must match requested person (is_person_match).
    3. Location constraint: record must belong to requested state/city (hard filter).
    4. Hybrid constraints: department/role filter.
    """
    raw = record.get("raw_data") or {}

    # 1. Company constraint (Hard filter for exact and multi-entity queries)
    if structured_query.companies:
        rec_comp = record.get("company_name") or raw.get("Company Name") or raw.get("company_name") or ""
        matched = False
        for target_comp in structured_query.companies:
            if is_company_match(target_comp, rec_comp):
                matched = True
                break
        if not matched:
            return False

    # 2. Person constraint (Hard filter for person search)
    if structured_query.people:
        rec_person = (
            record.get("person_name")
            or raw.get("Contact Person")
            or raw.get("Person Name")
            or raw.get("name")
            or ""
        )
        matched = False
        for target_person in structured_query.people:
            if is_person_match(target_person, rec_person):
                matched = True
                break
        if not matched:
            return False

    # 3. Location constraint (Hard filter)
    # "A record from Karnataka must not appear simply because its vector similarity is high."
    if structured_query.state:
        target_state = normalize_location_string(structured_query.state)
        rec_state = normalize_location_string(record.get("state"))
        rec_loc = normalize_location_string(record.get("location"))
        rec_addr = normalize_location_string(record.get("address") or raw.get("Address") or raw.get("address") or "")
        raw_state = normalize_location_string(raw.get("State") or raw.get("state") or "")

        state_match = (
            target_state in rec_state
            or target_state in rec_loc
            or target_state in rec_addr
            or target_state in raw_state
        )
        if not state_match:
            return False

    if structured_query.city:
        target_city = normalize_location_string(structured_query.city)
        rec_city = normalize_location_string(record.get("city"))
        rec_loc = normalize_location_string(record.get("location"))
        rec_addr = normalize_location_string(raw.get("Address", ""))
        raw_city = normalize_location_string(raw.get("City", ""))
        city_match = (
            target_city in rec_city
            or target_city in rec_loc
            or target_city in rec_addr
            or target_city in raw_city
        )
        if not city_match:
            return False

    # 4. Department / Designation for hybrid queries
    if structured_query.department and (plan is None or plan.search_strategy == "hybrid"):
        target_dept = normalize_text(structured_query.department)
        rec_dept = normalize_text(record.get("department"))
        rec_desig = normalize_text(record.get("designation"))
        raw_desig = normalize_text(raw.get("Designation", ""))
        if target_dept not in rec_dept and target_dept not in rec_desig and target_dept not in raw_desig:
            return False

    return True


def group_records_by_source(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups retrieved records by source dataset/file/collection.
    Preserves original source fields without forcing into a single schema.
    Deduplicates only truly identical records within the same source.
    Returns:
    [
        {
            "database_source": "MongoDB Atlas",
            "source_collection": "metrology",
            "source_file": "metrology_5000.xlsx",
            "source_sheet": "Sheet1",  # or None
            "records": [...]
        },
        ...
    ]
    """
    from ..database import get_database_name
    default_db_name = get_database_name()
    groups_dict: Dict[Tuple[str, str, Optional[str], Optional[str]], Dict[str, Any]] = {}

    for r in records:
        db_src = r.get("database_source") or r.get("database") or default_db_name
        col = r.get("source_collection") or "default"
        # Only preserve genuine source file from an actual column or upload
        raw_s_file = r.get("source_file")
        if raw_s_file:
            s_clean = str(raw_s_file).strip()
            if s_clean.lower() in ("mongodb", "mongodb atlas", "dataset_records", "none", "not available", "null") or s_clean.startswith("MongoDB:"):
                f_name = None
            else:
                f_name = s_clean
        else:
            f_name = None

        sheet = r.get("source_sheet")

        group_key = (str(db_src), str(col), f_name, str(sheet) if sheet else None)
        if group_key not in groups_dict:
            groups_dict[group_key] = {
                "database_source": db_src,
                "source_collection": col,
                "source_file": f_name,
                "source_sheet": sheet,
                "records": [],
                "_seen_record_keys": set(),
            }

        raw = r.get("raw_data") or {}
        raw_fingerprint = tuple(sorted((str(k), str(v)) for k, v in raw.items() if v not in (None, "", "Not Available")))
        if not raw_fingerprint:
            raw_fingerprint = (str(r.get("id")), str(r.get("company_name")), str(r.get("person_name")))

        if raw_fingerprint not in groups_dict[group_key]["_seen_record_keys"]:
            groups_dict[group_key]["_seen_record_keys"].add(raw_fingerprint)
            groups_dict[group_key]["records"].append(r)

    result = []
    for g in groups_dict.values():
        del g["_seen_record_keys"]
        if g["records"]:
            result.append(g)
    return result


async def execute_hybrid_retrieval(
    structured_query: StructuredQuery,
    plan: Optional[SearchPlan] = None,
    dataset_id: Optional[str] = "all",
    limit: int = 50
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Executes end-to-end Hybrid Retrieval:
    1. Executes structured MongoDB search (if indicated by SearchPlan).
    2. Executes vector/semantic search (ONLY if indicated by SearchPlan).
    3. Merges results with STRICT RELEVANCE VALIDATION GUARD.
       Never permits unrelated records from vector similarity when an exact entity is queried.
    4. Deduplicates identical records while strictly PRESERVING source separation.
    5. Applies optional reranking.
    6. Groups records by source dataset/file/collection.
    
    Returns:
    (final_records: List[Dict[str, Any]], debug_info: Dict[str, Any])
    """
    if plan is None:
        plan = route_query(structured_query)

    user_query = structured_query.original_query
    exact_results: List[Dict[str, Any]] = []
    vector_results: List[Dict[str, Any]] = []

    # 1. Structured Search
    if plan.use_structured:
        try:
            exact_results = execute_structured_search(
                structured_query=structured_query,
                dataset_id=dataset_id,
                limit=limit
            )
        except Exception as e:
            print(f"[Retrieval Service Warning - Structured Search] {e}")
            exact_results = []

    # 2. Vector / Semantic Search (ONLY when plan indicates use_vector)
    # "For explicit exact company queries, vector search should NOT introduce unrelated records."
    # "Vector similarity must NEVER override an explicit exact filter."
    if plan.use_vector:
        vector_query = plan.semantic_query or user_query
        try:
            raw_vector_results = await execute_vector_search(
                query_text=vector_query,
                dataset_id=dataset_id,
                limit=limit
            )
            # Filter vector results with hard constraints
            vector_results = [
                r for r in raw_vector_results
                if validate_record_relevance(r, structured_query, plan)
            ]
        except Exception as e:
            print(f"[Retrieval Service Warning - Vector Search] {e}")
            vector_results = []

    # 3. Result Merging & Relevance Guard
    # Structured results take priority
    candidate_records: List[Dict[str, Any]] = []
    seen_ids = set()

    for r in exact_results:
        if validate_record_relevance(r, structured_query, plan):
            rid = f"{r.get('source_file')}::{r.get('id')}::{r.get('company_name')}::{r.get('person_name')}"
            if rid not in seen_ids:
                seen_ids.add(rid)
                candidate_records.append(r)

    for r in vector_results:
        if validate_record_relevance(r, structured_query, plan):
            rid = f"{r.get('source_file')}::{r.get('id')}::{r.get('company_name')}::{r.get('person_name')}"
            if rid not in seen_ids:
                seen_ids.add(rid)
                candidate_records.append(r)

    # 4. Deduplication: deduplicate identical records within the same source, preserving source separation
    deduped_results = deduplicate_records(candidate_records, preserve_source_separation=True)

    # 5. Reranking & Top-K Truncation
    final_results = rerank_records(
        records=deduped_results,
        structured_query=structured_query,
        original_query=user_query,
        top_k=limit
    )

    # 6. Source Grouping (Critical Requirement 2)
    source_groups = group_records_by_source(final_results)

    # 7. Structured Logging
    filters_used = {
        k: v for k, v in {
            "companies": structured_query.companies,
            "people": structured_query.people,
            "designation": structured_query.designation,
            "department": structured_query.department,
            "state": structured_query.state,
            "city": structured_query.city,
            "country": structured_query.country,
            "location": structured_query.location,
        }.items() if v
    }

    debug_info = {
        "user_query": user_query,
        "structured_query": structured_query.model_dump(),
        "search_type": plan.search_strategy,
        "filters_used": filters_used,
        "number_of_exact_results": len(exact_results),
        "number_of_vector_results": len(vector_results),
        "number_after_merging": len(candidate_records),
        "number_after_deduplication": len(deduped_results),
        "final_result_count": len(final_results),
        "sources": source_groups,
        "source_groups": source_groups,
    }

    # Console logging formatted cleanly
    print("=" * 60)
    print(f"QUERY:\n\"{user_query}\"")
    print(f"STRUCTURED QUERY:\n{json.dumps(filters_used, indent=2)}")
    print(f"SEARCH TYPE:\n{plan.search_strategy}")
    print(f"EXACT RESULTS:\n{len(exact_results)}")
    print(f"VECTOR RESULTS:\n{len(vector_results)}")
    print(f"MERGED:\n{len(candidate_records)}")
    print(f"DEDUPLICATED:\n{len(deduped_results)}")
    print(f"FINAL:\n{len(final_results)}")
    print(f"SOURCE GROUPS:\n{len(source_groups)}")
    print("=" * 60)

    return final_results, debug_info
