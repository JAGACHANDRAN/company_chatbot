import re
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field, ValidationError
import httpx

from ..config import (
    OLLAMA_CLOUD_URL,
    OLLAMA_API_KEY,
    LLM_MODEL,
    LLM_REASONING,
    PRIVACY_MODE
)
from .query_understanding import (
    normalize_query_typos,
    fallback_query_understanding,
    detect_followup_availability_filter
)
from ..utils.normalization import normalize_company

logger = logging.getLogger("calispec.query_planner")

ALLOWED_FIELDS = [
    "company", "contact_person", "designation", "email", "phone",
    "linkedin", "address", "city", "state", "location", "source"
]

DESIGNATION_SYNONYMS = {
    "quality": ["quality", "qa", "qc", "quality assurance", "quality control", "quality manager", "quality head", "quality engineer", "quality dept"],
    "qa": ["qa", "qc", "quality", "quality assurance", "quality control"],
    "qc": ["qc", "qa", "quality", "quality control"],
    "purchase": ["purchase", "procurement", "buyer", "purchase manager", "purchase head", "sourcing"],
    "procurement": ["procurement", "purchase", "sourcing", "buyer", "procurement manager"],
    "director": ["director", "managing director", "md", "board member", "executive director"],
    "maintenance": ["maintenance", "plant maintenance", "service engineer", "maintenance head"],
    "sales": ["sales", "business development", "marketing", "sales manager", "sales head"],
    "marketing": ["marketing", "sales", "business development", "marketing manager"],
    "hr": ["hr", "human resources", "hr manager", "talent acquisition"],
    "ceo": ["ceo", "chief executive officer", "president", "proprietor", "owner"],
    "manager": ["manager", "head", "lead", "general manager", "gm", "assistant manager"]
}


class SearchTask(BaseModel):
    intent: Literal["lookup", "filter_previous", "count", "open_question"] = "lookup"
    companies: List[str] = Field(default_factory=list)
    must_have: List[str] = Field(default_factory=list)
    must_not_have: List[str] = Field(default_factory=list)
    fields: List[str] = Field(default_factory=list)
    only_requested_fields: bool = False
    designation_keywords: List[str] = Field(default_factory=list)
    city: Optional[str] = None
    state: Optional[str] = None
    use_previous_results: bool = False


class QueryPlan(BaseModel):
    tasks: List[SearchTask] = Field(default_factory=list)
    used_fallback: bool = False
    filters_removed_by_guard: bool = False

    @property
    def intent(self) -> str:
        return self.tasks[0].intent if self.tasks else "lookup"

    @property
    def companies(self) -> List[str]:
        all_comps = []
        for t in self.tasks:
            all_comps.extend(t.companies)
        return list(dict.fromkeys(all_comps))

    @property
    def must_have(self) -> List[str]:
        return self.tasks[0].must_have if self.tasks else []

    @property
    def must_not_have(self) -> List[str]:
        return self.tasks[0].must_not_have if self.tasks else []

    @property
    def fields(self) -> List[str]:
        return self.tasks[0].fields if self.tasks else []

    @property
    def only_requested_fields(self) -> bool:
        return self.tasks[0].only_requested_fields if self.tasks else False

    @property
    def designation_keywords(self) -> List[str]:
        return self.tasks[0].designation_keywords if self.tasks else []

    @property
    def city(self) -> Optional[str]:
        return self.tasks[0].city if self.tasks else None

    @property
    def state(self) -> Optional[str]:
        return self.tasks[0].state if self.tasks else None

    @property
    def person_name(self) -> Optional[str]:
        return None

    @property
    def use_previous_results(self) -> bool:
        return any(t.use_previous_results for t in self.tasks)


PLANNER_SYSTEM_PROMPT = """You are a Strict Query Planning Engine for a B2B Database Search System.
Analyze the user's search request and generate a structured JSON query plan.

CRITICAL RULES:
1. Output ONLY valid JSON matching the schema: {"tasks": [SearchTask, ...]}.
2. If the user message contains multiple independent sub-requests (e.g. "tvs companies with emails, ashok leyland in chennai, and titan quality persons"), return a separate SearchTask for each sub-request in the "tasks" array.
3. If a pasted list of multiple company names is provided with one set of filters, put all company names in "companies" of a single SearchTask.
4. "must_have" can contain: "contact", "email", "phone", "linkedin", "address", "designation", "contact_person".
   - "contact available", "contacts available", "have contact details", "with contact" -> must_have ["contact"]
   - "email available", "with email" -> must_have ["email"]
   - "phone available", "with number" -> must_have ["phone"]
   - "linkedin available" -> must_have ["linkedin"]
   - The word "list" or "contact" alone, without available/with/have, is NOT a filter.
   - "fields" is the set of columns to show; it must not be used instead of must_have.
5. "must_not_have" can contain: "email", "phone", "linkedin".
6. If the user refers to previous results ("from those", "from them", "out of these", "only with phone"), set intent="filter_previous" and use_previous_results=true.
7. If the user asks a count question ("how many have email"), set intent="count".
8. If the user asks a semantic/descriptive question (e.g. "labs that calibrate pressure gauges"), set intent="open_question".
9. If the user asks for "another company", "other companies", or "a different company" (e.g. "give me another company list which having email alone"), this is EXPLICITLY NOT previous results. Set intent="lookup", use_previous_results=false, and never set "another" or "other" as a company name.
10. A company name can contain several words (e.g. "delphi tvs", "tvs motor company", "3d solution"). Return ONE entry per company in "companies". NEVER break a single company name into individual words.

FEW-SHOT EXAMPLES:
User: "delphi tvs"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["delphi tvs"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs motor company"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs motor company"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "3d solution"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["3d solution"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "delphi tvs, titan"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["delphi tvs", "titan"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs and titan"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs", "titan"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "give tvs company list which have emails"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": ["email"],
      "must_not_have": [],
      "fields": ["email"],
      "only_requested_fields": true,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "chennai tvs companies"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": "chennai",
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs contact available list"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": ["contact"],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs contact list"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs emails available"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": ["email"],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs phone and email available"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": ["phone", "email"],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}
"""


