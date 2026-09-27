import os
import re
import json
from typing import List, Dict, Any, Optional
import httpx
from dotenv import load_dotenv
from .query_understanding import StructuredQuery
from ..utils.normalization import extract_original_source_fields

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", os.getenv("LLM_API_KEY", "")).strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:120b")

FINAL_ANSWER_SYSTEM_PROMPT = """You are the final answer generator for an enterprise company and contact RAG directory.

CRITICAL RULES:
1. Answer the user's question using ONLY the provided retrieved database records.
2. At the TOP of each source section, show ONLY the source file information:
   **Source File: <file_name>**
   (and **Source Sheet: <sheet_name>** if available)
   DO NOT show "Dataset: ...", "Database: ...", or "MongoDB Atlas".
3. Directly show the retrieved records.
   If the record has a valid source row number, show:
   **Source Row: <row>**
   followed by the record's source columns:
   <Column Name>: <Value>
4. HYPERLINKS (MANDATORY):
   Format all email addresses, LinkedIn URLs, websites, and web links as clickable markdown hyperlinks:
   - Email: [user@domain.com](mailto:user@domain.com)
   - LinkedIn / Web URLs: [https://...](https://...)
5. DO NOT SHOW:
   - "Dataset: ..."
   - "Database: ..."
   - "SOURCE 1", "SOURCE 2", "SOURCE 3"
   - "Record 1", "Record 2", "Record 3"
   - "Norm Company Name", "Norm Person Name", "Norm Designation", "Norm Department", "Norm Location"
   - "Search Text", "Raw Data", or any internal/normalized fields
6. If results come from multiple datasets/files, simply separate each section with "---".
   Do NOT label them SOURCE 1, SOURCE 2, etc.
7. STRICT SOURCE SCHEMA PRESERVATION:
   Display each source using ONLY the columns that actually exist in that source record.
   NEVER invent missing fields or add placeholders like "Not Available" for columns that do not exist in that source file.
8. If no relevant records were retrieved, respond strictly with 'No data found'."""


def is_valid_source_row(row_val: Any) -> Optional[str]:
    """Returns clean string row representation if it is a genuine row number, else None."""
    if row_val in (None, "", "None", "null", "NaN", "Not Available"):
        return None
    s = str(row_val).strip()
    # Exclude MongoDB ObjectIds (24 hex characters)
    if len(s) == 24 and all(c in "0123456789abcdefABCDEF" for c in s):
        return None
    return s


