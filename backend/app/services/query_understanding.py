import os
import re
import json
from typing import Optional, List, Dict, Any, Tuple
import httpx
from pydantic import BaseModel, Field
from ..config import (
    PRIVACY_MODE,
    OLLAMA_BASE_URL,
    OLLAMA_API_KEY,
    LLM_MODEL,
)


class StructuredQuery(BaseModel):
    intent: str = Field(
        "general_search",
        description="Intent: company_search, person_search, contact_search, location_search, designation_search, department_search, mixed_search, general_search"
    )
    companies: List[str] = Field(default_factory=list, description="List of individual company names (never collapsed into one)")
    people: List[str] = Field(default_factory=list, description="List of individual person names")
    designation: Optional[str] = Field(None, description="Job title or role (e.g. Quality Manager, Quality Head, Director)")
    department: Optional[str] = Field(None, description="Department name (e.g. Quality, Sales, HR, Production)")
    state: Optional[str] = Field(None, description="State name dynamically extracted from query")
    city: Optional[str] = Field(None, description="City name dynamically extracted from query")
    country: Optional[str] = Field(None, description="Country name dynamically extracted from query")
    location: Optional[str] = Field(None, description="General or unspecified location (e.g. territory, area, address)")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional structured filter criteria")
    semantic_query: str = Field("", description="Natural language semantic search query for vector retrieval")
    original_query: str = Field("", description="The original user query text")


QUERY_UNDERSTANDING_SYSTEM_PROMPT = """You are a strict Query Understanding LLM for an enterprise company and contact directory RAG system.
Your ONLY task is to convert the user's natural language question into a clean, validated JSON object.

CRITICAL RULES:
1. Do NOT answer the user's question.
2. Return ONLY a single raw JSON object matching the schema below. No markdown backticks, no explanations.
3. EXACT/ENTITY QUERIES:
   If the user enters a company name directly (e.g. "2D INC", "TVS", "ABC Industries", "Find TVS", "Show 2D INC", "Search for 2D INC"):
   - "intent": "company_search"
   - "companies": ["2D INC"] (or ["TVS"], ["ABC Industries"])
   - NEVER populate "semantic_query" for explicit entity queries! Leave "semantic_query" as "".
4. MULTIPLE COMPANIES:
   When user mentions multiple companies (e.g. "Find ABC, TVS and 2D INC", "ABC, TVS and XYZ", "Give me ABC, TVS and XYZ"):
   - "companies": ["ABC", "TVS", "XYZ"]
   - NEVER collapse them into a single string. Leave "semantic_query" as "".
5. PERSON NAME SEARCH:
   - "Find Ravi Kumar" or "Ravi Kumar" -> "intent": "person_search", "people": ["Ravi Kumar"], "companies": []
   - NEVER interpret person names as company names. Leave "semantic_query" as "".
6. DYNAMIC LOCATION EXTRACTION:
   Extract any state, city, country, or location dynamically from the query.
   - "Companies in Andhra Pradesh" -> "state": "Andhra Pradesh", "intent": "location_search", "companies": []
   - "Which companies are available in Chennai?" -> "city": "Chennai", "intent": "location_search", "companies": []
   - "Companies in Tamil Nadu" -> "state": "Tamil Nadu", "intent": "location_search", "companies": []
7. DESIGNATION & DEPARTMENT & HYBRID:
   - "quality managers in Tamil Nadu" -> "designation": "Quality Manager", "department": "Quality", "state": "Tamil Nadu", "intent": "mixed_search"
   - "quality contacts from ABC, TVS and 2D INC" -> "companies": ["ABC", "TVS", "2D INC"], "department": "Quality", "intent": "company_search"
   - "Who is the Quality Head of ABC?" -> "companies": ["ABC"], "designation": "Quality Head", "department": "Quality", "intent": "mixed_search"
8. SEMANTIC QUERIES:
   ONLY if the query is conceptual, descriptive, or procedural (e.g. "Who is responsible for quality operations?", "Describe the calibration process", "Show companies matching this description"):
   - "intent": "general_search"
   - "semantic_query": "<the full user query>"
   - Do NOT populate "companies" or "people" for pure conceptual questions.

Supported Intents:
- company_search
- person_search
- contact_search
- location_search
- designation_search
- department_search
- mixed_search
- general_search

JSON Schema to output:
{
  "intent": "company_search" | "person_search" | "contact_search" | "location_search" | "designation_search" | "department_search" | "mixed_search" | "general_search",
  "companies": ["string"],
  "people": ["string"],
  "designation": "string" | null,
  "department": "string" | null,
  "state": "string" | null,
  "city": "string" | null,
  "country": "string" | null,
  "location": "string" | null,
  "filters": {},
  "semantic_query": "string",
  "original_query": "string"
}"""


