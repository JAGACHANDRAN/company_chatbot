import unittest
from app.services.query_understanding import fallback_query_understanding, StructuredQuery
from app.services.response_generator import generate_deterministic_answer
from app.utils.normalization import normalize_record_fields, extract_original_source_fields
from app.routes.chat import format_api_sources_and_records


class TestSourceSchemaPreservation(unittest.TestCase):

    def test_test1_tvs_motor_company_actual_columns_only(self):
        """
        TEST 1:
        Query: TVS Motor Company
        Expected:
        Dataset: dataset_records
        Database: MongoDB Atlas
        Source File: Company Leadership Database - Sheet1.csv
        Source Row: 8
        Then ONLY the actual columns from that CSV row.
        No extra: Department, State, City, Country, Location, Norm Company Name, Norm Person Name.
        """
        # Simulated raw doc from dataset_records row 8
        raw_doc = {
            "_id": "6ab8ca3df2fa7140373fe4c4",
            "dataset_id": "ds_1deae915a5bd",
            "record_index": 7,  # Row 8
            "data": {
                "Company Name": "TVS Motor Company",
                "Person Name": "Shreethan Srinivasaiah Shetty",
                "Designation": "Senior Quality Engineer",
                "LinkedIn URL": "https://in.linkedin.com/in/shreethan-srinivasaiah-shetty-b8094b185",
                "Contact Number": "No",
                "Contact Source": "No"
            },
            "source_file": "Company Leadership Database - Sheet1.csv",
            "source_collection": "dataset_records",
            "database_source": "MongoDB Atlas"
        }

        norm_rec = normalize_record_fields(raw_doc, source_file="Company Leadership Database - Sheet1.csv", source_row=8)
        self.assertEqual(norm_rec["source_row"], 8)
        self.assertEqual(norm_rec["source_file"], "Company Leadership Database - Sheet1.csv")

        # Check extracted source fields
        source_fields = extract_original_source_fields(norm_rec)
        expected_keys = {"Company Name", "Person Name", "Designation", "LinkedIn URL", "Contact Number", "Contact Source"}
        self.assertEqual(set(source_fields.keys()), expected_keys)

        # Must NOT contain non-existing columns
        self.assertNotIn("Department", source_fields)
        self.assertNotIn("State", source_fields)
        self.assertNotIn("City", source_fields)
        self.assertNotIn("Country", source_fields)
        self.assertNotIn("Location", source_fields)
        self.assertNotIn("norm_company_name", source_fields)
        self.assertNotIn("norm_person_name", source_fields)
        self.assertNotIn("raw_data", source_fields)

        # Test final formatted answer
        sq = fallback_query_understanding("TVS Motor Company")
        ans = generate_deterministic_answer("TVS Motor Company", sq, [norm_rec])

        # ONLY source file name alone at top - no Dataset: or Database:
        self.assertNotIn("Dataset:", ans)
        self.assertNotIn("Database:", ans)
        self.assertIn("**Source File: Company Leadership Database - Sheet1.csv**", ans)
        self.assertIn("**Source Row: 8**", ans)
        self.assertIn("Company Name: TVS Motor Company", ans)
        self.assertIn("Person Name: Shreethan Srinivasaiah Shetty", ans)
        self.assertIn("Designation: Senior Quality Engineer", ans)

        # URL must be a markdown hyperlink
        self.assertIn("[https://in.linkedin.com/in/shreethan-srinivasaiah-shetty-b8094b185](https://in.linkedin.com/in/shreethan-srinivasaiah-shetty-b8094b185)", ans)

        # Ensure NO extra fields in final text answer
        self.assertNotIn("Department:", ans)
        self.assertNotIn("State:", ans)
        self.assertNotIn("City:", ans)
        self.assertNotIn("Country:", ans)
        self.assertNotIn("Location:", ans)
        self.assertNotIn("Norm Company Name", ans)
        self.assertNotIn("norm_company_name", ans)
        self.assertNotIn("SOURCE 1", ans)
        self.assertNotIn("Record 1", ans)

    def test_test2_tvs_in_two_different_files_different_schemas(self):
        """
        TEST 2:
        If TVS exists in two different files with different columns:
        Return two separate source sections separated with ---.
        Do NOT label them SOURCE 1, SOURCE 2, etc.
        Each section must contain only the columns from that source.
        """
        file_a_rec = {
            "source_file": "File A.csv",
            "source_collection": "dataset_records",
            "database_source": "MongoDB Atlas",
            "source_fields": {
                "Company Name": "TVS",
                "Person Name": "Ravi",
                "Phone": "123456",
                "Location": "Chennai",
                "Region": "South"
            }
        }
        file_b_rec = {
            "source_file": "File B.csv",
            "source_collection": "dataset_records",
            "database_source": "MongoDB Atlas",
            "source_fields": {
                "Company": "TVS",
                "Contact": "Kumar",
                "Email": "abc@example.com",
                "Department": "Production"
            }
        }

        sq = fallback_query_understanding("Find TVS")
        ans = generate_deterministic_answer("Find TVS", sq, [file_a_rec, file_b_rec])

        self.assertNotIn("SOURCE 1", ans)
        self.assertNotIn("SOURCE 2", ans)
        self.assertNotIn("Record 1", ans)
        self.assertNotIn("Dataset:", ans)
        self.assertNotIn("Database:", ans)
        self.assertIn("---", ans)

        sections = ans.split("---")
        self.assertEqual(len(sections), 2)

        section_1 = sections[0]
        section_2 = sections[1]

        self.assertIn("**Source File: File A.csv**", section_1)
        self.assertIn("Company Name: TVS", section_1)
        self.assertIn("Phone: 123456", section_1)
        self.assertIn("Region: South", section_1)
        self.assertNotIn("Department: Production", section_1)

        self.assertIn("**Source File: File B.csv**", section_2)
        self.assertIn("Company: TVS", section_2)
        self.assertIn("Contact: Kumar", section_2)
        # Email must be formatted as hyperlink
        self.assertIn("[abc@example.com](mailto:abc@example.com)", section_2)
        self.assertIn("Department: Production", section_2)
        self.assertNotIn("Region: South", section_2)

    def test_test3_empty_column_behavior(self):
        """
        TEST 3:
        If a source has an empty column value:
        - If the column exists in the file but value is empty: Column: Not Available
        - If the column itself does not exist: Do not display the column.
        """
        rec = {
            "source_file": "customers.csv",
            "source_collection": "dataset_records",
            "database_source": "MongoDB Atlas",
            "source_fields": {
                "Company Name": "Acme Corp",
                "Person Name": "Alice",
                "Department": "Not Available"  # Existed in source file but empty
            }
        }
        sq = fallback_query_understanding("Acme Corp")
        ans = generate_deterministic_answer("Acme Corp", sq, [rec])

        self.assertIn("Company Name: Acme Corp", ans)
        self.assertIn("Person Name: Alice", ans)
        self.assertIn("Department: Not Available", ans)
        # Non-existing columns must NOT appear at all
        self.assertNotIn("State:", ans)
        self.assertNotIn("City:", ans)
        self.assertNotIn("LinkedIn URL:", ans)

    def test_test4_no_object_object(self):
        """
        TEST 4:
        Ensure the output and API representation never show 'Raw Data: [object Object]' or '[object Object]'.
        """
        raw_doc = {
            "_id": "6ab8ca3df2fa7140373fe4c4",
            "data": {
                "Company Name": "TVS Motor Company",
                "Person Name": "Ravi"
            },
            "source_file": "test.csv",
            "source_collection": "dataset_records",
            "database_source": "MongoDB Atlas"
        }
        norm_rec = normalize_record_fields(raw_doc)
        formatted_sources, display_records, _, _ = format_api_sources_and_records([norm_rec])

        # Verify in display records
        for d in display_records:
            self.assertNotIn("raw_data", d)
            for k, v in d.items():
                self.assertNotEqual(v, "[object Object]")
                self.assertFalse(isinstance(v, (dict, list)), f"Key {k} contains nested object: {v}")

        # Verify in text answer
        sq = fallback_query_understanding("TVS")
        ans = generate_deterministic_answer("TVS", sq, [norm_rec])
        self.assertNotIn("[object Object]", ans)
        self.assertNotIn("Raw Data", ans)

    def test_test5_no_normalized_fields_in_output(self):
        """
        TEST 5:
        Ensure normalized fields (norm_company_name, norm_person_name, search_text, embedding)
        are never shown in user-facing responses.
        """
        raw_doc = {
            "_id": "6ab8ca3df2fa7140373fe4c4",
            "data": {
                "Company Name": "2D INC",
                "Address": "Coimbatore"
            },
            "source_file": "metrology.xlsx",
            "source_collection": "metrology",
            "database_source": "MongoDB Atlas"
        }
        norm_rec = normalize_record_fields(raw_doc)
        formatted_sources, display_records, _, _ = format_api_sources_and_records([norm_rec])

        forbidden = [
            "norm_company_name", "norm_person_name", "norm_designation", "norm_department",
            "norm_state", "norm_city", "norm_country", "norm_location",
            "_norm_company_name", "search_text", "embedding", "vector_score", "retrieval_score"
        ]

        for d in display_records:
            for f in forbidden:
                self.assertNotIn(f, d)

        sq = fallback_query_understanding("2D INC")
        ans = generate_deterministic_answer("2D INC", sq, [norm_rec])
        for f in forbidden:
            self.assertNotIn(f, ans)


if __name__ == "__main__":
    unittest.main()
