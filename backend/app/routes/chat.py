import re
import time
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("calispec.chat")
from bson import ObjectId
from fastapi import APIRouter, Depends, Query, HTTPException
from pymongo.collection import Collection
from ..database import get_db, get_database, get_database_name, get_configured_collection_names
from ..config import PRIVACY_MODE, FINAL_K
from ..schemas import ChatRequest, ChatResponse, LookupResult
from ..services.mongo_dataset import get_dataset, list_datasets
from ..search import ALLOWED_SEARCH_FIELDS
from ..utils.normalization import extract_original_source_fields
from ..services.retrieval_service import group_records_by_source, execute_hybrid_retrieval, validate_record_relevance
from ..services.query_understanding import (
    parse_query_understanding,
    fallback_query_understanding,
    normalize_query_typos,
    detect_followup_availability_filter,
    StructuredQuery,
    FollowupFilter
)
from ..services.query_router import route_query
from ..services.response_generator import (
    is_valid_source_row,
    generate_final_answer,
    format_strict_company_records,
    format_followup_answer,
    extract_company_name,
    extract_person_info,
    extract_emails,
    extract_contact_numbers,
    extract_location,
    extract_linkedin
)
from ..services.source_resolver import (
    get_dataset_name,
    get_record_sources,
    get_record_source_display,
    get_company_sources_summary
)
from ..services.session_cache import (
    store_last_result_set,
    get_last_result_set,
    update_current_result_set,
    reset_session_filter
)
from ..services.contact_search import (
    get_or_build_vocab,
    parse_query,
    search as contact_search_exec,
)
from ..services.embeddings import strip_embedding

router = APIRouter(prefix="/api", tags=["Chat & Search"])


def fetch_records_by_ids(db, record_ids: List[str], target_dataset_id: str = "all") -> List[Dict[str, Any]]:
    """Fetches full MongoDB documents by ID list while preserving original ordering and stripping embeddings."""
    if not record_ids:
        return []

    configured_cols = get_configured_collection_names()
    all_target_cols = list(dict.fromkeys(configured_cols + ["dataset_records"]))

    obj_ids = []
    str_ids = []
    for rid in record_ids:
        s_rid = str(rid).strip()
        str_ids.append(s_rid)
        if len(s_rid) == 24:
            try:
                obj_ids.append(ObjectId(s_rid))
            except Exception:
                pass

    query_filter: Dict[str, Any] = {
        "$or": [
            {"_id": {"$in": obj_ids + str_ids}},
            {"id": {"$in": str_ids}},
            {"doc_id": {"$in": str_ids}}
        ]
    }
    if target_dataset_id != "all":
        query_filter["dataset_id"] = target_dataset_id

    records_map: Dict[str, Dict[str, Any]] = {}
    for col_name in all_target_cols:
        try:
            cursor = db[col_name].find(query_filter, {"embedding": 0})
            for doc in cursor:
                doc_id_str = str(doc.get("_id") or doc.get("id"))
                if doc_id_str not in records_map:
                    doc["source_collection"] = col_name
                    records_map[doc_id_str] = doc
        except Exception:
            pass

    ordered_records: List[Dict[str, Any]] = []
    for rid in record_ids:
        if rid in records_map:
            ordered_records.append(records_map[rid])
        else:
            for doc in records_map.values():
                if str(doc.get("id")) == rid or str(doc.get("doc_id")) == rid:
                    ordered_records.append(doc)
                    break

    return ordered_records


def matches_followup_filter(rec: Dict[str, Any], followup: FollowupFilter) -> bool:
    """Evaluates whether a single record matches follow-up conditions and location filters."""
    # 1. Conditions check (email, phone, linkedin, address, person, designation)
    cond_results = []
    for c in followup.conditions:
        f = c["field"]
        req = c["required"]
        has_val = False
        if f == "email":
            has_val = bool(extract_emails(rec))
        elif f == "phone":
            has_val = bool(extract_contact_numbers(rec))
        elif f == "linkedin":
            has_val = bool(extract_linkedin(rec))
        elif f == "address":
            loc = extract_location(rec)
            has_val = bool(loc.get("address") or loc.get("city") or loc.get("state"))
        elif f == "person":
            has_val = bool(extract_person_info(rec).get("name"))
        elif f == "designation":
            has_val = bool(extract_person_info(rec).get("designation"))

        cond_results.append(has_val == req)

    if cond_results:
        if followup.operator == "OR":
            if not any(cond_results):
                return False
        else:
            if not all(cond_results):
                return False

    # 2. Location / City / State narrowing
    if followup.city_filter:
        loc = extract_location(rec)
        city = (loc.get("city") or "").lower()
        addr = (loc.get("address") or "").lower()
        target_city = followup.city_filter.lower()
        if target_city not in city and target_city not in addr:
            return False

    if followup.state_filter:
        loc = extract_location(rec)
        state = (loc.get("state") or "").lower()
        target_state = followup.state_filter.lower()
        if target_state not in state:
            return False

    return True


