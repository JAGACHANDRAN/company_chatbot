import os
import sys
import re
import pytest
import asyncio
from typing import Any, List, Set, Dict

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import get_database
from app.routes.chat import execute_rag_pipeline
import app.services.observability as obs


def extract_all_strings(obj: Any) -> List[str]:
    """Recursively extracts all string values and keys from any object/payload."""
    found = []
    if isinstance(obj, str):
        found.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.append(str(k))
            found.extend(extract_all_strings(v))
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            found.extend(extract_all_strings(item))
    return found


@pytest.fixture(scope="module")
def forbidden_database_values():
    """
    Fetches raw database values via raw pymongo to build the forbidden list:
    - company names from records
    - person names from records
    - emails from records
    - phone numbers from records
    - dataset names
    """
    db = get_database()
    col = db["dataset_records"]

    # Raw company names
    raw_companies = set()
    for doc in col.find({}, {"company": 1, "Company": 1}).limit(500):
        c1 = doc.get("company")
        c2 = doc.get("Company")
        if c1 and isinstance(c1, str) and len(c1.strip()) > 2:
            raw_companies.add(c1.strip())
        if c2 and isinstance(c2, str) and len(c2.strip()) > 2:
            raw_companies.add(c2.strip())

    # Raw person names
    raw_persons = set()
    for doc in col.find({}, {"person": 1, "Person Name": 1, "name": 1}).limit(500):
        for k in ("person", "Person Name", "name"):
            val = doc.get(k)
            if val and isinstance(val, str) and len(val.strip()) > 2:
                # Exclude placeholders
                if "no data" not in val.lower() and "n/a" not in val.lower():
                    raw_persons.add(val.strip())

    # Raw emails
    raw_emails = set()
    for doc in col.find({}, {"email": 1, "Email": 1}).limit(500):
        for k in ("email", "Email"):
            val = doc.get(k)
            if val and isinstance(val, str) and "@" in val:
                raw_emails.add(val.strip().lower())

    # Raw phones
    raw_phones = set()
    for doc in col.find({}, {"phone": 1, "Phone": 1, "Mobile": 1, "mobile": 1}).limit(500):
        for k in ("phone", "Phone", "Mobile", "mobile"):
            val = doc.get(k)
            if val and isinstance(val, str):
                digits = re.sub(r"\D", "", val)
                if len(digits) >= 7:
                    raw_phones.add(digits)

    # Raw dataset names
    raw_datasets = set()
    datasets_col = db["datasets"]
    for ds in datasets_col.find({}, {"filename": 1, "name": 1}):
        f1 = ds.get("filename")
        f2 = ds.get("name")
        if f1 and isinstance(f1, str):
            raw_datasets.add(f1.strip())
        if f2 and isinstance(f2, str):
            raw_datasets.add(f2.strip())
    raw_datasets.add("dataset_records")

    return {
        "companies": raw_companies,
        "persons": raw_persons,
        "emails": raw_emails,
        "phones": raw_phones,
        "datasets": raw_datasets,
    }


