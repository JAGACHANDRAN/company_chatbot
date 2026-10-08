import sys
import os
import re
import asyncio
from pathlib import Path

# Ensure project root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_database
from app.services.multi_stage_search import execute_multi_stage_retrieval
from app.services.response_generator import extract_company_name
from app.utils.normalization import normalize_company


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/search_debug.py \"<query>\"")
        return

    query = sys.argv[1].strip()
    print(f"\n=======================================================")
    print(f"SEARCH DEBUG: '{query}'")
    print(f"Normalized Company: '{normalize_company(query)}'")
    print(f"=======================================================\n")

    res = await execute_multi_stage_retrieval(query)
    
    stages = res.get("stages", {})
    keyword_records = res.get("keyword_records", [])
    vector_records = res.get("vector_records", [])
    merged_records = res.get("records", [])

    print("STAGE COUNTS:")
    print(f" - Stage A (Exact): {stages.get('A', 0)}")
    print(f" - Stage B (Starts-With): {stages.get('B', 0)}")
    print(f" - Stage C (Whole-Word Phrase): {stages.get('C', 0)}")
    print(f" - Stage D (All Tokens Whole-Word): {stages.get('D', 0)}")
    print(f" - Keyword Total: {len(keyword_records)}")
    print(f" - Vector Total: {len(vector_records)}")
    print(f" - Merged Total: {len(merged_records)}")
    print(f" - Latency: {res.get('latency_ms', 0)}ms")

    if res.get("suggestions"):
        print(f" - Suggestions (Did you mean): {', '.join(res['suggestions'])}")

    print("\nFIRST 3 COMPANY NAMES (NO PHONES/EMAILS):")
    seen_names = []
    for r in merged_records:
        c_name = extract_company_name(r)
        if c_name and c_name not in seen_names:
            seen_names.append(c_name)
            if len(seen_names) >= 3:
                break

    if seen_names:
        for idx, name in enumerate(seen_names, 1):
            print(f" {idx}. {name}")
    else:
        print(" (No companies found)")

    print("\n=======================================================\n")


if __name__ == "__main__":
    asyncio.run(main())
