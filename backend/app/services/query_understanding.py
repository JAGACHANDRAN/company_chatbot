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


class FollowupFilter(BaseModel):
    is_followup: bool = False
    is_reset: bool = False
    is_count_query: bool = False
    company_reference: Optional[str] = None
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    operator: str = "AND"
    location_filter: Optional[str] = None
    city_filter: Optional[str] = None
    state_filter: Optional[str] = None
    designation_filter: Optional[str] = None
    requested_fields: List[str] = Field(default_factory=list)
    raw_query: str = ""


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
    email_required: Optional[bool] = Field(None, description="True if query requires email to be available, False if requires no email, None if no constraint")
    phone_required: Optional[bool] = Field(None, description="True if query requires phone to be available, False if requires no phone, None if no constraint")
    linkedin_required: Optional[bool] = Field(None, description="True if query requires LinkedIn to be available, False if requires no LinkedIn, None if no constraint")
    requested_fields: List[str] = Field(default_factory=list, description="List of specific fields requested (e.g. ['email'], ['phone', 'city'])")
    is_only_fields: bool = Field(False, description="True if user specifically requested 'only', 'alone', or 'just' those fields")
    is_count_query: bool = Field(False, description="True if user asked for a count / how many")
    missing_filter: Optional[str] = Field(None, description="Field name if user specifically asked for records missing that field (e.g. 'email')")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional structured filter criteria")
    semantic_query: str = Field("", description="Natural language semantic search query for vector retrieval")
    original_query: str = Field("", description="The original user query text")


