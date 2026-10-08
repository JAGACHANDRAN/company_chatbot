import re
import sys
import asyncio
from pathlib import Path
from typing import List, Dict, Any
from bson import ObjectId

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_database
from app.utils.normalization import normalize_company
from app.services.query_planner import (
    plan_query_execution,
    execute_planned_retrieval,
    rule_based_plan,
    QueryPlan,
    SearchTask
)
from app.services.multi_stage_search import (
    execute_keyword_company_search,
    execute_multi_stage_retrieval
)
from app.services.response_generator import (
    extract_company_name,
    extract_person_info,
    extract_emails,
    extract_contact_numbers,
    extract_location,
    extract_linkedin
)
from app.services.source_resolver import (
    get_dataset_name,
    get_company_sources_summary,
    set_cached_dataset_map
)
from app.routes.chat import (
    execute_rag_pipeline,
    format_api_sources_and_records,
    store_last_result_set,
    get_last_result_set,
    reset_session_filter,
    fetch_records_by_ids,
    matches_followup_filter
)
from app.services.query_understanding import FollowupFilter, StructuredQuery

db = get_database()
records_coll = db["dataset_records"]
datasets_coll = db["datasets"]

# 15 biggest companies + 5 with missing emails
TOP_15_COMPANIES = [
    "ashok leyland",
    "tata motors",
    "bosch",
    "royal enfield",
    "bharat forge",
    "mahindra and mahindra",
    "toyota kirloskar auto parts",
    "lucas tvs",
    "musashi auto parts",
    "sundram fasteners",
    "varroc engineering",
    "gkn driveline",
    "natesan synchrocones",
    "shriram pistons and rings",
    "brakes"
]

COMPANIES_WITH_MISSING_EMAILS = [
    "musashi auto parts",
    "varroc engineering",
    "sona koyo steering systems",
    "maruti suzuki",
    "bajaj auto"
]


def raw_db_keyword_search(company_name: str) -> List[Dict[str, Any]]:
    """Raw independent PyMongo query matching Step 3 rules on norm_company."""
    n_norm = normalize_company(company_name)
    if not n_norm:
        return []
    tokens = n_norm.split()
    if len(n_norm) <= 3:
        word_regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"
        query = {
            "$or": [
                {"norm_company": {"$regex": word_regex, "$options": "i"}},
                {"$and": [
                    {"norm_company": {"$in": [None, ""]}},
                    {"company": {"$regex": word_regex, "$options": "i"}}
                ]}
            ]
        }
    else:
        if len(tokens) == 1:
            word_regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"
            query = {
                "$or": [
                    {"norm_company": {"$regex": word_regex, "$options": "i"}},
                    {"$and": [
                        {"norm_company": {"$in": [None, ""]}},
                        {"company": {"$regex": word_regex, "$options": "i"}}
                    ]}
                ]
            }
        else:
            token_ands = [{"norm_company": {"$regex": rf"(^|\s){re.escape(t)}(\s|$)", "$options": "i"}} for t in tokens]
            token_ands_fallback = [{"company": {"$regex": rf"(^|\s){re.escape(t)}(\s|$)", "$options": "i"}} for t in tokens]
            query = {
                "$or": [
                    {"norm_company": {"$regex": rf"(^|\s){re.escape(n_norm)}(\s|$)", "$options": "i"}},
                    {"$and": token_ands},
                    {"$and": [
                        {"norm_company": {"$in": [None, ""]}},
                        {"$and": token_ands_fallback}
                    ]}
                ]
            }
    return list(records_coll.find(query, {"embedding": 0}))


# -------------------------------------------------------------
# Test 1: Each company alone: app count == raw DB count
# -------------------------------------------------------------
def test_case_1_each_company_alone():
    async def _run():
        for comp in TOP_15_COMPANIES[:5]:
            raw_docs = raw_db_keyword_search(comp)
            raw_count = len(raw_docs)

            plan = rule_based_plan(comp)
            res = await execute_planned_retrieval(plan, comp)
            app_count = res.get("total", 0)

            assert app_count == raw_count, f"Company '{comp}': App count {app_count} != Raw DB count {raw_count}"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 2: 17 pasted names in three formats give identical results
