import asyncio
import json
import re
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.mongo_search import build_safe_dataset_filter
from app.services.query_parser import deterministic_parse_query, parse_query_with_privacy_llm
from app.search import build_mongo_query


class QueryParserTests(unittest.TestCase):
    def setUp(self):
        self.fields = ["Company Name", "Contact Person", "Email", "Phone Number", "Address", "Designation"]

    def test_field_questions_separate_target_and_return_fields(self):
        examples = {
            "What is the email in 2dinc?": ("2dinc", ["Email"]),
            "What is the email of 2dinc?": ("2dinc", ["Email"]),
            "Give me the email for 2dinc.": ("2dinc", ["Email"]),
            "What is the phone number of ABC Industries?": ("ABC Industries", ["Phone Number"]),
            "Give me the address of ABC Industries.": ("ABC Industries", ["Address"]),
            "What is the designation of John Smith?": ("John Smith", ["Designation"]),
            "Show me the email and phone number of ABC Industries.": (
                "ABC Industries",
                ["Email", "Phone Number"],
            ),
            "What are the details of ABC Industries?": ("ABC Industries", ["*"]),
        }

        for question, (target, requested_fields) in examples.items():
            with self.subTest(question=question):
                matched, intent = deterministic_parse_query(question, self.fields)
                self.assertTrue(matched)
                self.assertEqual(intent.intent, "lookup_field")
                self.assertEqual(intent.conditions[0].field, "Company Name" if target != "John Smith" else "Contact Person")
                self.assertEqual(intent.conditions[0].value, target)
                self.assertEqual(intent.return_fields, requested_fields)
                self.assertEqual(
                    set(intent.model_dump()),
                    {"intent", "conditions", "logic", "return_fields"},
                )

    def test_question_text_is_not_used_as_search_value(self):
        matched, intent = deterministic_parse_query("What is the email in 2dinc?", self.fields)

        self.assertTrue(matched)
        self.assertEqual(intent.conditions[0].value, "2dinc")

    def test_company_search_allows_case_and_whitespace_differences(self):
        mongo_filter = build_safe_dataset_filter(
            "ds_test",
            None,
            "",
            dataset_fields=self.fields,
            conditions=[{"field": "Company Name", "operator": "contains", "value": "2dinc"}],
        )
        pattern = mongo_filter["$or"][0]["data.Company Name"]["$regex"]

        self.assertRegex("2D Inc", re.compile(pattern, re.IGNORECASE))
        self.assertRegex("2DINC", re.compile(pattern, re.IGNORECASE))

    def test_search_condition_field_must_be_in_schema(self):
        with self.assertRaises(ValueError):
            build_safe_dataset_filter(
                "ds_test",
                None,
                "",
                dataset_fields=self.fields,
                conditions=[{"field": "Not a dataset field", "value": "2dinc"}],
            )

    def test_legacy_search_matches_normalized_company_names(self):
        mongo_filter = build_mongo_query(["company_name"], "2dinc", operator="equals")
        pattern = mongo_filter["$or"][0]["company_name"]["$regex"]

        self.assertRegex("2D Inc", re.compile(pattern, re.IGNORECASE))
        self.assertRegex("2DINC", re.compile(pattern, re.IGNORECASE))


class PrivacyParserTests(unittest.TestCase):
    def test_llm_cannot_turn_the_full_question_into_a_search_value(self):
        question = "What is the email in 2dinc?"
        response = Mock(status_code=200)
        response.json.return_value = {
            "message": {
                "content": json.dumps({
                    "intent": "lookup_field",
                    "conditions": [{
                        "field": "Company Name",
                        "operator": "contains",
                        "value": question,
                    }],
                    "logic": "AND",
                    "return_fields": ["Email"],
                }),
            },
        }
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.post.return_value = response

        with patch("app.services.query_parser.httpx.AsyncClient", return_value=client):
            intent = asyncio.run(parse_query_with_privacy_llm(question, ["Company Name", "Email"]))

        self.assertEqual(intent.conditions[0].value, "2dinc")
        self.assertEqual(intent.return_fields, ["Email"])
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][1]["content"], question)
        self.assertEqual(payload["messages"][0]["content"].count("Company Name"), 1)

if __name__ == "__main__":
    unittest.main()