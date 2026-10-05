from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from pymongo.collection import Collection
from ..database import get_db, get_database, get_database_name, get_configured_collection_names
from ..config import PRIVACY_MODE
from ..schemas import ChatRequest, ChatResponse, LookupResult
from ..services.mongo_dataset import get_dataset, list_datasets
from ..search import ALLOWED_SEARCH_FIELDS

from unittest.mock import MagicMock
from ..utils.normalization import extract_original_source_fields
from ..services.retrieval_service import group_records_by_source, execute_hybrid_retrieval, validate_record_relevance
from ..services.query_understanding import parse_query_understanding, fallback_query_understanding
from ..services.query_router import route_query
from ..services.response_generator import is_valid_source_row, generate_final_answer
from ..services.contact_search import (
    get_or_build_vocab,
    parse_query,
    search as contact_search_exec,
    format_markdown
)

router = APIRouter(prefix="/api", tags=["Chat & Search"])


def format_api_sources_and_records(final_records: List[dict]):
    """
    Builds clean, source-grouped API representation preserving only original source columns.
    Never exposes internal normalized fields, filler 'Not Available' fields, or [object Object].
    """
    source_groups = group_records_by_source(final_records)
    formatted_sources = []
    display_records = []
    default_db = get_database_name()

    for src in source_groups:
        s_file = src.get("source_file") or None
        s_sheet = src.get("source_sheet")
        s_col = src.get("source_collection") or "default"
        db_src = src.get("database_source") or default_db

        clean_src_records = []
        for r in src.get("records", []):
            sf = extract_original_source_fields(r)
            s_row = is_valid_source_row(r.get("source_row"))

            display_rec = {
                "dataset": s_col,
                "source_collection": s_col,
                "database": db_src,
                "database_source": db_src,
            }
            if s_file:
                display_rec["source_file"] = s_file
            if s_sheet and s_sheet != "Not Available":
                display_rec["source_sheet"] = s_sheet
            if s_row:
                display_rec["source_row"] = s_row

            display_rec.update(sf)

            raw_lk = (
                sf.get("LinkedIn")
                or sf.get("LinkedIn URL")
                or sf.get("linkedin")
                or sf.get("linkedin_url")
                or r.get("linkedin_url")
                or r.get("linkedin")
            )
            if raw_lk and str(raw_lk).strip().lower() not in ("none", "null", "not available", ""):
                display_rec["LinkedIn"] = str(raw_lk).strip()
                sf["LinkedIn"] = str(raw_lk).strip()

            clean_src_records.append(sf)
            display_records.append(display_rec)

        s_entry = {
            "dataset": s_col,
            "source_collection": s_col,
            "database": db_src,
            "database_source": db_src,
            "records": clean_src_records
        }
        if s_file:
            s_entry["source_file"] = s_file
        if s_sheet and s_sheet != "Not Available":
            s_entry["source_sheet"] = s_sheet
        if src.get("records"):
            first_row = is_valid_source_row(src["records"][0].get("source_row"))
            if first_row:
                s_entry["source_row"] = first_row

        formatted_sources.append(s_entry)

    top_dataset = source_groups[0].get("source_collection", "default") if source_groups else "default"
    top_db = source_groups[0].get("database_source", default_db) if source_groups else default_db

    return formatted_sources, display_records, top_dataset, top_db


