from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from .query_understanding import StructuredQuery


class SearchPlan(BaseModel):
    search_strategy: str = Field(
        ...,
        description="Strategy: exact_entity, multi_value_structured, location_filter, person_search, designation_department, semantic_vector, hybrid, combined"
    )
    use_structured: bool = True
    use_vector: bool = False
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


def route_query(structured_query: StructuredQuery) -> SearchPlan:
    """
    Decides the optimal retrieval strategy based on the structured query:
    - exact_entity: single company exact entity lookup (use_vector=False)
    - multi_value_structured: multiple companies searched independently (use_vector=False)
    - location_filter: structured location filter (use_vector=False)
    - person_search: exact/controlled person search (use_vector=False)
    - hybrid: structured filters as HARD constraints + semantic assistance
    - semantic_vector: broad conceptual/semantic inquiry (use_vector=True)
    """
    comps = structured_query.companies
    people = structured_query.people
    desig = structured_query.designation
    dept = structured_query.department
    state = structured_query.state
    city = structured_query.city
    country = structured_query.country
    loc = structured_query.location
    has_loc = bool(state or city or country or loc)
    sem = structured_query.semantic_query

    structured_filters: Dict[str, Any] = {}
    if comps:
        structured_filters["companies"] = comps
    if people:
        structured_filters["people"] = people
    if desig:
        structured_filters["designation"] = desig
    if dept:
        structured_filters["department"] = dept
    if state:
        structured_filters["state"] = state
    if city:
        structured_filters["city"] = city
    if country:
        structured_filters["country"] = country
    if loc:
        structured_filters["location"] = loc

    orig_lower = structured_query.original_query.lower()
    has_semantic_intent = bool(
        "responsible for" in orig_lower
        or "who handles" in orig_lower
        or "matching this description" in orig_lower
        or "how to" in orig_lower
        or "describe" in orig_lower
        or "procedure" in orig_lower
        or "overview" in orig_lower
    )

    # 1. Multi-company explicit query: e.g. "Find ABC, TVS and 2D INC", "ABC, TVS and XYZ"
    if len(comps) > 1 and not has_semantic_intent:
        return SearchPlan(
            search_strategy="multi_value_structured",
            use_structured=True,
            use_vector=False,
            structured_filters=structured_filters,
            companies=comps,
            description="Multi-company exact entity lookup. Independent entity search for each requested company."
        )

    # 2. Single Exact Company Query: e.g. "2D INC", "TVS", "ABC Industries", "Find TVS"
    if comps and not has_semantic_intent and not (desig or dept):
        return SearchPlan(
            search_strategy="exact_entity",
            use_structured=True,
            use_vector=False,
            structured_filters=structured_filters,
            companies=comps,
            state=state,
            city=city,
            location=loc,
            description="Exact company entity retrieval without vector pollution."
        )

    # 3. Person Name Query: e.g. "Find Ravi Kumar", "Ravi Kumar"
    if people and not has_semantic_intent and not (comps or desig or dept):
        return SearchPlan(
            search_strategy="person_search",
            use_structured=True,
            use_vector=False,
            structured_filters=structured_filters,
            people=people,
            description="Exact/controlled person entity search."
        )

    # 4. Pure Location Filter Query: e.g. "Companies in Tamil Nadu", "Which companies are in Chennai?"
    if has_loc and not (comps or people or desig or dept or has_semantic_intent):
        return SearchPlan(
            search_strategy="location_filter",
            use_structured=True,
            use_vector=False,
            structured_filters=structured_filters,
            state=state,
            city=city,
            country=country,
            location=loc,
            description="Structured location filter across all database records."
        )

    # 5. Hybrid Query: structured constraints (role, department, location, company) + semantic matching
    # e.g. "Quality managers in Tamil Nadu"
    if (desig or dept) and (has_loc or comps) and not has_semantic_intent:
        return SearchPlan(
            search_strategy="hybrid",
            use_structured=True,
            use_vector=True,
            structured_filters=structured_filters,
            companies=comps,
            people=people,
            designation=desig,
            department=dept,
            state=state,
            city=city,
            country=country,
            location=loc,
            semantic_query=desig or dept or structured_query.original_query,
            description="Hybrid query: structured filters as HARD constraints with semantic assistance."
        )

    # 6. Designation / Department only: e.g. "Show quality managers"
    if (desig or dept) and not (comps or people or has_loc or has_semantic_intent):
        return SearchPlan(
            search_strategy="designation_department",
            use_structured=True,
            use_vector=True,
            structured_filters=structured_filters,
            designation=desig,
            department=dept,
            semantic_query=desig or dept or "",
            description="Role/department structured filter with semantic role matching."
        )

    # 7. Pure Semantic Query: e.g. "Who is responsible for quality operations?"
    if has_semantic_intent or (sem and not (comps or people or has_loc)):
        return SearchPlan(
            search_strategy="semantic_vector",
            use_structured=bool(dept or desig),
            use_vector=True,
            structured_filters=structured_filters,
            department=dept,
            designation=desig,
            semantic_query=sem or structured_query.original_query,
            description="Semantic vector retrieval for conceptual or descriptive inquiry."
        )

    # Fallback to controlled entity search
    return SearchPlan(
        search_strategy="exact_entity",
        use_structured=True,
        use_vector=False,
        structured_filters=structured_filters,
        companies=comps,
        people=people,
        description="Controlled entity structured search."
    )
