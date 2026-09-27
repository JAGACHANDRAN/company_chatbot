import asyncio
import os
import sys
import json
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.services.query_understanding import parse_query_understanding
from app.services.query_router import route_query
from app.services.retrieval_service import execute_hybrid_retrieval
from app.services.response_generator import generate_final_answer

REQUIRED_QUERIES = [
    "2D INC",
    "ABC, TVS and 2D INC",
    "Find TVS",
    "Quality managers in Tamil Nadu",
]


async def run_query(query: str):
    print("\n" + "=" * 80)
    print(f"QUERY: '{query}'")
    print("=" * 80)

    # 1. Query Understanding
    sq, was_llm = await parse_query_understanding(query)
    print("1. QUERY UNDERSTANDING:")
    print(f"   Intent: {sq.intent} (parsed_by_llm={was_llm})")
    print(f"   Companies: {sq.companies}")
    print(f"   People: {sq.people}")
    print(f"   Designation: {sq.designation}")
    print(f"   Department: {sq.department}")
    print(f"   State: {sq.state}")
    print(f"   City: {sq.city}")
    print(f"   Semantic Query: '{sq.semantic_query}'")

    # 2. Query Routing
    plan = route_query(sq)
    print(f"\n2. QUERY ROUTING:")
    print(f"   Strategy: {plan.search_strategy}")
    print(f"   Use Structured: {plan.use_structured}")
    print(f"   Use Vector: {plan.use_vector}")

    # 3. Retrieval & Guarding
    records, debug_info = await execute_hybrid_retrieval(sq, plan=plan, limit=10)
    print(f"\n3. RETRIEVAL & RELEVANCE GUARD:")
    print(f"   Exact Records Retrieved: {len(debug_info.get('structured_records', []))}")
    print(f"   Vector Records Retrieved: {len(debug_info.get('vector_records', []))}")
    print(f"   After Relevance Guard & Dedup: {len(records)} records")

    for i, r in enumerate(records[:5], 1):
        raw = r.get("raw_data") or {}
        c_name = r.get("company_name") or raw.get("Company Name") or raw.get("Company")
        s_file = r.get("source_file") or raw.get("source_file")
        s_col = r.get("source_collection") or raw.get("source_collection")
        print(f"   Record {i}: Company='{c_name}' | Source File='{s_file}' | Collection='{s_col}'")

    # 4. Final Answer Generation (Source-grouped & Schema-preserving)
    answer = await generate_final_answer(query, sq, records)
    print(f"\n4. FINAL OUTPUT:")
    print(answer)
    print("=" * 80)


async def main():
    for q in REQUIRED_QUERIES:
        await run_query(q)


if __name__ == "__main__":
    asyncio.run(main())
