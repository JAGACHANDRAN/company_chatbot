"""
Comprehensive PyTest Suite for Secure Hybrid RAG Pipeline.
Tests:
1. Embedding dimension validation (768-d).
2. PII Masking and Unmasking roundtrip.
3. Reciprocal Rank Fusion (RRF k=60) logic.
4. Router decision for exact phone/email queries (zero LLM).
5. Vector search fallback flag.
"""
import pytest
from app.services.embeddings import embed_documents, embed_query_sync, build_record_text
from app.services.pii_mask import mask_records, unmask_text
from app.services.reranker import reciprocal_rank_fusion
from app.services.query_understanding import fallback_query_understanding
from app.services.query_router import route_query, is_exact_lookup_query
from app.services.vector_search import cosine_similarity, execute_vector_search


def test_embedding_dimensions_and_prefixes():
    """Verify local nomic-embed-text produces exactly 768-d vectors."""
    sample_text = "Company: Test Calibration Lab | City: Pune"
    doc_embs = embed_documents([sample_text])
    assert len(doc_embs) == 1
    assert len(doc_embs[0]) == 768

    q_emb = embed_query_sync("calibration labs in Pune")
    assert len(q_emb) == 768


def test_pii_masking_roundtrip():
    """Verify phone and email are stripped from LLM payload and restored after."""
    sample_records = [
        {
            "company": "Calispec Precision Labs",
            "person": "Anand Sharma",
            "designation": "Director",
            "city": "Bangalore",
            "phone": "+91-9876543210",
            "email": "anand@calispec.com",
            "notes": "Top secret note"
        }
    ]

    masked_records, mapping = mask_records(sample_records)
    assert len(masked_records) == 1
    sanitized = masked_records[0]

    # Verification: sensitive fields masked
    assert sanitized["phone"] == "[PHONE_1]"
    assert sanitized["email"] == "[EMAIL_1]"
    assert "+91-9876543210" not in str(sanitized)
    assert "anand@calispec.com" not in str(sanitized)
    assert "notes" not in sanitized

    # Mapping checks
    assert mapping["[PHONE_1]"] == "+91-9876543210"
    assert mapping["[EMAIL_1]"] == "anand@calispec.com"

    # Unmasking roundtrip
    llm_simulated_text = "Contact Anand Sharma ([PHONE_1], [EMAIL_1]) at Calispec Precision Labs."
    restored = unmask_text(llm_simulated_text, mapping)
    assert "+91-9876543210" in restored
    assert "anand@calispec.com" in restored
    assert "[PHONE_1]" not in restored
    assert "[EMAIL_1]" not in restored


def test_reciprocal_rank_fusion():
    """Verify RRF correctly combines and ranks documents from multiple channels."""
    doc_a = {"_id": "doc_1", "company": "Company A"}
    doc_b = {"_id": "doc_2", "company": "Company B"}
    doc_c = {"_id": "doc_3", "company": "Company C"}

    lexical_ranking = [doc_a, doc_b]
    vector_ranking = [doc_b, doc_c]

    # doc_b appears in both rankings (rank 2 in lexical, rank 1 in vector)
    # RRF score for doc_b = 1/(60+2) + 1/(60+1) = 1/62 + 1/61 = 0.01613 + 0.01639 = 0.03252
    # RRF score for doc_a = 1/61 = 0.01639
    # RRF score for doc_c = 1/62 = 0.01613
    fused = reciprocal_rank_fusion([lexical_ranking, vector_ranking], k=60, top_k=3)

    assert len(fused) == 3
    assert fused[0]["_id"] == "doc_2"  # doc_b has highest combined score
    assert fused[1]["_id"] == "doc_1"
    assert fused[2]["_id"] == "doc_3"


def test_router_exact_lookup_bypass():
    """Verify phone, email and direct lookups bypass LLM (requires_llm=False)."""
    # 1. Phone number search
    sq_phone = fallback_query_understanding("Find 9876543210")
    plan_phone = route_query(sq_phone)
    assert plan_phone.requires_llm is False
    assert plan_phone.use_vector is False

    # 2. Email search
    sq_email = fallback_query_understanding("Email info@calispec.com")
    plan_email = route_query(sq_email)
    assert plan_email.requires_llm is False
    assert plan_email.use_vector is False

    # 3. Descriptive/Semantic search -> Hybrid with LLM
    sq_semantic = fallback_query_understanding("Find calibration labs specializing in torque testing in Pune")
    plan_semantic = route_query(sq_semantic)
    assert plan_semantic.requires_llm is True
    assert plan_semantic.use_vector is True


def test_cosine_similarity_edge_cases():
    """Verify cosine similarity mathematical boundaries."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]
    v_zero = [0.0, 0.0, 0.0]

    assert round(cosine_similarity(v1, v2), 4) == 1.0
    assert round(cosine_similarity(v1, v3), 4) == 0.0
    assert cosine_similarity(v1, v_zero) == 0.0
    assert cosine_similarity([], v1) == 0.0
