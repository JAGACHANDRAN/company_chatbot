"""
LLM Answer Generation Module for Calispec Hybrid RAG.
SECURITY GUARANTEES:
1. Receives ONLY: user question, last 3 chat turns, and masked matching records.
2. Only allowed fields in payload: company, person, designation, city, plus placeholders [PHONE_n], [EMAIL_n].
3. Unmasks placeholders in the backend before returning.
"""
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import httpx

from .config import (
    LLM_MODE,
    OLLAMA_CLOUD_URL,
    OLLAMA_LOCAL_URL,
    OLLAMA_API_KEY,
    LLM_MODEL,
    LLM_REASONING,
    MASK_PII,
)
from .services.pii_mask import mask_records, unmask_text
from .services.response_generator import deterministic_synthesize

logger = logging.getLogger("calispec.llm")


def call_llm(*args, **kwargs):
    """Legacy stub for backwards compatibility with test harnesses."""
    raise RuntimeError("Direct call_llm deprecated. Use generate_answer().")


RAG_SYSTEM_PROMPT = """You are a contact-search assistant for a metrology and calibration business directory. Answer ONLY from the provided records. When contacts or companies are found, include all matching companies and their details from the provided records without omitting matching entries. Never invent companies, people, phone numbers or emails. Use placeholders exactly as given."""


def format_records_for_llm(masked_records: List[Dict[str, str]]) -> str:
    """Formats masked records into compact key: value lines for the LLM prompt."""
    lines = []
    for idx, r in enumerate(masked_records, start=1):
        lines.append(f"Record {idx}:")
        lines.append(f"  Company: {r.get('company', 'Not Available')}")
        lines.append(f"  Contact Person: {r.get('person', 'Not Available')}")
        lines.append(f"  Designation: {r.get('designation', 'Not Available')}")
        lines.append(f"  City: {r.get('city', 'Not Available')}")
        lines.append(f"  Phone: {r.get('phone', 'Not Available')}")
        lines.append(f"  Email: {r.get('email', 'Not Available')}")
    return "\n".join(lines)


async def generate_answer(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
    records: Optional[List[Dict[str, Any]]] = None,
    max_records: int = 50
) -> Dict[str, Any]:
    """
    Generates a secure RAG answer via gpt-oss:120b.
    1. Masks phone numbers and emails to [PHONE_1], [EMAIL_1]...
    2. Calls Ollama Cloud (or local signed-in endpoint) with strict grounding prompt.
    3. Unmasks placeholders back to original values in backend.
    4. Returns {answer: str, records: List[Dict], meta: Dict}.
    """
    if not records:
        return {
            "answer": "I could not find any matching contact or company records in the database.",
            "records": [],
            "meta": {"status": "no_records", "latency_ms": 0}
        }

    # 1. PII Masking
    if MASK_PII:
        masked_recs, placeholder_map = mask_records(records, max_records=max_records)
    else:
        masked_recs = [{k: str(v) for k, v in r.items() if k in ("company", "person", "designation", "city", "phone", "email")} for r in records[:max_records]]
        placeholder_map = {}

    formatted_context = format_records_for_llm(masked_recs)

    # 2. Build conversation messages (System + History + Prompt)
    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]

    # Include at most last 3 history turns
    if history:
        for turn in history[-3:]:
            role = turn.get("role") or ("user" if "user" in turn else "assistant")
            content = turn.get("content") or turn.get("message") or turn.get("user") or turn.get("assistant") or ""
            if content:
                messages.append({"role": role, "content": str(content).strip()})

    user_prompt = f"Provided Records:\n{formatted_context}\n\nUser Question: {question.strip()}"
    messages.append({"role": "user", "content": user_prompt})

    # 3. Resolve endpoint and headers per LLM_MODE
    if LLM_MODE == "local_signed_in":
        endpoint = f"{OLLAMA_LOCAL_URL}/api/chat"
        headers = {"Content-Type": "application/json"}
        model_to_use = f"{LLM_MODEL}-cloud" if not LLM_MODEL.endswith("-cloud") else LLM_MODEL
    else:  # cloud_direct
        endpoint = f"{OLLAMA_CLOUD_URL}/api/chat"
        if "/v1" in OLLAMA_CLOUD_URL:
            endpoint = f"{OLLAMA_CLOUD_URL}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
        model_to_use = LLM_MODEL

    payload = {
        "model": model_to_use,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "reasoning": LLM_REASONING
        }
    }

    t_start = time.time()
    unmasked_text = None
    meta: Dict[str, Any] = {
        "model": model_to_use,
        "llm_mode": LLM_MODE,
        "masked_records_count": len(masked_recs),
        "placeholders_count": len(placeholder_map),
        "fallback_used": False
    }

    # 4. Invoke LLM with retry
    for attempt in range(1, 3):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    raw_reply = ""
                    if "message" in data and isinstance(data["message"], dict):
                        raw_reply = data["message"].get("content", "").strip()
                    elif "choices" in data and len(data["choices"]) > 0:
                        raw_reply = data["choices"][0].get("message", {}).get("content", "").strip()

                    if raw_reply:
                        # Unmask backend placeholders
                        unmasked_text = unmask_text(raw_reply, placeholder_map) if MASK_PII else raw_reply
                        meta["tokens_prompt"] = data.get("prompt_eval_count")
                        meta["tokens_completion"] = data.get("eval_count")
                        break
                else:
                    logger.warning(f"[LLM] HTTP {res.status_code} from {endpoint}: {res.text[:200]}")
        except Exception as err:
            logger.warning(f"[LLM Attempt {attempt}/2 Failed] Error: {err}")

    latency_ms = round((time.time() - t_start) * 1000, 2)
    meta["latency_ms"] = latency_ms

    # 5. Fallback if LLM failed or key missing
    if not unmasked_text:
        logger.warning(f"[LLM Fallback] Generating deterministic answer for query.")
        meta["fallback_used"] = True
        unmasked_text = deterministic_synthesize(records[:max_records])

    logger.info(f"[LLM Completed] Latency: {latency_ms}ms | Records: {len(masked_recs)} | Fallback: {meta['fallback_used']}")

    return {
        "answer": unmasked_text,
        "records": records[:max_records],
        "meta": meta
    }