def split_comma_and_conjunction(text: str) -> List[str]:
    """
    Splits phrases like 'ABC, XYZ and PQR' or 'ABC and XYZ' into ['ABC', 'XYZ', 'PQR'].
    Preserves multi-word entity names like 'Tata Motors' or '2D INC'.
    """
    clean = text.strip()
    if not clean:
        return []
    standardized = re.sub(r"\s+(?:and|&)\s+", ", ", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in standardized.split(",") if p.strip()]
    return parts


COMPANY_SUFFIX_TOKENS = {
    "pvt ltd", "private limited", "pvt", "ltd", "limited", "corp", "corporation",
    "inc", "incorporated", "llc", "llp", "group", "enterprises", "enterprise",
    "industries", "industry", "tech", "technologies", "solutions", "motors",
    "systems", "automations", "automation", "engineering", "products", "tools",
    "company", "companies", "co"
}


def fallback_query_understanding(user_query: str) -> StructuredQuery:
    """
    High-precision, fully dynamic NLP fallback query parser and classifier.
    Accurately classifies:
    - Exact entity queries: "2D INC", "TVS", "ABC Industries", "Find TVS", "Show ABC company"
    - Multi-entity queries: "Find ABC, TVS and 2D INC", "ABC, TVS and XYZ", "Give me quality contacts from ABC, XYZ and PQR"
    - Person name queries: "Find Ravi Kumar", "Ravi Kumar"
    - Structured location queries: "Companies in Tamil Nadu", "Which companies are in Andhra Pradesh?"
    - Structured + semantic / hybrid queries: "Quality managers in Tamil Nadu"
    - Semantic queries: "Who is responsible for quality operations?"
    """
    clean = user_query.strip()
    q_lower = clean.lower()

    companies: List[str] = []
    people: List[str] = []
    designation: Optional[str] = None
    department: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    semantic_query = ""
    intent = "general_search"

    # 1. Pure conceptual/semantic query detection
    is_semantic_intent = bool(re.search(
        r"\b(who\s+is\s+responsible\s+for|responsible\s+for|who\s+handles|how\s+to|what\s+is\s+the\s+procedure|describe|matching\s+this\s+description|explain|overview\s+of)\b",
        q_lower
    ))

    # 2. Department Detection
    dept_match = re.search(
        r"\b(quality|sales|marketing|hr|human resources|finance|production|operations|purchase|procurement|r&d|research)\b",
        clean,
        re.IGNORECASE
    )
    if dept_match and not is_semantic_intent:
        matched_word = dept_match.group(1).lower()
        if any(w in q_lower for w in ["department", "dept", "team", "division", "contacts", "operations", "quality"]):
            if matched_word == "hr":
                department = "Human Resources"
            elif matched_word == "r&d":
                department = "R&D"
            else:
                department = matched_word.title()
            intent = "department_search"

    # 3. Designation Detection (e.g. Quality Manager, Quality Head, Director, Engineer)
    desig_patterns = [
        r"\b(quality\s+(?:managers?|heads?|engineers?|leads?|directors?|executives?|officers?|supervisors?|inspectors?))\b",
        r"\b(head\s+of\s+quality)\b",
        r"\b(general\s+managers?|managing\s+directors?|directors?|ceo|cto|cfo|vice\s+presidents?|vp)\b",
        r"\b(sales\s+(?:managers?|heads?|executives?|leads?|directors?))\b",
        r"\b(plant\s+heads?|operations\s+managers?|production\s+managers?)\b",
    ]
    if not is_semantic_intent:
        for pat in desig_patterns:
            d_match = re.search(pat, clean, re.IGNORECASE)
            if d_match:
                raw_desig = d_match.group(1).strip()
                raw_lower = raw_desig.lower()
                if raw_lower.endswith("s") and not raw_lower.endswith("ss"):
                    raw_lower = raw_lower[:-1]
                if raw_lower == "head of quality":
                    designation = "Quality Head"
                else:
                    designation = raw_lower.title()
                if not department and "quality" in raw_desig.lower():
                    department = "Quality"
                intent = "designation_search"
                break

    # 4. Dynamic Location Extraction
    loc_match = re.search(
        r"\b(?:available\s+in|located\s+in|based\s+in|in|at)\s+([A-Za-z][A-Za-z\s,.-]+?)(?:\s+(?:having|with|for|where|across|and\s+has|who\s+is|companies|company)|\?|\.|$)",
        clean,
        re.IGNORECASE
    )
    if loc_match and not is_semantic_intent:
        extracted_loc = loc_match.group(1).strip()
        extracted_loc = re.sub(r"^(?:the\s+)", "", extracted_loc, flags=re.IGNORECASE)
        extracted_loc = re.sub(r"\s+(?:state|city|region|district|country|territory)$", "", extracted_loc, flags=re.IGNORECASE).strip()

        if extracted_loc.lower() not in ("quality", "quality manager", "sales", "all files", "every file", "uploaded files", "this description"):
            location = extracted_loc.title()
            if "city" in q_lower:
                city = location
            elif "state" in q_lower:
                state = location
            elif "country" in q_lower:
                country = location
            else:
                location = extracted_loc.title()
                state = location
            intent = "location_search"

    # 5. Person Name Extraction (e.g. "Find Ravi Kumar", "Search Ravi Kumar", "Ravi Kumar")
    if not is_semantic_intent and not designation:
        person_match = re.search(
            r"\b(?:find|search\s+for|search\s+all\s+uploaded\s+files\s+for|look\s+for|who\s+is)\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)\b",
            clean,
            re.IGNORECASE
        )
        if person_match:
            p_cand = person_match.group(1).strip().rstrip("?.!")
            p_lower = p_cand.lower()
            words = p_lower.split()
            if (
                not any(w in COMPANY_SUFFIX_TOKENS for w in words)
                and p_lower not in ("quality manager", "quality head", "all files", "andhra pradesh", "tamil nadu", "companies", "the companies")
                and not any(w in p_lower for w in ["technologies", "automations", "motors", "industries", "systems", "solutions"])
            ):
                people.append(p_cand.title())
                intent = "person_search"
        elif not location and not department:
            # Check standalone 2-3 word capitalized person name
            if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}", clean):
                words = clean.lower().split()
                if not any(w in COMPANY_SUFFIX_TOKENS for w in words):
                    people.append(clean)
                    intent = "person_search"

    # 6. Entity & Company Extraction
    is_general_location_query = bool(location and re.search(r"\b(?:companies|firms|businesses|customers)\b", clean, re.IGNORECASE))
    is_role_loc = bool(designation and location)
    is_role_only = bool(designation and not re.search(r"\b(?:of|from|at)\s+[A-Za-z0-9&.-]+", clean, re.IGNORECASE))

    if not people and not is_semantic_intent and not is_general_location_query and not is_role_loc and not is_role_only:
        # Check "Who is the Quality Head of ABC?" or "Quality manager at TVS"
        of_comp_match = re.search(r"\b(?:of|from|at)\s+([A-Za-z0-9&.-]+(?:\s+[A-Za-z0-9&.-]+)?)\b[?.!]*$", clean, re.IGNORECASE)
        if of_comp_match and designation:
            c_val = of_comp_match.group(1).strip()
            if c_val.lower() not in ("quality", "all files"):
                companies.append(c_val)
                intent = "company_search"
        else:
            # Strip command prefixes
            prefix_pattern = (
                r"^(?:find|show|search\s+for|look\s+for|get|give\s+me|details\s+of|list\s+of\s+companies\s+in|companies\s+in|list\s+of|companies\s*:?|company\s*:?)\s+"
                r"|(?:give\s+me\s+)?(?:quality\s+)?contacts?\s+(?:of|from)\s+"
            )
            cmd_stripped = re.sub(prefix_pattern, "", clean, flags=re.IGNORECASE).strip().rstrip("?.!")

            standardized = re.sub(r"\s+(?:and|&)\s+", ", ", cmd_stripped, flags=re.IGNORECASE)
            parts = [p.strip().rstrip("?.!") for p in standardized.split(",") if p.strip()]

            cleaned_parts = []
            for p in parts:
                p_clean = re.sub(r"\s+\b(?:companies|company|firm|firms)\b\.?$", "", p, flags=re.IGNORECASE).strip()
                p_lower = p_clean.lower()
                if designation and (p_lower == designation.lower() or designation.lower() in p_lower or p_lower in designation.lower()):
                    continue
                if p_clean and p_lower not in ("quality", "contacts", "all", "uploaded", "this description"):
                    cleaned_parts.append(p_clean)

            if len(cleaned_parts) > 1:
                companies.extend(cleaned_parts)
                intent = "company_search"
            elif len(cleaned_parts) == 1:
                single_c = cleaned_parts[0]
                if single_c.lower() not in ("quality", "sales", "all files", "this description"):
                    companies.append(single_c)
                    intent = "company_search"

    # 7. Semantic Query Assignment
    if is_semantic_intent or ("responsible for" in q_lower or "matching this description" in q_lower):
        semantic_query = clean
        intent = "general_search"
    elif not (companies or people or location or state or city or designation or department):
        if len(clean.split()) <= 4:
            companies.append(clean)
            intent = "company_search"
        else:
            semantic_query = clean
            intent = "general_search"

    # Multi-intent classification
    if (companies and people) or (companies and location) or (designation and location) or (department and location) or (companies and designation):
        intent = "mixed_search"
    elif companies and len(companies) > 1:
        intent = "company_search"
    elif people:
        intent = "person_search"
    elif companies:
        intent = "company_search"
    elif designation:
        intent = "designation_search"
    elif department:
        intent = "department_search"
    elif location or state or city:
        intent = "location_search"

    return StructuredQuery(
        intent=intent,
        companies=companies,
        people=people,
        designation=designation,
        department=department,
        state=state,
        city=city,
        country=country,
        location=location,
        filters={},
        semantic_query=semantic_query,
        original_query=clean
    )


