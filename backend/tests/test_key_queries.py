import asyncio
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.query_understanding import parse_query_understanding
from app.services.query_router import route_query
from app.services.retrieval_service import execute_hybrid_retrieval
from app.services.response_generator import generate_final_answer

KEY_QUERIES = [
    "Show ABC, XYZ and PQR companies",
    "Which companies are in Andhra Pradesh?",
    "Find Ravi Kumar",
]


async def run():
    for q in KEY_QUERIES:
        print("\n" + "=" * 70, flush=True)
        print(f">>> TESTING QUERY: '{q}'", flush=True)

        sq, was_llm = await parse_query_understanding(q)
        print(f"1. STRUCTURED QUERY: {sq.model_dump_json()}", flush=True)

        plan = route_query(sq)
        print(f"2. ROUTER PLAN: strategy={plan.search_strategy}, use_structured={plan.use_structured}, use_vector={plan.use_vector}", flush=True)

        records, debug = await execute_hybrid_retrieval(sq, plan=plan, limit=10)
        print(f"3. RETRIEVED COUNT: {len(records)}", flush=True)
        if records:
            print("   Sample Matches:", flush=True)
            for r in records[:3]:
                print(f"   - {r.get('company_name')} | {r.get('person_name')} | {r.get('designation')} | {r.get('state')} | {r.get('source_file')}", flush=True)

        answer = await generate_final_answer(q, sq, records)
        print("4. FINAL ANSWER:", flush=True)
        print(answer[:400] + ("..." if len(answer) > 400 else ""), flush=True)
        print("=" * 70, flush=True)


if __name__ == "__main__":
    asyncio.run(run())