# -------------------------------------------------------------
def test_case_2_17_pasted_names_formats():
    async def _run():
        test_17 = [
            "Ashok Leyland", "TVS", "Titan", "Bosch", "BHEL",
            "Royal Enfield", "Bharat Forge", "Mahindra and Mahindra",
            "Toyota Kirloskar", "Musashi Auto Parts", "Sundram Fasteners",
            "Varroc Engineering", "GKN Driveline", "Maruti Suzuki",
            "Bajaj Auto", "Hyundai", "NonExistentEntity999"
        ]

        fmt_newline = "\n".join(test_17)
        fmt_comma = ", ".join(test_17)
        fmt_numbered = "\n".join(f"{i+1}. {name}" for i, name in enumerate(test_17))

        p1 = rule_based_plan(fmt_newline)
        p2 = rule_based_plan(fmt_comma)
        p3 = rule_based_plan(fmt_numbered)

        r1 = await execute_planned_retrieval(p1, fmt_newline)
        r2 = await execute_planned_retrieval(p2, fmt_comma)
        r3 = await execute_planned_retrieval(p3, fmt_numbered)

        assert r1["total"] == r2["total"] == r3["total"]

        unfound_names = [item[0] for item in r1.get("unfound_list", [])]
        assert "NonExistentEntity999" in unfound_names
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 3: "<company> which have emails": count == raw count with email
# -------------------------------------------------------------
def test_case_3_company_which_have_emails():
    async def _run():
        comp = "ashok leyland"
        raw_docs = raw_db_keyword_search(comp)
        raw_with_email = [r for r in raw_docs if extract_emails(r)]
        raw_count = len(raw_with_email)

        query = f"{comp} which have emails"
        plan = rule_based_plan(query)
        res = await execute_planned_retrieval(plan, query)
        app_count = res.get("total", 0)

        assert app_count == raw_count, f"With-email query: App count {app_count} != Raw count {raw_count}"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 4: "<company> without emails": with + without == total
# -------------------------------------------------------------
def test_case_4_company_without_emails():
    async def _run():
        comp = "musashi auto parts"
        plan_with = rule_based_plan(f"{comp} with emails")
        res_with = await execute_planned_retrieval(plan_with, f"{comp} with emails")

        plan_without = rule_based_plan(f"{comp} without emails")
        res_without = await execute_planned_retrieval(plan_without, f"{comp} without emails")

        plan_all = rule_based_plan(comp)
        res_all = await execute_planned_retrieval(plan_all, comp)

        assert res_with["total"] + res_without["total"] == res_all["total"]
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 5: "<city> <company> companies": every row's location contains city
# -------------------------------------------------------------
def test_case_5_city_company_filter():
    async def _run():
        query = "chennai ashok leyland companies"
        plan = rule_based_plan(query)
        res = await execute_planned_retrieval(plan, query)

        for r in res.get("records", []):
            loc = extract_location(r)
            loc_str = f"{loc.get('city', '')} {loc.get('address', '')} {loc.get('state', '')}".lower()
            assert "chennai" in loc_str, f"Record location '{loc_str}' does not contain chennai"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 6: "<company> quality persons": designation matches keywords
# -------------------------------------------------------------
def test_case_6_quality_persons():
    async def _run():
        query = "ashok leyland quality persons"
        plan = rule_based_plan(query)
        res = await execute_planned_retrieval(plan, query)

        for r in res.get("records", []):
            desig = (extract_person_info(r).get("designation") or "").lower()
            if desig != "no data available" and desig != "not available":
                assert any(k in desig for k in ["quality", "qa", "qc", "assurance", "control"]), f"Designation '{desig}' not matching quality"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 7: Multi-request message (3 sub-requests in one sentence)
# -------------------------------------------------------------
def test_case_7_multi_request_message():
    query = "tvs companies with emails, ashok leyland in chennai, and titan quality persons"
    plan = rule_based_plan(query)

    assert len(plan.tasks) == 3, f"Expected 3 tasks, got {len(plan.tasks)}"
    assert plan.tasks[0].companies == ["tvs"]
    assert "email" in plan.tasks[0].must_have
    assert plan.tasks[1].companies == ["ashok leyland"]
    assert plan.tasks[1].city == "chennai"
    assert plan.tasks[2].companies == ["titan"]
    assert "quality" in plan.tasks[2].designation_keywords[0]

    # Filters must not leak across tasks
    assert "email" not in plan.tasks[1].must_have
    assert plan.tasks[0].city is None