def split_pasted_companies(raw_text: str) -> List[str]:
    """
    Splits pasted lists of company names ONLY on newlines, semicolons, bullets, tabs, and commas.
    NEVER splits on plain spaces.
    """
    if not raw_text:
        return []

    # Check if text contains explicit sentence filter instructions: 'with email', 'in chennai', etc.
    has_filter_clause = bool(re.search(
        r"\b(with\s+(?:emails?|phones?|linkedin)|without\s+(?:emails?|phones?)|in\s+[a-z]+|dept|department|quality\s+(?:persons?|dept)|alone|only)\b",
        raw_text,
        re.IGNORECASE
    ))

    lines = [line.strip() for line in re.split(r"[\r\n;\t]+", raw_text) if line.strip()]
    companies = []

    for l in lines:
        cleaned = re.sub(r"^(?:\d+[\.\)]|\*|\-|\•)\s*", "", l).strip()
        if not has_filter_clause:
            # If line has commas, split on commas
            sub_items = [s.strip() for s in cleaned.split(",") if len(s.strip()) > 1]
            if len(sub_items) > 1:
                for s in sub_items:
                    s_clean = re.sub(r"^(?:\d+[\.\)]|\*|\-|\•)\s*", "", s).strip()
                    if len(s_clean) >= 2:
                        companies.append(s_clean)
            else:
                if len(cleaned) >= 2:
                    companies.append(cleaned)
        else:
            if len(cleaned) >= 2:
                companies.append(cleaned)

    # Deduplicate while preserving order
    return list(dict.fromkeys(companies))


KNOWN_CITIES = [
    "chennai", "mumbai", "bangalore", "bengaluru", "coimbatore",
    "hyderabad", "pune", "delhi", "kolkata", "hosur", "gurgaon",
    "noida", "faridabad", "ahmedabad", "madurai", "salem", "trichy"
]
KNOWN_STATES = [
    "tamil nadu", "andhra pradesh", "karnataka", "maharashtra",
    "kerala", "gujarat", "haryana", "uttar pradesh", "telangana"
]


def find_another_company_from_db(
    exclude_companies: List[str],
    must_have: Optional[List[str]] = None,
    city: Optional[str] = None
) -> Optional[str]:
    """
    Finds a prominent company from the database different from exclude_companies,
    optionally satisfying must_have criteria (e.g. having email).
    """
    from ..database import get_database
    db = get_database()
    col = db["dataset_records"]

    candidate_names = [
        "Brakes India", "Tata Motors", "Hyundai", "Premier CNC",
        "Ashok Leyland", "Bosch", "Titan", "Mahindra",
        "Kone Elevators", "Deekashith Technologies", "SAAB Engineering"
    ]

    exclude_clean = [c.lower().strip() for c in exclude_companies if c]
    for c_name in candidate_names:
        if any(ex in c_name.lower() or c_name.lower() in ex for ex in exclude_clean):
            continue
        q: Dict[str, Any] = {"norm_company": {"$regex": rf"\b{re.escape(c_name.lower())}\b"}}
        if city:
            q["$or"] = [
                {"city": {"$regex": rf"\b{re.escape(city.lower())}\b", "$options": "i"}},
                {"location": {"$regex": rf"\b{re.escape(city.lower())}\b", "$options": "i"}}
            ]
        if must_have and "email" in must_have:
            email_q = [
                {"email": {"$regex": "@"}},
                {"data.Email": {"$regex": "@"}},
                {"data.Email 2": {"$regex": "@"}}
            ]
            if "$or" in q:
                q["$and"] = [{"$or": q.pop("$or")}, {"$or": email_q}]
            else:
                q["$or"] = email_q
        if col.find_one(q):
            return c_name

    try:
        sample_q: Dict[str, Any] = {}
        if must_have and "email" in must_have:
            sample_q["$or"] = [
                {"email": {"$regex": "@"}},
                {"data.Email": {"$regex": "@"}}
            ]
        cursor = col.find(sample_q, {"company": 1, "norm_company": 1}).limit(100)
        for doc in cursor:
            c = doc.get("company")
            nc = doc.get("norm_company", "").lower()
            if c and not any(ex in nc for ex in exclude_clean) and len(c) > 2:
                return c
    except Exception:
        pass

    for fallback_cand in ["Brakes India", "Tata Motors", "Hyundai", "Premier CNC", "Ashok Leyland", "Bosch", "Titan", "Mahindra"]:
        if not any(ex in fallback_cand.lower() for ex in exclude_clean):
            return fallback_cand

    return "Brakes India"


