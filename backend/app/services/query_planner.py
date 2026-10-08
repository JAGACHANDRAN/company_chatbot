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
4. "must_have" can contain: "email", "phone", "linkedin", "address", "designation", "contact_person".
5. "must_not_have" can contain: "email", "phone", "linkedin".
6. If the user refers to previous results ("from those", "from them", "out of these", "only with phone"), set intent="filter_previous" and use_previous_results=true.
7. If the user asks a count question ("how many have email"), set intent="count".
8. If the user asks a semantic/descriptive question (e.g. "labs that calibrate pressure gauges"), set intent="open_question".
9. If the user asks for "another company", "other companies", or "a different company" (e.g. "give me another company list which having email alone"), this is EXPLICITLY NOT previous results. Set intent="lookup", use_previous_results=false, and never set "another" or "other" as a company name.

FEW-SHOT EXAMPLES:
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

User: "tvs quality dept persons alone"
JSON:
{
  "tasks": [
    {
      "intent": "lookup",
      "companies": ["tvs"],
      "must_have": ["designation"],
      "must_not_have": [],
      "fields": ["contact_person", "designation"],
      "only_requested_fields": true,
      "designation_keywords": ["quality", "qa", "qc", "quality assurance", "quality control", "quality manager", "quality head"],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "tvs companies with emails, ashok leyland in chennai, and titan quality persons"
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
    },
    {
      "intent": "lookup",
      "companies": ["ashok leyland"],
      "must_have": [],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": "chennai",
      "state": null,
      "use_previous_results": false
    },
    {
      "intent": "lookup",
      "companies": ["titan"],
      "must_have": ["designation"],
      "must_not_have": [],
      "fields": ["contact_person", "designation"],
      "only_requested_fields": true,
      "designation_keywords": ["quality", "qa", "qc", "quality assurance", "quality control"],
      "city": null,
      "state": null,
      "use_previous_results": false
    }
  ]
}

User: "from those only with phone"
JSON:
{
  "tasks": [
    {
      "intent": "filter_previous",
      "companies": [],
      "must_have": ["phone"],
      "must_not_have": [],
      "fields": [],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": true
    }
  ]
}

User: "how many have linkedin"
JSON:
{
  "tasks": [
    {
      "intent": "count",
      "companies": [],
      "must_have": ["linkedin"],
      "must_not_have": [],
      "fields": ["linkedin"],
      "only_requested_fields": false,
      "designation_keywords": [],
      "city": null,
      "state": null,
      "use_previous_results": true
    }
  ]
}

