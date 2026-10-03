import unittest
import asyncio
from app.services.query_understanding import fallback_query_understanding, StructuredQuery
from app.services.query_router import route_query
from app.services.mongo_search import build_structured_mongo_filter
from app.utils.deduplication import deduplicate_records
from app.utils.normalization import normalize_record_fields
from app.services.response_generator import generate_deterministic_answer


class TestRAGPipeline(unittest.TestCase):

    def test_query_understanding_multi_companies(self):
        """Verify multiple companies are parsed as distinct list items, not collapsed."""
        q = "Show ABC, XYZ and PQR companies"
        sq = fallback_query_understanding(q)
        self.assertIn("ABC", sq.companies)
        self.assertIn("XYZ", sq.companies)
        self.assertIn("PQR", sq.companies)
        self.assertEqual(len(sq.companies), 3)

    def test_query_understanding_single_company(self):
        q = "Show ABC company"
        sq = fallback_query_understanding(q)
        self.assertEqual(sq.companies, ["ABC"])
        self.assertEqual(sq.intent, "company_search")

    def test_dynamic_location_search_andhra_pradesh(self):
        """Verify state is extracted and NOT treated as a company."""
        q = "Which companies are in Andhra Pradesh?"
        sq = fallback_query_understanding(q)
        self.assertEqual(sq.state, "Andhra Pradesh")
        self.assertEqual(len(sq.companies), 0)

    def test_dynamic_location_search_tamil_nadu(self):
        """Verify location is fully dynamic without hardcoding."""
        q = "Which companies are in Tamil Nadu?"
        sq = fallback_query_understanding(q)
        self.assertEqual(sq.state, "Tamil Nadu")
        self.assertEqual(len(sq.companies), 0)

    def test_dynamic_location_search_karnataka(self):
        q = "Give me all companies in Karnataka"
        sq = fallback_query_understanding(q)
        self.assertEqual(sq.state, "Karnataka")
        self.assertEqual(len(sq.companies), 0)

    def test_dynamic_location_search_chennai(self):
        q = "Which companies are available in Chennai?"
        sq = fallback_query_understanding(q)
        self.assertTrue(sq.city == "Chennai" or sq.location == "Chennai")
        self.assertEqual(len(sq.companies), 0)

    def test_dynamic_location_search_maharashtra(self):
        q = "Quality managers in Maharashtra"
        sq = fallback_query_understanding(q)
        self.assertEqual(sq.state, "Maharashtra")
        self.assertIn("Quality", sq.designation or sq.department)

    def test_person_search(self):
        """Verify person is extracted and NOT treated as a company."""
        q = "Find Ravi Kumar"
        sq = fallback_query_understanding(q)
        self.assertIn("Ravi Kumar", sq.people)
        self.assertEqual(len(sq.companies), 0)

    def test_role_and_dynamic_location(self):
        q = "Show quality managers in Andhra Pradesh"
        sq = fallback_query_understanding(q)
        self.assertIn("Quality", sq.designation)
        self.assertEqual(sq.state, "Andhra Pradesh")

    def test_multi_company_quality_contacts(self):
        q = "Give me quality contacts from ABC, XYZ and PQR"
        sq = fallback_query_understanding(q)
        self.assertIn("ABC", sq.companies)
        self.assertIn("XYZ", sq.companies)
        self.assertIn("PQR", sq.companies)
        self.assertEqual(sq.department, "Quality")

    def test_query_router_strategies(self):
        # 1. Exact entity
        plan1 = route_query(fallback_query_understanding("Show ABC company"))
        self.assertEqual(plan1.search_strategy, "exact_entity")

        # 2. Multi-value structured
        plan2 = route_query(fallback_query_understanding("Show ABC, XYZ and PQR companies"))
        self.assertEqual(plan2.search_strategy, "multi_value_structured")

        # 3. Location filter
        plan3 = route_query(fallback_query_understanding("Companies in Andhra Pradesh"))
        self.assertEqual(plan3.search_strategy, "location_filter")

        # 4. Person search
        plan4 = route_query(fallback_query_understanding("Find Ravi Kumar"))
        self.assertEqual(plan4.search_strategy, "person_search")

        # 5. Hybrid
        plan5 = route_query(fallback_query_understanding("Quality managers in Andhra Pradesh"))
        self.assertEqual(plan5.search_strategy, "hybrid")

        # 6. Semantic
        plan6 = route_query(fallback_query_understanding("Who is responsible for quality operations?"))
        self.assertEqual(plan6.search_strategy, "semantic_vector")

    def test_mongo_filter_multi_company(self):
        sq = StructuredQuery(
            intent="company_search",
            companies=["ABC", "XYZ", "PQR"],
            original_query="Show ABC, XYZ and PQR companies"
        )
        f = build_structured_mongo_filter(sq, is_dataset_records=True)
        self.assertIn("$or", f)
        # Should have clauses for each company
        clauses_str = str(f["$or"])
        self.assertIn("ABC", clauses_str)
        self.assertIn("XYZ", clauses_str)
        self.assertIn("PQR", clauses_str)

    def test_deduplication_preserves_distinct_people(self):
        """Ravi Kumar and Priya Kumar at the same company must NOT be collapsed."""
        records = [
            {
                "company_name": "ABC Industries",
                "person_name": "Ravi Kumar",
                "designation": "Quality Manager",
                "contact_number": "9876543210",
                "source_file": "File 1"
            },
            {
                "company_name": "ABC Industries",
                "person_name": "Priya Kumar",
                "designation": "Quality Manager",
                "contact_number": "9876543211",
                "source_file": "File 2"
            }
        ]
        deduped = deduplicate_records(records)
        self.assertEqual(len(deduped), 2)
        people = [r["person_name"] for r in deduped]
        self.assertIn("Ravi Kumar", people)
        self.assertIn("Priya Kumar", people)

    def test_deduplication_preserves_source_separation(self):
        """Records from different files must NOT be merged into one artificial record."""
        records = [
            {
                "company_name": "ABC",
                "person_name": "Ravi Kumar",
                "designation": "Quality Manager",
                "contact_number": "9876543210",
                "personal_mail_id": "ravi@abc.com",
                "source_file": "File 1.csv",
                "source_collection": "collection_a"
            },
            {
                "company_name": "ABC",
                "person_name": "Ravi Kumar",
                "designation": "Quality Manager",
                "contact_number": "9876543210",
                "personal_mail_id": "ravi@abc.com",
                "source_file": "File 2.xlsx",
                "source_collection": "collection_b"
            }
        ]
        # By default preserve_source_separation=True keeps them separated per source
        deduped = deduplicate_records(records, preserve_source_separation=True)
        self.assertEqual(len(deduped), 2)

        # Identical duplicates within the SAME source file/collection are deduped
        identical_records = [
            {"company_name": "ABC", "source_file": "File 1.csv", "source_collection": "col_a"},
            {"company_name": "ABC", "source_file": "File 1.csv", "source_collection": "col_a"}
        ]
        deduped_identical = deduplicate_records(identical_records, preserve_source_separation=True)
        self.assertEqual(len(deduped_identical), 1)

    def test_empty_results_returns_no_data_found(self):
        sq = StructuredQuery(original_query="Find unknown company")
        ans = generate_deterministic_answer("Find unknown company", sq, [])
        self.assertEqual(ans, "No data found")

    def test_exact_company_2d_inc_validation(self):
        """Exact company query '2D INC' must reject unrelated high-similarity vector results."""
        from app.services.retrieval_service import validate_record_relevance
        sq = fallback_query_understanding("2D INC")
        self.assertEqual(sq.companies, ["2D INC"])

        # Genuine match
        valid_rec = {"company_name": "2D INC", "norm_company_name": "2d inc"}
        self.assertTrue(validate_record_relevance(valid_rec, sq))

        # Unrelated vector hallucination candidates must be rejected
        unrelated = [
            {"company_name": "ACCUMEN AUTOMATION - CAL CBE", "norm_company_name": "accumen automation cal cbe"},
            {"company_name": "AKSHARA INDUSTRIES - CAL CBE", "norm_company_name": "akshara industries cal cbe"},
            {"company_name": "AIR FILL - CAL CBE", "norm_company_name": "air fill cal cbe"},
            {"company_name": "A.K.Automatics (III)", "norm_company_name": "a k automatics iii"},
            {"company_name": "ADqIK HITECH PVT. LTD", "norm_company_name": "adqik hitech pvt ltd"}
        ]
        for bad_rec in unrelated:
            self.assertFalse(validate_record_relevance(bad_rec, sq), f"Failed to reject: {bad_rec['company_name']}")

    def test_exact_company_abc_query(self):
        """Query 'ABC' must route to exact_entity and reject XYZ."""
        from app.services.retrieval_service import validate_record_relevance
        sq = fallback_query_understanding("ABC")
        self.assertEqual(sq.companies, ["ABC"])
        plan = route_query(sq)
        self.assertEqual(plan.search_strategy, "exact_entity")
        self.assertFalse(plan.use_vector)

        self.assertTrue(validate_record_relevance({"company_name": "ABC"}, sq))
        self.assertFalse(validate_record_relevance({"company_name": "XYZ Corp"}, sq))

    def test_multi_company_abc_tvs_2d_inc(self):
        """Query 'ABC, TVS and 2D INC' must extract all 3 independently."""
        sq = fallback_query_understanding("ABC, TVS and 2D INC")
        self.assertIn("ABC", sq.companies)
        self.assertIn("TVS", sq.companies)
        self.assertIn("2D INC", sq.companies)
        self.assertEqual(len(sq.companies), 3)

        plan = route_query(sq)
        self.assertEqual(plan.search_strategy, "multi_value_structured")
        self.assertFalse(plan.use_vector)

    def test_person_ravi_kumar_relevance_guard(self):
        """Query 'Find Ravi Kumar' must accept Ravi Kumar and reject unrelated people."""
        from app.services.retrieval_service import validate_record_relevance
        sq = fallback_query_understanding("Find Ravi Kumar")
        self.assertIn("Ravi Kumar", sq.people)

        # Genuine match
        self.assertTrue(validate_record_relevance({"person_name": "Ravi Kumar"}, sq))
        # Unrelated person must be rejected
        self.assertFalse(validate_record_relevance({"person_name": "Priya Sharma"}, sq))
        self.assertFalse(validate_record_relevance({"person_name": "Ravi Teja"}, sq))

    def test_companies_in_tamil_nadu_location_guard(self):
        """Structured location query must require state match and not hallucinate other states."""
        from app.services.retrieval_service import validate_record_relevance
        sq = fallback_query_understanding("Companies in Tamil Nadu")
        self.assertEqual(sq.state, "Tamil Nadu")

        # Tamil Nadu match
        self.assertTrue(validate_record_relevance({"state": "Tamil Nadu", "company_name": "TVS"}, sq))
        self.assertTrue(validate_record_relevance({"address": "Hosur, Tamil Nadu", "company_name": "TVS"}, sq))

        # Different state must be rejected
        self.assertFalse(validate_record_relevance({"state": "Karnataka", "company_name": "Infosys"}, sq))

    def test_quality_managers_in_tamil_nadu_hybrid_routing(self):
        """Query 'Quality managers in Tamil Nadu' routes to hybrid with hard state filter."""
        from app.services.retrieval_service import validate_record_relevance
        sq = fallback_query_understanding("Quality managers in Tamil Nadu")
        self.assertEqual(sq.state, "Tamil Nadu")
        self.assertIn("Quality", sq.designation or sq.department)

        plan = route_query(sq, privacy_mode=False)
        self.assertEqual(plan.search_strategy, "hybrid")
        self.assertTrue(plan.use_structured)
        self.assertTrue(plan.use_vector)

        # Karnataka record must be rejected even with matching designation
        bad_rec = {"designation": "Quality Manager", "state": "Karnataka"}
        self.assertFalse(validate_record_relevance(bad_rec, sq))

        good_rec = {"designation": "Quality Manager", "state": "Tamil Nadu"}
        self.assertTrue(validate_record_relevance(good_rec, sq))

    def test_semantic_query_routing(self):
        """Query 'Who is responsible for quality operations?' routes to semantic vector."""
        sq = fallback_query_understanding("Who is responsible for quality operations?")
        plan = route_query(sq, privacy_mode=False)
        self.assertEqual(plan.search_strategy, "semantic_vector")
        self.assertTrue(plan.use_vector)

    def test_source_grouping_tvs_in_two_files(self):
        """TVS appearing in File A and File C must produce two separate source groups."""
        from app.services.retrieval_service import group_records_by_source
        records = [
            {
                "company_name": "TVS",
                "person_name": "Ravi",
                "source_file": "file_a.xlsx",
                "source_collection": "collection_a",
                "database_source": "MongoDB Atlas",
                "raw_data": {"Company Name": "TVS", "Person Name": "Ravi", "Phone": "123"}
            },
            {
                "company_name": "TVS",
                "person_name": "Kumar",
                "source_file": "file_c.xlsx",
                "source_collection": "collection_c",
                "database_source": "MongoDB Atlas",
                "raw_data": {"Company": "TVS", "Contact Person": "Kumar", "Email": "test@example.com", "Location": "Chennai"}
            }
        ]
        groups = group_records_by_source(records)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["source_file"], "file_a.xlsx")
        self.assertEqual(groups[1]["source_file"], "file_c.xlsx")

        # Test deterministic output preserves source file association under STRICT RESPONSE FORMATTER rules
        sq = fallback_query_understanding("Find TVS")
        ans = generate_deterministic_answer("Find TVS", sq, records)
        self.assertNotIn("SOURCE 1", ans)
        self.assertNotIn("SOURCE 2", ans)
        self.assertIn("Source File: file_a.xlsx", ans)
        self.assertIn("Source File: file_c.xlsx", ans)
        self.assertIn("Company Name: TVS", ans)
        self.assertIn("Contact Person 1:", ans)
        self.assertIn("Ravi", ans)
        self.assertIn("Kumar", ans)

    def test_same_company_three_files_different_schemas(self):
        """Same company in 3 files with different schemas must preserve each source's association."""
        from app.services.retrieval_service import group_records_by_source
        records = [
            {
                "company_name": "TVS",
                "source_file": "file_a.xlsx",
                "source_collection": "col_a",
                "raw_data": {"Company Name": "TVS", "Person Name": "Ravi", "Phone": "123"}
            },
            {
                "company_name": "TVS",
                "source_file": "file_b.xlsx",
                "source_collection": "col_b",
                "raw_data": {"Company": "TVS", "Contact": "Suresh", "Department": "Production"}
            },
            {
                "company_name": "TVS",
                "source_file": "file_c.xlsx",
                "source_collection": "col_c",
                "raw_data": {"Organization": "TVS", "Contact Person": "Kumar", "Customer Type": "Industrial"}
            }
        ]
        groups = group_records_by_source(records)
        self.assertEqual(len(groups), 3)

        sq = fallback_query_understanding("Find TVS")
        ans = generate_deterministic_answer("Find TVS", sq, records)
        self.assertNotIn("SOURCE 1", ans)
        self.assertNotIn("SOURCE 2", ans)
        self.assertNotIn("SOURCE 3", ans)
        self.assertIn("Source File: file_a.xlsx", ans)
        self.assertIn("Source File: file_b.xlsx", ans)
        self.assertIn("Source File: file_c.xlsx", ans)
        self.assertIn("Company Name: TVS", ans)
        # Disallowed/internal database fields must never be displayed
        self.assertNotIn("Customer Type", ans)
        self.assertNotIn("Department", ans)



if __name__ == "__main__":
    unittest.main()
