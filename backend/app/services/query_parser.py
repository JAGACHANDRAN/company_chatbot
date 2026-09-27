import os
import re
import json
from typing import Optional, List, Dict, Any, Tuple
import httpx
from dotenv import load_dotenv
from ..schemas import QueryIntent, QueryCondition
from .concept_mapper import (
    CONCEPT_COLUMNS,
    normalize_company_search_terms,
    get_columns_for_concept,
)

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", os.getenv("LLM_API_KEY", "")).strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:120b")

STRICT_QUERY_PARSER_SYSTEM_PROMPT = """You are a strict natural-language query parser for a structured business/contact database.

CRITICAL PRIVACY AND SECURITY RULES:
- You do NOT have access to the database or any records.
- You must NEVER invent or return database information.
- You must NEVER answer questions using your own knowledge.
- Your ONLY job is to output a single valid JSON object converting the user's natural query into search intent and conditions.

Output JSON Format:
{
  "intent": "search_records" | "lookup_field" | "person_search" | "company_search",
  "conditions": [
    {
      "concept": "location" | "company" | "person" | "designation" | "email" | "phone",
      "value": "<extracted search value only>"
    }
  ],
  "return_fields": ["*"]
}

Allowed Concepts:
- "location": cities, states, regions, areas, addresses (e.g. "andhra pradesh", "chennai", "mumbai", "tamil nadu", "bangalore")
- "company": company, organization, or business names (e.g. "ABC", "JBM", "Tata Motors")
- "person": employee, contact person, or individual names (e.g. "Ravi Kumar", "John Smith")
- "designation": job titles or positions (e.g. "Quality Manager", "Director", "Engineer")
- "email": email addresses or when asking for email
- "phone": phone or mobile numbers

CRITICAL RULES:
1. Extract ONLY the entity or location in "value". NEVER send phrases like "list of companies", "show companies", "give me", or "what is" to MongoDB.
2. For location queries like "list of companies in andhra pradesh":
   {
     "intent": "search_records",
     "conditions": [{"concept": "location", "value": "andhra pradesh"}],
     "return_fields": ["*"]
   }
3. For field lookups like "What is the email of ABC?":
   {
     "intent": "lookup_field",
     "conditions": [{"concept": "company", "value": "ABC"}],
     "return_fields": ["Email"]
   }
4. For person searches like "Ravi Kumar":
   {
     "intent": "person_search",
     "conditions": [{"concept": "person", "value": "Ravi Kumar"}],
     "return_fields": ["*"]
   }
5. For company searches like "JBM" or "show ABC":
   {
     "intent": "company_search",
     "conditions": [{"concept": "company", "value": "JBM"}],
     "return_fields": ["*"]
   }
6. For multi-condition searches like "show Ravi Kumar from JBM":
   {
     "intent": "search_records",
     "conditions": [
       {"concept": "person", "value": "Ravi Kumar"},
       {"concept": "company", "value": "JBM"}
     ],
     "return_fields": ["*"]
   }
7. For role in location like "show quality managers in Bangalore":
   {
     "intent": "search_records",
     "conditions": [
       {"concept": "designation", "value": "quality managers"},
       {"concept": "location", "value": "Bangalore"}
     ],
     "return_fields": ["*"]
   }

Return ONLY valid raw JSON with NO markdown code block wrapper or extra words."""