def _parse_single_clause(clause: str, history: Optional[List[Dict[str, Any]]] = None, has_previous_results: bool = False) -> SearchTask:
    """Parses a single independent search clause into a SearchTask."""
    clause_clean = normalize_query_typos(clause)
    sq = fallback_query_understanding(clause_clean)
    followup = detect_followup_availability_filter(clause_clean, history=history)

    intent = "lookup"
    use_prev = False
    must_have = []
    must_not_have = []

    if followup and followup.is_followup:
        use_prev = True
        intent = "count" if followup.is_count_query else "filter_previous"
        for c in followup.conditions:
            f = c.get("field")
            if f:
                if c.get("required") is True:
                    must_have.append(f)
                else:
                    must_not_have.append(f)
    else:
        q_low_c = clause_clean.lower()
        has_avail_words = bool(re.search(r"\b(available|availability|having|which\s+have|who\s+have|with|only\s+those\s+with|exists|present|listed)\b", q_low_c))
        has_contact_phrase = bool(re.search(r"\b(contact\s+available|contacts\s+available|contact\s+details\s+available|have\s+contact\s+details|with\s+contact)\b", q_low_c))
        has_contact_kw = bool(re.search(r"\b(contacts?|contact\s+details)\b", q_low_c))
        has_avail_contact = has_contact_phrase or (has_avail_words and has_contact_kw and not re.search(r"\b(emails?|phones?|numbers?)\b", q_low_c))
        if has_avail_contact:
            must_have.append("contact")

        if sq.email_required is True or (has_avail_words and re.search(r"\b(emails?|e-mail|mail)\b", q_low_c)) or "with email" in q_low_c or "email available" in q_low_c:
            if "email" not in must_have:
                must_have.append("email")
        if sq.email_required is False or "without email" in q_low_c or "no email" in q_low_c:
            must_not_have.append("email")

        if sq.phone_required is True or (has_avail_words and re.search(r"\b(phones?|numbers?|contact\s+numbers?|mobiles?)\b", q_low_c)) or "with number" in q_low_c or "phone available" in q_low_c:
            if "phone" not in must_have:
                must_have.append("phone")
        if sq.phone_required is False or "without phone" in q_low_c or "no phone" in q_low_c:
            must_not_have.append("phone")

        if sq.linkedin_required is True or (has_avail_words and "linkedin" in q_low_c) or "linkedin available" in q_low_c or "with linkedin" in q_low_c:
            if "linkedin" not in must_have:
                must_have.append("linkedin")

    clause_low = clause.lower()
    city_val = sq.city
    state_val = sq.state

    for c_name in KNOWN_CITIES:
        if re.search(rf"\b{re.escape(c_name)}\b", clause_low):
            city_val = c_name
            break

    for s_name in KNOWN_STATES:
        if re.search(rf"\b{re.escape(s_name)}\b", clause_low):
            state_val = s_name
            break

    raw_companies = sq.companies or []
    companies = []
    for c in raw_companies:
        c_clean = c
        if city_val:
            c_clean = re.sub(rf"\b{re.escape(city_val)}\b", "", c_clean, flags=re.IGNORECASE)
        if state_val:
            c_clean = re.sub(rf"\b{re.escape(state_val)}\b", "", c_clean, flags=re.IGNORECASE)
        c_clean = re.sub(
            r"\b(?:quality\s+(?:dept|department)?\s*(?:persons?|contacts?|heads?|managers?)?|quality|dept|department|persons?|contacts?|available|availability|having|exists|present|listed|list|alone|only|emails?|phones?|numbers?|details|companies|company|in|at|from|with|without|another|other|others|different|next|new|same|previous|one)\b",
            "",
            c_clean,
            flags=re.IGNORECASE
        ).strip()
        c_clean = re.sub(r"^(?:and|&)\s+|\s+(?:and|&)$", "", c_clean, flags=re.IGNORECASE).strip()
        c_clean = re.sub(r"\s+", " ", c_clean).strip()
        if c_clean and len(c_clean) >= 2 and c_clean.lower() not in ("another", "other", "others", "different", "next", "new", "same", "previous", "one"):
            companies.append(c_clean.lower())
        elif c and len(c.strip()) >= 2 and c.strip().lower() not in ("another", "other", "others", "different", "next", "new", "same", "previous", "one"):
            companies.append(c.strip().lower())

    is_another = bool(re.search(r"\b(another|other|others|different|next|new|aanothe|anothe|aanother|anothr|anthr|diffrent|diferent)\b", clause_clean.lower()))
    if is_another:
        use_prev = False
        intent = "lookup"
        companies = [c for c in companies if c.lower() not in ("another", "other", "others", "different", "next", "new", "same", "previous", "one", "aanothe", "anothe", "anthr")]
        if not companies:
            prev_comps = []
            if history:
                for turn in reversed(history[-6:]):
                    p_text = str(turn.get("content") or turn.get("message") or "")
                    p_sq = fallback_query_understanding(p_text)
                    if p_sq.companies:
                        prev_comps.extend(p_sq.companies)
                        break
            chosen = find_another_company_from_db(exclude_companies=prev_comps, must_have=must_have, city=city_val)
            if chosen:
                companies = [chosen]

    fields = []
    if sq.requested_fields:
        fields = sq.requested_fields
    elif sq.email_required:
        fields.append("email")
    elif sq.phone_required:
        fields.append("phone")
    elif sq.linkedin_required:
        fields.append("linkedin")

    desig_kws = []
    if sq.designation:
        raw_dk = sq.designation.lower().strip()
        desig_kws.append(raw_dk)
        if raw_dk in DESIGNATION_SYNONYMS:
            desig_kws.extend(DESIGNATION_SYNONYMS[raw_dk])
    elif "quality" in clause_low or (sq.department and sq.department.lower() == "quality"):
        desig_kws.extend(DESIGNATION_SYNONYMS["quality"])
        if "designation" not in must_have and "contact_person" not in must_have:
            must_have.append("designation")
        if "contact_person" not in fields:
            fields.append("contact_person")
    desig_kws = list(dict.fromkeys(desig_kws))

    if sq.intent == "general_search" and not companies and not followup:
        intent = "open_question"

    return SearchTask(
        intent=intent,
        companies=companies,
        must_have=must_have,
        must_not_have=must_not_have,
        fields=fields,
        only_requested_fields=sq.is_only_fields,
        designation_keywords=desig_kws,
        city=city_val,
        state=state_val,
        use_previous_results=use_prev
    )