def format_api_sources_and_records(final_records: List[dict], structured_query: Optional[StructuredQuery] = None, display_dataset_name: str = "All Datasets"):
    """
    Builds clean, source-grouped API representation preserving only original source columns.
    Uses unified get_dataset_name helper for accurate dataset name attribution per record.
    All missing values default strictly to 'No data available'.
    """
    source_groups = group_records_by_source(final_records)
    formatted_sources = []
    display_records = []
    default_db = get_database_name()
    req_fields = structured_query.requested_fields if structured_query else []
    is_selective = bool(
        structured_query and (
            structured_query.is_only_fields
            or (req_fields and not (structured_query.email_required is True or structured_query.phone_required is True or structured_query.linkedin_required is True))
        )
    )

    for src in source_groups:
        s_file = src.get("source_file") or None
        s_sheet = src.get("source_sheet")
        s_dataset_name = src.get("dataset_name") or src.get("source_collection") or display_dataset_name
        s_col = src.get("source_collection") or "dataset_records"
        db_src = src.get("database_source") or default_db

        clean_src_records = []
        for r in src.get("records", []):
            sf = strip_embedding(extract_original_source_fields(r))
            s_row = is_valid_source_row(r.get("source_row"))
            from ..services.response_generator import get_contact_fields
            fields = get_contact_fields(r)

            c_val = fields["company"]
            p_name = ", ".join(fields["contact_persons"]) if fields["contact_persons"] else "No data available"
            p_desig = ", ".join(fields["designations"]) if fields["designations"] else "No data available"
            emails_extracted = fields["emails"]
            phones_extracted = fields["phones"]
            linkedin_val = ", ".join(fields["linkedin"]) if fields["linkedin"] else "No data available"
            resolved_source_display = fields["dataset_name"]
            rec_dataset_name = resolved_source_display if resolved_source_display != "No data available" else s_dataset_name

            if is_selective and req_fields:
                proj_sf = {}
                proj_sf["Company Name"] = c_val if c_val else "No data available"

                if "person" in req_fields:
                    proj_sf["Contact Person"] = p_name
                if "designation" in req_fields:
                    proj_sf["Designation"] = p_desig
                if "email" in req_fields:
                    proj_sf["Email"] = emails_extracted[0] if emails_extracted else "No data available"
                    for idx_e, em in enumerate(emails_extracted[1:], 2):
                        proj_sf[f"Email {idx_e}"] = em
                if "phone" in req_fields:
                    proj_sf["Contact Number"] = phones_extracted[0] if phones_extracted else "No data available"
                    for idx_p, ph in enumerate(phones_extracted[1:], 2):
                        proj_sf[f"Contact Number {idx_p}"] = ph
                if "city" in req_fields:
                    proj_sf["City"] = fields["city"]
                if "state" in req_fields:
                    proj_sf["State"] = fields["state"]
                if "address" in req_fields:
                    proj_sf["Address"] = fields["address"]
                if "linkedin" in req_fields:
                    proj_sf["LinkedIn"] = linkedin_val

                proj_sf["Source"] = resolved_source_display
                sf = proj_sf

            display_rec = {
                "dataset": rec_dataset_name,
                "dataset_name": rec_dataset_name,
                "source_collection": s_col,
                "database": db_src,
                "database_source": db_src,
                "source_file": resolved_source_display,
                "Source File": resolved_source_display,
                "Sources": resolved_source_display,
                "source": resolved_source_display,
                "Source": resolved_source_display
            }
            if s_sheet and s_sheet != "Not Available":
                display_rec["source_sheet"] = s_sheet
            if s_row:
                display_rec["source_row"] = s_row

            display_rec.update(sf)

            # Standard keys populated with 'No data available' for missing values
            display_rec["company"] = c_val if c_val else "No data available"
            display_rec["Company"] = display_rec["company"]
            display_rec["Company Name"] = display_rec["company"]
            
            display_rec["person"] = p_name
            display_rec["Contact Person"] = p_name
            display_rec["Person Name"] = p_name
            
            display_rec["designation"] = p_desig
            display_rec["Designation"] = p_desig
            
            display_rec["email"] = emails_extracted[0] if emails_extracted else "No data available"
            display_rec["Email"] = display_rec["email"]
            display_rec["Email 1"] = display_rec["email"]
            display_rec["email_2"] = emails_extracted[1] if len(emails_extracted) > 1 else "No data available"
            display_rec["Email 2"] = display_rec["email_2"]
            
            display_rec["phone"] = phones_extracted[0] if phones_extracted else "No data available"
            display_rec["Phone"] = display_rec["phone"]
            display_rec["Contact Number"] = display_rec["phone"]
            display_rec["phone_2"] = phones_extracted[1] if len(phones_extracted) > 1 else "No data available"
            display_rec["Phone 2"] = display_rec["phone_2"]
            
            display_rec["city"] = fields["city"]
            display_rec["City"] = fields["city"]
            
            display_rec["state"] = fields["state"]
            display_rec["State"] = fields["state"]
            
            display_rec["address"] = fields["address"]
            display_rec["Address"] = fields["address"]
            
            display_rec["location"] = fields["address"] if fields["address"] != "No data available" else fields["city"]
            display_rec["Location"] = display_rec["location"]
            
            display_rec["linkedin"] = linkedin_val
            display_rec["LinkedIn"] = linkedin_val

            display_rec = strip_embedding(display_rec)
            clean_src_records.append(sf)
            display_records.append(display_rec)

        s_entry = {
            "dataset": s_dataset_name,
            "dataset_name": s_dataset_name,
            "source_collection": s_col,
            "database": db_src,
            "database_source": db_src,
            "records": clean_src_records
        }
        if s_file:
            s_entry["source_file"] = s_file
        if s_sheet and s_sheet != "Not Available":
            s_entry["source_sheet"] = s_sheet

        formatted_sources.append(s_entry)

    top_dataset = source_groups[0].get("dataset_name") or source_groups[0].get("source_collection", "dataset_records") if source_groups else "dataset_records"
    top_db = source_groups[0].get("database_source", default_db) if source_groups else default_db

    return formatted_sources, display_records, top_dataset, top_db


