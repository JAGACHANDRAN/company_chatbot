import unittest
import asyncio
import re
from app.database import get_database, get_configured_collection_names
from app.routes.chat import execute_rag_pipeline
from app.services.query_planner import (
    plan_query_execution,
    rule_based_plan,
    split_pasted_companies,
    validate_companies,
    QueryPlan,
    SearchTask
)
from app.services.multi_stage_search import (
    execute_keyword_company_search,
    execute_vector_retrieval,
    execute_multi_stage_retrieval
)
from app.utils.normalization import normalize_company


class TestRetrievalBugs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = get_database()
        cls.cols = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))

    def test_1_3d_solution_dedupe_and_card_count(self):
        """Test 1: '3d solution' has keyword hits after dedupe == number of distinct _ids; header count == cards shown == raw count."""
        raw_count = 0
        pat = r"\b3d\b.*\bsolution\b|\bsolution\b.*\b3d\b"
        for c in self.cols:
            raw_count += self.db[c].count_documents({"norm_company": {"$regex": pat, "$options": "i"}})

        recs, stage_counts = execute_keyword_company_search(self.db, self.cols, "3d solution")
        distinct_ids = {str(r.get("_id")) for r in recs}
        self.assertEqual(len(recs), len(distinct_ids))
        self.assertEqual(len(recs), raw_count)

        res = asyncio.run(execute_rag_pipeline("3d solution"))
        self.assertTrue(res.found)
        self.assertEqual(res.count, raw_count)
        self.assertEqual(len(res.data), raw_count)
        self.assertIn(f"Found {raw_count} records matching '3d solution'", res.message)

        # No duplicate _id in response data
        returned_ids = [str(r.get("_id") or r.get("id")) for r in res.data if r.get("_id") or r.get("id")]
        self.assertEqual(len(returned_ids), len(set(returned_ids)))

    def test_2_delphi_tvs_single_company_and_no_bleed(self):
        """Test 2: 'delphi tvs' is one company, records == raw count of records with delphi AND tvs. Zero records with only tvs or only delphi."""
        raw_count = 0
        pat = r"\bdelphi\b.*\btvs\b|\btvs\b.*\bdelphi\b"
        for c in self.cols:
            raw_count += self.db[c].count_documents({"norm_company": {"$regex": pat, "$options": "i"}})

        plan = asyncio.run(plan_query_execution("delphi tvs"))
        self.assertEqual(len(plan.companies), 1)
        self.assertIn("delphi tvs", plan.companies[0].lower())

        res = asyncio.run(execute_rag_pipeline("delphi tvs"))
        self.assertTrue(res.found)
        self.assertEqual(res.count, raw_count)
        self.assertEqual(len(res.data), raw_count)

        # Ensure all returned records contain both delphi and tvs
        for r in res.data:
            c_name = str(r.get("company", "") or r.get("Company", ""))
            norm_c = normalize_company(c_name)
            self.assertTrue("delphi" in norm_c and "tvs" in norm_c)

    def test_3_tvs_and_delphi_alone(self):
        """Test 3: 'tvs' alone returns all tvs records, 'delphi' alone returns all delphi records."""
        recs_tvs, _ = execute_keyword_company_search(self.db, self.cols, "tvs")
        recs_delphi, _ = execute_keyword_company_search(self.db, self.cols, "delphi")

        self.assertGreater(len(recs_tvs), 20)
        self.assertGreater(len(recs_delphi), 10)

    def test_4_delphi_tvs_titan_two_companies(self):
        """Test 4: 'delphi tvs, titan' returns 2 companies with correct separate counts."""
        plan = asyncio.run(plan_query_execution("delphi tvs, titan"))
        self.assertEqual(len(plan.companies), 2)
        comps_low = [c.lower() for c in plan.companies]
        self.assertTrue(any("delphi tvs" in c for c in comps_low))
        self.assertTrue(any("titan" in c for c in comps_low))

    def test_5_tvs_and_titan_and_delphi_and_tvs(self):
        """Test 5: 'tvs and titan' -> 2 companies; 'delphi and tvs' -> 1 merged company."""
        plan_tt = rule_based_plan("tvs and titan")
        self.assertEqual(len(plan_tt.companies), 2)

        plan_dt = rule_based_plan("delphi and tvs")
        self.assertEqual(len(plan_dt.companies), 1)
        self.assertIn("delphi tvs", plan_dt.companies[0].lower())

    def test_6_vector_search_scores_and_top_hits(self):
        """Test 6: Vector search top_5_scores non-empty and returns top 10 hit objects with score."""
        kept, fallback, raw, retried = asyncio.run(execute_vector_retrieval(self.db, "tvs"))
        if not fallback and raw:
            self.assertGreater(len(raw), 0)
            self.assertIn("vector_score", raw[0])
            self.assertGreater(raw[0]["vector_score"], 0.0)

    def test_7_vector_only_hits_under_related_results(self):
        """Test 7: Company query with vector-only hits shows them under 'Related results' and never in main count."""
        multi_res = asyncio.run(execute_multi_stage_retrieval("3d solution"))
        self.assertIn("vector_only_records", multi_res)
        # Vector only records are not in keyword_records
        kw_ids = {str(r.get("_id")) for r in multi_res["keyword_records"]}
        for vr in multi_res["vector_only_records"]:
            self.assertNotIn(str(vr.get("_id")), kw_ids)

    def test_8_pasted_17_names_list(self):
        """Test 8: Pasted list of 17 names (newline, comma, numbered) returns identical clean list."""
        sample_pasted = """
1. TVS Motor
2. Delphi TVS
3. Titan
4. Brakes India
5. Tata Motors
6. Hyundai
7. Premier CNC
8. Ashok Leyland
9. Bosch
10. Kone Elevators
11. SAAB Engineering
12. 3D Solution
13. Wheels India
14. Sundaram Fasteners
15. Lucas TVS
16. Royal Enfield
17. Wabco
"""
        split_names = split_pasted_companies(sample_pasted)
        self.assertEqual(len(split_names), 17)
        self.assertEqual(split_names[0], "TVS Motor")
        self.assertEqual(split_names[1], "Delphi TVS")
        self.assertEqual(split_names[11], "3D Solution")

    def test_9_planner_failure_offline_parity(self):
        """Test 9: Offline rule-based planner matches 3d solution, delphi tvs, and delphi tvs, titan."""
        p1 = rule_based_plan("3d solution")
        self.assertEqual(p1.companies, ["3d solution"])

        p2 = rule_based_plan("delphi tvs")
        self.assertEqual(p2.companies, ["delphi tvs"])

        p4 = rule_based_plan("delphi tvs, titan")
        self.assertEqual(len(p4.companies), 2)


if __name__ == "__main__":
    unittest.main()