def test_langfuse_security_on_5_queries(forbidden_database_values, monkeypatch):
    """
    Runs 5 diverse queries with tracing ON, captures every single payload passed to Langfuse,
    and asserts that NONE of the following ever appear:
      1. Any company name from the database (unless explicitly typed by the user in the query)
      2. Any person name from the database
      3. Any email from the database or raw email string
      4. Any phone number from the database or raw phone string
      5. Any dataset name
    """
    captured_payloads: List[Dict[str, Any]] = []

    # Monkeypatch SafeSpanWrapper and SafeTraceWrapper to intercept all payloads
    orig_span_update = obs.SafeSpanWrapper.update
    orig_span_end = obs.SafeSpanWrapper.end
    orig_trace_end = obs.SafeTraceWrapper.end
    orig_trace_score = obs.SafeTraceWrapper.score

    def capturing_span_update(self, output=None, metadata=None, **kwargs):
        captured_payloads.append({
            "type": "span_update",
            "output": output,
            "metadata": metadata,
            "kwargs": kwargs
        })
        return orig_span_update(self, output=output, metadata=metadata, **kwargs)

    def capturing_span_end(self, output=None, **kwargs):
        captured_payloads.append({
            "type": "span_end",
            "output": output,
            "kwargs": kwargs
        })
        return orig_span_end(self, output=output, **kwargs)

    def capturing_trace_end(self, output=None, **kwargs):
        captured_payloads.append({
            "type": "trace_end",
            "output": output,
            "kwargs": kwargs
        })
        return orig_trace_end(self, output=output, **kwargs)

    def capturing_trace_score(self, name, value, comment=None, **kwargs):
        captured_payloads.append({
            "type": "trace_score",
            "name": name,
            "value": value,
            "comment": comment,
            "kwargs": kwargs
        })
        return orig_trace_score(self, name, value, comment=comment, **kwargs)

    monkeypatch.setattr(obs.SafeSpanWrapper, "update", capturing_span_update)
    monkeypatch.setattr(obs.SafeSpanWrapper, "end", capturing_span_end)
    monkeypatch.setattr(obs.SafeTraceWrapper, "end", capturing_trace_end)
    monkeypatch.setattr(obs.SafeTraceWrapper, "score", capturing_trace_score)

    test_queries = [
        # Query 1: Single company lookup
        "Find contacts at Delphi",
        # Query 2: Multi-company query
        "Show contacts at Delphi and Bosch",
        # Query 3: Filtered query with designation & email request
        "Find Manager at Delphi with email",
        # Query 4: Follow-up style availability query
        "How many have email at Delphi?",
        # Query 5: Open question / informational query
        "What companies are based in Michigan?",
    ]

    for q_idx, q_text in enumerate(test_queries, 1):
        captured_payloads.clear()

        # Run pipeline
        res = asyncio.run(execute_rag_pipeline(
            raw_query=q_text,
            dataset_id="all",
            session_id=f"security_test_sess_{q_idx}",
            user_id="sec_auditor@calispec.ai"
        ))
        assert res.success is True

        # Words typed by the user in this specific query (case-insensitive)
        user_typed_words = {w.lower() for w in re.findall(r"\b\w+\b", q_text)}

        # Extract all strings in all captured payloads
        all_captured_strings = []
        for p in captured_payloads:
            all_captured_strings.extend(extract_all_strings(p))

        # Check assertions
        for s in all_captured_strings:
            s_clean = s.strip()
            s_lower = s_clean.lower()

            # 1. Assert NO email appears (unless properly masked token '[EMAIL]')
            if "@" in s_clean:
                # Any real email address format is strictly forbidden
                assert not obs.CONTAINS_EMAIL_REGEX.search(s_clean), (
                    f"Forbidden email leaked in Langfuse payload for query '{q_text}': {s_clean}"
                )
            for db_email in forbidden_database_values["emails"]:
                assert db_email not in s_lower, (
                    f"Database email '{db_email}' leaked in Langfuse payload for query '{q_text}': {s_clean}"
                )

            # 2. Assert NO phone number appears (unless '[PHONE]')
            digits = re.sub(r"\D", "", s_clean)
            if len(digits) >= 7 and ("PHONE" not in s_clean):
                assert not obs.PHONE_DIGITS_REGEX.match(s_clean), (
                    f"Forbidden phone leaked in Langfuse payload for query '{q_text}': {s_clean}"
                )
            for db_phone in forbidden_database_values["phones"]:
                if len(db_phone) >= 8:
                    assert db_phone not in digits, (
                        f"Database phone '{db_phone}' leaked in Langfuse payload for query '{q_text}': {s_clean}"
                    )

            # 3. Assert NO dataset name appears
            for ds_name in forbidden_database_values["datasets"]:
                if len(ds_name) >= 3 and ds_name.lower() not in user_typed_words:
                    assert ds_name.lower() != s_lower and f"/{ds_name.lower()}" not in s_lower, (
                        f"Database dataset name '{ds_name}' leaked in Langfuse payload for query '{q_text}': {s_clean}"
                    )

            # 4. Assert NO person name appears
            for p_name in forbidden_database_values["persons"]:
                if len(p_name) >= 4 and p_name.lower() not in user_typed_words:
                    # Exact or word boundary match
                    assert not re.search(rf"\b{re.escape(p_name.lower())}\b", s_lower), (
                        f"Database person name '{p_name}' leaked in Langfuse payload for query '{q_text}': {s_clean}"
                    )

            # 5. Assert NO untyped company name from database appears
            for comp_name in forbidden_database_values["companies"]:
                # If the user typed this company name in the query, it is allowed in plan JSON.
                # If the user did NOT type it, it must NEVER appear in any Langfuse payload!
                c_clean = comp_name.strip().lower()
                if len(c_clean) >= 4 and not any(w in c_clean or c_clean in w for w in user_typed_words):
                    assert not re.search(rf"\b{re.escape(c_clean)}\b", s_lower), (
                        f"Untyped database company '{comp_name}' leaked in Langfuse payload for query '{q_text}': {s_clean}"
                    )


def test_sanitizer_fails_on_forbidden_data():
    """Verifies that the test assertions catch leaks and that sanitize() drops forbidden keys/values."""
    # 1. Test forbidden key dropping
    dirty_payload = {
        "company": "Acme Corp",
        "person": "John Doe",
        "email": "john@acme.com",
        "phone": "+1 555-123-4567",
        "linkedin": "https://linkedin.com/in/johndoe",
        "city": "Detroit",
        "state": "MI",
        "dataset_name": "master_leads.xlsx",
        "search_text": "Acme Corp Detroit",
        "embedding": [0.1, 0.2, 0.3],
        "unknown_key": "some_value",
        "company_count": 2,
        "keyword_hits": 10,
        "hits_per_name": {"Acme": 10},
        "duplicates_removed": 2
    }

    clean = obs.sanitize(dirty_payload)
    assert "company" not in clean
    assert "person" not in clean
    assert "email" not in clean
    assert "phone" not in clean
    assert "linkedin" not in clean
    assert "city" not in clean
    assert "state" not in clean
    assert "dataset_name" not in clean
    assert "search_text" not in clean
    assert "embedding" not in clean
    assert "unknown_key" not in clean  # dropped because not in ALLOWED_KEYS
    assert clean["company_count"] == 2
    assert clean["keyword_hits"] == 10
    assert clean["duplicates_removed"] == 2
    assert clean["hits_per_name"] == {"Acme": 10}

    # 2. Test email string dropping
    dirty_list = ["valid_string", "test@example.com", "+1-800-555-0199"]
    clean_list = obs.sanitize(dirty_list)
    assert clean_list == ["valid_string"]