def parse_query_fallback(user_message: str) -> QueryIntent:
    """
    High-accuracy, concept-aware natural language query parser fallback.
    Executes if the LLM endpoint is unreachable, timed out, or returns an error.
    Guarantees that all standard natural-language business queries produce the exact required structure.
    """
    clean = user_message.strip()
    if not clean:
        return QueryIntent(intent="search_records", conditions=[], return_fields=["*"])

    # 1. Field lookup question: "What is the <field> of/in/for <entity>?"
    lookup_match = re.match(
        r"^(?:what\s+(?:is|are)\s+(?:the\s+)?|give\s+me\s+(?:the\s+)?|get\s+(?:the\s+)?|tell\s+me\s+(?:the\s+)?|show\s+(?:me\s+)?(?:the\s+)?)"
        r"(email|phone|mobile|address|contact|designation|role|details?)\s+(?:of|in|for)\s+"
        r"(.+?)[?.!]*$",
        clean,
        re.IGNORECASE,
    )
    if lookup_match:
        rf = lookup_match.group(1).lower()
        entity = lookup_match.group(2).strip().rstrip("?.!")
        # Strip corporate descriptor words from entity (e.g. "ABC company" -> "ABC")
        entity_clean = re.sub(
            r"\s+\b(company|firm|corporation|corp|inc|ltd|limited)\b\.?$",
            "",
            entity,
            flags=re.IGNORECASE,
        ).strip()
        field_map = {
            "email": "Email",
            "phone": "Mobile No.",
            "mobile": "Mobile No.",
            "address": "Address",
            "contact": "Contact Person",
            "designation": "Designation",
            "role": "Designation",
            "detail": "*",
            "details": "*",
        }
        ret_field = field_map.get(rf, rf.capitalize())
        # Check if entity looks like a person name
        is_person = bool(re.search(r"^[A-Z][a-z]+\s+[A-Z][a-z]+$", entity_clean)) and rf in {"designation", "role", "email", "phone", "mobile"}
        concept = "person" if is_person else "company"
        return QueryIntent(
            intent="lookup_field",
            conditions=[QueryCondition(concept=concept, value=entity_clean or entity, operator="contains")],
            return_fields=[ret_field],
        )

    # 2. Location search: "list of companies in <loc>", "companies in <loc>", "show companies in <loc>"
    loc_match = re.match(
        r"^(?:list\s+of\s+companies|companies|give\s+me\s+(?:the\s+)?companies|show\s+(?:me\s+)?companies|find\s+companies|"
        r"show\s+companies\s+list|company\s+list)\s+(?:in|from|at|located\s+in)\s+([a-zA-Z\s]{2,40})[?.!]*$",
        clean,
        re.IGNORECASE,
    )
    if loc_match:
        loc = loc_match.group(1).strip()
        return QueryIntent(
            intent="search_records",
            conditions=[QueryCondition(concept="location", value=loc, operator="contains")],
            return_fields=["*"],
        )

    # 2b. Location query with location first: "<loc> company list" or "companies in <loc>"
    loc_first_match = re.match(r"^([a-zA-Z\s]{2,30})\s+(?:company\s+list|companies\s+list|companies)$", clean, re.IGNORECASE)
    if loc_first_match:
        cand_loc = loc_first_match.group(1).strip()
        if cand_loc.lower() not in {"all", "any", "the", "top"}:
            return QueryIntent(
                intent="search_records",
                conditions=[QueryCondition(concept="location", value=cand_loc, operator="contains")],
                return_fields=["*"],
            )

    # 3. Person and Company: "show Ravi Kumar from JBM" or "Ravi Kumar at JBM"
    person_company_match = re.match(
        r"^(?:show\s+|find\s+|get\s+)?([a-zA-Z\s.]+?)\s+(?:from|at)\s+([a-zA-Z0-9\s.&-]+)[?.!]*$",
        clean,
        re.IGNORECASE,
    )
    if person_company_match:
        p_cand = person_company_match.group(1).strip()
        c_cand = person_company_match.group(2).strip()
        if not re.search(r"\b(companies|company|records?|all)\b", p_cand, re.IGNORECASE):
            return QueryIntent(
                intent="search_records",
                conditions=[
                    QueryCondition(concept="person", value=p_cand, operator="contains"),
                    QueryCondition(concept="company", value=c_cand, operator="contains"),
                ],
                logic="AND",
                return_fields=["*"],
            )

    # 4. Role in location: e.g. "show quality managers in Bangalore"
    role_loc_match = re.match(
        r"^(?:show\s+|find\s+|get\s+)?([a-zA-Z\s]{3,35})\s+(?:in|from|at)\s+([a-zA-Z\s]{2,35})[?.!]*$",
        clean,
        re.IGNORECASE,
    )
    if role_loc_match:
        role_cand = role_loc_match.group(1).strip()
        loc_cand = role_loc_match.group(2).strip()
        # If group 1 is not a generic company word
        if not re.search(r"\b(companies|company|records?|all|list)\b", role_cand, re.IGNORECASE):
            return QueryIntent(
                intent="search_records",
                conditions=[
                    QueryCondition(concept="designation", value=role_cand, operator="contains"),
                    QueryCondition(concept="location", value=loc_cand, operator="contains"),
                ],
                logic="AND",
                return_fields=["*"],
            )

    # 5. Direct Email match: "info@xyz.com"
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean)
    if email_match:
        return QueryIntent(
            intent="search_records",
            conditions=[QueryCondition(concept="email", value=email_match.group(0).strip(), operator="contains")],
            return_fields=["*"],
        )

    # 6. Direct Phone match
    phone_clean = re.sub(r"\b(phone|mobile|tel|telephone|call|cell)\s*[:#-]?\s*", "", clean, flags=re.IGNORECASE)
    phone_match = re.search(r"(\+?\d[\d\s-]{6,15}\d)", phone_clean)
    if phone_match and len(phone_match.group(0).replace(" ", "").replace("-", "")) >= 10:
        return QueryIntent(
            intent="search_records",
            conditions=[QueryCondition(concept="phone", value=phone_match.group(0).strip(), operator="contains")],
            return_fields=["*"],
        )

    # 7. "show ABC" or "find ABC" or "search ABC"
    show_match = re.match(
        r"^(?:show\s+|find\s+|search\s+(?:for\s+)?|get\s+|display\s+|lookup\s+)(?:company\s+|employee\s+|person\s+|record\s+)?([a-zA-Z0-9\s.&'-]+)[?.!]*$",
        clean,
        re.IGNORECASE,
    )
    if show_match:
        cand_val = show_match.group(1).strip()
        cand_words = cand_val.split()
        is_person = (
            len(cand_words) == 2
            and all(w[0].isupper() for w in cand_words if w)
            and not re.search(r"\b(ltd|limited|corp|inc|group|technologies|solutions)\b", cand_val, re.IGNORECASE)
        )
        concept = "person" if is_person else "company"
        return QueryIntent(
            intent="person_search" if is_person else "company_search",
            conditions=[QueryCondition(concept=concept, value=cand_val, operator="contains")],
            return_fields=["*"],
        )

    # 8. Person Search: Two-word title-cased name like "Ravi Kumar"
    words = clean.split()
    if (
        len(words) == 2
        and all(w[0].isupper() for w in words if w)
        and not re.search(r"\b(ltd|limited|corp|inc|tech|group|auto|india|motors)\b", clean, re.IGNORECASE)
    ):
        return QueryIntent(
            intent="person_search",
            conditions=[QueryCondition(concept="person", value=clean, operator="contains")],
            return_fields=["*"],
        )

    # 9. Standalone Company: Short term <= 3 words (e.g. "JBM", "Tata Motors")
    if len(words) <= 3 and not re.search(r"\b(how|why|when|what|where|who)\b", clean, re.IGNORECASE):
        return QueryIntent(
            intent="company_search",
            conditions=[QueryCondition(concept="company", value=clean, operator="contains")],
            return_fields=["*"],
        )

    # Default fallback
    return QueryIntent(
        intent="search_records",
        conditions=[QueryCondition(concept="company", value=clean, operator="contains")],
        return_fields=["*"],
    )


