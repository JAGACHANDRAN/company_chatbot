from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pymongo.collection import Collection
from ..database import get_db
from ..schemas import ChatRequest, ChatResponse, QueryIntent, LookupResult
from ..services.query_understanding import parse_query_understanding, fallback_query_understanding, StructuredQuery
from ..services.query_router import route_query
from ..services.retrieval_service import execute_hybrid_retrieval
from ..services.response_generator import generate_final_answer, is_valid_source_row
from ..services.mongo_dataset import get_dataset, list_datasets
from ..search import ALLOWED_SEARCH_FIELDS

from ..utils.normalization import extract_original_source_fields
from ..services.retrieval_service import group_records_by_source

router = APIRouter(prefix="/api", tags=["Chat & Search"])


def format_api_sources_and_records(final_records: List[dict]):
    """
    Builds clean, source-grouped API representation preserving only original source columns.
    Never exposes internal normalized fields, filler 'Not Available' fields, or [object Object].
    """
    source_groups = group_records_by_source(final_records)
    formatted_sources = []
    display_records = []

    for src in source_groups:
        s_file = src.get("source_file", "")
        s_sheet = src.get("source_sheet")
        s_col = src.get("source_collection", "dataset_records")
        db_src = src.get("database_source", "MongoDB Atlas")

        clean_src_records = []
        for r in src.get("records", []):
            sf = extract_original_source_fields(r)
            s_row = is_valid_source_row(r.get("source_row"))

            display_rec = {
                "dataset": s_col,
                "database": db_src,
                "source_file": s_file,
            }
            if s_sheet and s_sheet != "Not Available":
                display_rec["source_sheet"] = s_sheet
            if s_row:
                display_rec["source_row"] = s_row

            display_rec.update(sf)
            clean_src_records.append(sf)
            display_records.append(display_rec)

        s_entry = {
            "dataset": s_col,
            "database": db_src,
            "source_file": s_file,
            "records": clean_src_records
        }
        if s_sheet and s_sheet != "Not Available":
            s_entry["source_sheet"] = s_sheet
        if src.get("records"):
            first_row = is_valid_source_row(src["records"][0].get("source_row"))
            if first_row:
                s_entry["source_row"] = first_row

        formatted_sources.append(s_entry)

    top_dataset = source_groups[0].get("source_collection", "dataset_records") if source_groups else "dataset_records"
    top_db = source_groups[0].get("database_source", "MongoDB Atlas") if source_groups else "MongoDB Atlas"

    return formatted_sources, display_records, top_dataset, top_db


