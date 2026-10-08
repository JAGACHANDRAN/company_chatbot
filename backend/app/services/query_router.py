"""
Query Router Service for Hybrid RAG.
Classifies user search intents and decides the execution plan:
1. Exact lookups (Phone, Email, Exact Person/Company name) -> Lexical only (No LLM call, direct cards).
2. Descriptive or semantic queries -> Hybrid (Vector Search + Lexical Search in parallel, RRF merged).
"""
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from .query_understanding import StructuredQuery


class SearchPlan(BaseModel):
    search_strategy: str = Field(
        ...,
        description="Strategy: exact_lookup, exact_entity, multi_value_structured, location_filter, person_search, designation_department, semantic_vector, hybrid"
    )
    use_structured: bool = True
    use_vector: bool = True
    requires_llm: bool = True
    structured_filters: Dict[str, Any] = Field(default_factory=dict)
    companies: List[str] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)
    designation: Optional[str] = None
    department: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    location: Optional[str] = None
    semantic_query: str = ""
    description: str = ""


PHONE_REGEX = re.compile(r"(\+?\d[\d\s-]{6,15}\d)")
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def is_exact_lookup_query(structured_query: StructuredQuery) -> bool:
    """
    Identifies if a query is a direct lookup for phone, email, or exact entity
    where results should be served directly from MongoDB without calling the cloud LLM.
    """
    orig = structured_query.original_query.strip()
    
    # Check for direct phone number or email string
    if PHONE_REGEX.search(orig) and not any(kw in orig.lower() for kw in ("how", "why", "compare", "summary", "list")):
        return True
    if EMAIL_REGEX.search(orig):
        return True

    # Check for exact single person name lookup (e.g. "Ravi Kumar", "Find Rajesh")
    if structured_query.people and len(structured_query.people) == 1 and not structured_query.designation and not structured_query.semantic_query:
        words = orig.split()
        if len(words) <= 4 and any(kw in orig.lower() for kw in ("who is", "contact for", "find", "lookup", "phone of", "email of")):
            return True

    return False


def route_query(structured_query: StructuredQuery) -> SearchPlan:
    """
    Routes the structured query to the optimal execution plan:
    - Exact Phone/Email/Entity -> Lexical only (requires_llm=False)
    - Semantic / Descriptive / Hybrid -> Vector + Lexical (requires_llm=True)
    """
    comps = structured_query.companies
    people = structured_query.people
    desig = structured_query.designation
    dept = structured_query.department
    state = structured_query.state
    city = structured_query.city
    country = structured_query.country
    loc = structured_query.location
    orig_lower = structured_query.original_query.lower()

    structured_filters: Dict[str, Any] = {}
    if comps: structured_filters["companies"] = comps
    if people: structured_filters["people"] = people
    if desig: structured_filters["designation"] = desig
    if dept: structured_filters["department"] = dept
    if state: structured_filters["state"] = state
    if city: structured_filters["city"] = city
    if country: structured_filters["country"] = country
    if loc: structured_filters["location"] = loc

    # 1. Exact Phone / Email / Direct Lookup
    if is_exact_lookup_query(structured_query):
        strategy = "person_search" if people and not (comps or desig or dept) else "exact_lookup"
        return SearchPlan(
            search_strategy=strategy,
            use_structured=True,
            use_vector=False,
            requires_llm=False,
            structured_filters=structured_filters,
            companies=comps,
            people=people,
            city=city,
            description="Exact phone/email/person lookup. Database direct answer without LLM call."
        )

    # 2. Multi-company exact query
    if len(comps) > 1 and not any(kw in orig_lower for kw in ("best", "describe", "recommend", "summary", "compare")):
        return SearchPlan(
            search_strategy="multi_value_structured",
            use_structured=True,
            use_vector=False,
            requires_llm=False,
            structured_filters=structured_filters,
            companies=comps,
            description="Multi-company exact entity lookup."
        )

    # 3. Company entity search (e.g. "TVS", "show TVS companies", "companies related to TVS")
    if comps and not (desig or dept or city or state):
        is_analytical = any(kw in orig_lower for kw in ("best", "describe", "recommend", "summary", "compare", "why", "how", "explain", "overview"))
        return SearchPlan(
            search_strategy="exact_entity",
            use_structured=True,
            use_vector=True,
            requires_llm=is_analytical,
            structured_filters=structured_filters,
            companies=comps,
            description="Company entity search with hybrid retrieval."
        )

    # 4. Pure location query (e.g. "Companies in Chennai")
    if (city or state) and not (comps or people or desig) and any(w in orig_lower for w in ("in", "at", "companies in", "list")):
        return SearchPlan(
            search_strategy="location_filter",
            use_structured=True,
            use_vector=True,
            requires_llm=True,
            structured_filters=structured_filters,
            city=city,
            state=state,
            description="Location-scoped hybrid search."
        )

    # 5. Default Hybrid strategy for descriptive or semantic questions
    return SearchPlan(
        search_strategy="hybrid",
        use_structured=True,
        use_vector=True,
        requires_llm=True,
        structured_filters=structured_filters,
        companies=comps,
        people=people,
        designation=desig,
        department=dept,
        city=city,
        state=state,
        semantic_query=structured_query.semantic_query or structured_query.original_query,
        description="Hybrid RAG: Parallel Vector ($vectorSearch) + Lexical search merged via RRF (k=60)."
    )