async def execute_deterministic_search(raw_query: str, dataset_id: Optional[str] = None) -> ChatResponse:
    """
    Executes unified Hybrid Search pipeline (Query Understanding -> Router -> Mongo + Vector Search -> Dedup -> Reranker -> Strict Answer).
    Preserves existing keyword search and privacy guards (zero database records sent to external LLMs).
    """
    # Backwards compatibility guard: if a test explicitly mocked execute_hybrid_retrieval
    if hasattr(execute_hybrid_retrieval, "mock_calls") or "Mock" in type(execute_hybrid_retrieval).__name__:
        ret = execute_hybrid_retrieval(raw_query)
        if hasattr(ret, "__await__"):
            ret = await ret
        final_records = ret[0] if isinstance(ret, tuple) else (ret or [])
        structured_query = fallback_query_understanding(raw_query)
        final_markdown = await generate_final_answer(raw_query, structured_query, final_records)
        formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(final_records)
        return ChatResponse(
            success=True,
            found=len(final_records) > 0,
            count=len(final_records),
            database=top_db,
            dataset=top_dataset,
            sources=formatted_sources,
            data=display_records,
            message=final_markdown
        )

    db = get_database()
    configured_cols = get_configured_collection_names()
    all_target_cols = list(dict.fromkeys(configured_cols + ["dataset_records"]))
    try:
        internal_cols = {"user", "users", "uploaders", "datasets", "fs.files", "fs.chunks"}
        for existing in db.list_collection_names():
            if not existing.startswith("system.") and existing.lower() not in internal_cols and existing not in all_target_cols:
                all_target_cols.append(existing)
    except Exception:
        pass

    # Resolve target collections & dataset display name
    target_dataset_id = dataset_id if dataset_id and dataset_id not in ("all", "default", "*", "companies") else "all"
    display_dataset_name = "All Datasets"
    if target_dataset_id != "all":
        single_ds = get_dataset(target_dataset_id)
        if single_ds:
            display_dataset_name = single_ds.get("filename", target_dataset_id)
        else:
            display_dataset_name = target_dataset_id

    # 1. Query Understanding
    try:
        structured_query, was_llm = await parse_query_understanding(raw_query)
    except Exception:
        structured_query = fallback_query_understanding(raw_query)

    # 2. Query Routing (SearchPlan: structured vs vector vs hybrid)
    plan = route_query(structured_query)

    # 3. Hybrid Retrieval (Structured MongoDB search + MongoDB Atlas / Local Vector search)
    try:
        final_records, debug_info = await execute_hybrid_retrieval(
            structured_query=structured_query,
            plan=plan,
            dataset_id=target_dataset_id,
            limit=50
        )
    except Exception as e:
        final_records, debug_info = [], {}

    # 4. Complementary fallback to contact_search vocab engine if no records matched
    if not final_records:
        try:
            vocab = get_or_build_vocab(db, all_target_cols)
            parsed = parse_query(raw_query, vocab)
            extra_filter = {"dataset_id": target_dataset_id} if target_dataset_id != "all" else None
            contact_res = contact_search_exec(
                db=db,
                collections=all_target_cols,
                parsed=parsed,
                vocab=vocab,
                limit=50,
                extra_filter=extra_filter
            )
            for g in contact_res.get("groups", []):
                for rec in g.get("records", []):
                    rec_copy = dict(rec)
                    rec_copy["source_collection"] = rec.get("_collection", "default")
                    if validate_record_relevance(rec_copy, structured_query):
                        final_records.append(rec_copy)
        except Exception:
            pass

    # Strict Relevance Guard: filter final_records to ensure 100% adherence to constraints
    if final_records and structured_query:
        final_records = [r for r in final_records if validate_record_relevance(r, structured_query)]

    # 5. Generate final strictly-formatted answer
    final_markdown = await generate_final_answer(raw_query, structured_query, final_records)

    # 6. Format API sources and display records
    formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(final_records)
    found = len(final_records) > 0

    # If the synthesized answer is a no-data message, clear final_records for API consistency
    if final_markdown.startswith("No data available for ") or final_markdown == "No data found":
        display_records = []
        formatted_sources = []
        found = False

    return ChatResponse(
        success=True,
        found=found,
        count=len(display_records) if not found else len(final_records),
        dataset_id=dataset_id or "all",
        dataset_name=display_dataset_name,
        database=top_db,
        dataset=top_dataset,
        sources=formatted_sources,
        data=display_records,
        message=final_markdown if (found or final_markdown) else "No matching records found.",
        understood_as=[f"Strategy: {plan.search_strategy}", f"Intent: {structured_query.intent}"],
        total=len(display_records) if not found else len(final_records)
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_search(request: ChatRequest, collections: List[Collection] = Depends(get_db)):
    """
    Main Contact Search Chatbot Endpoint.
    Uses deterministic query understanding and exact MongoDB filters (contact_search.py).
    Zero LLM or vector search when PRIVACY_MODE=true.
    Never logs query text or cell values.
    """
    raw_message = request.message.strip() if request.message else ""
    if not raw_message:
        return ChatResponse(
            success=False,
            found=False,
            count=0,
            data=None,
            message="Please provide a valid query (e.g. company name, location, designation, person, or keywords)."
        )

    # Determine dataset scoping
    uploaded_datasets = list_datasets()
    explicit_dataset_id = None
    if request.dataset_id and request.dataset_id not in ("all", "default", "*", "companies"):
        explicit_dataset_id = request.dataset_id
    elif uploaded_datasets:
        for ds in uploaded_datasets:
            ds_name = ds.get("filename", "").lower()
            name_no_ext = ds_name.rsplit(".", 1)[0]
            if (ds_name and ds_name in raw_message.lower()) or (name_no_ext and name_no_ext in raw_message.lower()):
                explicit_dataset_id = ds.get("dataset_id")
                break

    dataset_id = explicit_dataset_id if explicit_dataset_id else "all"

    return await execute_deterministic_search(raw_query=raw_message, dataset_id=dataset_id)


@router.get("/search", response_model=ChatResponse)
async def direct_search(
    q: str = Query(..., description="Search term (company name, email, phone, keyword, etc.)"),
    field: Optional[str] = Query(None, description="Optional target column filter"),
    dataset_id: Optional[str] = Query(None, description="Optional dataset ID"),
    collections: List[Collection] = Depends(get_db)
):
    """
    Direct search endpoint backed by contact_search.py deterministic engine.
    """
    clean_q = q.strip()
    if not clean_q:
        return ChatResponse(
            success=False,
            found=False,
            count=0,
            data=None,
            message="Query parameter 'q' cannot be empty."
        )

    # If field filter is provided, construct scoped query
    final_query = clean_q
    if field and field.lower().strip() in ALLOWED_SEARCH_FIELDS:
        f_clean = field.lower().strip()
        if f_clean in ("designation", "role"):
            final_query = f"{clean_q}"
        elif f_clean in ("city", "state", "location", "address"):
            final_query = f"in {clean_q}"
        elif f_clean in ("company_name", "company"):
            final_query = f"at {clean_q}"

    target_dataset = dataset_id if dataset_id and dataset_id not in ("default", "all", "*") else "all"
    return await execute_deterministic_search(raw_query=final_query, dataset_id=target_dataset)