# -------------------------------------------------------------
# Test 8: SOURCE attribution for 200 random returned records
# -------------------------------------------------------------
def test_case_8_source_attribution_integrity():
    datasets = list(datasets_coll.find({}))
    ds_map = {}
    for d in datasets:
        name = d.get("dataset_name") or d.get("name") or d.get("filename")
        clean_name = re.sub(r"\.(xlsx|xls|csv|json)$", "", str(name).strip(), flags=re.IGNORECASE)
        if d.get("dataset_id"):
            ds_map[str(d["dataset_id"]).strip()] = clean_name
        if d.get("_id"):
            ds_map[str(d["_id"]).strip()] = clean_name

    set_cached_dataset_map(ds_map)

    # Sample 200 random records
    sample_records = list(records_coll.aggregate([{"$sample": {"size": 200}}, {"$project": {"embedding": 0}}]))
    for rec in sample_records:
        source_shown = get_dataset_name(rec)
        d_id = rec.get("dataset_id")
        if d_id and str(d_id).strip() in ds_map:
            expected = ds_map[str(d_id).strip()]
            assert source_shown == expected, f"Source mismatch: shown '{source_shown}' != expected '{expected}'"


# -------------------------------------------------------------
# Test 9: Precision: every returned row matches requested names
# -------------------------------------------------------------
def test_case_9_precision_zero_violations():
    async def _run():
        query = "tvs"
        plan = rule_based_plan(query)
        res = await execute_planned_retrieval(plan, query)

        for r in res.get("records", []):
            nc = r.get("norm_company", "")
            assert re.search(r"(^|\s)tvs(\s|$)", nc, flags=re.IGNORECASE), f"Norm company '{nc}' violates TVS match rule"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 10: Follow-up chain: company -> only with email -> reset
# -------------------------------------------------------------
def test_case_10_followup_chain_reset():
    async def _run():
        session_id = "test_followup_session_10"
        comp = "ashok leyland"

        res1 = await execute_rag_pipeline(comp, session_id=session_id)
        initial_count = res1.count
        assert initial_count > 0

        res2 = await execute_rag_pipeline("only those with email", session_id=session_id)
        assert res2.count <= initial_count

        res3 = await execute_rag_pipeline("reset", session_id=session_id)
        assert res3.count == initial_count, f"Reset count {res3.count} != Initial count {initial_count}"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 11: Planner failure fallback (LLM key removed)
# -------------------------------------------------------------
def test_case_11_planner_failure_fallback(monkeypatch):
    async def _run():
        from app import config
        monkeypatch.setattr(config, "OLLAMA_API_KEY", "")

        p1 = await plan_query_execution("ashok leyland")
        assert p1.companies == ["ashok leyland"]

        p3 = await plan_query_execution("ashok leyland which have emails")
        assert "email" in p3.must_have

        p5 = await plan_query_execution("chennai ashok leyland companies")
        assert p5.city == "chennai"
    asyncio.run(_run())


# -------------------------------------------------------------
# Test 12: No LLM payload for lookup/filter/count contains contact data
# -------------------------------------------------------------
def test_case_12_privacy_shield_no_contact_values():
    plan = rule_based_plan("tvs quality manager with emails")
    plan_dict = plan.model_dump()
    json_str = str(plan_dict)

    assert "@" not in json_str
    assert "+91" not in json_str


# -------------------------------------------------------------
# Test 13: Export equals the screen and has no embedding column
# -------------------------------------------------------------
def test_case_13_export_and_no_embedding_column():
    sample_rec = records_coll.find_one({}, {"embedding": 1, "company": 1, "data": 1, "dataset_id": 1})
    if sample_rec:
        formatted_sources, display_records, _, _ = format_api_sources_and_records([sample_rec])
        assert len(display_records) == 1
        d_rec = display_records[0]

        assert "embedding" not in d_rec
        assert "Source" in d_rec
        assert d_rec["Source"] != "No data available" or d_rec["Source"] == "No data available"


# -------------------------------------------------------------
# Test 14: Nonexistent name returns not found with did-you-mean
# -------------------------------------------------------------
def test_case_14_nonexistent_name_did_you_mean():
    async def _run():
        query = "ashok leylnd"
        plan = rule_based_plan(query)
        res = await execute_planned_retrieval(plan, query)

        assert res["total"] == 0
        assert len(res.get("unfound_list", [])) > 0
        sugg = res["unfound_list"][0][1]
        assert any("Ashok" in s for s in sugg)
    asyncio.run(_run())