def format_clickable_value(key: str, val: Any) -> str:
    """Formats emails and URLs as clickable markdown hyperlinks."""
    if val in (None, "", "None", "null", "NaN"):
        return "Not Available"
    s = str(val).strip()
    if s.lower() in ("not available", "no", "n/a", "none"):
        return s

    k = key.lower()

    # Email hyperlink
    if ("email" in k or "mail" in k or "@" in s) and re.search(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", s):
        # Extract email address
        m = re.search(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", s)
        if m:
            email_addr = m.group(0)
            return s.replace(email_addr, f"[{email_addr}](mailto:{email_addr})")
        return f"[{s}](mailto:{s})"

    # URL / LinkedIn hyperlink
    if s.startswith("http://") or s.startswith("https://"):
        return f"[{s}]({s})"
    elif s.startswith("www."):
        return f"[{s}](https://{s})"
    elif "linkedin.com" in s.lower() and not s.startswith("["):
        clean_url = f"https://{s}" if not s.startswith("http") else s
        return f"[{s}]({clean_url})"

    return s


def sanitize_final_answer(text: str) -> str:
    """Removes any accidental 'SOURCE 1', 'Record 1:', 'Dataset:', or 'Database:' markers from the generated answer."""
    if not text:
        return text
    # Remove lines like "SOURCE 1", "**SOURCE 1**", "## SOURCE 1", "SOURCE 1:"
    cleaned = re.sub(r'(?im)^(?:\*\*|\#\#)?\s*SOURCE\s+\d+\s*(?:\:|\*\*|\#\#)?\s*$\n?', '', text)
    # Remove lines like "Record 1:", "**Record 1:**", "Record 1", "### Record 1"
    cleaned = re.sub(r'(?im)^(?:\*\*|\#\#\#?)?\s*Record\s+\d+\s*(?:\:|\*\*|\#\#\#?)?\s*$\n?', '', cleaned)
    # Remove lines like "**Dataset: ...**" or "Dataset: ..."
    cleaned = re.sub(r'(?im)^(?:\*\*)?Dataset:\s*.*?(?:\*\*)?\s*$\n?', '', cleaned)
    # Remove lines like "**Database: ...**" or "Database: ..."
    cleaned = re.sub(r'(?im)^(?:\*\*)?Database:\s*.*?(?:\*\*)?\s*$\n?', '', cleaned)
    # Collapse 3+ newlines into 2
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


def generate_deterministic_answer(
    user_query: str,
    structured_query: StructuredQuery,
    records: List[Dict[str, Any]]
) -> str:
    """
    High-quality deterministic fallback response synthesizer.
    Used when LLM is unavailable or offline.
    Never invents data; returns 'No data found' when empty.
    Groups records by source dataset/file/collection and formats them preserving
    only the columns that actually exist in each source.
    """
    if not records:
        return "No data found"

    from .retrieval_service import group_records_by_source
    source_groups = group_records_by_source(records)

    dataset_sections = []

    for src in source_groups:
        col = src.get("source_collection", "dataset_records")
        f_name = src.get("source_file", f"{col}.xlsx")
        sheet = src.get("source_sheet")
        src_recs = src.get("records", [])

        # Display ONLY Source File name at the top (and sheet if present)
        sec_lines = [
            f"**Source File: {f_name}**"
        ]
        if sheet and sheet != "Not Available":
            sec_lines.append(f"**Source Sheet: {sheet}**")

        rec_blocks = []
        for r in src_recs:
            r_lines = []
            s_row = is_valid_source_row(r.get("source_row"))
            if s_row:
                r_lines.append(f"**Source Row: {s_row}**")

            source_fields = extract_original_source_fields(r)
            for k, v in source_fields.items():
                formatted_v = format_clickable_value(k, v)
                r_lines.append(f"{k}: {formatted_v}")
            if r_lines:
                rec_blocks.append("\n".join(r_lines))

        if rec_blocks:
            dataset_text = "\n".join(sec_lines) + "\n\n" + "\n\n".join(rec_blocks)
        else:
            dataset_text = "\n".join(sec_lines)

        dataset_sections.append(dataset_text.strip())

    return "\n\n---\n\n".join(dataset_sections).strip()


async def generate_final_answer(
    user_query: str,
    structured_query: StructuredQuery,
    records: List[Dict[str, Any]]
) -> str:
    """
    Calls the Final Answer LLM with the retrieved database records grouped by source.
    Preserves source-specific columns and falls back to deterministic generator if LLM is offline.
    """
    if not records:
        return "No data found"

    from .retrieval_service import group_records_by_source
    source_groups = group_records_by_source(records)

    # Format the retrieved records grouped by source for LLM context
    formatted_sources = []
    for src in source_groups:
        cleaned_records = []
        for r in src["records"][:15]:
            sf = extract_original_source_fields(r)
            cleaned_records.append(sf)

        s_entry = {
            "Source File": src.get("source_file", ""),
            "Source Sheet": src.get("source_sheet"),
            "Source Row": is_valid_source_row(src["records"][0].get("source_row")) if src["records"] else None,
            "records": cleaned_records
        }
        formatted_sources.append(s_entry)

    user_prompt = f"""User Question:
{user_query}

Retrieved Records Grouped By Source ({len(records)} total records across {len(source_groups)} sources):
{json.dumps(formatted_sources, indent=2)}

Please answer the user's question by formatting the records grouped by source file.
At the top of each section, show ONLY:
**Source File: <Source File name>**
(and **Source Sheet: <Source Sheet>** if available)

DO NOT include "Dataset: ...", "Database: ...", or "MongoDB Atlas".

Then directly list the retrieved records. If a record has a source row, show:
**Source Row: <row>**
followed by the actual columns:
<Column Name>: <Value>

CRITICAL RULES:
- Format ALL emails as clickable markdown links: [email@domain.com](mailto:email@domain.com)
- Format ALL URLs and LinkedIn links as clickable markdown links: [https://...](https://...)
- DO NOT show "Dataset: ...", "Database: ...", "MongoDB Atlas".
- DO NOT show "SOURCE 1", "SOURCE 2", etc.
- DO NOT show "Record 1", "Record 2", etc.
- DO NOT show internal normalized fields (Norm Company Name, etc.) or raw data.
- If results come from multiple sources, simply separate them with "---".
- Display ONLY the columns that actually exist in that source file."""

    try:
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": FINAL_ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.0}
        }

        endpoint = f"{OLLAMA_BASE_URL}/api/chat"
        if "/v1" in OLLAMA_BASE_URL:
            endpoint = f"{OLLAMA_BASE_URL}/chat/completions"

        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code == 404 and "/v1" not in OLLAMA_BASE_URL:
                response = await client.post(f"{OLLAMA_BASE_URL}/v1/chat/completions", json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                raw_answer = ""
                if "message" in data and isinstance(data["message"], dict):
                    raw_answer = data["message"].get("content", "").strip()
                elif "choices" in data and len(data["choices"]) > 0:
                    raw_answer = data["choices"][0].get("message", {}).get("content", "").strip()

                if raw_answer:
                    return sanitize_final_answer(raw_answer)
    except Exception:
        pass

    return generate_deterministic_answer(user_query, structured_query, records)
