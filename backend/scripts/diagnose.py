import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import get_database


def scan_hardcoded_limits() -> List[Dict[str, Any]]:
    """Scans Python files in backend/app for limit patterns."""
    backend_app_dir = Path(__file__).resolve().parent.parent / "app"
    limit_patterns = [
        re.compile(r"\.limit\(\s*(\d+)\s*\)"),
        re.compile(r'"\$limit"\s*:\s*(\d+)'),
        re.compile(r"\[\s*:\s*(\d+)\s*\]"),
        re.compile(r"top_k\s*=\s*(\d+)"),
        re.compile(r"FINAL_K\s*=\s*(\d+)"),
        re.compile(r"RETRIEVE_K\s*=\s*(\d+)"),
        re.compile(r"limit\s*:\s*int\s*=\s*(\d+)")
    ]

    findings = []
    for root, _, files in os.walk(backend_app_dir):
        for f in files:
            if f.endswith(".py"):
                file_path = Path(root) / f
                rel_path = file_path.relative_to(backend_app_dir.parent)
                try:
                    with open(file_path, "r", encoding="utf-8") as fp:
                        for idx, line in enumerate(fp, start=1):
                            line_str = line.strip()
                            for pat in limit_patterns:
                                m = pat.search(line_str)
                                if m:
                                    val = m.group(1)
                                    findings.append({
                                        "file": str(rel_path).replace("\\", "/"),
                                        "line": idx,
                                        "match": line_str[:120],
                                        "limit_value": val
                                    })
                except Exception:
                    pass

    return findings


def check_17_names(db, names_list: List[str]) -> Dict[str, int]:
    """Queries how many records each name matches using plain case-insensitive regex."""
    results = {}
    for name in names_list:
        clean = re.escape(name.strip())
        pattern = rf"{clean}"
        q = {
            "$or": [
                {"norm_company": {"$regex": pattern, "$options": "i"}},
                {"company": {"$regex": pattern, "$options": "i"}},
                {"data.company": {"$regex": pattern, "$options": "i"}},
                {"data.Company Name": {"$regex": pattern, "$options": "i"}},
                {"search_text": {"$regex": pattern, "$options": "i"}}
            ]
        }
        count = db["dataset_records"].count_documents(q)
        results[name] = count
    return results


def check_20_random_records(db) -> List[Dict[str, Any]]:
    """Pulls 20 random records, resolves dataset_name from datasets collection, and flags missing/orphans."""
    datasets_cursor = db["datasets"].find({})
    ds_map = {}
    for d in datasets_cursor:
        name = d.get("dataset_name") or d.get("filename")
        if d.get("dataset_id"):
            ds_map[str(d["dataset_id"]).strip()] = name
        if d.get("_id"):
            ds_map[str(d["_id"]).strip()] = name

    # Sample 20 records using aggregation $sample
    try:
        sample_cursor = db["dataset_records"].aggregate([{"$sample": {"size": 20}}])
        docs = list(sample_cursor)
    except Exception:
        docs = list(db["dataset_records"].find({}).limit(20))

    results = []
    for doc in docs:
        doc_id = str(doc.get("_id"))
        ds_id = doc.get("dataset_id")
        source_file = doc.get("source_file") or doc.get("Source File") or doc.get("Sources")
        
        status = "OK"
        if not ds_id:
            status = "MISSING DATASET_ID"
            resolved_ds_name = "Not available"
        elif str(ds_id).strip() not in ds_map:
            status = "ORPHANED (No matching dataset in datasets collection)"
            resolved_ds_name = "Not available"
        else:
            resolved_ds_name = ds_map[str(ds_id).strip()]

        results.append({
            "_id": doc_id,
            "dataset_id": ds_id,
            "resolved_dataset_name": resolved_ds_name,
            "source_file": source_file,
            "status": status,
            "company": doc.get("company")
        })

    return results


def main():
    db = get_database()

    print("================================================================================")
    print("STEP 0 DIAGNOSTIC REPORT")
    print("================================================================================")

    # (a) Hardcoded limits
    print("\n--- (A) HARD-CODED LIMITS IN CHAT / SEARCH / RESPONSE CODE ---")
    limits = scan_hardcoded_limits()
    # Filter for low limits <= 100
    low_limits = [l for l in limits if int(l["limit_value"]) <= 100]
    for l in low_limits[:30]:
        print(f"  [{l['file']}:{l['line']}] (Limit: {l['limit_value']}) -> {l['match']}")
    print(f"  Total limit occurrences scanned: {len(limits)} ({len(low_limits)} <= 100)")

    # (b) 17 names check
    sample_17_names = [
        "tvs",
        "ashok leyland",
        "bosch",
        "premier cnc",
        "india pistons",
        "milton roy",
        "deeps engineering",
        "delphi tvs",
        "tata motors",
        "sundaram fasteners",
        "b r precisions",
        "super max cnc",
        "accurate india instruments",
        "a m engg",
        "preri shop",
        "marposs",
        "metrology"
    ]
    print("\n--- (B) REGEX MATCH COUNTS FOR 17 TEST COMPANY NAMES ---")
    name_counts = check_17_names(db, sample_17_names)
    for name, cnt in name_counts.items():
        print(f"  - '{name}': {cnt} matching records")

    # (c) 20 random records
    print("\n--- (C) 20 RANDOM RECORDS: DATASET RESOLUTION & ORPHAN CHECK ---")
    twenty_recs = check_20_random_records(db)
    for i, r in enumerate(twenty_recs, 1):
        flag_str = f"[{r['status']}]" if r['status'] != "OK" else "[OK]"
        print(f"  {i:2d}. ID: {r['_id']} | ds_id: {r['dataset_id']} | Source File: '{r['source_file']}' | Dataset: '{r['resolved_dataset_name']}' {flag_str}")

    # (d) Source value code path
    print("\n--- (D) CODE PATH THAT BUILDS SOURCE VALUE FOR A COMPANY ROW ---")
    print("  1. DB Record Fetch -> record contains `dataset_id` (e.g. ds_00fd75bd908a) and optional `dataset_name`")
    print("  2. app/services/source_resolver.py -> `get_dataset_name(record)`")
    print("     - Looks up record.dataset_id in in-memory cached map {dataset_id: dataset_name}")
    print("     - Returns clean comma-separated dataset_name(s)")
    print("  3. app/services/response_generator.py -> `get_company_sources_summary(records)`")
    print("     - Unifies dataset names across all contacts for a company (e.g. 'Metrology_5000_2628_Cleaned_R1.0, Cleaned_Met_Sales_Unique_R1.0')")
    print("     - Formats 'Source File: {company_sources_summary}' into markdown and JSON payload")
    print("  4. app/routes/chat.py -> `format_api_sources_and_records`")
    print("     - Attaches dataset_name to display_records and source_groups")
    print("  5. frontend/src/components/ChatMessage.jsx -> `parseStrictCompanyText` & `company.sourceFile` badge")
    print("================================================================================\n")


if __name__ == "__main__":
    main()
