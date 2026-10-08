"""
Reranker and Reciprocal Rank Fusion (RRF) Service.
Combines and reranks search results from lexical and vector retrieval streams.
"""
from typing import List, Dict, Any, Optional
from ..utils.normalization import normalize_company_name, normalize_person_name, normalize_text
from .query_understanding import StructuredQuery
from ..config import RRF_K, FINAL_K


def compute_relevance_score(
    record: Dict[str, Any],
    structured_query: StructuredQuery,
    original_query: str
) -> float:
    """
    Computes a modular heuristic relevance score for a record against the user's query:
    - Exact/clean company match: +10.0
    - Exact/clean person match: +10.0
    - Exact designation / role match: +5.0
    - Department match: +4.0
    - Location match (State/City): +5.0
    - Populated contact info (phone/email): +1.0
    """
    score = 0.0

    rec_comp = normalize_company_name(record.get("company_name") or record.get("company"))
    rec_person = normalize_person_name(record.get("person_name") or record.get("person"))
    rec_desig = normalize_text(record.get("designation"))
    rec_dept = normalize_text(record.get("department"))
    rec_state = normalize_text(record.get("state"))
    rec_city = normalize_text(record.get("city") or record.get("location"))
    rec_loc = normalize_text(record.get("location"))

    # 1. Company match
    if structured_query.companies:
        for q_comp in structured_query.companies:
            norm_q = normalize_company_name(q_comp)
            if norm_q and (norm_q == rec_comp or norm_q in rec_comp or rec_comp in norm_q):
                score += 10.0
                break

    # 2. Person match
    if structured_query.people:
        for q_person in structured_query.people:
            norm_p = normalize_person_name(q_person)
            if norm_p and (norm_p == rec_person or norm_p in rec_person or rec_person in norm_p):
                score += 10.0
                break

    # 3. Designation match
    if structured_query.designation:
        norm_d = normalize_text(structured_query.designation)
        if norm_d and (norm_d in rec_desig or rec_desig in norm_d):
            score += 5.0

    # 4. Department match
    if structured_query.department:
        norm_dept = normalize_text(structured_query.department)
        if norm_dept and (norm_dept in rec_dept or norm_dept in rec_desig):
            score += 4.0

    # 5. Location match
    if structured_query.state:
        norm_st = normalize_text(structured_query.state)
        if norm_st and (norm_st in rec_state or norm_st in rec_loc):
            score += 5.0

    if structured_query.city:
        norm_ct = normalize_text(structured_query.city)
        if norm_ct and (norm_ct in rec_city or norm_ct in rec_loc):
            score += 5.0

    if structured_query.location and not (structured_query.state or structured_query.city):
        norm_l = normalize_text(structured_query.location)
        if norm_l and (norm_l in rec_loc or norm_l in rec_state or norm_l in rec_city):
            score += 5.0

    # 6. Quality boost if record has phone or email
    has_contact = (
        record.get("contact_number") not in (None, "Not Available", "")
        or record.get("phone") not in (None, "Not Available", "")
        or record.get("personal_mail_id") not in (None, "Not Available", "")
        or record.get("email") not in (None, "Not Available", "")
    )
    if has_contact:
        score += 1.0

    return score


def reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    k: int = RRF_K,
    top_k: int = FINAL_K
) -> List[Dict[str, Any]]:
    """
    Combines multiple ranked result lists using Reciprocal Rank Fusion (RRF).
    Formula: RRF_score(d) = sum(1 / (k + rank)) across ranking channels.
    Dedupes by document _id (or normalized entity signature) and returns top_k docs.
    """
    scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}

    for ranking in ranked_lists:
        for rank, doc in enumerate(ranking, start=1):
            doc_id = str(doc.get("_id") or "")
            if not doc_id:
                # Fallback entity signature
                c = doc.get("company_name") or doc.get("company") or ""
                p = doc.get("person_name") or doc.get("person") or ""
                doc_id = f"{c}::{p}"

            rrf_delta = 1.0 / (k + rank)
            scores[doc_id] = scores.get(doc_id, 0.0) + rrf_delta

            if doc_id not in doc_map:
                doc_map[doc_id] = doc

    # Sort documents by total RRF score descending
    sorted_doc_ids = sorted(scores.keys(), key=lambda did: scores[did], reverse=True)
    fused_results = []
    for did in sorted_doc_ids[:top_k]:
        doc = doc_map[did]
        doc["rrf_score"] = round(scores[did], 6)
        fused_results.append(doc)

    return fused_results


def rerank_records(
    records: List[Dict[str, Any]],
    structured_query: StructuredQuery,
    original_query: str,
    top_k: int = FINAL_K
) -> List[Dict[str, Any]]:
    """
    Reranks candidate records by relevance score and limits to top_k.
    Keeps original record data while placing the best matches at the top.
    """
    if not records:
        return []

    scored_records = []
    for rec in records:
        s = compute_relevance_score(rec, structured_query, original_query)
        scored_records.append((s, rec))

    scored_records.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored_records[:top_k]]