def validate_companies(plan: QueryPlan, raw_query: str) -> QueryPlan:
    """
    Bug C Code Guard:
    For any plan with 2+ companies that were separated only by spaces or 'and'/'&',
    first test the WHOLE phrase with keyword rules (normalize_company, whole-word, all-tokens).
    If the whole phrase matches >= 1 records in DB, replace the pieces with the one whole name.
    Prefer the longest phrase that matches the database.
    Logs: '[Planner] merged split company name -> <name>'.
    """
    from ..database import get_database, get_configured_collection_names
    from .multi_stage_search import execute_keyword_company_search
    try:
        db = get_database()
        cols = list(dict.fromkeys(get_configured_collection_names() + ["dataset_records"]))
    except Exception as e:
        logger.warning(f"[validate_companies] DB access skipped: {e}")
        return plan

    for task in plan.tasks:
        if len(task.companies) >= 2:
            # Test whole combined phrase
            joined_phrase = " ".join(task.companies)
            recs, _ = execute_keyword_company_search(db, cols, joined_phrase)
            if recs:
                logger.info(f"[Planner] merged split company name -> {joined_phrase}")
                task.companies = [joined_phrase]
                continue

            # Test whole query normalized after stripping noise
            clean_q = re.sub(
                r"\b(?:give|show|find|list|me|companies|company|with|having|emails?|phones?|details|in|at|from)\b",
                "",
                raw_query,
                flags=re.IGNORECASE
            ).strip()
            clean_q = re.sub(r"\s+(?:and|&)\s+", " ", clean_q, flags=re.IGNORECASE).strip()
            norm_q = normalize_company(clean_q)
            if norm_q and norm_q != joined_phrase:
                recs_q, _ = execute_keyword_company_search(db, cols, norm_q)
                if recs_q:
                    logger.info(f"[Planner] merged split company name -> {norm_q}")
                    task.companies = [norm_q]
                    continue

            # Pairwise merging for adjacent split names
            new_comps = []
            idx = 0
            while idx < len(task.companies):
                if idx + 1 < len(task.companies):
                    pair_name = f"{task.companies[idx]} {task.companies[idx+1]}"
                    recs_pair, _ = execute_keyword_company_search(db, cols, pair_name)
                    if recs_pair:
                        logger.info(f"[Planner] merged split company name -> {pair_name}")
                        new_comps.append(pair_name)
                        idx += 2
                        continue
                new_comps.append(task.companies[idx])
                idx += 1
            task.companies = new_comps

    return plan


AVAILABILITY_WORDS = [
    "available", "availability", "having", "which have", "who have", "with",
    "only those with", "exists", "present", "listed",
    "contact available", "contact details available", "contacts available",
    "have contact details", "with contact"
]


