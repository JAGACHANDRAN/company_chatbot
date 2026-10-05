import pytest
from app.services.query_understanding import fallback_query_understanding
from app.services.query_router import route_query
from app.services.reranker import rerank_records
from app.services.response_generator import generate_deterministic_answer
from app.services.retrieval_service import validate_record_relevance, group_records_by_source
from app.utils.deduplication import deduplicate_records
from app.services.vector_search import (
    build_record_search_text,
    generate_local_embedding,
    cosine_similarity,
    VECTOR_DIMENSIONS
)

TEST_DATASET = [
    {
        "id": "1",
        "company": "ABC Industries Pvt Ltd",
        "company_name": "ABC Industries Pvt Ltd",
        "person": "Babu John",
        "person_name": "Babu John",
        "designation": "Quality Manager",
        "location": "Chennai, Tamil Nadu",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "phone": "+91 9876543210",
        "email": "babu.john@abcindustries.com",
        "source_file": "Vendor_List_2026.xlsx",
        "source_sheet": "Sheet1",
        "source_collection": "metrology"
    },
    {
        "id": "2",
        "company": "TVS Motor Company",
        "company_name": "TVS Motor Company",
        "person": "Ravi Kumar",
        "person_name": "Ravi Kumar",
        "designation": "Quality Head",
        "location": "Hosur, Tamil Nadu",
        "city": "Hosur",
        "state": "Tamil Nadu",
        "phone": "+91 9876543211",
        "email": "ravi.kumar@tvs.com",
        "source_file": "Expo_Acme.xlsx",
        "source_sheet": "Sheet1",
        "source_collection": "Expo_Acme"
    },
    {
        "id": "3",
        "company": "2D INC",
        "company_name": "2D INC",
        "person": "David Miller",
        "person_name": "David Miller",
        "designation": "Calibration Engineer",
        "location": "Bangalore, Karnataka",
        "city": "Bangalore",
        "state": "Karnataka",
        "phone": "+91 9876543212",
        "email": "david@2dinc.com",
        "source_file": "ECG_Marposs.xlsx",
        "source_sheet": "Sheet1",
        "source_collection": "ECG_Marposs"
    }
]

# Precompute embeddings
for doc in TEST_DATASET:
    doc["search_text"] = build_record_search_text(doc)
    doc["embedding"] = generate_local_embedding(doc["search_text"])


def test_case_a_keyword_search():
    """A. Existing keyword search: 'Find Babu John'"""
    q = "Find Babu John"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    assert "Babu John" in sq.people
    assert plan.search_strategy == "person_search"
    matched = [d for d in TEST_DATASET if validate_record_relevance(d, sq, plan)]
    assert len(matched) == 1
    assert matched[0]["person_name"] == "Babu John"
    ans = generate_deterministic_answer(q, sq, matched)
    assert "Source File: Vendor_List_2026.xlsx | Sheet1" in ans
    assert "Babu John" in ans
    assert "+91 9876543210" in ans


def test_case_b_company_search():
    """B. Company search: 'Find contacts at ABC Industries'"""
    q = "Find contacts at ABC Industries"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    assert len(sq.companies) > 0
    matched = [d for d in TEST_DATASET if validate_record_relevance(d, sq, plan)]
    assert len(matched) == 1
    assert matched[0]["company"] == "ABC Industries Pvt Ltd"
    ans = generate_deterministic_answer(q, sq, matched)
    assert "Company Name: ABC Industries Pvt Ltd" in ans
    assert "Babu John" in ans


def test_case_c_designation_search():
    """C. Designation search: 'Find Quality Manager'"""
    q = "Find Quality Manager"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    assert sq.designation == "Quality Manager"
    matched = [d for d in TEST_DATASET if validate_record_relevance(d, sq, plan)]
    assert len(matched) >= 1
    ans = generate_deterministic_answer(q, sq, matched)
    assert "Quality Manager" in ans


def test_case_d_location_and_designation():
    """D. Location + designation: 'Find Quality Manager in Chennai'"""
    q = "Find Quality Manager in Chennai"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    assert sq.designation == "Quality Manager"
    assert sq.state == "Chennai" or sq.city == "Chennai" or sq.location == "Chennai"
    matched = [d for d in TEST_DATASET if validate_record_relevance(d, sq, plan)]
    assert len(matched) == 1
    assert matched[0]["city"] == "Chennai"
    ans = generate_deterministic_answer(q, sq, matched)
    assert "Chennai" in ans


def test_case_e_semantic_query():
    """E. Semantic query: 'Who is responsible for quality at ABC Industries?'"""
    q = "Who is responsible for quality at ABC Industries?"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    q_emb = generate_local_embedding(q)
    assert len(q_emb) == VECTOR_DIMENSIONS
    matched = []
    for doc in TEST_DATASET:
        sim = cosine_similarity(q_emb, doc["embedding"])
        if sim > 0.15:
            matched.append(doc)
    assert len(matched) >= 1
    reranked = rerank_records(matched, sq, q, top_k=5)
    assert len(reranked) >= 1


def test_case_f_multi_matching_records():
    """F. Multiple matching records: 'Show ABC, TVS and 2D INC'"""
    q = "Show ABC, TVS and 2D INC"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    assert len(sq.companies) == 3
    matched = [d for d in TEST_DATASET if validate_record_relevance(d, sq, plan)]
    assert len(matched) == 3
    deduped = deduplicate_records(matched, preserve_source_separation=True)
    assert len(deduped) == 3
    ans = generate_deterministic_answer(q, sq, deduped)
    assert "Vendor_List_2026.xlsx" in ans
    assert "Expo_Acme.xlsx" in ans
    assert "ECG_Marposs.xlsx" in ans


def test_case_g_no_match_query():
    """G. No-match query: 'Find NonExistentCompany123xyz'"""
    q = "Find NonExistentCompany123xyz"
    sq = fallback_query_understanding(q)
    plan = route_query(sq)
    matched = [d for d in TEST_DATASET if validate_record_relevance(d, sq, plan)]
    assert len(matched) == 0
    ans = generate_deterministic_answer(q, sq, matched)
    assert ans == "No data found"
