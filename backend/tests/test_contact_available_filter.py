import os
import sys
import pytest
import asyncio
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import get_database, get_configured_collection_names
from app.services.query_planner import (
    plan_query_execution,
    rule_based_plan,
    execute_planned_retrieval,
    validate_filters,
    QueryPlan,
    SearchTask
)
from app.services.multi_stage_search import execute_keyword_company_search
from app.services.response_generator import get_contact_fields


@pytest.fixture(scope="module")
def tvs_raw_data():
    db = get_database()
    cols = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))
    raw_records, _ = execute_keyword_company_search(db, cols, "tvs")
    raw_total = len(raw_records)

    raw_with_contact = [
        r for r in raw_records
        if bool(get_contact_fields(r).get("emails")) or bool(get_contact_fields(r).get("phones"))
    ]
    raw_with_email = [
        r for r in raw_records
        if bool(get_contact_fields(r).get("emails"))
    ]
    raw_with_both = [
        r for r in raw_records
        if bool(get_contact_fields(r).get("emails")) and bool(get_contact_fields(r).get("phones"))
    ]

    return {
        "raw_records": raw_records,
        "raw_total": raw_total,
        "raw_with_contact": raw_with_contact,
        "raw_with_email": raw_with_email,
        "raw_with_both": raw_with_both
    }


def test_1_tvs_contact_available_list(tvs_raw_data):
    """
    'tvs contact available list': result count == raw count of TVS records with a real
    email or phone; every card shows an email or phone; count_after < count_before.
    """
    raw_contact_count = len(tvs_raw_data["raw_with_contact"])
    raw_total = tvs_raw_data["raw_total"]

    plan = rule_based_plan("tvs contact available list")
    assert plan.companies == ["tvs"]
    assert "contact" in plan.must_have

    res = asyncio.run(execute_planned_retrieval(plan, "tvs contact available list"))
    result_records = res["records"]
    count_after = res["total"]
    count_before = res.get("candidates_before_filter", raw_total)

    assert count_after == raw_contact_count
    assert count_after < count_before
    assert count_before == raw_total

    # Every record has at least one real email or phone
    for r in result_records:
        cf = get_contact_fields(r)
        has_email = bool(cf.get("emails"))
        has_phone = bool(cf.get("phones"))
        assert has_email or has_phone, f"Record {r.get('_id')} missing both email and phone"

    assert f"Found {raw_total} TVS records" in res["summary_header"]
    assert f"{raw_contact_count} have contact details (email or phone)" in res["summary_header"]


def test_2_tvs_contact_list_no_filter(tvs_raw_data):
    """
    'tvs contact list': all TVS records, no filter.
    """
    raw_total = tvs_raw_data["raw_total"]

    plan = rule_based_plan("tvs contact list")
    assert plan.companies == ["tvs"]
    assert "contact" not in plan.must_have
    assert len(plan.must_have) == 0

    res = asyncio.run(execute_planned_retrieval(plan, "tvs contact list"))
    assert res["total"] == raw_total
    assert len(res["records"]) == raw_total
    assert len(res.get("filter_events", [])) == 0


def test_3_tvs_emails_available(tvs_raw_data):
    """
    'tvs emails available': equals raw count with a real email.
    """
    raw_email_count = len(tvs_raw_data["raw_with_email"])
    raw_total = tvs_raw_data["raw_total"]

    plan = rule_based_plan("tvs emails available")
    assert plan.companies == ["tvs"]
    assert "email" in plan.must_have

    res = asyncio.run(execute_planned_retrieval(plan, "tvs emails available"))
    assert res["total"] == raw_email_count

    for r in res["records"]:
        cf = get_contact_fields(r)
        assert bool(cf.get("emails")), f"Record {r.get('_id')} missing email"

    assert f"Found {raw_total} TVS records" in res["summary_header"]
    assert f"{raw_email_count} have an email" in res["summary_header"]


def test_4_tvs_phone_and_email_available(tvs_raw_data):
    """
    'tvs phone and email available': both present on every record.
    """
    raw_both_count = len(tvs_raw_data["raw_with_both"])
    raw_total = tvs_raw_data["raw_total"]

    plan = rule_based_plan("tvs phone and email available")
    assert plan.companies == ["tvs"]
    assert "phone" in plan.must_have
    assert "email" in plan.must_have

    res = asyncio.run(execute_planned_retrieval(plan, "tvs phone and email available"))
    assert res["total"] == raw_both_count

    # Both present on every record
    for r in res["records"]:
        cf = get_contact_fields(r)
        assert bool(cf.get("emails")), f"Record {r.get('_id')} missing email"
        assert bool(cf.get("phones")), f"Record {r.get('_id')} missing phone"

    assert f"Found {raw_total} TVS records" in res["summary_header"]
    assert f"{raw_both_count} have both phone and email" in res["summary_header"]


def test_5_planner_failure_offline_parity(tvs_raw_data):
    """
    Planner failure (LLM key removed or network failure) gives identical results.
    """
    test_queries = [
        "tvs contact available list",
        "tvs contact list",
        "tvs emails available",
        "tvs phone and email available"
    ]

    for q in test_queries:
        rule_plan = rule_based_plan(q)

        # Force plan_query_execution to trigger fallback (LLM key removed / connection failure)
        with patch("httpx.AsyncClient.post", side_effect=Exception("LLM unreachable")):
            fallback_plan = asyncio.run(plan_query_execution(q))

        assert rule_plan.companies == fallback_plan.companies
        assert set(rule_plan.must_have) == set(fallback_plan.must_have)
        assert rule_plan.filters_removed_by_guard == fallback_plan.filters_removed_by_guard

        rule_res = asyncio.run(execute_planned_retrieval(rule_plan, q))
        fallback_res = asyncio.run(execute_planned_retrieval(fallback_plan, q))

        assert rule_res["total"] == fallback_res["total"]
        assert len(rule_res["records"]) == len(fallback_res["records"])
        assert rule_res["summary_header"] == fallback_res["summary_header"]


def test_6_guard_removes_unsolicited_contact_filter():
    """
    Test guard behavior: If LLM produces must_have=['contact'] for 'tvs contact list',
    the guard removes it and sets filters_removed_by_guard=True.
    """
    task = SearchTask(companies=["tvs"], must_have=["contact"])
    plan = QueryPlan(tasks=[task])
    guarded_plan = validate_filters(plan, "tvs contact list")

    assert "contact" not in guarded_plan.must_have
    assert guarded_plan.filters_removed_by_guard is True
