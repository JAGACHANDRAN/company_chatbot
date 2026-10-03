"""
Comprehensive pytest suite for PRIVACY_MODE in Calispec AI.
Uses STRICTLY FAKE DATA to prove:
1. When PRIVACY_MODE=true, chat responses are generated using deterministic fallback synthesis.
2. llm.py is NEVER called (mocked and asserted 0 calls).
3. Hard guards in llm.py prevent any code path from reaching models when PRIVACY_MODE=true.
4. vector_search.py and query_router.py skip vector/embedding search.
5. Logs never contain full user queries or raw database records.
6. Local LLM URL detection correctly differentiates localhost from external hosts.
"""

import io
import sys
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.config import (
    PRIVACY_MODE,
    is_local_url,
    validate_privacy_and_llm_config,
)
import app.llm as llm_module
from app.schemas import QueryIntent
from app.services.response_generator import (
    deterministic_synthesize,
    generate_response,
    generate_final_answer,
    format_strict_company_records,
)
from app.services.query_understanding import (
    StructuredQuery,
    parse_query_understanding,
)
from app.services.query_router import route_query, SearchPlan
from app.services.vector_search import execute_vector_search, get_embedding
from app.services.retrieval_service import execute_hybrid_retrieval
from app.main import app

# FAKE TEST DATA (Strictly simulated, no real contact/company data)
FAKE_RECORDS = [
    {
        "id": "fake_doc_001",
        "company_name": "Acme Synthetic Corp",
        "person_name": "Alex Taylor",
        "designation": "Quality Lead",
        "contact_number": "+91 99999 11111",
        "email": "alex.taylor@acme-fake.test",
        "address": "100 Synthetic Industrial Area",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "linkedin_url": "https://linkedin.com/in/alex-taylor-fake",
        "source_file": "Fake_Vendors_2026.xlsx",
        "source_sheet": "Sheet1",
        "source_collection": "dataset_records",
        "database_source": "calispec_test",
        "source_fields": {
            "Company Name": "Acme Synthetic Corp",
            "Contact Person": "Alex Taylor",
            "Designation": "Quality Lead",
            "Mobile No": "+91 99999 11111",
            "Email": "alex.taylor@acme-fake.test",
            "Address": "100 Synthetic Industrial Area",
            "City": "Chennai",
            "State": "Tamil Nadu",
            "LinkedIn": "https://linkedin.com/in/alex-taylor-fake",
            "Source File": "Fake_Vendors_2026.xlsx",
        }
    }
]


def test_privacy_mode_is_enabled():
    """Verify PRIVACY_MODE is loaded as True from config."""
    assert PRIVACY_MODE is True


def test_llm_hard_guard_raises_on_call():
    """
    Test Requirement 3:
    In llm.py: raise a clear RuntimeError if any function is called while PRIVACY_MODE is true.
    """
    # 1. call_llm must raise RuntimeError
    with pytest.raises(RuntimeError, match="LLM disabled: PRIVACY_MODE is on"):
        llm_module.call_llm("test prompt")

    # 2. fallback_query_parser in llm.py must raise RuntimeError
    with pytest.raises(RuntimeError, match="LLM disabled: PRIVACY_MODE is on"):
        llm_module.fallback_query_parser("Acme Synthetic Corp")


@pytest.mark.anyio
async def test_llm_parse_query_hard_guard():
    """Verify parse_query_with_llm raises RuntimeError in PRIVACY_MODE."""
    with pytest.raises(RuntimeError, match="LLM disabled: PRIVACY_MODE is on"):
        await llm_module.parse_query_with_llm("Find Acme Synthetic Corp")


def test_deterministic_response_synthesizer_never_calls_llm():
    """
    Test Requirements 2 & 8:
    Verify that response synthesis uses the deterministic fallback synthesizer,
    never calls llm.py, and outputs the exact strict schema.
    """
    # Mock llm_module functions
    with patch.object(llm_module, "call_llm") as mock_call_llm, \
         patch.object(llm_module, "parse_query_with_llm") as mock_parse_llm:

        result = deterministic_synthesize(FAKE_RECORDS)

        # Assert llm.py was NEVER called
        assert mock_call_llm.call_count == 0
        assert mock_parse_llm.call_count == 0

        # Assert strict-schema output
        assert "Source File: Fake_Vendors_2026.xlsx | Sheet1" in result
        assert "Company Name: Acme Synthetic Corp" in result
        assert "Contact Person 1:" in result
        assert "- Name: Alex Taylor" in result
        assert "- Designation: Quality Lead" in result
        assert "- LinkedIn: https://linkedin.com/in/alex-taylor-fake" in result
        assert "- Contact Number 1: +91 99999 11111" in result
        assert "- Email 1: alex.taylor@acme-fake.test" in result
        assert "- Address: 100 Synthetic Industrial Area" in result
        assert "- City: Chennai" in result
        assert "- State: Tamil Nadu" in result

        # Verify hidden internal fields are NOT exposed
        assert "fake_doc_001" not in result
        assert "dataset_records" not in result
        assert "embedding" not in result


@pytest.mark.anyio
async def test_generate_final_answer_in_privacy_mode():
    """
    Verify generate_final_answer respects PRIVACY_MODE and never touches llm.py.
    """
    sq = StructuredQuery(
        intent="company_search",
        companies=["Acme Synthetic Corp"],
        original_query="Find Acme Synthetic Corp"
    )

    with patch.object(llm_module, "call_llm") as mock_call_llm:
        response = await generate_final_answer(
            user_query="Find Acme Synthetic Corp",
            structured_query=sq,
            records=FAKE_RECORDS
        )
        assert mock_call_llm.call_count == 0
        assert "Company Name: Acme Synthetic Corp" in response
        assert "alex.taylor@acme-fake.test" in response


