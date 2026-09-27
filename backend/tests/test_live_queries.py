import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure backend root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.services.query_understanding import parse_query_understanding
from app.services.query_router import route_query
from app.services.retrieval_service import execute_hybrid_retrieval
from app.services.response_generator import generate_final_answer


TEST_QUERIES = [
    "Show ABC company",
    "Show ABC, XYZ and PQR companies",
    "Which companies are in Andhra Pradesh?",
    "Find Ravi Kumar",
    "Show quality managers",
    "Show quality managers in Andhra Pradesh",
    "Give me quality contacts from ABC and XYZ",
    "Find Ravi Kumar in ABC",
    "Which companies are available in Chennai?",
    "Give me all quality department contacts in Andhra Pradesh",
    "Find ABC company across all uploaded files",
    "Who is responsible for quality operations?",
    "Show all companies having a Quality Head",
    "Find people from the quality department in Chennai",
    "Give me ABC, XYZ and PQR contacts from every uploaded file",
]


async def run_live_test(query: str):
    print("=" * 80)
    print(f"QUERY: {query}")

    # 1. Query Understanding
    sq, was_llm = await parse_query_understanding(query)
    print(f"Structured Query (LLM={was_llm}):")
    print(f"  Intent: {sq.intent}")
    print(f"  Companies: {sq.companies}")
    print(f"  People: {sq.people}")
    print(f"  Designation: {sq.designation}")
    print(f"  Department: {sq.department}")
    print(f"  State: {sq.state}")
    print(f"  City: {sq.city}")
    print(f"  Semantic Query: {sq.semantic_query}")

    # 2. Query Router
    plan = route_query(sq)
    print(f"Search Plan: Strategy={plan.search_strategy} (Structured={plan.use_structured}, Vector={plan.use_vector})")

    # 3. Hybrid Retrieval
    records, debug_info = await execute_hybrid_retrieval(sq, plan=plan, limit=10)
    print(f"Retrieved Records Count: {len(records)}")

    # 4. Final Answer Generation
    answer = await generate_final_answer(query, sq, records)
    print(f"Final Answer Preview:\n{answer[:300]}...")
    print("=" * 80)


async def main():
    print(f"Running End-to-End RAG Verification on {len(TEST_QUERIES)} Test Queries...")
    for q in TEST_QUERIES:
        await run_live_test(q)


if __name__ == "__main__":
    asyncio.run(main())