User: "labs that calibrate pressure gauges"
JSON:
{
  "tasks": [
    {
      "intent": "open_question",
      "companies": [],
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
"""


def split_pasted_companies(raw_text: str) -> List[str]:
    """Splits pasted lists of company names on newlines, semicolons, bullets, tabs, and commas."""
    if not raw_text:
        return []

    # Check if text contains explicit sentence filter instructions: 'with email', 'in chennai', etc.
    # Note: avoid matching 'and' as a filter because company names contain 'and' (e.g. 'mahindra and mahindra')
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

    # Dynamic fallback: find any doc in DB where norm_company is not in exclude_clean
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
        if sq.email_required is True:
            must_have.append("email")
        if sq.email_required is False or "without email" in clause.lower() or "no email" in clause.lower():
            must_not_have.append("email")
        if sq.phone_required is True:
            must_have.append("phone")
        if sq.phone_required is False or "without phone" in clause.lower() or "no phone" in clause.lower():
            must_not_have.append("phone")
        if sq.linkedin_required is True:
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
            r"\b(?:quality\s+(?:dept|department)?\s*(?:persons?|contacts?|heads?|managers?)?|quality|dept|department|persons?|contacts?|alone|only|emails?|phones?|details|companies|company|in|at|from|with|without|another|other|others|different|next|new|same|previous|one)\b",
            "",
            c_clean,
            flags=re.IGNORECASE
        ).strip()
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
                companies.append(chosen.lower())

    desig_kw = []
    if sq.designation:
        desig_clean = sq.designation.lower().strip()
        if desig_clean in DESIGNATION_SYNONYMS:
            desig_kw = list(DESIGNATION_SYNONYMS[desig_clean])
        else:
            desig_kw = [desig_clean]
    elif "quality" in clause_low or (sq.department and sq.department.lower() == "quality"):
        desig_kw = list(DESIGNATION_SYNONYMS["quality"])
        if "designation" not in must_have and "contact_person" not in must_have:
            must_have.append("designation")

    open_indicators = ["which", "what", "where", "how", "labs that", "companies that", "who makes", "who provides", "calibrate", "calibration"]
    if not companies and not use_prev and any(ind in clause_low for ind in open_indicators):
        intent = "open_question"

    fields = list(sq.requested_fields)
    if not fields and ("alone" in clause_low or "only" in clause_low):
        if "email" in clause_low or "mail" in clause_low:
            fields.append("email")
        if "phone" in clause_low or "contact" in clause_low:
            fields.append("phone")
        if "person" in clause_low or "quality" in clause_low:
            fields.extend(["contact_person", "designation"])

    return SearchTask(
        intent=intent,
        companies=companies,
        must_have=list(set(must_have)),
        must_not_have=list(set(must_not_have)),
        fields=list(set(fields)),
        only_requested_fields=sq.is_only_fields or bool(fields),
        designation_keywords=desig_kw,
        city=city_val,
        state=state_val,
        use_previous_results=use_prev
    )


def rule_based_plan(
    raw_query: str,
    history: Optional[List[Dict[str, Any]]] = None,
    has_previous_results: bool = False
) -> QueryPlan:
    """
    Deterministic fallback planner using local regex, clause splitting, & heuristics.
    Handles multi-request sentences, pasted company lists, follow-ups, and counts.
    """
    clean = raw_query.strip()
    if not clean:
        return QueryPlan(tasks=[SearchTask()])

    # Check for pasted multi-line / bulleted / comma-separated list first
    pasted = split_pasted_companies(clean)
    if len(pasted) > 1:
        single_task = _parse_single_clause(clean, history=history, has_previous_results=has_previous_results)
        single_task.companies = pasted
        return QueryPlan(tasks=[single_task])

    # Check for multi-clause sentence: e.g. "tvs companies with emails, ashok leyland in chennai, and titan quality persons"
    # A sentence is multi-clause if it contains multiple clauses with distinct search filters/intents (with/in/quality/dept/persons)
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
                return QueryPlan(tasks=tasks)

    # Single clause fallback
    task = _parse_single_clause(clean, history=history, has_previous_results=has_previous_results)
    return QueryPlan(tasks=[task])


async def plan_query_execution(
    raw_query: str,
    history: Optional[List[Dict[str, Any]]] = None,
    has_previous_results: bool = False
) -> QueryPlan:
    """
    Step 2: Calls gpt-oss:20b with temperature 0, JSON output, timeout 20s.
    Sends ONLY: user query, last 3 user messages (text only), allowed fields, has_previous_results.
    NEVER sends any confidential records or contact values.
    Falls back to rule_based_plan on any error or timeout.
    """
    clean_query = normalize_query_typos(raw_query.strip())
    if not clean_query:
        return QueryPlan(tasks=[SearchTask()])

    # Check if fast rule-based parser handles simple entities or lists with 100% confidence
    pasted = split_pasted_companies(clean_query)
    if len(pasted) > 1:
        return rule_based_plan(clean_query, history=history, has_previous_results=has_previous_results)

    # Privacy mode or missing API key fallback
    if PRIVACY_MODE or not OLLAMA_API_KEY:
        logger.info("[Planner] fallback to rules (privacy mode / no key)")
        return rule_based_plan(clean_query, history=history, has_previous_results=has_previous_results)

    # Extract last 3 user messages (text only)
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
            # Support both {"tasks": [...]} and single task JSON
            if "tasks" in parsed_json:
                plan = QueryPlan(**parsed_json)
            else:
                task = SearchTask(**parsed_json)
                plan = QueryPlan(tasks=[task])

            # Expand designation keywords
            for t in plan.tasks:
                if t.designation_keywords:
                    expanded = set(t.designation_keywords)
                    for kw in list(t.designation_keywords):
                        kw_low = kw.lower().strip()
                        if kw_low in DESIGNATION_SYNONYMS:
                            expanded.update(DESIGNATION_SYNONYMS[kw_low])
                    t.designation_keywords = list(expanded)

            # Enforce Rule 9: If user asks for another/different company, ensure intent is lookup, no prev results, and real new company
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

            logger.info(f"[Planner] Generated Plan -> {len(plan.tasks)} tasks")
            return plan

    except Exception as e:
        logger.warning(f"[Planner] fallback to rules due to exception: {e}")
        return rule_based_plan(clean_query, history=history, has_previous_results=has_previous_results)


async def execute_planned_task(
    task: SearchTask,
    target_dataset: str = "all",
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Executes a single SearchTask independently.
    Its filters apply strictly to its own companies.
    """
    from .multi_stage_search import execute_multi_stage_retrieval
    from .response_generator import (
        extract_company_name,
        extract_person_info,
        extract_emails,
        extract_contact_numbers,
        extract_location,
        extract_linkedin
    )

    companies_to_query = list(dict.fromkeys(task.companies)) if task.companies else []
    found_by_company: Dict[str, List[Dict[str, Any]]] = {}
    unfound_list: List[Tuple[str, List[str]]] = []
    all_matched_records: List[Dict[str, Any]] = []
    seen_ids = set()

    stage_metrics = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "vector": 0}
    total_keyword_hits = 0
    total_vector_hits = 0

    if not companies_to_query:
        return {
            "task": task.model_dump(),
            "found_by_company": {},
            "unfound_list": [],
            "records": [],
            "total": 0,
            "stages": stage_metrics,
            "keyword_hits": 0,
            "vector_hits": 0,
            "summary_header": ""
        }

    # Run retrieval concurrently for each company in task
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

        # If no keyword matches found for this company name, it is an unfound/misspelled entity
        if not multi_res.get("keyword_records"):
            sugg = multi_res.get("suggestions", [])
            unfound_list.append((c_name, sugg))
            continue

        raw_candidates = multi_res.get("records", [])
        filtered_for_company: List[Dict[str, Any]] = []

        for r in raw_candidates:
            # 1. Location / City / State check
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

            # 2. Must Have Conditions
            if "email" in task.must_have and not extract_emails(r):
                continue
            if "phone" in task.must_have and not extract_contact_numbers(r):
                continue
            if "linkedin" in task.must_have and not extract_linkedin(r):
                continue
            if "address" in task.must_have:
                loc = extract_location(r)
                if not (loc.get("address") or loc.get("city") or loc.get("state")):
                    continue
            if "designation" in task.must_have and not extract_person_info(r).get("designation"):
                continue
            if "contact_person" in task.must_have and not extract_person_info(r).get("name"):
                continue

            # 3. Must Not Have Conditions
            if "email" in task.must_not_have and extract_emails(r):
                continue
            if "phone" in task.must_not_have and extract_contact_numbers(r):
                continue
            if "linkedin" in task.must_not_have and extract_linkedin(r):
                continue

            # 4. Designation Keywords Check
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

        # If designation keyword was requested and company matched but 0 contacts matched role:
        # Still list company with "No data available" for person and designation (Step 4 requirement)
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

    # Build section header
    total_req = len(companies_to_query)
    total_found = len(found_by_company)
    total_records = len(all_matched_records)

    if total_req > 1:
        hdr = f"You asked for {total_req} companies. Found {total_found}."
        if unfound_list:
            unf_parts = []
            for name, sugg in unfound_list:
                if sugg:
                    unf_parts.append(f"{name} (did you mean {', '.join(sugg)}?)")
                else:
                    unf_parts.append(name)
            hdr += f" Not found: {', '.join(unf_parts)}."
        hdr += f" Total {total_records} records from {total_found} companies."
    else:
        single_name = companies_to_query[0]
        if total_records > 0:
            filter_desc = []
            if task.city:
                filter_desc.append(f"in {task.city.title()}")
            if "email" in task.must_have:
                filter_desc.append("with email")
            elif "email" in task.must_not_have:
                filter_desc.append("without email")
            if task.designation_keywords:
                filter_desc.append("with matching designation")

            f_str = (" " + " ".join(filter_desc)) if filter_desc else ""
            emails_count = sum(1 for r in all_matched_records if extract_emails(r))
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
        "total": len(all_matched_records[:limit]),
        "cap_hit": cap_hit,
        "stages": stage_metrics,
        "keyword_hits": total_keyword_hits,
        "vector_hits": total_vector_hits
    }


async def execute_planned_retrieval(
    plan: QueryPlan,
    raw_query: str,
    target_dataset: str = "all",
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Executes all tasks in the QueryPlan sequentially/concurrently.
    Preserves task sections and order.
    """
    task_results = []
    all_records = []
    seen_ids = set()

    for task in plan.tasks:
        t_res = await execute_planned_task(task, target_dataset=target_dataset, limit=limit)
        task_results.append(t_res)
        for r in t_res.get("records", []):
            rec_id = str(r.get("_id") or id(r))
            if rec_id not in seen_ids:
                seen_ids.add(rec_id)
                all_records.append(r)

    # Combine headers across tasks
    headers = [t["summary_header"] for t in task_results if t.get("summary_header")]
    combined_header = "\n\n".join(headers)

    tot_kw = sum(t.get("keyword_hits", 0) for t in task_results)
    tot_vec = sum(t.get("vector_hits", 0) for t in task_results)
    stages = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "vector": 0}
    for t in task_results:
        for k_st, count in t.get("stages", {}).items():
            stages[k_st] = stages.get(k_st, 0) + count

    all_unfound = [item for t in task_results for item in t.get("unfound_list", [])]

    return {
        "summary_header": combined_header,
        "task_results": task_results,
        "records": all_records[:limit],
        "total": len(all_records[:limit]),
        "unfound_list": all_unfound,
        "unfound": all_unfound,
        "cap_hit": any(t.get("cap_hit", False) for t in task_results),
        "stages": stages,
        "keyword_hits": tot_kw,
        "vector_hits": tot_vec,
        "plan": plan.model_dump()
    }