async def parse_query_understanding(user_query: str) -> Tuple[StructuredQuery, bool]:
    """
    Main Query Understanding entry point.
    1. Invokes Query Understanding LLM (Ollama) with strict schema prompt.
    2. Validates output with Pydantic StructuredQuery model.
    3. If LLM fails, times out, or produces invalid output:
       Executes fallback_query_understanding to guarantee 100% reliability.
    Returns (StructuredQuery, was_llm_generated: bool).
    """
    clean_query = user_query.strip()
    if not clean_query:
        return StructuredQuery(original_query=""), False

    # Under PRIVACY_MODE, never call external LLM; use deterministic heuristic parsing
    if PRIVACY_MODE:
        fallback_result = fallback_query_understanding(clean_query)
        return fallback_result, False

    # Attempt LLM query understanding
    try:
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": QUERY_UNDERSTANDING_SYSTEM_PROMPT},
                {"role": "user", "content": clean_query}
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0}
        }

        endpoint = f"{OLLAMA_BASE_URL}/api/chat"
        if "/v1" in OLLAMA_BASE_URL:
            endpoint = f"{OLLAMA_BASE_URL}/chat/completions"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            if response.status_code == 404 and "/v1" not in OLLAMA_BASE_URL:
                response = await client.post(f"{OLLAMA_BASE_URL}/v1/chat/completions", json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                raw_content = ""
                if "message" in data and isinstance(data["message"], dict):
                    raw_content = data["message"].get("content", "").strip()
                elif "choices" in data and len(data["choices"]) > 0:
                    raw_content = data["choices"][0].get("message", {}).get("content", "").strip()

                cleaned_content = re.sub(r"^```(json)?", "", raw_content, flags=re.MULTILINE)
                cleaned_content = re.sub(r"```$", "", cleaned_content, flags=re.MULTILINE).strip()

                if cleaned_content:
                    parsed_dict = json.loads(cleaned_content)
                    parsed_dict["original_query"] = clean_query

                    # Ensure companies is a list of strings
                    raw_companies = parsed_dict.get("companies")
                    if isinstance(raw_companies, str):
                        parsed_dict["companies"] = split_comma_and_conjunction(raw_companies)
                    elif isinstance(raw_companies, list):
                        flat_companies = []
                        for item in raw_companies:
                            if isinstance(item, str):
                                flat_companies.extend(split_comma_and_conjunction(item))
                        parsed_dict["companies"] = flat_companies

                    # Ensure people is a list of strings
                    raw_people = parsed_dict.get("people")
                    if isinstance(raw_people, str):
                        parsed_dict["people"] = [raw_people.strip()]

                    # Validate with Pydantic
                    structured = StructuredQuery(**parsed_dict)
                    return structured, True

    except Exception as e:
        # LLM unavailable, timed out, or returned malformed JSON
        pass

    # High-accuracy fallback
    fallback_result = fallback_query_understanding(clean_query)
    return fallback_result, False