def validate_filters(plan: QueryPlan, raw_query: str) -> QueryPlan:
    """
    Planner Guard for Filters:
    Verifies that any must_have filter generated by the planner is explicitly grounded
    in the raw query. If words like 'contact' or 'list' appear alone without availability
    words, removes the filter and sets plan.filters_removed_by_guard = True.
    If availability words are present, retains the filter.
    Also ensures 'fields' is not used instead of 'must_have'.
    """
    q_low = raw_query.lower()
    has_avail = any(re.search(rf"\b{re.escape(w)}\b", q_low) for w in AVAILABILITY_WORDS)

    for t in plan.tasks:
        if "contact" in t.fields:
            t.fields = [f for f in t.fields if f != "contact"]
            if has_avail and "contact" not in t.must_have:
                t.must_have.append("contact")

        kept_must_have = []
        for f in t.must_have:
            if f == "contact":
                has_contact_avail = has_avail or bool(re.search(
                    r"\b(contact\s+available|contacts\s+available|contact\s+details\s+available|have\s+contact\s+details|with\s+contact)\b",
                    q_low
                ))
                has_avail_trigger = bool(re.search(
                    r"\b(available|availability|having|which\s+have|who\s+have|with|only\s+those\s+with|exists|present|listed|have)\b",
                    q_low
                ))
                if has_contact_avail and has_avail_trigger:
                    kept_must_have.append(f)
                else:
                    plan.filters_removed_by_guard = True
                    logger.info(f"[Planner Guard] Removed filter '{f}' (contact/list alone without availability words)")
            elif f == "email":
                has_email_kw = bool(re.search(r"\b(emails?|e-mail|mail)\b", q_low))
                if has_email_kw and (has_avail or "without" not in q_low):
                    kept_must_have.append(f)
                elif has_avail:
                    kept_must_have.append(f)
                else:
                    plan.filters_removed_by_guard = True
                    logger.info(f"[Planner Guard] Removed filter '{f}' (no explicit query match)")
            elif f == "phone":
                has_phone_kw = bool(re.search(r"\b(phones?|numbers?|contact\s+numbers?|mobiles?)\b", q_low))
                if has_phone_kw and (has_avail or "without" not in q_low):
                    kept_must_have.append(f)
                elif has_avail:
                    kept_must_have.append(f)
                else:
                    plan.filters_removed_by_guard = True
                    logger.info(f"[Planner Guard] Removed filter '{f}' (no explicit query match)")
            elif f == "linkedin":
                if "linkedin" in q_low:
                    kept_must_have.append(f)
                else:
                    plan.filters_removed_by_guard = True
                    logger.info(f"[Planner Guard] Removed filter '{f}' (no explicit query match)")
            elif f in ("address", "contact_person", "designation"):
                has_kw = bool(re.search(rf"\b{f}\b", q_low)) or (f == "designation" and any(k in q_low for k in ["quality", "qa", "qc", "manager", "head", "director", "role", "title"])) or (f == "contact_person" and any(k in q_low for k in ["person", "persons", "people", "name"]))
                if has_kw or has_avail:
                    kept_must_have.append(f)
                else:
                    plan.filters_removed_by_guard = True
                    logger.info(f"[Planner Guard] Removed filter '{f}' (no explicit query match)")
            else:
                kept_must_have.append(f)
        t.must_have = kept_must_have

    return plan


def rule_based_plan(
    raw_query: str,
    history: Optional[List[Dict[str, Any]]] = None,
    has_previous_results: bool = False
) -> QueryPlan:
    """
    Fallback deterministic rule-based query planner (Zero LLM, 100% offline).
    """
    clean = raw_query.strip()
    if not clean:
        return QueryPlan(tasks=[SearchTask()], used_fallback=True)

    # Check for pasted list
    pasted = split_pasted_companies(clean)
    if len(pasted) > 1:
        single_task = _parse_single_clause(clean, history=history, has_previous_results=has_previous_results)
        single_task.companies = pasted
        plan = QueryPlan(tasks=[single_task], used_fallback=True)
        plan = validate_companies(plan, clean)
        return validate_filters(plan, clean)
    # Follow-up query check: genuine follow-up queries referring to previous results are single-task
    followup = detect_followup_availability_filter(clean, history=history)
    if followup and followup.is_followup:
        single_task = _parse_single_clause(clean, history=history, has_previous_results=has_previous_results)
        plan = QueryPlan(tasks=[single_task], used_fallback=True)
        plan = validate_companies(plan, clean)
        return validate_filters(plan, clean)

    # Multi-clause sentence check
    if any(re.search(rf"\b{k}\b", clean, re.IGNORECASE) for k in ["with", "without", "in", "dept", "department", "quality", "persons?", "alone", "only"]):
        raw_clauses = re.split(r",\s*and\s+|\band\b|,\s*", clean, flags=re.IGNORECASE)
        candidate_clauses = [c.strip() for c in raw_clauses if c.strip() and len(c.strip()) >= 2]
        if len(candidate_clauses) > 1:
            tasks = []
            for cl in candidate_clauses:
                t = _parse_single_clause(cl, history=history, has_previous_results=has_previous_results)
                if t.companies or t.intent == "open_question" or t.use_previous_results:
                    tasks.append(t)
            if len(tasks) > 1:
                plan = QueryPlan(tasks=tasks, used_fallback=True)
                plan = validate_companies(plan, clean)
                return validate_filters(plan, clean)

    task = _parse_single_clause(clean, history=history, has_previous_results=has_previous_results)
    plan = QueryPlan(tasks=[task], used_fallback=True)
    plan = validate_companies(plan, clean)
    return validate_filters(plan, clean)