QUERY_UNDERSTANDING_SYSTEM_PROMPT = """You are a strict Query Understanding LLM for an enterprise company and contact directory RAG system.
Your ONLY task is to convert the user's natural language question into a clean, validated JSON object.

CRITICAL RULES:
1. Do NOT answer the user's question.
2. Return ONLY a single raw JSON object matching the schema below. No markdown backticks, no explanations.
3. EXACT/ENTITY QUERIES:
   If the user enters a company name directly (e.g. "2D INC", "TVS", "ABC Industries", "Find TVS", "Show 2D INC", "Show all TVS companies", "Do we have TVS companies?"):
   - "intent": "company_search"
   - "companies": ["2D INC"] (or ["TVS"], ["ABC Industries"])
   - NEVER populate "semantic_query" for explicit entity queries! Leave "semantic_query" as "".
4. AVAILABILITY FILTERS:
   - "with email", "email available", "having email", "which have email", "where email IDs are available" -> "email_required": true
   - "without email", "don't have email", "no email", "email not available" -> "email_required": false
   - "with phone", "with contact numbers", "phone available", "having phone" -> "phone_required": true
   - "without phone", "no phone" -> "phone_required": false
   - "with linkedin", "contacts with linkedin" -> "linkedin_required": true
   - "without linkedin" -> "linkedin_required": false
5. MULTIPLE COMPANIES:
   When user mentions multiple companies (e.g. "Find ABC, TVS and 2D INC", "ABC, TVS and XYZ"):
   - "companies": ["ABC", "TVS", "XYZ"]
   - NEVER collapse them into a single string.
6. PERSON NAME SEARCH:
   - "Find Ravi Kumar" or "Ravi Kumar" -> "intent": "person_search", "people": ["Ravi Kumar"], "companies": []
7. DYNAMIC LOCATION EXTRACTION:
   - "Companies in Andhra Pradesh" -> "state": "Andhra Pradesh", "intent": "location_search"
   - "Which companies are available in Chennai?" -> "city": "Chennai", "intent": "location_search"
8. DESIGNATION & HYBRID:
   - "quality managers in Chennai who have email" -> "designation": "Quality Manager", "city": "Chennai", "email_required": true, "intent": "mixed_search"
   - "Who is the Quality Manager at TVS in Chennai?" -> "companies": ["TVS"], "designation": "Quality Manager", "city": "Chennai", "intent": "mixed_search"

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
  "email_required": boolean | null,
  "phone_required": boolean | null,
  "linkedin_required": boolean | null,
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

TYPO_CORRECTIONS = {
    r"\balsone\b": "alone",
    r"\balon\b": "alone",
    r"\balonee\b": "alone",
    r"\bmeial\b": "email",
    r"\bmeials\b": "emails",
    r"\bemial\b": "email",
    r"\bemials\b": "emails",
    r"\bemal\b": "email",
    r"\bemals\b": "emails",
    r"\bemaill\b": "email",
    r"\bemaillist\b": "email list",
    r"\bavailble\b": "available",
    r"\bavailabe\b": "available",
    r"\bavialable\b": "available",
    r"\bavailabilty\b": "availability",
    r"\bcompanis\b": "companies",
    r"\bcompnies\b": "companies",
    r"\bcomapnies\b": "companies",
    r"\bcompnaies\b": "companies",
    r"\bcomapny\b": "company",
    r"\bcompnay\b": "company",
    r"\bmaneger\b": "manager",
    r"\bmanger\b": "manager",
    r"\bphne\b": "phone",
    r"\bphn\b": "phone",
    r"\bphno\b": "phone number",
    r"\bcontactno\b": "contact number",
    r"\bchenai\b": "chennai",
    r"\bbanglore\b": "bangalore",
    r"\bbengaluru\b": "bangalore",
    r"\btamilnadu\b": "tamil nadu",
    r"\blelyland\b": "leyland",
    r"\bleland\b": "leyland",
    r"\bashok\s+lelyland\b": "ashok leyland",
    r"\baanothe\b": "another",
    r"\banothe\b": "another",
    r"\baanother\b": "another",
    r"\banotherr\b": "another",
    r"\banothr\b": "another",
    r"\banthr\b": "another",
    r"\brcompany\b": "company",
    r"\brcomapny\b": "company",
    r"\brcompnay\b": "company",
    r"\brcompanies\b": "companies",
    r"\brcomapnies\b": "companies",
    r"\brcompnaies\b": "companies",
    r"\bdiffrent\b": "different",
    r"\bdiferent\b": "different",
    r"\bdiffrently\b": "differently",
    r"\bwhcih\b": "which",
    r"\bidf\b": "if",
    r"\bliek\b": "like",
    r"\bcrct\b": "correct",
    r"\bprblm\b": "problem",
}


def normalize_query_typos(text: str) -> str:
    """Applies high-confidence typo corrections for common keywords without altering entity names."""
    res = text
    for pat, rep in TYPO_CORRECTIONS.items():
        res = re.sub(pat, rep, res, flags=re.IGNORECASE)
    return res


FIELD_SYNONYMS: Dict[str, List[str]] = {
    "email": ["email", "emails", "e-mail", "mail", "mail id", "mail ids", "email id", "email ids", "email address", "email addresses"],
    "phone": ["phone", "phones", "phone number", "phone numbers", "contact number", "contact numbers", "mobile", "mobiles", "mobile number", "mobile numbers", "telephone"],
    "address": ["address", "addresses", "street", "street address", "location address", "postal address", "pincode", "pin code", "zip", "zipcode"],
    "city": ["city", "cities", "town"],
    "state": ["state", "states", "province"],
    "designation": ["designation", "designations", "job title", "role", "position", "title"],
    "person": ["person", "person name", "contact person", "contact name", "representative"],
    "linkedin": ["linkedin", "linkedin url", "linkedin profile", "profile url", "social"],
}


def detect_field_requests(q_lower: str) -> Tuple[List[str], bool, bool, Optional[str]]:
    """
    Deterministically detects:
    1. requested_fields: e.g. ['email'], ['phone', 'city']
    2. is_only_fields: True if 'only', 'alone', 'just' qualifier present
    3. is_count_query: True if 'how many', 'count of', 'number of' present
    4. missing_filter: Field name if asked for missing data (e.g. 'email' for 'companies with no email')
    """
    is_full = bool(re.search(r"\b(all\s+details|full\s+details|everything|all\s+columns|complete\s+details|all\s+info)\b", q_lower))
    if is_full:
        return [], False, False, None

    is_count = bool(re.search(r"\b(how\s+many|count\s+of|total\s+count|number\s+of)\b", q_lower))
    is_only = bool(re.search(r"\b(only|alone|just)\b", q_lower))

    missing_field = None
    if re.search(r"\b(without\s+(?:an?\s+)?(?:email|emails|mail)|no\s+(?:email|emails|mail)|missing\s+emails?|have\s+no\s+email|don'?t\s+have\s+(?:an?\s+)?email)\b", q_lower):
        missing_field = "email"
    elif re.search(r"\b(without\s+(?:a\s+)?(?:phone|mobile|contact)|no\s+(?:phone|mobile|contact\s*numbers?)|missing\s+phones?|have\s+no\s+phone|don'?t\s+have\s+(?:a\s+)?phone)\b", q_lower):
        missing_field = "phone"
    elif re.search(r"\b(without\s+(?:a\s+)?linkedin|no\s+linkedin|missing\s+linkedin|have\s+no\s+linkedin|don'?t\s+have\s+linkedin)\b", q_lower):
        missing_field = "linkedin"

    matched_fields: List[str] = []
    for standard_field, syns in FIELD_SYNONYMS.items():
        for syn in syns:
            pat = r"\b" + re.escape(syn) + r"\b"
            if re.search(pat, q_lower):
                if standard_field not in matched_fields:
                    matched_fields.append(standard_field)
                break

    return matched_fields, is_only, is_count, missing_field


def detect_followup_availability_filter(
    user_query: str,
    history: Optional[List[Dict[str, Any]]] = None
) -> Optional[FollowupFilter]:
    """
    Detects follow-up queries that reference and filter previous result sets (plain code, zero LLM).
    Only activates for genuine follow-ups (referring to 'those', 'them', 'previous', reset, or short modifiers).
    NEVER hijacks new standalone company/entity searches (e.g. 'ashok leyland companies list where emails available?').
    """
    raw_clean = user_query.strip()
    clean = normalize_query_typos(raw_clean)
    q_lower = clean.lower()

    # Never treat queries asking for another/different/other company as a follow-up filter on previous records
    if re.search(r"\b(another|other|others|different|next|new|aanothe|anothe|aanother|anothr|anthr|diffrent|diferent)\b", q_lower):
        return None

    # 1. Reset command
    if re.search(r"^(?:reset|show\s+all\s+again|show\s+all|restore\s+all|restore\s+original|clear\s+filters?|unfilter|remove\s+filters?)[.?!]*$", q_lower) or q_lower == "reset":
        return FollowupFilter(
            is_followup=True,
            is_reset=True,
            raw_query=user_query
        )

    # 2. Check for explicit follow-up / anaphoric markers
    has_ref_word = bool(re.search(
        r"\b(those|them|they|these|same\s+companies|from\s+these|from\s+those|of\s+those|from\s+them|of\s+them|previous|earlier|above|from\s+the\s+above|the\s+ones|give\s+the\s+ones|only\s+the\s+ones|only\s+those|from\s+the\s+results?)\b",
        q_lower
    ))
    
    # Check for company reference with reference qualifier like "those tvs ones", "from those tvs companies", "the tvs ones"
    comp_ref_match = re.search(r"\b(?:those|from\s+those|from\s+the|of\s+those|the)\s+([a-zA-Z0-9&.-]+)\s+(?:ones|companies|results|records)\b", q_lower)
    company_ref = None
    if comp_ref_match:
        c_cand = comp_ref_match.group(1).strip()
        if c_cand.lower() not in ("those", "them", "these", "same", "all", "previous", "earlier", "the", "with", "without", "having"):
            company_ref = c_cand.upper() if len(c_cand) <= 4 else c_cand.title()
            has_ref_word = True

    is_count_on_previous = bool(
        re.search(r"\b(how\s+many\s+of\s+them|how\s+many\s+of\s+those|how\s+many\s+have|count\s+of\s+them|availability\s+of\s+them|email\s+and\s+phone\s+availability)\b", q_lower)
    )

    # Check if query is a pure short follow-up filter WITHOUT a company entity
    # (e.g. "with email and phone", "having email", "without email", "now only Chennai", "only Chennai", "now only those in Chennai")
    is_pure_modifier = bool(
        re.search(r"^(?:now\s+)?(?:only\s+)?(?:those\s+in\s+|with\s+|having\s+|without\s+|in\s+|from\s+|located\s+in\s+|who\s+has\s+|that\s+have\s+|whose\s+|give\s+the\s+ones\s+|show\s+only\s+)[a-zA-Z0-9\s,.-]*$", clean, re.IGNORECASE)
        and not re.search(r"\b(?:companies|company|firms|businesses|customers|find|search|list|records)\b", clean, re.IGNORECASE)
        and (
            any(w in q_lower for w in ["email", "mail", "phone", "contact", "mobile", "linkedin", "address", "city", "state", "chennai", "bangalore", "mumbai", "delhi", "pune", "hyderabad", "coimbatore", "tamil nadu", "with", "without", "having", "only", "now"])
        )
    )

    is_followup = has_ref_word or is_count_on_previous or is_pure_modifier

    if not is_followup:
        return None

    is_count = bool(is_count_on_previous or re.search(r"\b(how\s+many|count\s+of|total\s+count|number\s+of)\b", q_lower))

    # Determine logical operator (AND vs OR)
    operator = "AND"
    if re.search(r"\b\s+or\s+\b", q_lower) and not re.search(r"\b\s+and\s+\b", q_lower):
        operator = "OR"

    conditions: List[Dict[str, Any]] = []
    requested_fields: List[str] = []

    # Check Email
    if re.search(r"\b(without\s+(?:an?\s+)?(?:email|emails|e-mail|mail\s*ids?|mail)|no\s+(?:email|emails|mail)|missing\s+emails?|have\s+no\s+email|don'?t\s+have\s+(?:an?\s+)?(?:email|mail)|email\s+(?:is\s+)?(?:not\s+available|unavailable|missing))\b", q_lower):
        conditions.append({"field": "email", "required": False})
        requested_fields.append("email")
    elif re.search(r"\b(with\s+(?:an?\s+)?(?:email|emails|e-mail|mail\s*ids?|mail)|having\s+(?:an?\s+)?(?:email|e-mail|mail\s*ids?|mail\s*id|mail)|that\s+have\s+(?:an?\s+)?(?:email|mail\s*id|mail)|who\s+has\s+(?:an?\s+)?(?:email|mail)|email\s+available|email\s+is\s+available|has\s+(?:an?\s+)?(?:email|mail)|have\s+mail\s*id|having\s+mail\s*id|email\s+ids?|emails?)\b", q_lower):
        conditions.append({"field": "email", "required": True})
        requested_fields.append("email")

    # Check Phone
    if re.search(r"\b(without\s+(?:a\s+)?(?:phone|phones|mobile|contact\s*numbers?|telephone)|no\s+(?:phone|phones|mobile|contact\s*numbers?)|missing\s+phones?|have\s+no\s+phone|don'?t\s+have\s+(?:a\s+)?phone|phone\s+(?:is\s+)?(?:not\s+available|unavailable|missing))\b", q_lower):
        conditions.append({"field": "phone", "required": False})
        requested_fields.append("phone")
    elif re.search(r"\b(with\s+(?:a\s+)?(?:phone|phones|mobile|contact\s*numbers?|telephone)|having\s+(?:a\s+)?(?:phone|mobile|contact\s*numbers?)|that\s+have\s+(?:phone|mobile)|who\s+has\s+(?:phone|mobile)|phone\s+available|has\s+(?:a\s+)?phone|phones?|contact\s*numbers?|mobiles?)\b", q_lower):
        conditions.append({"field": "phone", "required": True})
        requested_fields.append("phone")

    # Check LinkedIn
    if re.search(r"\b(without\s+(?:a\s+)?linkedin|no\s+linkedin|missing\s+linkedin|have\s+no\s+linkedin|linkedin\s+(?:is\s+)?(?:not\s+available|unavailable|missing))\b", q_lower):
        conditions.append({"field": "linkedin", "required": False})
        requested_fields.append("linkedin")
    elif re.search(r"\b(with\s+(?:a\s+)?linkedin|having\s+(?:a\s+)?linkedin|that\s+have\s+linkedin|who\s+has\s+linkedin|linkedin\s+available|has\s+linkedin|linkedin)\b", q_lower):
        conditions.append({"field": "linkedin", "required": True})
        requested_fields.append("linkedin")

    # Check Address / Location
    if re.search(r"\b(without\s+(?:an?\s+)?(?:address|location)|no\s+(?:address|location)|missing\s+address|address\s+not\s+available)\b", q_lower):
        conditions.append({"field": "address", "required": False})
        requested_fields.append("address")
    elif re.search(r"\b(with\s+(?:an?\s+)?(?:address|location)|having\s+(?:an?\s+)?(?:address|location)|address\s+available|with\s+location)\b", q_lower):
        conditions.append({"field": "address", "required": True})
        requested_fields.append("address")

    # Check Person / Designation
    if re.search(r"\b(with\s+(?:a\s+)?(?:contact\s+person|person\s+name|representative)|having\s+(?:a\s+)?(?:contact\s+person|person))\b", q_lower):
        conditions.append({"field": "person", "required": True})
        requested_fields.append("person")
    if re.search(r"\b(with\s+(?:a\s+)?designation|having\s+(?:a\s+)?designation)\b", q_lower):
        conditions.append({"field": "designation", "required": True})
        requested_fields.append("designation")

    # Check Location / City / State narrowing
    city_filter = None
    state_filter = None
    location_filter = None

    loc_narrow_match = re.search(
        r"\b(?:now\s+only\s+those\s+in|now\s+only\s+in|only\s+those\s+in|only\s+in|located\s+in|now\s+only|only|in|from)\s+([A-Za-z\s]+?)(?:\s+(?:having|with|without|and|\?|\.|$)|$)",
        clean,
        re.IGNORECASE
    )
    if loc_narrow_match:
        cand_loc = loc_narrow_match.group(1).strip()
        cand_lower = cand_loc.lower()
        if cand_lower not in ("the database", "all files", "this description", "quality", "those", "them", "these", "ones", "companies", "tvs", "abc"):
            if cand_lower in ("chennai", "mumbai", "bangalore", "bengaluru", "coimbatore", "hyderabad", "pune", "delhi", "kolkata", "hosur"):
                city_filter = cand_loc.title()
                location_filter = city_filter
            elif cand_lower in ("tamil nadu", "andhra pradesh", "karnataka", "maharashtra", "kerala", "gujarat"):
                state_filter = cand_loc.title()
                location_filter = state_filter
            else:
                location_filter = cand_loc.title()

    # If no conditions or location or count or ref word found, it's not a follow-up filter
    if not conditions and not location_filter and not is_count and not has_ref_word:
        return None

    return FollowupFilter(
        is_followup=True,
        is_reset=False,
        is_count_query=is_count,
        company_reference=company_ref,
        conditions=conditions,
        operator=operator,
        location_filter=location_filter,
        city_filter=city_filter,
        state_filter=state_filter,
        requested_fields=requested_fields,
        raw_query=user_query
    )


def fallback_query_understanding(user_query: str) -> StructuredQuery:
    """
    High-precision, fully dynamic NLP fallback query parser and classifier.
    Understands natural language variations, entity lookup, role/location constraints,
    field projections (email alone, phone, etc.), typo tolerance, and availability filters.
    """
    raw_clean = user_query.strip()
    clean = normalize_query_typos(raw_clean)
    q_lower = clean.lower()

    companies: List[str] = []
    people: List[str] = []
    designation: Optional[str] = None
    department: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    email_required: Optional[bool] = None
    phone_required: Optional[bool] = None
    linkedin_required: Optional[bool] = None
    semantic_query = ""
    intent = "general_search"

    requested_fields, is_only_fields, is_count_query, missing_filter = detect_field_requests(q_lower)

    # 1. Availability Filters Detection
    # Email required / missing
    if missing_filter == "email" or re.search(r"\b(without\s+(?:an?\s+)?(?:email|emails|e-mail|mail\s*ids?|mail)|no\s+(?:email|emails|mail)|email\s+(?:is\s+)?(?:not\s+available|unavailable|missing)|don'?t\s+have\s+(?:an?\s+)?(?:email|mail)|does\s+not\s+have\s+(?:an?\s+)?(?:email|mail))\b", q_lower):
        email_required = False
    elif re.search(r"\b(?:whose\s+email\s+is\s+available|where\s+(?:an?\s+)?(?:emails?|email\s*ids?|mail\s*ids?|mail)\s+(?:are\s+|is\s+)?available|with\s+(?:an?\s+)?(?:email|emails|e-mail|mail\s*ids?|mail)|having\s+(?:an?\s+)?(?:email|e-mail|mail\s*ids?|mail\s*id|mail)|email\s+available|emails?\s+available|emails?\s+are\s+available|email\s+is\s+available|has\s+(?:an?\s+)?(?:email|email\s*address)|have\s+(?:an?\s+)?(?:email|email\s*addresses|email\s*ids?|emails)|only\s+show\s+(?:the\s+ones\s+that\s+)?have\s+email|email\s+exists|which\s+have\s+email|having\s+mail\s*id|which\s+are\s+having\s+mail\s*id)\b", q_lower):
        email_required = True

    # Phone required / missing
    if missing_filter == "phone" or re.search(r"\b(without\s+(?:a\s+)?(?:phone|mobile|contact\s*numbers?|telephone)|no\s+(?:phone|mobile|contact\s*numbers?)|phone\s+(?:is\s+)?(?:not\s+available|unavailable)|don'?t\s+have\s+(?:a\s+)?(?:phone|contact\s*number))\b", q_lower):
        phone_required = False
    elif re.search(r"\b(with\s+(?:a\s+)?(?:phone|phones|mobile|contact\s*numbers?|telephone)|having\s+(?:a\s+)?(?:phone|mobile|contact\s*numbers?)|phone\s+available|phone\s+numbers?\s+available|have\s+(?:phone\s+numbers?|contact\s*numbers?)|has\s+(?:a\s+)?phone)\b", q_lower):
        phone_required = True

    # LinkedIn required / missing
    if missing_filter == "linkedin" or re.search(r"\b(without\s+(?:a\s+)?linkedin|no\s+linkedin|linkedin\s+(?:is\s+)?(?:not\s+available|unavailable))\b", q_lower):
        linkedin_required = False
    elif re.search(r"\b(with\s+(?:a\s+)?linkedin|contacts\s+with\s+linkedin|having\s+(?:a\s+)?linkedin|linkedin\s+available|has\s+linkedin)\b", q_lower):
        linkedin_required = True

    # 2. Pure conceptual/semantic query detection
    is_semantic_intent = bool(re.search(
        r"\b(who\s+is\s+responsible\s+for|responsible\s+for|who\s+handles|how\s+to|what\s+is\s+the\s+procedure|describe|matching\s+this\s+description|explain|overview\s+of)\b",
        q_lower
    ))

    # 3. Department Detection
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

    # 4. Designation Detection (e.g. Quality Manager, Quality Head, Director, Engineer)
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

    # 5. Dynamic Location Extraction
    loc_match = re.search(
        r"\b(?:available\s+in|located\s+in|based\s+in|in)\s+([A-Za-z][A-Za-z\s,.-]+?)(?:\s+(?:having|with|without|for|where|across|and\s+has|who\s+is|whose|which|who|companies|company|that)|\?|\.|$)",
        clean,
        re.IGNORECASE
    )
    if loc_match and not is_semantic_intent:
        extracted_loc = loc_match.group(1).strip()
        extracted_loc = re.sub(r"^(?:the\s+)", "", extracted_loc, flags=re.IGNORECASE)
        extracted_loc = re.sub(r"\s+(?:state|city|region|district|country|territory)$", "", extracted_loc, flags=re.IGNORECASE).strip()
        loc_words = extracted_loc.lower().split()

        if (
            extracted_loc.lower() not in ("quality", "quality manager", "sales", "all files", "every file", "uploaded files", "this description", "the database", "database")
            and not any(w in COMPANY_SUFFIX_TOKENS for w in loc_words)
            and not any(w in extracted_loc.lower() for w in ["industries", "motors", "technologies", "automations", "systems", "solutions", "enterprise", "tvs", "abc"])
        ):
            location = extracted_loc.title()
            if "city" in q_lower or location.lower() in ("chennai", "mumbai", "bangalore", "bengaluru", "coimbatore", "hyderabad", "pune", "delhi", "kolkata", "hosur"):
                city = location
            elif "state" in q_lower or location.lower() in ("tamil nadu", "andhra pradesh", "karnataka", "maharashtra", "kerala", "gujarat"):
                state = location
            elif "country" in q_lower or location.lower() in ("india", "usa"):
                country = location
            else:
                location = extracted_loc.title()
                state = location
            intent = "location_search"

    # 6. Person Name Extraction
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
            if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}", clean):
                words = clean.lower().split()
                if not any(w in COMPANY_SUFFIX_TOKENS for w in words):
                    people.append(clean)
                    intent = "person_search"

    # 7. Entity & Company Extraction
    is_general_location_query = bool(location and re.search(r"\b(?:companies|firms|businesses|customers)\b", clean, re.IGNORECASE) and not re.search(r"\b(tvs|abc|2d\s*inc|jbm|tata)\b", q_lower))
    is_role_loc = bool(designation and location and not re.search(r"\b(?:at|of|from)\s+[A-Za-z0-9&.-]+", clean, re.IGNORECASE))
    # Check if query is a direct phone or email search
    is_phone_query = bool(re.search(r"(\+?\d[\d\s-]{6,15}\d)", clean) and not any(c.isalpha() for c in clean if c not in ("+", "-", " ", ":", ".")))
    is_email_query = bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean))

    is_role_only = bool(designation and not re.search(r"\b(?:of|from|at)\s+[A-Za-z0-9&.-]+", clean, re.IGNORECASE))

    if not is_phone_query and not is_email_query and not people and not is_semantic_intent and not is_general_location_query and not is_role_loc and not is_role_only:
        # Check "Who is the Quality Manager at TVS in Chennai?" or "Quality Manager of ABC"
        comp_in_role_match = re.search(r"\b(?:of|from|at)\s+([A-Za-z0-9&.-]+(?:\s+[A-Za-z0-9&.-]+)?)(?:\s+in\s+([A-Za-z\s]+))?[?.!]*$", clean, re.IGNORECASE)
        if comp_in_role_match and designation:
            c_val = comp_in_role_match.group(1).strip()
            loc_val = comp_in_role_match.group(2)
            if c_val.lower() not in ("quality", "all files", "chennai", "tamil nadu", "bangalore", "mumbai"):
                c_norm = c_val.upper() if len(c_val) <= 4 else c_val.title()
                companies.append(c_norm)
                intent = "company_search"
            if loc_val:
                loc_clean = loc_val.strip().title()
                if loc_clean.lower() in ("chennai", "mumbai", "bangalore", "bengaluru", "coimbatore", "hyderabad", "pune", "delhi", "kolkata", "hosur"):
                    city = loc_clean
                else:
                    state = loc_clean
        else:
            # Strip conversational and command prefixes/suffixes
            comp_filter_clean = clean

            # Strip availability clauses and field specifiers first
            avail_pattern = (
                r"\b(?:where\s+(?:an?\s+)?(?:emails?|email\s*ids?|mail\s*ids?|phones?|contact\s*numbers?|linkedin)\s*(?:are\s+|is\s+)?available\??|"
                r"where\s+(?:an?\s+)?(?:emails?|email\s*ids?|mail\s*ids?|phones?|contact\s*numbers?|linkedin)\s*available\??|"
                r"whose\s+email\s+is\s+available|where\s+email\s+ids?\s+are\s+available|"
                r"with\s+(?:an?\s+)?(?:email|emails|e-mail|mail\s*ids?|mail|phone|mobile|contact\s*numbers?|telephone|linkedin)|"
                r"having\s+(?:an?\s+)?(?:email|e-mail|mail\s*ids?|mail\s*id|mail|phone|mobile|contact\s*numbers?|linkedin)|"
                r"without\s+(?:an?\s+)?(?:email|e-mail|mail\s*ids?|mail|phone|mobile|contact\s*numbers?|linkedin)|"
                r"emails?\s+(?:are\s+|is\s+)?available\??|phones?\s+(?:are\s+|is\s+)?available\??|linkedin\s+(?:is\s+)?available\??|"
                r"no\s+email|no\s+phone|no\s+linkedin|"
                r"and\s+only\s+show\s+(?:the\s+ones\s+that\s+)?have\s+email|which\s+have\s+(?:email|email\s*ids?|emails)|which\s+are\s+having\s+mail\s*id|"
                r"having\s+mail\s*id|don'?t\s+have\s+email|have\s+(?:email\s*ids?|email\s*addresses|email|emails|phone\s*numbers?|contact\s*numbers?)|"
                r"has\s+(?:an?\s+)?(?:email\s*ids?|email\s*address|email|phone)|"
                r"emails?\s+alone|phones?\s+alone|contacts?\s+alone|numbers?\s+alone|details\s+alone|"
                r"only\s+emails?|only\s+phones?|only\s+contact\s+numbers?|only\s+numbers?|only\s+city|only\s+state|"
                r"emails?|phones?|contact\s+numbers?|numbers?|mobiles?|linkedin)\b[?.]*"
            )
            comp_filter_clean = re.sub(avail_pattern, "", comp_filter_clean, flags=re.IGNORECASE).strip()

            # Handle natural language company search patterns
            comp_of_match = (
                re.search(r"\b(?:that\s+have|having|with|related\s+to|of|named)\s+([A-Za-z0-9&.-]+(?:\s+[A-Za-z0-9&.-]+)?)\s+(?:name|company|companies)", comp_filter_clean, re.IGNORECASE)
                or re.search(r"\b(?:companies\s+(?:of|related\s+to|that\s+have|having|with|named|called)|company\s+(?:of|related\s+to|that\s+have|having|with|named|called)|related\s+to)\s+([A-Za-z0-9&.-]+(?:\s+[A-Za-z0-9&.-]+)?)", comp_filter_clean, re.IGNORECASE)
            )
            NON_COMPANY_WORDS = {
                "all", "the", "every", "any", "each", "this", "that", "email", "emails", "mail",
                "phone", "contact", "mobile", "linkedin", "how", "many", "what", "which", "are",
                "where", "available", "another", "other", "others", "different", "next", "new",
                "same", "previous", "one"
            }
            if comp_of_match and comp_of_match.group(1).lower() not in NON_COMPANY_WORDS:
                extracted_c = comp_of_match.group(1).strip()
                c_norm = extracted_c.upper() if len(extracted_c) <= 4 else extracted_c.title()
                companies.append(c_norm)
                intent = "company_search"
            else:
                prefix_pattern = (
                    r"^(?:show\s+me|give\s+me\s+all|give\s+me|find|show|search\s+for|look\s+for|get|do\s+we\s+have|which|are\s+there\s+any|details\s+of|list\s+of\s+companies\s+in|companies\s+in|list\s+of|companies\s*:?|company\s*:?)\s+"
                    r"|(?:give\s+me\s+)?(?:quality\s+)?contacts?\s+(?:of|from|at|in|for)\s+"
                    r"|^(?:find\s+)?companies\s+related\s+to\s+"
                    r"|^(?:who\s+are\s+the|what\s+are\s+the|list\s+all\s+companies\s+that\s+have|list\s+companies\s+that\s+have|companies\s+that\s+have|companies\s+having|companies\s+with)\s+"
                    r"|^(?:how\s+many\s+companies\s+(?:of|related\s+to|in|named)?|how\s+many\s+)\s*"
                )
                cmd_stripped = re.sub(prefix_pattern, "", comp_filter_clean, flags=re.IGNORECASE).strip().rstrip("?.!")

                # Strip trailing fillers like "companies list", "companies in the database", "company", "companies", "group", "name", "where", "available"
                cmd_stripped = re.sub(r"\s+\b(?:companies\s+list|company\s+list|companies\s+are\s+in\s+the\s+database|are\s+in\s+the\s+database|in\s+the\s+database|companies\s+related\s+to|companies|company|firm|firms|where|available|is\s+available|are\s+available|list)\b[?.!]*$", "", cmd_stripped, flags=re.IGNORECASE).strip()

                standardized = re.sub(r"\s+(?:and|&)\s+", ", ", cmd_stripped, flags=re.IGNORECASE)
                parts = [p.strip().rstrip("?.!") for p in standardized.split(",") if p.strip()]

                cleaned_parts = []
                for p in parts:
                    p_clean = re.sub(
                        r"\b(?:companies|company|firm|firms|list|details|records|info|data|all|contacts?|have|has|having|with|without|which|who|where|how\s+many|show|give|now|their|them|they|add|also|alone|only|just|emails?|phones?|numbers?|mobiles?|linkedin|address|city|state|another|other|others|different|next|new|same|previous|one)\b",
                        "",
                        p,
                        flags=re.IGNORECASE
                    ).strip()
                    p_clean = re.sub(r"\s+", " ", p_clean).strip()
                    p_lower = p_clean.lower()
                    if not p_clean:
                        continue
                    if designation and (p_lower == designation.lower() or designation.lower() in p_lower or p_lower in designation.lower()):
                        continue
                    if p_clean and p_lower not in ("quality", "contacts", "all", "uploaded", "this description", "the", "related to", "all companies of", "list", "records", "how many", "which", "another", "other", "others", "different", "next", "new", "same", "previous", "one"):
                        if p_clean.isupper():
                            p_norm = p_clean
                        elif len(p_clean) <= 4 or p_lower in ("tvs", "abc", "jbm", "tata", "bhel", "mrf", "l&t", "2d inc"):
                            p_norm = p_clean.upper()
                        else:
                            p_norm = p_clean.title()
                        cleaned_parts.append(p_norm)

                if len(cleaned_parts) > 1:
                    companies.extend(cleaned_parts)
                    intent = "company_search"
                elif len(cleaned_parts) == 1:
                    single_c = cleaned_parts[0]
                    if single_c.lower() not in ("quality", "sales", "all files", "this description", "the", "how many", "another", "other", "others", "different", "next", "new", "same", "previous", "one"):
                        companies.append(single_c)
                        intent = "company_search"

    # Check if query is a direct phone or email search
    is_phone_query = bool(re.search(r"(\+?\d[\d\s-]{6,15}\d)", clean) and not any(c.isalpha() for c in clean if c not in ("+", "-", " ")))
    is_email_query = bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean))

    # 8. Semantic Query Assignment & Fallback
    if is_phone_query:
        intent = "contact_search"
        phone_required = True
    elif is_email_query:
        intent = "contact_search"
        email_required = True
    elif is_semantic_intent or ("responsible for" in q_lower or "matching this description" in q_lower):
        semantic_query = clean
        intent = "general_search"
    elif not (companies or people or location or state or city or designation or department):
        clean_words = set(q_lower.split())
        is_all_noise = clean_words.issubset({
            "now", "their", "them", "they", "the", "add", "show", "give", "me", "what", "is", "are",
            "phone", "phones", "number", "numbers", "email", "emails", "address", "city", "state",
            "details", "alone", "only", "just", "how", "many", "have", "has", "who", "which",
            "another", "other", "others", "different", "next", "new", "same", "previous", "one"
        })
        if len(clean.split()) <= 4 and not (email_required is not None or phone_required is not None or requested_fields or is_count_query or missing_filter or is_all_noise):
            if clean.isupper():
                c_norm = clean
            elif len(clean) <= 4 or clean.lower() in ("tvs", "abc", "jbm", "tata", "bhel", "mrf", "l&t", "2d inc"):
                c_norm = clean.upper()
            else:
                c_norm = clean.title()
            companies.append(c_norm)
            intent = "company_search"
        else:
            semantic_query = clean
            intent = "general_search"

    # Multi-intent classification
    if (companies and people) or (companies and location) or (designation and location) or (department and location) or (companies and designation) or (companies and email_required is not None) or (location and phone_required is not None):
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
        email_required=email_required,
        phone_required=phone_required,
        linkedin_required=linkedin_required,
        requested_fields=requested_fields,
        is_only_fields=is_only_fields,
        is_count_query=is_count_query,
        missing_filter=missing_filter,
        filters={},
        semantic_query=semantic_query,
        original_query=raw_clean
    )


def resolve_followup_context(
    current_sq: StructuredQuery,
    history: Optional[List[Dict[str, str]]] = None
) -> StructuredQuery:
    """
    Carries over entities (companies, people, location, designation) and adapts requested fields
    from the last 3 turns if the current query is anaphoric / follow-up (e.g. 'now their phone numbers', 'add address').
    Zero LLM calls required.
    """
    if not history:
        return current_sq

    q_lower = current_sq.original_query.lower()
    is_add_column = bool(re.search(r"\b(add|include|also\s+show|and\s+also)\b", q_lower))
    is_followup = is_add_column or bool(re.search(
        r"\b(their|them|they|his|her|this\s+company|that\s+company|give\s+(?:me\s+)?(?:their|the)\s+(?:phone|number|email|contact|details|address)|where\s+(?:are\s+they|is\s+it)|what\s+is\s+(?:their|the)\s+(?:phone|email|address)|now\s+(?:their|the|show))\b",
        q_lower
    ))

    if not is_followup and current_sq.companies:
        return current_sq

    # If the user asks for another/different/other company, NEVER carry over previous companies
    if re.search(r"\b(another|other|others|different|next|new|aanothe|anothe|aanother|anothr|anthr|diffrent|diferent)\b", q_lower):
        return current_sq

    # Inspect last 3 turns (from newest to oldest)
    recent_turns = history[-3:] if len(history) > 3 else history
    for turn in reversed(recent_turns):
        prev_user_text = turn.get("user") or turn.get("message") or turn.get("content") or ""
        if prev_user_text:
            prev_sq = fallback_query_understanding(prev_user_text)
            # Carry over companies if missing
            if not current_sq.companies and prev_sq.companies:
                current_sq.companies = prev_sq.companies
            # Carry over people if missing
            if not current_sq.people and prev_sq.people:
                current_sq.people = prev_sq.people
            # Carry over location if missing
            if not current_sq.city and prev_sq.city:
                current_sq.city = prev_sq.city
            if not current_sq.state and prev_sq.state:
                current_sq.state = prev_sq.state
            # Carry over designation if missing
            if not current_sq.designation and prev_sq.designation:
                current_sq.designation = prev_sq.designation

            # If user said 'add <field>', combine with previous requested fields
            if is_add_column and prev_sq.requested_fields:
                merged = list(dict.fromkeys(prev_sq.requested_fields + current_sq.requested_fields))
                current_sq.requested_fields = merged

            if current_sq.companies or current_sq.people:
                break

    return current_sq


async def parse_query_understanding(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Tuple[StructuredQuery, bool]:
    """
    Main Query Understanding entry point.
    Uses high-precision local deterministic heuristic extraction and synonym mapping.
    Resolves follow-ups across the last 3 chat turns.
    SECURITY: NEVER makes external LLM calls for query rewriting.
    Returns (StructuredQuery, was_llm_generated=False).
    """
    clean_query = user_query.strip() if user_query else ""
    if not clean_query:
        return StructuredQuery(original_query=""), False

    structured = fallback_query_understanding(clean_query)
    if history:
        structured = resolve_followup_context(structured, history)

    return structured, False

