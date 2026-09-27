import json
import os
import re
from typing import Optional
import httpx
from dotenv import load_dotenv
from .schemas import QueryIntent

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", os.getenv("LLM_API_KEY", "")).strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:120b")

SYSTEM_PROMPT = """You are an intelligent query parser for a structured company database.

Your only task is to understand the user's natural language search request
and identify the relevant database field and search value.

You do NOT have access to the database.
You must NOT invent company information.
You must NOT answer using your general knowledge.
Never generate SQL.
Return ONLY valid JSON.

Database searchable fields across collections:
1. company_name       : Company Name or business name
2. contact_person     : Contact Person name / manager / executive
3. designation        : Job title, designation, position (e.g. Director, Manager, Engineer)
4. mobile_no          : Mobile number (e.g., 9876543210, +91-9876543210)
5. landline_telephone : Landline / Telephone / Office phone
6. telephone_1        : Telephone 1
7. telephone_2        : Telephone 2
8. email              : Email address (searches Email, Email 1, Email 2)
9. address            : Physical address, street, building, or location
10. city              : City (e.g., Chennai, Mumbai, Coimbatore, Bangalore)
11. state             : State (e.g., Tamil Nadu, Maharashtra, Karnataka)
12. pin               : Postal PIN code / ZIP code (e.g., 600001)
13. group             : Group / Business conglomerate / Division
14. records_merged    : Records merged count/status
15. review_required   : Review required status
16. sources           : Source catalog/fair/exhibition
17. remarks           : Remarks, notes, status, or comments

Special shortcuts:
- Use "email" if user mentions email generally
- Use "phone" or "landline" if user mentions phone/telephone/landline
- Use "city" if user is filtering by a city name
- Use "designation" if user is filtering by a person's role or designation

Response format:
{
  "field": "company_name" | "contact_person" | "designation" | "mobile_no" | "landline" | "phone" | "email" | "address" | "city" | "state" | "pin" | "group" | "remarks" | null,
  "value": "extracted search string"
}

Examples:
- "Find ABC Tech" -> {"field": "company_name", "value": "ABC Tech"}
- "Show companies in Chennai" -> {"field": "city", "value": "Chennai"}
- "Search for Director Rajesh" -> {"field": "contact_person", "value": "Rajesh"}
- "Look up General Manager" -> {"field": "designation", "value": "General Manager"}
- "Show companies in Tata Group" -> {"field": "group", "value": "Tata"}
- "Lookup mobile 9876543210" -> {"field": "mobile_no", "value": "9876543210"}
- "Email info@xyz.com" -> {"field": "email", "value": "info@xyz.com"}
- "Call 044-24567890" -> {"field": "phone", "value": "044-24567890"}
- "PIN 600028" -> {"field": "pin", "value": "600028"}
- "Address Guindy" -> {"field": "address", "value": "Guindy"}

If no specific field is identified, return:
{
  "field": null,
  "value": "user's search text"
}"""