async def plan_query_execution(
    raw_query: str,
    history: Optional[List[Dict[str, Any]]] = None,
    has_previous_results: bool = False
) -> QueryPlan:
    """
    Step 2: Calls gpt-oss:120b / LLM with temperature 0, JSON output, timeout 20s.
    Falls back to rule_based_plan on any error or timeout.
    Applies validate_companies code guard.
    """
    clean_query = normalize_query_typos(raw_query.strip())
    if not clean_query:
        return QueryPlan(tasks=[SearchTask()])

    pasted = split_pasted_companies(clean_query)
    if len(pasted) > 1:
        return rule_based_plan(clean_query, history=history, has_previous_results=has_previous_results)

    if PRIVACY_MODE or not OLLAMA_API_KEY:
        logger.info("[Planner] fallback to rules (privacy mode / no key)")
        return rule_based_plan(clean_query, history=history, has_previous_results=has_previous_results)

    recent_user_turns = []
    if history:
        for turn in history[-6:]:
            if turn.get("role") == "user":
                recent_user_turns.append(str(turn.get("content", ""))[:200])
    recent_user_turns = recent_user_turns[-3:]

    prompt_payload = {
        "user_query": clean_query,
        "recent_user_messages": recent_user_turns,
        "allowed_fields": ALLOWED_FIELDS,
        "has_previous_results": has_previous_results
    }

    try:
        url = f"{OLLAMA_CLOUD_URL}/api/chat"
        headers = {
            "Authorization": f"Bearer {OLLAMA_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_payload)}
            ],
            "options": {
                "temperature": 0.0,
                "reasoning": LLM_REASONING
            },
            "format": "json",
            "stream": False
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            raw_content = data.get("message", {}).get("content", "")

            parsed_json = json.loads(raw_content)
            if "tasks" in parsed_json:
                plan = QueryPlan(**parsed_json)
            else:
                task = SearchTask(**parsed_json)
                plan = QueryPlan(tasks=[task])

            for t in plan.tasks:
                if t.designation_keywords:
                    expanded = set(t.designation_keywords)
                    for kw in list(t.designation_keywords):
                        kw_low = kw.lower().strip()
                        if kw_low in DESIGNATION_SYNONYMS:
                            expanded.update(DESIGNATION_SYNONYMS[kw_low])
                    t.designation_keywords = list(expanded)

            is_another = bool(re.search(
                r"\b(another|other|others|different|next|new|aanothe|anothe|aanother|anothr|anthr|diffrent|diferent)\b",
                clean_query.lower()
            ))
            if is_another:
                prev_comps = []
                if history:
                    for turn in reversed(history[-6:]):
                        p_text = str(turn.get("content") or turn.get("message") or "")
                        p_sq = fallback_query_understanding(normalize_query_typos(p_text))
                        if p_sq.companies:
                            prev_comps.extend(p_sq.companies)
                            break
                for t in plan.tasks:
                    t.intent = "lookup"
                    t.use_previous_results = False
                    clean_comps = [
                        c for c in t.companies
                        if c.lower().strip() not in ("another", "other", "others", "different", "next", "new", "same", "previous", "one", "aanothe", "anothe", "anthr")
                        and not any(pc.lower().strip() in c.lower() or c.lower() in pc.lower().strip() for pc in prev_comps)
                    ]
                    t.companies = clean_comps
                    if not t.companies:
                        chosen = find_another_company_from_db(exclude_companies=prev_comps, must_have=t.must_have, city=t.city)
                        if chosen:
                            t.companies = [chosen]

            plan = validate_companies(plan, clean_query)
            plan = validate_filters(plan, clean_query)
            logger.info(f"[Planner] Generated Plan -> {len(plan.tasks)} tasks, companies={plan.companies}")
            return plan

    except Exception as e:
        logger.warning(f"[Planner] fallback to rules due to exception: {e}")
        return rule_based_plan(clean_query, history=history, has_previous_results=has_previous_results)