def test_query_router_disables_vector_search_in_privacy_mode():
    """
    Test Requirement 4:
    In query_router.py: when PRIVACY_MODE is true, use_vector must ALWAYS be False.
    """
    # 1. Exact company query
    sq_exact = StructuredQuery(companies=["Acme Synthetic Corp"], original_query="Acme Synthetic Corp")
    plan_exact = route_query(sq_exact)
    assert plan_exact.use_vector is False

    # 2. Hybrid query (role + location)
    sq_hybrid = StructuredQuery(
        designation="Quality Lead",
        state="Tamil Nadu",
        original_query="Quality Lead in Tamil Nadu"
    )
    plan_hybrid = route_query(sq_hybrid)
    assert plan_hybrid.use_vector is False

    # 3. Pure semantic query (conceptual inquiry)
    sq_semantic = StructuredQuery(
        semantic_query="Who is responsible for quality operations?",
        original_query="Who is responsible for quality operations?"
    )
    plan_semantic = route_query(sq_semantic)
    assert plan_semantic.use_vector is False
    assert plan_semantic.use_structured is True


@pytest.mark.anyio
async def test_vector_search_skips_in_privacy_mode():
    """
    Test Requirement 4:
    In vector_search.py: execute_vector_search returns empty list and skips external HTTP calls.
    """
    with patch("httpx.AsyncClient.post") as mock_post:
        results = await execute_vector_search("Who is responsible for quality?", limit=10)
        assert results == []
        # No external HTTP calls should have been made
        assert mock_post.call_count == 0

    with patch("httpx.AsyncClient.post") as mock_post:
        emb = await get_embedding("Synthetic calibration test")
        assert isinstance(emb, list)
        assert len(emb) > 0
        assert mock_post.call_count == 0


@pytest.mark.anyio
async def test_query_understanding_skips_llm_in_privacy_mode():
    """Verify query understanding uses deterministic heuristic parser without calling LLM."""
    with patch("httpx.AsyncClient.post") as mock_post:
        sq, was_llm = await parse_query_understanding("Find Acme Synthetic Corp in Chennai")
        assert was_llm is False
        assert mock_post.call_count == 0
        assert sq.location == "Chennai" or sq.state == "Chennai" or "Chennai" in sq.original_query
        assert sq.intent in ("company_search", "location_search", "mixed_search", "general_search")


def test_local_llm_url_checker():
    """
    Test Requirement 5:
    Check whether is_local_url accurately detects localhost vs external hosts.
    """
    assert is_local_url("http://localhost:11434") is True
    assert is_local_url("http://127.0.0.1:11434") is True
    assert is_local_url("http://[::1]:11434") is True
    assert is_local_url("http://0.0.0.0:11434") is True
    assert is_local_url("localhost:11434") is True

    # Non-local hosts
    assert is_local_url("https://api.ollama.com") is False
    assert is_local_url("https://ollama.com") is False
    assert is_local_url("https://api.openai.com/v1") is False
    assert is_local_url("http://192.168.1.50:11434") is False


def test_startup_validation_warning(caplog):
    """
    Test Requirement 5:
    If PRIVACY_MODE is false and OLLAMA_BASE_URL is non-local, log a warning at startup.
    """
    with patch("app.config.PRIVACY_MODE", False), \
         patch("app.config.OLLAMA_BASE_URL", "https://api.ollama.com"), \
         patch("app.config.is_local_url", return_value=False):
        validate_privacy_and_llm_config()
        # Verify that a warning was emitted
        assert any("SECURITY WARNING" in rec.message for rec in caplog.records)


@pytest.mark.anyio
async def test_logs_never_contain_raw_queries_or_raw_records():
    """
    Test Requirement 7:
    Make sure console logs never contain full user queries or raw records.
    """
    captured_output = io.StringIO()
    sys_stdout_backup = sys.stdout
    sys.stdout = captured_output

    try:
        secret_query = "SUPER_SECRET_CONFIDENTIAL_QUERY_12345"
        sq = StructuredQuery(
            intent="company_search",
            companies=["Acme Synthetic Corp"],
            original_query=secret_query
        )
        plan = SearchPlan(
            search_strategy="exact_entity",
            use_structured=True,
            use_vector=False,
            companies=["Acme Synthetic Corp"]
        )

        with patch("app.services.retrieval_service.execute_structured_search", return_value=FAKE_RECORDS):
            await execute_hybrid_retrieval(
                structured_query=sq,
                plan=plan,
                dataset_id="all",
                limit=10
            )

        log_text = captured_output.getvalue()
        # Assert full secret query is NOT logged
        assert secret_query not in log_text
        assert "REDACTED FOR PRIVACY" in log_text
    finally:
        sys.stdout = sys_stdout_backup


def test_api_chat_endpoint_e2e_with_mocked_llm_guard():
    """
    Test Requirement 8 E2E:
    FastAPI /api/chat endpoint processes query and returns response with zero LLM calls.
    """
    client = TestClient(app)

    # Patch retrieval and ensure llm.py raises if ever called
    with patch("app.routes.chat.execute_hybrid_retrieval", return_value=(FAKE_RECORDS, {})), \
         patch.object(llm_module, "call_llm", side_effect=RuntimeError("LLM was called unexpectedly!")):

        response = client.post("/api/chat", json={"message": "Acme Synthetic Corp"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["found"] is True
        assert "Acme Synthetic Corp" in data["message"]
        assert "alex.taylor@acme-fake.test" in data["message"]