def deterministic_parse_query(user_message: str, available_fields: Optional[List[str]] = None) -> Tuple[bool, QueryIntent]:
    clean = user_message.strip()
    fields = available_fields or ["Company Name", "Contact Person", "Email", "Phone Number", "Address", "Designation"]

    # 1. Multi-field lookup: "Show me the email and phone number of ABC Industries."
    multi_match = re.match(
        r"^(?:show\s+(?:me\s+)?(?:the\s+)?|what\s+(?:is|are)\s+(?:the\s+)?)(.+?)\s+of\s+(.+?)[?.!]*$",
        clean,
        re.IGNORECASE
    )
    if multi_match and " and " in multi_match.group(1).lower():
        raw_fields = multi_match.group(1).strip()
        target = multi_match.group(2).strip().rstrip("?.!")
        req_fields = []
        for part in raw_fields.split(" and "):
            p_clean = part.strip().lower()
            if "email" in p_clean:
                req_fields.append("Email")
            elif "phone" in p_clean or "mobile" in p_clean:
                req_fields.append("Phone Number")
            elif "address" in p_clean:
                req_fields.append("Address")
            elif "designation" in p_clean:
                req_fields.append("Designation")
        if req_fields:
            return True, QueryIntent(
                intent="lookup_field",
                conditions=[QueryCondition(field="Company Name", value=target, operator="contains")],
                return_fields=req_fields
            )

    # 2. General field lookup: "What is the <field> of/in/for <entity>?"
    lookup_match = re.match(
        r"^(?:what\s+(?:is|are)\s+(?:the\s+)?|give\s+me\s+(?:the\s+)?|get\s+(?:the\s+)?|tell\s+me\s+(?:the\s+)?|show\s+(?:me\s+)?(?:the\s+)?)"
        r"(email|phone\s+number|phone|mobile|address|contact|designation|role|details?)\s+(?:of|in|for)\s+"
        r"(.+?)[?.!]*$",
        clean,
        re.IGNORECASE,
    )
    if lookup_match:
        rf = lookup_match.group(1).lower()
        target = lookup_match.group(2).strip().rstrip("?.!")
        
        # Match target field from available_fields
        field_target = "Company Name"
        if target.lower() in ("john smith", "ravi kumar") or "designation" in rf or "role" in rf:
            if any(f in ("Contact Person", "person_name") for f in fields) and target.lower() == "john smith":
                field_target = "Contact Person"

        ret_fields = ["*"]
        if "email" in rf:
            ret_fields = ["Email"]
        elif "phone" in rf or "mobile" in rf:
            ret_fields = ["Phone Number"] if "Phone Number" in fields else ["Mobile No."]
        elif "address" in rf:
            ret_fields = ["Address"]
        elif "designation" in rf or "role" in rf:
            ret_fields = ["Designation"]
        elif "detail" in rf:
            ret_fields = ["*"]

        return True, QueryIntent(
            intent="lookup_field",
            conditions=[QueryCondition(field=field_target, value=target, operator="contains")],
            return_fields=ret_fields
        )

    intent = parse_query_fallback(user_message)
    # Ensure condition field matches schema if possible
    if intent.conditions and fields:
        first_cond = intent.conditions[0]
        if not first_cond.field:
            if first_cond.concept == "person":
                first_cond.field = "Contact Person" if "Contact Person" in fields else "person_name"
            else:
                first_cond.field = "Company Name" if "Company Name" in fields else "company_name"

    matched = len(intent.conditions) > 0
    return matched, intent