async def execute_rag_pipeline(
    raw_query: str,
    dataset_id: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    session_id: Optional[str] = "default_session",
    explain: bool = False
) -> ChatResponse:
    """
    Executes End-to-End Hybrid RAG Pipeline or Follow-up Result Filter.
    """
    db = get_database()
    target_dataset_id = dataset_id if dataset_id and dataset_id not in ("all", "default", "*", "companies") else "all"
    display_dataset_name = "All Datasets"
    if target_dataset_id != "all":
        single_ds = get_dataset(target_dataset_id)
        if single_ds:
            display_dataset_name = single_ds.get("filename", target_dataset_id)
        else:
            display_dataset_name = target_dataset_id

    # Check for --explain flag inside query string
    effective_query = raw_query
    if "--explain" in effective_query.lower():
        explain = True
        effective_query = re.sub(r"--explain\b", "", effective_query, flags=re.IGNORECASE).strip()

    # 1. Execute LLM Query Planner (Step 3)
    has_prev = bool(get_last_result_set(session_id))
    from ..services.query_planner import plan_query_execution, execute_planned_retrieval, QueryPlan
    query_plan = await plan_query_execution(effective_query, history=history, has_previous_results=has_prev)

    # 2. Detect Follow-up Availability Filter (Task 4 & 5)
    normalized_q = normalize_query_typos(effective_query)
    is_another_request = bool(re.search(
        r"\b(another|other|others|different|next|new|aanothe|anothe|aanother|anothr|anthr|diffrent|diferent)\b",
        normalized_q.lower()
    ))

    followup_filter = detect_followup_availability_filter(effective_query, history=history)

    is_explicit_followup = bool(
        not is_another_request
        and (
            query_plan.intent == "filter_previous"
            or (
                followup_filter
                and followup_filter.is_followup
                and not query_plan.companies
                and query_plan.intent != "open_question"
            )
        )
    )

    if is_another_request:
        from ..services.query_planner import find_another_company_from_db
        prev_companies = []
        if has_prev:
            session_data = get_last_result_set(session_id)
            if session_data and session_data.get("company"):
                prev_companies.append(str(session_data.get("company")).lower().strip())
        if history:
            for turn in reversed(history[-6:]):
                p_text = str(turn.get("content") or turn.get("message") or "")
                p_sq = fallback_query_understanding(normalize_query_typos(p_text))
                if p_sq.companies:
                    for pc in p_sq.companies:
                        prev_companies.append(pc.lower().strip())
        prev_companies = list(dict.fromkeys(prev_companies))

        for t in query_plan.tasks:
            t.intent = "lookup"
            t.use_previous_results = False
            clean_comps = [
                c for c in t.companies
                if c.lower().strip() not in ("another", "other", "others", "different", "next", "new", "same", "previous", "one", "aanothe", "anothe", "anthr")
                and not any(pc in c.lower() or c.lower() in pc for pc in prev_companies)
            ]
            t.companies = clean_comps
            if not t.companies:
                chosen = find_another_company_from_db(
                    exclude_companies=prev_companies,
                    must_have=t.must_have or query_plan.must_have,
                    city=t.city or query_plan.city
                )
                if chosen:
                    t.companies = [chosen]

        # If user asked for 'alone' or 'only' with email, ensure fields and only_requested_fields are set
        if ("alone" in normalized_q.lower() or "only" in normalized_q.lower()) and "email" in query_plan.must_have:
            for t in query_plan.tasks:
                if "email" not in t.fields:
                    t.fields.append("email")
                t.only_requested_fields = True

    if is_explicit_followup and has_prev:
        session_data = get_last_result_set(session_id)
        if not session_data or not session_data.get("original_ids"):
            return ChatResponse(
                success=True,
                found=False,
                count=0,
                dataset_id=dataset_id or "all",
                dataset_name=display_dataset_name,
                database=get_database_name(),
                dataset="dataset_records",
                sources=[],
                data=[],
                message="Please search for a company first.",
                understood_as=["Follow-up Filter: No previous result set found"],
                retrieval_mode="session_cache",
                total=0
            )

        # Handle Reset / Restore All
        if followup_filter and followup_filter.is_reset:
            orig_ids = reset_session_filter(session_id) or []
            restored_records = fetch_records_by_ids(db, orig_ids, target_dataset_id=target_dataset_id)
            comp_name = session_data.get("company") or "the database"
            formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(restored_records, display_dataset_name=display_dataset_name)
            msg = f"Reset filters. Showing all {len(display_records)} original results for '{comp_name}'."
            return ChatResponse(
                success=True,
                found=len(display_records) > 0,
                count=len(display_records),
                dataset_id=dataset_id or "all",
                dataset_name=display_dataset_name,
                database=top_db,
                dataset=top_dataset,
                sources=formatted_sources,
                data=display_records,
                message=msg,
                understood_as=["Follow-up: Reset filters to original results"],
                retrieval_mode="session_cache_reset",
                total=len(display_records)
            )

        # Handle Availability Filter / Count on Stored Results
        current_candidate_ids = session_data.get("current_ids") or session_data.get("original_ids") or []
        candidate_records = fetch_records_by_ids(db, current_candidate_ids, target_dataset_id=target_dataset_id)
        total_prev_count = len(candidate_records)

        # Filter candidate records deterministically in code
        active_filter = followup_filter if followup_filter else FollowupFilter(
            is_followup=True,
            raw_query=effective_query,
            conditions=[{"field": f, "required": True} for f in query_plan.must_have],
            is_count_query=(query_plan.intent == "count")
        )

        filtered_records = [r for r in candidate_records if matches_followup_filter(r, active_filter)]
        matched_count = len(filtered_records)
        company_name = session_data.get("company") or (active_filter.company_reference if active_filter else "matching")

        # Update session cache if narrowing down and not a count query
        if not active_filter.is_count_query and matched_count > 0:
            new_active_ids = [str(r.get("_id") or r.get("id")) for r in filtered_records]
            update_current_result_set(session_id, new_active_ids, active_filter.raw_query)

        # Build clean markdown answer (ZERO LLM CALL)
        final_markdown = format_followup_answer(
            records=filtered_records,
            total_prev_count=total_prev_count,
            followup_filter=active_filter,
            company_name=company_name
        )

        formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(filtered_records, display_dataset_name=display_dataset_name)

        return ChatResponse(
            success=True,
            found=matched_count > 0,
            count=matched_count,
            dataset_id=dataset_id or "all",
            dataset_name=display_dataset_name,
            database=top_db,
            dataset=top_dataset,
            sources=formatted_sources,
            data=display_records,
            message=final_markdown,
            understood_as=[f"Follow-up Availability Filter: {active_filter.operator}", f"Conditions: {active_filter.conditions}"],
            retrieval_mode="session_result_filter",
            total=matched_count,
            meta={"plan": query_plan.model_dump()}
        )

    # 3. Open Question Intent (Step 5)
    if query_plan.intent == "open_question":
        structured_query, _ = await parse_query_understanding(effective_query, history=history)
        plan_route = route_query(structured_query)
        final_records, debug_info = await execute_hybrid_retrieval(
            structured_query=structured_query,
            plan=plan_route,
            dataset_id=target_dataset_id,
            limit=FINAL_K
        )
        found = len(final_records) > 0
        from ..llm import generate_answer
        llm_res = await generate_answer(
            question=effective_query,
            history=history,
            records=final_records[:5],
            max_records=5
        )
        final_markdown = llm_res.get("answer") or "No relevant information found for your question."
        formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(
            final_records,
            structured_query=structured_query,
            display_dataset_name=display_dataset_name
        )
        return ChatResponse(
            success=True,
            found=found,
            count=len(display_records) if found else 0,
            dataset_id=dataset_id or "all",
            dataset_name=display_dataset_name,
            database=top_db,
            dataset=top_dataset,
            sources=formatted_sources,
            data=display_records if found else [],
            message=final_markdown,
            understood_as=["Intent: open_question"],
            retrieval_mode="hybrid_rrf_llm",
            total=len(display_records) if found else 0,
            meta={"plan": query_plan.model_dump()}
        )

    # 4. Standard / Multi-Company Planned Search (Step 1, 2, 4)
    t_start = time.time()
    plan_res = await execute_planned_retrieval(
        plan=query_plan,
        raw_query=effective_query,
        target_dataset=target_dataset_id,
        limit=FINAL_K
    )

    final_records = plan_res.get("records", [])
    summary_header = plan_res.get("summary_header", "")
    found = len(final_records) > 0

    structured_query = StructuredQuery(
        original_query=effective_query,
        companies=query_plan.companies,
        city=query_plan.city,
        state=query_plan.state,
        requested_fields=query_plan.fields,
        is_only_fields=query_plan.only_requested_fields,
        email_required=("email" in query_plan.must_have),
        phone_required=("phone" in query_plan.must_have),
        linkedin_required=("linkedin" in query_plan.must_have),
        designation=query_plan.designation_keywords[0] if query_plan.designation_keywords else None
    )

    # Store last result set in session cache for subsequent follow-up queries (Step 4 & 6)
    if found:
        comp_primary = query_plan.companies[0] if query_plan.companies else None
        store_last_result_set(
            session_id=session_id,
            records=final_records,
            company=comp_primary,
            entities={"people": [query_plan.person_name] if query_plan.person_name else [], "city": query_plan.city, "state": query_plan.state},
            columns_shown=query_plan.fields
        )

    # 5. Answer Generation per task (Step 5)
    task_sections = []
    task_results = plan_res.get("task_results", [])
    if task_results and len(task_results) > 1:
        for t_res in task_results:
            t_task = t_res.get("task", {})
            t_hdr = t_res.get("summary_header", "")
            t_recs = t_res.get("records", [])
            if not t_recs:
                task_sections.append(t_hdr)
            else:
                t_sq = StructuredQuery(
                    original_query=effective_query,
                    companies=t_task.get("companies", []),
                    city=t_task.get("city"),
                    state=t_task.get("state"),
                    requested_fields=t_task.get("fields", []),
                    is_only_fields=t_task.get("only_requested_fields", False),
                    email_required=("email" in t_task.get("must_have", [])),
                    phone_required=("phone" in t_task.get("must_have", [])),
                    linkedin_required=("linkedin" in t_task.get("must_have", [])),
                    designation=t_task.get("designation_keywords", [None])[0] if t_task.get("designation_keywords") else None
                )
                t_body = await generate_final_answer(effective_query, t_sq, t_recs)
                task_sections.append(f"### {t_hdr}\n\n{t_body}".strip())
        final_markdown = "\n\n---\n\n".join(task_sections)
    else:
        if not found:
            final_markdown = summary_header
        else:
            body_markdown = await generate_final_answer(effective_query, structured_query, final_records)
            final_markdown = f"{summary_header}\n\n{body_markdown}".strip()

    # 6. Format API sources and UI display records
    formatted_sources, display_records, top_dataset, top_db = format_api_sources_and_records(
        final_records,
        structured_query=structured_query,
        display_dataset_name=display_dataset_name
    )

    unfound = plan_res.get("unfound", [])
    suggestions = [s for item in unfound for s in item[1]] if unfound else None

    elapsed_ms = int((time.time() - t_start) * 1000)
    logger.info(
        f"[RAG] tasks={len(query_plan.tasks)} keyword={plan_res.get('keyword_hits', 0)} "
        f"vector={plan_res.get('vector_hits', 0)} total={len(display_records)} "
        f"fallback={'no'} {elapsed_ms}ms"
    )

    meta_info = {
        "stages": plan_res.get("stages", {}),
        "keyword_hits": plan_res.get("keyword_hits", 0),
        "vector_hits": plan_res.get("vector_hits", 0),
        "merged": len(display_records),
        "fallback_used": False,
        "latency_ms": elapsed_ms,
        "total": len(display_records),
        "plan": plan_res.get("plan", {})
    }

    return ChatResponse(
        success=True,
        found=found,
        count=len(display_records) if found else 0,
        dataset_id=dataset_id or "all",
        dataset_name=display_dataset_name,
        database=top_db,
        dataset=top_dataset,
        sources=formatted_sources,
        data=display_records if found else [],
        message=final_markdown,
        understood_as=[f"Tasks: {len(query_plan.tasks)}", f"Companies: {query_plan.companies}"],
        retrieval_mode="planned_hybrid_retrieval",
        total=len(display_records) if found else 0,
        suggestions=suggestions if (not found and suggestions) else None,
        meta=meta_info
    )





