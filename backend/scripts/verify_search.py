import sys
import os
import re
import json
import asyncio
from typing import Dict, Any, List
from collections import Counter

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import get_database, get_configured_collection_names
from app.services.query_planner import plan_query_execution
from app.services.multi_stage_search import (
    execute_keyword_company_search,
    execute_vector_retrieval,
    VECTOR_SIMILARITY_THRESHOLD
)
from app.services.response_generator import (
    extract_company_name,
    extract_person_info,
    extract_emails,
    extract_contact_numbers,
    extract_location,
    extract_linkedin,
    format_strict_company_records,
    report_database_duplicates
)
from app.utils.normalization import normalize_company, is_company_match


async def run_verification(raw_query: str, as_json: bool = False):
    db = get_database()
    cols = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))

    # 1. PLAN
    query_plan = await plan_query_execution(raw_query)
    plan_info = {
        "companies": query_plan.companies,
        "intent": query_plan.intent,
        "must_have": query_plan.must_have,
        "must_not_have": query_plan.must_not_have,
        "city": query_plan.city,
        "state": query_plan.state,
        "fields": query_plan.fields,
        "designation_keywords": query_plan.designation_keywords,
        "used_fallback": query_plan.used_fallback
    }

    # 2. KEYWORD
    keyword_results = {}
    all_raw_keyword_hits = []
    all_deduped_keyword_records = []
    seen_kw_ids = set()

    stage_breakdowns = {}
    id_stage_tracker = Counter()

    for comp in query_plan.companies:
        recs, stage_counts = execute_keyword_company_search(db, cols, comp)
        stage_breakdowns[comp] = stage_counts
        
        # Track for duplicate report
        for r in recs:
            rid = str(r.get("_id") or r.get("id"))
            id_stage_tracker[rid] += 1
            if rid not in seen_kw_ids:
                seen_kw_ids.add(rid)
                all_deduped_keyword_records.append(r)

        top_20 = [
            {"_id": str(r.get("_id")), "company": str(r.get("company", "") or r.get("Company", ""))}
            for r in recs[:20]
        ]
        keyword_results[comp] = {
            "hits_before_dedupe": sum(stage_counts.values()),
            "hits_after_dedupe": len(recs),
            "stages": stage_counts,
            "top_20": top_20
        }

    # 3. DUPLICATES
    multi_hit_ids = {k: v for k, v in id_stage_tracker.items() if v > 1}
    db_dup_report = report_database_duplicates(all_deduped_keyword_records)
    duplicate_info = {
        "ids_appearing_multiple_times": len(multi_hit_ids),
        "multi_hit_id_counts": multi_hit_ids,
        "db_duplicate_records_report": db_dup_report
    }

    # 4. VECTOR
    kept_vector, fallback_used, raw_vector_records, retried_no_filter = await execute_vector_retrieval(db, raw_query)
    top_10_vector = [
        {
            "_id": str(r.get("_id")),
            "company": str(r.get("company", "") or r.get("Company", "")),
            "score": round(float(r.get("vector_score", 0.0)), 4)
        }
        for r in raw_vector_records[:10]
    ]
    vector_info = {
        "raw_hit_count": len(raw_vector_records),
        "hits_passing_threshold": len(kept_vector),
        "threshold_value": VECTOR_SIMILARITY_THRESHOLD,
        "top_10_hits": top_10_vector,
        "fallback_used": fallback_used,
        "filter_retried_without_filter": retried_no_filter
    }

    # 5. MERGE
    kw_id_set = {str(r.get("_id")) for r in all_deduped_keyword_records}
    vec_id_set = {str(r.get("_id")) for r in kept_vector}
    both_ids = kw_id_set.intersection(vec_id_set)
    keyword_only_records = [r for r in all_deduped_keyword_records if str(r.get("_id")) not in vec_id_set]
    vector_only_records = [r for r in kept_vector if str(r.get("_id")) not in kw_id_set]

    merge_info = {
        "keyword_only_count": len(keyword_only_records),
        "vector_only_count": len(vector_only_records),
        "both_count": len(both_ids),
        "main_list_count": len(all_deduped_keyword_records),
        "related_results_count": len(vector_only_records)
    }

    # 6. FILTER
    task = query_plan.tasks[0] if query_plan.tasks else None
    filtered_records = []
    before_filter_count = len(all_deduped_keyword_records)

    for r in all_deduped_keyword_records:
        if task and task.city:
            loc = extract_location(r)
            c_city = (loc.get("city") or "").lower()
            if task.city.lower() not in c_city:
                continue
        if task and "email" in task.must_have and not extract_emails(r):
            continue
        if task and "phone" in task.must_have and not extract_contact_numbers(r):
            continue
        if task and "designation" in task.must_have and not extract_person_info(r).get("designation"):
            continue
        filtered_records.append(r)

    filter_info = {
        "records_before_filters": before_filter_count,
        "records_after_filters": len(filtered_records)
    }

    # 7. FINAL
    total_found_comps = len(query_plan.companies)
    emails_count = sum(1 for r in filtered_records if extract_emails(r))
    if total_found_comps > 1:
        comp_str = ", ".join(query_plan.companies)
        header_text = f"Found {total_found_comps} companies ({comp_str}), {len(filtered_records)} records."
    else:
        c_name = query_plan.companies[0] if query_plan.companies else raw_query
        f_desc = f" with email" if task and "email" in task.must_have else ""
        header_text = f"Found {len(filtered_records)} records matching '{c_name}'{f_desc}. {emails_count} contacts have an email."

    final_info = {
        "header_text": header_text,
        "cards_shown_count": len(filtered_records),
        "records_count": len(filtered_records)
    }

    # 8. RAW CHECK
    # Build independent whole-word regex on norm_company
    raw_counts_per_company = {}
    atlas_filter_parts = []
    total_raw_expected = 0

    for comp_name in query_plan.companies:
        norm_tokens = [re.escape(t) for t in normalize_company(comp_name).split() if t]
        if len(norm_tokens) == 1:
            pat = rf"\b{norm_tokens[0]}\b"
        elif len(norm_tokens) == 2:
            t1, t2 = norm_tokens[0], norm_tokens[1]
            pat = rf"\b{t1}\b.*\b{t2}\b|\b{t2}\b.*\b{t1}\b"
        else:
            pat = r".*".join([rf"\b{t}\b" for t in norm_tokens])

        atlas_flt = {"norm_company": {"$regex": pat, "$options": "i"}}
        atlas_filter_parts.append(atlas_flt)

        c_cnt = 0
        for c_col in cols:
            try:
                c_cnt += db[c_col].count_documents(atlas_flt)
            except Exception:
                pass
        raw_counts_per_company[comp_name] = c_cnt
        total_raw_expected += c_cnt

    atlas_filter_snippet = {"$or": atlas_filter_parts} if len(atlas_filter_parts) > 1 else (atlas_filter_parts[0] if atlas_filter_parts else {})
    pass_fail = "PASS" if len(filtered_records) == total_raw_expected else "FAIL"

    raw_check_info = {
        "raw_counts_per_company": raw_counts_per_company,
        "total_raw_expected": total_raw_expected,
        "final_chatbot_count": len(filtered_records),
        "status": pass_fail,
        "atlas_filter_snippet": atlas_filter_snippet
    }

    full_report = {
        "query": raw_query,
        "plan": plan_info,
        "keyword": keyword_results,
        "duplicates": duplicate_info,
        "vector": vector_info,
        "merge": merge_info,
        "filter": filter_info,
        "final": final_info,
        "raw_check": raw_check_info
    }

    if as_json:
        print(json.dumps(full_report, indent=2))
        return

    # Plain text print
    print("=" * 70)
    print(f" SEARCH VERIFICATION REPORT: '{raw_query}'")
    print("=" * 70)

    print("\n1. PLAN:")
    print(f"   - Companies: {plan_info['companies']}")
    print(f"   - Intent   : {plan_info['intent']}")
    print(f"   - Must Have: {plan_info['must_have']}")
    print(f"   - City/Loc : {plan_info['city']}")

    print("\n2. KEYWORD:")
    for comp, kw_d in keyword_results.items():
        print(f"   - [{comp}]: hits_before_dedupe={kw_d['hits_before_dedupe']}, hits_after_dedupe={kw_d['hits_after_dedupe']}")
        print(f"     Stages: {kw_d['stages']}")
        print(f"     Top hits (_id, company):")
        for hit in kw_d["top_20"][:5]:
            print(f"       * {hit['_id']} | {hit['company']}")

    print("\n3. DUPLICATES:")
    print(f"   - Duplicate _id occurrences across stages: {duplicate_info['ids_appearing_multiple_times']}")
    print(f"   - DB records sharing identical (norm_company, person, email, phone): {db_dup_report['total_records_in_duplicate_groups']}")

    print("\n4. VECTOR:")
    print(f"   - Raw Hit Count: {vector_info['raw_hit_count']}")
    print(f"   - Threshold    : {vector_info['threshold_value']}")
    print(f"   - Passing Hits : {vector_info['hits_passing_threshold']}")
    print(f"   - Top hits (_id, company, score):")
    for vh in vector_info["top_10_hits"][:5]:
        print(f"       * {vh['_id']} | {vh['company']} | score={vh['score']}")

    print("\n5. MERGE:")
    print(f"   - Keyword-only hits: {merge_info['keyword_only_count']}")
    print(f"   - Vector-only hits : {merge_info['vector_only_count']}")
    print(f"   - Both             : {merge_info['both_count']}")
    print(f"   - Main List Cards  : {merge_info['main_list_count']}")
    print(f"   - Related Results  : {merge_info['related_results_count']}")

    print("\n6. FILTER:")
    print(f"   - Before Filters   : {filter_info['records_before_filters']}")
    print(f"   - After Filters    : {filter_info['records_after_filters']}")

    print("\n7. FINAL:")
    print(f"   - Header Text      : {final_info['header_text']}")
    print(f"   - Total Cards Shown: {final_info['cards_shown_count']}")

    print("\n8. RAW CHECK:")
    print(f"   - Raw Atlas Counts : {raw_check_info['raw_counts_per_company']}")
    print(f"   - Total Expected   : {raw_check_info['total_raw_expected']}")
    print(f"   - Final Returned   : {raw_check_info['final_chatbot_count']}")
    print(f"   - Gate Check Status: [{raw_check_info['status']}]")
    print(f"   - Atlas Filter     : {json.dumps(raw_check_info['atlas_filter_snippet'])}")
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_search.py \"<query>\" [--json]")
        sys.exit(1)

    query_arg = sys.argv[1]
    is_json_arg = "--json" in sys.argv
    asyncio.run(run_verification(query_arg, as_json=is_json_arg))