async def execute_planned_task(
    task: SearchTask,
    target_dataset: str = "all",
    limit: int = 1000,
    raw_query: str = ""
) -> Dict[str, Any]:
    """
    Executes a single SearchTask independently.
    Deduplicates by str(_id) immediately upon combining.
    """
    from .multi_stage_search import execute_multi_stage_retrieval
    from .response_generator import (
        extract_company_name,
        extract_person_info,
        extract_emails,
        extract_contact_numbers,
        extract_location,
        extract_linkedin,
        get_contact_fields
    )

    companies_to_query = list(dict.fromkeys(task.companies)) if task.companies else []
    found_by_company: Dict[str, List[Dict[str, Any]]] = {}
    unfound_list: List[Tuple[str, List[str]]] = []
    all_matched_records: List[Dict[str, Any]] = []
    all_vector_only_records: List[Dict[str, Any]] = []
    seen_ids = set()

    stage_metrics = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "vector": 0}
    total_keyword_hits = 0
    total_vector_hits = 0
    total_vector_hits_raw = 0
    top_vector_scores: List[float] = []
    all_raw_vector_records: List[Dict[str, Any]] = []
    total_candidates_before = 0
    all_filter_events: List[Dict[str, Any]] = []

    if not companies_to_query:
        return {
            "task": task.model_dump(),
            "found_by_company": {},
            "unfound_list": [],
            "records": [],
            "vector_only_records": [],
            "raw_vector_records": [],
            "top_vector_scores": [],
            "total": 0,
            "stages": stage_metrics,
            "keyword_hits": 0,
            "vector_hits": 0,
            "vector_hits_raw": 0,
            "summary_header": "",
            "candidates_before_filter": 0,
            "filter_events": []
        }

    retrieval_tasks = [
        execute_multi_stage_retrieval(
            raw_query=c_name,
            target_dataset=target_dataset,
            city_filter=task.city
        )
        for c_name in companies_to_query
    ]
    results = await asyncio.gather(*retrieval_tasks)

    for c_name, multi_res in zip(companies_to_query, results):
        for k_st in stage_metrics:
            stage_metrics[k_st] += multi_res.get("stages", {}).get(k_st, 0)
        total_keyword_hits += multi_res.get("keyword_hits", 0)
        total_vector_hits += multi_res.get("vector_hits", 0)
        total_vector_hits_raw += multi_res.get("vector_hits_raw", 0)
        top_vector_scores.extend(multi_res.get("top_vector_scores", []))
        all_raw_vector_records.extend(multi_res.get("raw_vector_records", []))
        all_vector_only_records.extend(multi_res.get("vector_only_records", []))

        if not multi_res.get("keyword_records"):
            sugg = multi_res.get("suggestions", [])
            unfound_list.append((c_name, sugg))
            continue

        raw_candidates = multi_res.get("records", [])
        total_candidates_before += len(raw_candidates)
        filtered_for_company: List[Dict[str, Any]] = []

        for r in raw_candidates:
            if task.city:
                loc = extract_location(r)
                c_city = (loc.get("city") or "").lower()
                c_addr = (loc.get("address") or "").lower()
                c_state = (loc.get("state") or "").lower()
                if task.city.lower() not in c_city and task.city.lower() not in c_addr and task.city.lower() not in c_state:
                    continue
            if task.state:
                loc = extract_location(r)
                c_state = (loc.get("state") or "").lower()
                if task.state.lower() not in c_state:
                    continue

            cf = get_contact_fields(r)

            if "contact" in task.must_have:
                has_email = bool(cf.get("emails"))
                has_phone = bool(cf.get("phones"))
                if not (has_email or has_phone):
                    continue

            if "email" in task.must_have and not cf.get("emails"):
                continue
            if "phone" in task.must_have and not cf.get("phones"):
                continue
            if "linkedin" in task.must_have and not cf.get("linkedin"):
                continue
            if "address" in task.must_have:
                addr = cf.get("address")
                if not addr or addr == "No data available":
                    continue
            if "designation" in task.must_have and not cf.get("designations"):
                continue
            if "contact_person" in task.must_have and not cf.get("contact_persons"):
                continue

            if "email" in task.must_not_have and cf.get("emails"):
                continue
            if "phone" in task.must_not_have and cf.get("phones"):
                continue
            if "linkedin" in task.must_not_have and cf.get("linkedin"):
                continue

            if task.designation_keywords:
                p_desig = (extract_person_info(r).get("designation") or "").lower()
                matched_desig = any(
                    re.search(rf"\b{re.escape(dk.lower())}\b", p_desig)
                    for dk in task.designation_keywords
                )
                if not matched_desig:
                    continue

            rec_id = str(r.get("_id") or f"{extract_company_name(r)}_{id(r)}")
            if rec_id not in seen_ids:
                seen_ids.add(rec_id)
                filtered_for_company.append(r)

        if not filtered_for_company and task.designation_keywords and raw_candidates:
            first_raw = dict(raw_candidates[0])
            first_raw["person"] = "No data available"
            first_raw["designation"] = "No data available"
            first_raw["data"] = {**first_raw.get("data", {}), "Person Name": "No data available", "Designation": "No data available"}
            filtered_for_company.append(first_raw)

        if filtered_for_company:
            found_by_company[c_name] = filtered_for_company
            all_matched_records.extend(filtered_for_company)
        else:
            sugg = multi_res.get("suggestions", [])
            unfound_list.append((c_name, sugg))

        if task.must_have:
            q_low = raw_query.lower() if raw_query else ""
            for f in task.must_have:
                matched_phrase = "available"
                for w in AVAILABILITY_WORDS:
                    if w in q_low:
                        matched_phrase = w
                        break
                all_filter_events.append({
                    "filter": f,
                    "count_before": len(raw_candidates),
                    "count_after": len(filtered_for_company),
                    "matched_phrase": matched_phrase
                })

    total_req = len(companies_to_query)
    total_found = len(found_by_company)
    total_records = len(all_matched_records)

    if total_req > 1:
        company_names_str = ", ".join(found_by_company.keys())
        hdr = f"Found {total_found} {'company' if total_found == 1 else 'companies'} ({company_names_str}), {total_records} records."
        if unfound_list:
            unf_parts = []
            for name, sugg in unfound_list:
                if sugg:
                    unf_parts.append(f"{name} (did you mean {', '.join(sugg)}?)")
                else:
                    unf_parts.append(name)
            hdr += f" Not found: {', '.join(unf_parts)}."
    else:
        single_name = companies_to_query[0] if companies_to_query else "query"
        disp_name = single_name.upper() if len(single_name) <= 4 else single_name.title()
        if total_records > 0:
            if "contact" in task.must_have:
                cnt_before = total_candidates_before
                cnt_after = total_records
                cnt_without = cnt_before - cnt_after
                hdr = f"Found {cnt_before} {disp_name} records. {cnt_after} have contact details (email or phone), {cnt_without} do not. Showing the {cnt_after}."
            elif "email" in task.must_have and "phone" in task.must_have:
                cnt_before = total_candidates_before
                cnt_after = total_records
                cnt_without = cnt_before - cnt_after
                hdr = f"Found {cnt_before} {disp_name} records. {cnt_after} have both phone and email, {cnt_without} do not. Showing the {cnt_after}."
            elif "email" in task.must_have:
                cnt_before = total_candidates_before
                cnt_after = total_records
                cnt_without = cnt_before - cnt_after
                hdr = f"Found {cnt_before} {disp_name} records. {cnt_after} have an email, {cnt_without} do not. Showing the {cnt_after}."
            elif "phone" in task.must_have:
                cnt_before = total_candidates_before
                cnt_after = total_records
                cnt_without = cnt_before - cnt_after
                hdr = f"Found {cnt_before} {disp_name} records. {cnt_after} have a phone, {cnt_without} do not. Showing the {cnt_after}."
            else:
                filter_desc = []
                if task.city:
                    filter_desc.append(f"in {task.city.title()}")
                if "email" in task.must_not_have:
                    filter_desc.append("without email")
                if task.designation_keywords:
                    filter_desc.append("with matching designation")

                f_str = (" " + " ".join(filter_desc)) if filter_desc else ""
                emails_count = sum(1 for r in all_matched_records if get_contact_fields(r).get("emails"))
                hdr = f"Found {total_records} records matching '{single_name}'{f_str}. {emails_count} contacts have an email."
        else:
            sugg = unfound_list[0][1] if unfound_list else []
            if sugg:
                hdr = f"No matching records found for '{single_name}'. Did you mean: {', '.join(sugg)}?"
            else:
                hdr = f"No matching records found for '{single_name}'."

    cap_hit = total_records >= 1000
    if cap_hit:
        hdr += " Maximum lookup limit of 1,000 records reached."

    return {
        "task": task.model_dump(),
        "summary_header": hdr,
        "found_by_company": found_by_company,
        "unfound_list": unfound_list,
        "records": all_matched_records[:limit],
        "vector_only_records": all_vector_only_records,
        "raw_vector_records": all_raw_vector_records,
        "top_vector_scores": top_vector_scores,
        "total": len(all_matched_records[:limit]),
        "cap_hit": cap_hit,
        "stages": stage_metrics,
        "keyword_hits": total_keyword_hits,
        "vector_hits": total_vector_hits,
        "vector_hits_raw": total_vector_hits_raw,
        "candidates_before_filter": total_candidates_before,
        "filter_events": all_filter_events
    }