@router.post("/chat", response_model=ChatResponse)
async def chat_search(request: ChatRequest, collections: List[Collection] = Depends(get_db)):
    """
    Main Secure Hybrid RAG Chat Endpoint.
    - Follow-up availability filters served instantaneously from session cache (Zero LLM)
    - Local nomic-embed-text (768-d) embeddings
    - MongoDB Atlas $vectorSearch + Lexical search merged via RRF (k=60)
    - Exact phone/email lookups served directly with NO LLM call.
    - Supports explain flag for diagnostic stage breakdown.
    """
    raw_message = request.message.strip() if request.message else ""
    if not raw_message:
        return ChatResponse(
            success=False,
            found=False,
            count=0,
            data=[],
            message="Please provide a valid query (e.g. company name, location, designation, person, or keywords)."
        )

    # Dataset scoping
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

    return await execute_rag_pipeline(
        raw_query=raw_message,
        dataset_id=dataset_id,
        history=request.history,
        explain=bool(request.explain)
    )


@router.get("/search", response_model=ChatResponse)
async def direct_search(
    q: str = Query(..., description="Search term (company name, email, phone, keyword, etc.)"),
    field: Optional[str] = Query(None, description="Optional target column filter"),
    dataset_id: Optional[str] = Query(None, description="Optional dataset ID"),
    explain: bool = Query(False, description="Flag to return diagnostic retrieval stage breakdown"),
    collections: List[Collection] = Depends(get_db)
):
    """Direct search endpoint backed by Hybrid RAG engine."""
    clean_q = q.strip()
    if not clean_q:
        return ChatResponse(
            success=False,
            found=False,
            count=0,
            data=[],
            message="Query parameter 'q' cannot be empty."
        )

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
    return await execute_rag_pipeline(
        raw_query=final_query,
        dataset_id=target_dataset,
        explain=explain
    )