def fallback_query_parser(message: str) -> QueryIntent:
    """
    Intelligent heuristic fallback if Ollama is unreachable or returns malformed response.
    Recognizes emails, phones, PIN codes, contact person patterns, group names, etc.
    """
    clean = message.strip()

    # 1. Email pattern
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean)
    if email_match:
        # Check if email 1 or email 2 explicitly mentioned
        if re.search(r"email\s*2\b", clean, re.IGNORECASE):
            return QueryIntent(field="email_2", value=email_match.group(0).strip())
        elif re.search(r"email\s*1\b", clean, re.IGNORECASE):
            return QueryIntent(field="email_1", value=email_match.group(0).strip())
        return QueryIntent(field="email", value=email_match.group(0).strip())

    # 2. PIN code pattern (e.g., "PIN 600001", "pincode 560001", or standalone 6-digit number)
    pin_match = re.search(r"\b(?:pin|pincode|zip|zipcode|postal\s*code)?\s*[:#-]?\s*([1-9][0-9]{5})\b", clean, re.IGNORECASE)
    if pin_match and re.search(r"\b(?:pin|pincode|zip|postal)\b", clean, re.IGNORECASE):
        return QueryIntent(field="pin", value=pin_match.group(1).strip())

    # 3. Phone / Mobile pattern
    phone_clean = clean
    field_detected = "phone"
    if re.search(r"\b(mobile(?:\s*no\.?)?|cell)\b", clean, re.IGNORECASE):
        field_detected = "mobile_no"
        phone_clean = re.sub(r"\b(mobile(?:\s*no\.?)?|cell)\s*[:#-]?\s*", "", clean, flags=re.IGNORECASE)
    elif re.search(r"\b(tel\s*1|telephone\s*1)\b", clean, re.IGNORECASE):
        field_detected = "telephone_1"
        phone_clean = re.sub(r"\b(tel\s*1|telephone\s*1)\s*[:#-]?\s*", "", clean, flags=re.IGNORECASE)
    elif re.search(r"\b(tel\s*2|telephone\s*2)\b", clean, re.IGNORECASE):
        field_detected = "telephone_2"
        phone_clean = re.sub(r"\b(tel\s*2|telephone\s*2)\s*[:#-]?\s*", "", clean, flags=re.IGNORECASE)
    elif re.search(r"\b(tel|telephone|phone|call)\b", clean, re.IGNORECASE):
        field_detected = "phone"
        phone_clean = re.sub(r"\b(tel|telephone|phone|call)\s*[:#-]?\s*", "", clean, flags=re.IGNORECASE)

    phone_match = re.search(r"(\+?\d[\d\s-]{5,15}\d)", phone_clean)
    if phone_match and not re.search(r"[a-zA-Z]", phone_match.group(0)):
        cleaned_phone = phone_match.group(0).strip()
        return QueryIntent(field=field_detected, value=cleaned_phone)

    # 4. Contact Person pattern
    contact_match = re.search(r"\b(?:contact\s*person|contact|representative|manager|mr\.|ms\.|mrs\.)\s*[:\-]?\s*([a-zA-Z\s.]+)", clean, re.IGNORECASE)
    if contact_match:
        val = contact_match.group(1).strip()
        if len(val) > 2:
            return QueryIntent(field="contact_person", value=val)

    # 5. Group pattern
    group_match = re.search(r"\b(?:group|division)\s*[:\-]?\s*([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
    if group_match:
        val = group_match.group(1).strip()
        if len(val) > 1:
            return QueryIntent(field="group", value=val)

    # 6. Remarks pattern
    remarks_match = re.search(r"\b(?:remarks?|notes?|comments?)\s*[:\-]?\s*([a-zA-Z0-9\s]+)", clean, re.IGNORECASE)
    if remarks_match:
        val = remarks_match.group(1).strip()
        if len(val) > 1:
            return QueryIntent(field="remarks", value=val)

    # 7. Address / Location keywords
    addr_match = re.search(r"\b(?:in|at|located in|address)\s+([a-zA-Z0-9\s,.-]+)$", clean, re.IGNORECASE)
    if addr_match:
        return QueryIntent(field="address", value=addr_match.group(1).strip())

    # 8. Clean conversational prefixes and default to company_name
    prefix_patterns = [
        r"^(find|search|show|get|display|lookup|look for|who is|which company has|tell me about)\s+(me\s+)?(the\s+)?(company\s+)?(named|with|having|called)?\s*",
        r"^(company\s+)?(details|info|record)\s+(for|of)\s*",
    ]
    extracted = clean
    for pat in prefix_patterns:
        extracted = re.sub(pat, "", extracted, flags=re.IGNORECASE).strip()

    if extracted:
        return QueryIntent(field="company_name", value=extracted)

    return QueryIntent(field=None, value=None)


async def parse_query_with_llm(user_message: str) -> QueryIntent:
    """
    Calls Ollama to parse natural language user search intent into a structured QueryIntent.
    Ensures strict JSON response without SQL generation.
    """
    if not user_message or not user_message.strip():
        return QueryIntent(field=None, value=None)

    # 1. Attempt Ollama Cloud / API
    try:
        headers = {
            "Content-Type": "application/json"
        }
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message.strip()}
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0
            }
        }

        # Try native /api/chat endpoint first, or /v1/chat/completions if using OpenAI-compatible cloud proxy
        endpoint = f"{OLLAMA_BASE_URL}/api/chat"
        if "/v1" in OLLAMA_BASE_URL:
            endpoint = f"{OLLAMA_BASE_URL}/chat/completions"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            
            # If 404 on /api/chat, try /v1/chat/completions fallback for cloud proxies
            if response.status_code == 404 and "/v1" not in OLLAMA_BASE_URL:
                response = await client.post(f"{OLLAMA_BASE_URL}/v1/chat/completions", json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()

                # Extract content from either native Ollama or OpenAI format
                raw_content = ""
                if "message" in data and isinstance(data["message"], dict):
                    raw_content = data["message"].get("content", "").strip()
                elif "choices" in data and len(data["choices"]) > 0:
                    raw_content = data["choices"][0].get("message", {}).get("content", "").strip()

                # Clean markdown backticks if any
                cleaned_content = re.sub(r"^```(json)?", "", raw_content, flags=re.MULTILINE)
                cleaned_content = re.sub(r"```$", "", cleaned_content, flags=re.MULTILINE).strip()

                if cleaned_content:
                    parsed = json.loads(cleaned_content)
                    field = parsed.get("field")
                    value = parsed.get("value")

                    if field and value:
                        return QueryIntent(field=str(field).strip().lower(), value=str(value).strip())
                    elif value:
                        return QueryIntent(field=None, value=str(value).strip())
            else:
                print(f"[Ollama Cloud Status] HTTP {response.status_code}: {response.text[:200]}")

    except Exception as e:
        print(f"[Ollama Cloud Warning] Request failed or unavailable ({e}). Using fallback parser.")

    # 2. Fallback heuristic parser
    return fallback_query_parser(user_message)