async def execute_planned_retrieval(
    plan: QueryPlan,
    raw_query: str,
    target_dataset: str = "all",
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Executes all tasks in the QueryPlan sequentially/concurrently.
    Preserves task sections, headers, and telemetry metrics.
    """
    task_results = []
    all_records = []
    all_vector_only = []
    all_raw_vector = []
    seen_ids = set()

    for task in plan.tasks:
        t_res = await execute_planned_task(task, target_dataset=target_dataset, limit=limit, raw_query=raw_query)
        task_results.append(t_res)
        for r in t_res.get("records", []):
            rec_id = str(r.get("_id") or id(r))
            if rec_id not in seen_ids:
                seen_ids.add(rec_id)
                all_records.append(r)
        all_vector_only.extend(t_res.get("vector_only_records", []))
        all_raw_vector.extend(t_res.get("raw_vector_records", []))

    headers = [t["summary_header"] for t in task_results if t.get("summary_header")]
    combined_header = "\n\n".join(headers)

    tot_kw = sum(t.get("keyword_hits", 0) for t in task_results)
    tot_vec = sum(t.get("vector_hits", 0) for t in task_results)
    tot_vec_raw = sum(t.get("vector_hits_raw", 0) for t in task_results)
    stages = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "vector": 0}
    for t in task_results:
        for k_st, count in t.get("stages", {}).items():
            stages[k_st] = stages.get(k_st, 0) + count

    all_unfound = [item for t in task_results for item in t.get("unfound_list", [])]
    top_vector_scores = [r.get("vector_score", 0.0) for r in all_raw_vector[:10]]
    all_filter_events = [item for t in task_results for item in t.get("filter_events", [])]
    total_candidates_before = sum(t.get("candidates_before_filter", 0) for t in task_results)

    return {
        "summary_header": combined_header,
        "task_results": task_results,
        "records": all_records[:limit],
        "vector_only_records": all_vector_only,
        "raw_vector_records": all_raw_vector,
        "vector_records": all_raw_vector,
        "top_vector_scores": top_vector_scores,
        "total": len(all_records[:limit]),
        "unfound_list": all_unfound,
        "unfound": all_unfound,
        "cap_hit": any(t.get("cap_hit", False) for t in task_results),
        "stages": stages,
        "keyword_hits": tot_kw,
        "vector_hits": tot_vec,
        "vector_hits_raw": tot_vec_raw,
        "candidates_before_filter": total_candidates_before,
        "filter_events": all_filter_events,
        "plan": plan.model_dump()
    }