@router.post("/chat", response_model=ChatResponse)
async def chat_search(request: ChatRequest, collections: List[Collection] = Depends(get_db)):
    """
    Main RAG Chatbot Search Endpoint.
    
    ARCHITECTURE:
    USER -> React Chat UI -> FastAPI -> Query Understanding LLM -> Structured Query JSON
    -> Query Router -> Hybrid Retrieval (Structured MongoDB + Vector Search)
    -> Result Merging -> Deduplication -> Reranking -> Final Answer LLM -> User
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

    # 1. Determine dataset scoping if explicitly requested
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

    # Step 1: Query Understanding
    structured_query, was_parsed_by_llm = await parse_query_understanding(raw_message)

    # Step 2: Query Router
    search_plan = route_query(structured_query)

    # Step 3: Hybrid Retrieval (Structured MongoDB + Vector / Semantic + Merge + Deduplicate + Rerank)
    final_records, debug_info = await execute_hybrid_retrieval(
        structured_query=structured_query,
        plan=search_plan,
        dataset_id=dataset_id,
        limit=50
    )

    # Step 4: Final Answer Generation (Ground truth LLM synthesis using only retrieved records)
    final_answer = await generate_final_answer(
        user_query=raw_message,
        structured_query=structured_query,
        records=final_records
    )

    # Resolve display dataset name
    if dataset_id and dataset_id not in ("all", "default", "*", "companies"):
        single_ds = get_dataset(dataset_id)
        display_dataset_name = single_ds.get("filename", dataset_id) if single_ds else dataset_id
    else:
        matched_sources = list(dict.fromkeys([r.get("source_file") for r in final_records if r.get("source_file") and r.get("source_file") != "Not Available"]))
        if len(matched_sources) == 1:
            display_dataset_name = matched_sources[0]
        elif len(matched_sources) > 1:
            display_dataset_name = f"{len(matched_sources)} sources ({', '.join(matched_sources[:3])}{'...' if len(matched_sources) > 3 else ''})"
        else:
            display_dataset_name = "All Uploaded Datasets & Database"

    if final_records:
        formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(final_records)
        return ChatResponse(
            success=True,
            found=True,
            count=len(final_records),
            dataset_id=dataset_id,
            dataset_name=display_dataset_name,
            database=top_db,
            dataset=top_dataset,
            sources=formatted_sources,
            data=display_records,
            query_intent=structured_query.model_dump(),
            message=final_answer
        )
    else:
        return ChatResponse(
            success=True,
            found=False,
            count=0,
            dataset_id=dataset_id,
            dataset_name=display_dataset_name,
            database="MongoDB Atlas",
            dataset="dataset_records",
            sources=[],
            data=[],
            query_intent=structured_query.model_dump(),
            message="No data found"
        )


@router.get("/search", response_model=ChatResponse)
async def direct_search(
    q: str = Query(..., description="Search term (company name, email, phone, keyword, etc.)"),
    field: Optional[str] = Query(None, description="Optional target column filter"),
    dataset_id: Optional[str] = Query(None, description="Optional dataset ID"),
    collections: List[Collection] = Depends(get_db)
):
    """
    Direct search endpoint backed by the Hybrid Retrieval engine.
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

    # Parse query using deterministic fallback
    structured_query = fallback_query_understanding(clean_q)
    if field and field.lower().strip() in ALLOWED_SEARCH_FIELDS:
        f_clean = field.lower().strip()
        if f_clean in ("company_name", "company"):
            structured_query.companies = [clean_q]
        elif f_clean in ("contact_person", "person"):
            structured_query.people = [clean_q]
        elif f_clean in ("designation", "role"):
            structured_query.designation = clean_q
        elif f_clean in ("city", "state", "location", "address"):
            structured_query.location = clean_q

    target_dataset = dataset_id if dataset_id and dataset_id not in ("default", "all", "*") else "all"

    search_plan = route_query(structured_query)
    final_records, _ = await execute_hybrid_retrieval(
        structured_query=structured_query,
        plan=search_plan,
        dataset_id=target_dataset,
        limit=50
    )

    if final_records:
        final_answer = await generate_final_answer(clean_q, structured_query, final_records)
        formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(final_records)
        return ChatResponse(
            success=True,
            found=True,
            count=len(final_records),
            dataset_id=target_dataset,
            dataset_name="MongoDB Search",
            database=top_db,
            dataset=top_dataset,
            sources=formatted_sources,
            data=display_records,
            query_intent=structured_query.model_dump(),
            message=final_answer
        )
    else:
        return ChatResponse(
            success=True,
            found=False,
            count=0,
            dataset_id=target_dataset,
            dataset_name="MongoDB Search",
            database="MongoDB Atlas",
            dataset="dataset_records",
            sources=[],
            data=[],
            query_intent=structured_query.model_dump(),
            message="No data found"
        )


@router.get("/collections")
def list_collections(collections: List[Collection] = Depends(get_db)):
    """Returns list of active configured MongoDB collections and their document counts."""
    data = []
    total_docs = 0
    for col in collections:
        try:
            cnt = col.estimated_document_count()
        except Exception:
            cnt = 0
        total_docs += cnt
        data.append({
            "name": col.name,
            "document_count": cnt
        })
    return {
        "total_collections": len(data),
        "total_documents": total_docs,
        "collections": data
    }


@router.get("/fields")
def get_searchable_fields(dataset_id: Optional[str] = Query(None)):
    """Returns available searchable fields in the active dataset or companies table."""
    if dataset_id and dataset_id not in ("default", "all", "*"):
        dataset_info = get_dataset(dataset_id)
        if dataset_info:
            return {
                "dataset_id": dataset_id,
                "dataset_name": dataset_info.get("filename"),
                "fields": dataset_info.get("fields", []),
                "normalized_fields": dataset_info.get("normalized_fields", [])
            }

    uploaded = list_datasets()
    if uploaded:
        all_fields = sorted(list(dict.fromkeys(
            [f for ds in uploaded for f in (ds.get("fields") or [])] + list(ALLOWED_SEARCH_FIELDS)
        )))
        return {
            "fields": all_fields,
            "primary_fields": [
                "company_name",
                "person_name",
                "designation",
                "department",
                "state",
                "city",
                "contact_number",
                "personal_mail_id",
                "address",
                "remarks"
            ]
        }

    return {
        "fields": sorted(list(ALLOWED_SEARCH_FIELDS)),
        "primary_fields": [
            "company_name",
            "contact_person",
            "designation",
            "mobile_no",
            "email_1",
            "email_2",
            "telephone_1",
            "telephone_2",
            "address",
            "pin",
            "remarks"
        ]
    }