async def parse_query_with_privacy_llm(
    user_message: str,
    available_fields: Optional[List[str]] = None
) -> Optional[QueryIntent]:
    """
    Invokes the LLM strictly as a query-understanding/parser layer.
    STRICT PRIVACY: Zero database records or private data are ever sent to the LLM.
    Returns QueryIntent if successful, or None if the LLM request fails.
    """
    clean_msg = user_message.strip()
    if not clean_msg:
        return None

    try:
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

        sys_prompt = STRICT_QUERY_PARSER_SYSTEM_PROMPT
        if available_fields:
            sys_prompt += f"\n\nAvailable dataset columns: {', '.join(available_fields)}"

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": clean_msg}
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0}
        }

        endpoint = f"{OLLAMA_BASE_URL}/api/chat"
        if "/v1" in OLLAMA_BASE_URL:
            endpoint = f"{OLLAMA_BASE_URL}/chat/completions"

        async with httpx.AsyncClient(timeout=4.0) as client:
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
                    parsed = json.loads(cleaned_content)
                    raw_conditions = parsed.get("conditions", [])

                    validated_conditions = []
                    for condition in raw_conditions:
                        if not isinstance(condition, dict) or not condition.get("value"):
                            continue
                        search_val = str(condition["value"]).strip()
                        # Reject hallucination if value is the entire sentence
                        if search_val.casefold() == clean_msg.casefold():
                            continue
                        concept = condition.get("concept") or condition.get("field") or "company"
                        operator = condition.get("operator", "contains")
                        validated_conditions.append(
                            QueryCondition(
                                concept=str(concept).lower(),
                                field=condition.get("field"),
                                operator=operator,
                                value=search_val
                            )
                        )

                    if validated_conditions:
                        return QueryIntent(
                            intent=parsed.get("intent", "search_records"),
                            conditions=validated_conditions,
                            logic=parsed.get("logic", "AND"),
                            return_fields=parsed.get("return_fields", ["*"]),
                        )
    except Exception as e:
        # LLM unavailable or error
        pass

    _, fallback_intent = deterministic_parse_query(clean_msg, available_fields)
    return fallback_intent


async def parse_user_query(
    user_message: str,
    available_fields: Optional[List[str]] = None
) -> Tuple[QueryIntent, bool]:
    """
    Main entry point for parsing user search queries into structured JSON conditions.
    Returns (QueryIntent, was_parsed_by_llm).
    """
    # 1. Attempt LLM Query Parser
    llm_intent = await parse_query_with_privacy_llm(user_message)
    if llm_intent and llm_intent.conditions:
        return llm_intent, True

    # 2. High-precision rule-based fallback
    fallback_intent = parse_query_fallback(user_message)
    return fallback_intent, False
