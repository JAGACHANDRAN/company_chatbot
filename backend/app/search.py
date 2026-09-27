import re
from typing import List, Dict, Any, Optional, Union
from pymongo.collection import Collection
from .models import CANONICAL_COLUMNS, format_mongo_document

# Maps canonical column names to the common key variations in MongoDB collections
FIELD_DOCUMENT_KEYS: Dict[str, List[str]] = {
    "company_name": ["company_name", "Company Name", "company", "Company", "name", "Name"],
    "group": ["group", "Group", "group_name", "Group Name"],
    "contact_person": ["contact_person", "Contact Person", "contact", "Contact", "person", "Person"],
    "designation": ["designation", "Designation", "title", "Title", "role", "Role"],
    "mobile_no": ["mobile_no", "Mobile No.", "Mobile No", "mobile", "Mobile", "cell", "Cell"],
    "landline_telephone": ["Landline / Telephone", "landline_telephone", "landline", "Landline", "telephone", "Telephone"],
    "landline_other_no": ["Landline / Other No.", "landline_other_no", "Landline / Other", "landline_other"],
    "telephone_1": ["telephone_1", "Telephone 1", "tel_1", "Tel 1", "telephone1", "tel1"],
    "telephone_2": ["telephone_2", "Telephone 2", "tel_2", "Tel 2", "telephone2", "tel2"],
    "email": ["Email", "email"],
    "email_1": ["email_1", "Email 1", "email1", "Email1"],
    "email_2": ["email_2", "Email 2", "email2", "Email2"],
    "address": ["address", "Address", "location", "Location"],
    "city": ["city", "City"],
    "state": ["state", "State"],
    "pin": ["pin", "PIN", "pincode", "Pincode", "pin_code", "Pin Code", "zip", "zipcode"],
    "records_merged": ["Records Merged", "records_merged"],
    "review_required": ["Review Required", "review_required"],
    "sources": ["Sources", "sources", "Source", "source"],
    "remarks": ["remarks", "Remarks", "remark", "Remark", "notes", "Notes", "comment", "Comments"],
}

# User query alias mapping -> canonical fields
FIELD_ALIASES: Dict[str, List[str]] = {
    # Company Name
    "company_name": ["company_name"],
    "company": ["company_name"],
    "companyname": ["company_name"],
    "name": ["company_name"],
    # Group
    "group": ["group"],
    "group_name": ["group"],
    "groupname": ["group"],
    # Contact Person
    "contact_person": ["contact_person"],
    "contactperson": ["contact_person"],
    "contact": ["contact_person"],
    "person": ["contact_person"],
    # Designation
    "designation": ["designation"],
    "title": ["designation"],
    "role": ["designation"],
    "position": ["designation"],
    # Mobile No.
    "mobile_no": ["mobile_no"],
    "mobileno": ["mobile_no"],
    "mobile": ["mobile_no"],
    "cell": ["mobile_no"],
    # Landline & Telephones
    "landline_telephone": ["landline_telephone"],
    "landline_other_no": ["landline_other_no"],
    "landline": ["landline_telephone", "landline_other_no", "telephone_1", "telephone_2"],
    "telephone_1": ["telephone_1"],
    "telephone_2": ["telephone_2"],
    "telephone": ["landline_telephone", "landline_other_no", "telephone_1", "telephone_2", "mobile_no"],
    "phone": ["mobile_no", "landline_telephone", "landline_other_no", "telephone_1", "telephone_2"],
    "phones": ["mobile_no", "landline_telephone", "landline_other_no", "telephone_1", "telephone_2"],
    # Emails
    "email_1": ["email_1"],
    "email1": ["email_1"],
    "email_2": ["email_2"],
    "email2": ["email_2"],
    "email": ["email", "email_1", "email_2"],
    "emails": ["email", "email_1", "email_2"],
    # Address, City, State
    "address": ["address"],
    "location": ["address", "city", "state"],
    "city": ["city"],
    "state": ["state"],
    # PIN
    "pin": ["pin"],
    "pincode": ["pin"],
    "pin_code": ["pin"],
    "zip": ["pin"],
    "zipcode": ["pin"],
    "postal_code": ["pin"],
    # Records & Metadata
    "records_merged": ["records_merged"],
    "review_required": ["review_required"],
    "sources": ["sources"],
    "source": ["sources"],
    # Remarks
    "remarks": ["remarks"],
    "remark": ["remarks"],
    "notes": ["remarks"],
    "comments": ["remarks"],
}

ALLOWED_SEARCH_FIELDS = set(FIELD_ALIASES.keys())


def normalize_search_value(value: str) -> str:
    """Trims whitespace while preserving formatting, phone symbols, and numbers."""
    if not value:
        return ""
    return value.strip()


def build_mongo_query(target_fields: List[str], clean_val: str, operator: str = "contains") -> Dict[str, Any]:
    """
    Builds a MongoDB filter condition with case-insensitive regex ($regex)
    across all relevant document key variations.
    """
    if operator not in {"equals", "contains", "starts_with", "ends_with"}:
        raise ValueError(f"Unsupported search operator: {operator}")
    if re.fullmatch(r"[A-Za-z0-9\s_-]+", clean_val):
        compact_val = re.sub(r"[^A-Za-z0-9]", "", clean_val)
        regex_pattern = r"[\W_]*".join(re.escape(char) for char in compact_val)
    else:
        regex_pattern = re.escape(clean_val)
    if operator == "equals":
        regex_pattern = f"^{regex_pattern}$"
    elif operator == "starts_with":
        regex_pattern = f"^{regex_pattern}"
    elif operator == "ends_with":
        regex_pattern = f"{regex_pattern}$"
    regex_clause = {"$regex": regex_pattern, "$options": "i"}

    or_clauses = []
    seen_keys = set()

    for canonical in target_fields:
        doc_keys = FIELD_DOCUMENT_KEYS.get(canonical, [canonical])
        for k in doc_keys:
            if k not in seen_keys:
                seen_keys.add(k)
                or_clauses.append({k: regex_clause})

    if len(or_clauses) == 1:
        return or_clauses[0]
    return {"$or": or_clauses}


def search_companies(
    target: Union[Collection, List[Collection]],
    field: Optional[str],
    value: str,
    limit: int = 50,
    operator: str = "contains",
) -> List[Dict[str, Any]]:
    """
    Executes a case-insensitive MongoDB search across the 11 columns:
    1. Company Name, 2. Group, 3. Contact Person, 4. Mobile No., 5. Email 1,
    6. Email 2, 7. Telephone 1, 8. Telephone 2, 9. Address, 10. PIN, 11. Remarks.
    
    Supports:
    - Single Collection or List of Collections (searches across all 6 collections)
    - Automatically tags each result with 'source_collection'
    - Deduplicates records matching across multiple collections
    - Both snake_case and verbatim key schemas
    """
    clean_val = normalize_search_value(value)
    if not clean_val:
        return []

    # 1. Resolve which canonical fields to query
    target_fields: List[str] = []
    if field:
        norm_field = re.sub(r"[^a-zA-Z0-9_]", "", field.lower())
        if norm_field in FIELD_ALIASES:
            target_fields = FIELD_ALIASES[norm_field]
        elif field.lower() in FIELD_ALIASES:
            target_fields = FIELD_ALIASES[field.lower()]

    if not target_fields:
        # Multi-column search across all 11 columns
        target_fields = CANONICAL_COLUMNS

    # 2. Build MongoDB query
    mongo_filter = build_mongo_query(target_fields, clean_val, operator=operator)

    # 3. Handle single collection vs list of collections
    collections: List[Collection] = target if isinstance(target, list) else [target]

    results: List[Dict[str, Any]] = []
    seen_unique_ids = set()

    for col in collections:
        if len(results) >= limit:
            break

        remaining = limit - len(results)
        try:
            cursor = col.find(mongo_filter).limit(remaining)
            for doc in cursor:
                doc_id = str(doc.get("_id", doc.get("id", "")))
                # Combine collection name with id to uniquely identify
                uid = f"{col.name}:{doc_id}" if doc_id else f"{col.name}:{len(results)}"
                if uid not in seen_unique_ids:
                    seen_unique_ids.add(uid)
                    clean_record = format_mongo_document(doc, collection_name=col.name)
                    results.append(clean_record)
        except Exception as err:
            print(f"[MongoDB Search Warning] Could not query collection '{col.name}': {err}")

    return results


def search_collections_conditions(
    collections: List[Collection],
    conditions: List[Dict[str, Any]],
    logic: str = "AND",
    return_fields: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Executes a structured, concept-aware search across default MongoDB collections.
    Dynamically maps concepts (location, company, person, etc.) to all matching fields in each collection.
    Handles company normalization and combines multiple conditions with AND/OR logic.
    """
    if not conditions:
        return []

    # Map of concepts to canonical fields in default collections
    concept_canonical_map = {
        "location": ["address", "city", "state"],
        "company": ["company_name", "group"],
        "person": ["contact_person"],
        "designation": ["designation"],
        "email": ["email", "email_1", "email_2"],
        "phone": ["mobile_no", "landline_telephone", "landline_other_no", "telephone_1", "telephone_2"],
    }

    results: List[Dict[str, Any]] = []
    seen_unique_ids = set()

    for col in collections:
        if len(results) >= limit:
            break

        condition_clauses = []
        for cond in conditions:
            concept = str(cond.get("concept") or "").lower().strip()
            field = str(cond.get("field") or "").strip()
            raw_val = str(cond.get("value") or "").strip()
            operator = str(cond.get("operator") or "contains")

            clean_val = normalize_search_value(raw_val)
            if not clean_val:
                continue

            # Determine target canonical fields
            target_canonicals = []
            if concept in concept_canonical_map:
                target_canonicals = concept_canonical_map[concept]
            elif field:
                norm_f = re.sub(r"[^a-zA-Z0-9_]", "", field.lower())
                target_canonicals = FIELD_ALIASES.get(norm_f, [norm_f])
            else:
                target_canonicals = CANONICAL_COLUMNS

            # For company concept, normalize search terms
            search_terms = [clean_val]
            if concept == "company" or "company_name" in target_canonicals:
                stripped = re.sub(
                    r"\s+\b(ltd|limited|pvt|private|corp|corporation|inc|llc|group|auto|technologies|tech|solutions|industries)\b\.?$",
                    "",
                    clean_val,
                    flags=re.IGNORECASE
                ).strip()
                if stripped and stripped.lower() != clean_val.lower() and len(stripped) >= 2:
                    search_terms.append(stripped)

            sub_clauses = []
            for term in search_terms:
                query_part = build_mongo_query(target_canonicals, term, operator=operator)
                sub_clauses.append(query_part)

            if len(sub_clauses) == 1:
                condition_clauses.append(sub_clauses[0])
            elif sub_clauses:
                condition_clauses.append({"$or": sub_clauses})

        if not condition_clauses:
            continue

        if logic.upper() == "OR":
            mongo_filter = {"$or": condition_clauses} if len(condition_clauses) > 1 else condition_clauses[0]
        else:
            mongo_filter = {"$and": condition_clauses} if len(condition_clauses) > 1 else condition_clauses[0]

        remaining = limit - len(results)
        try:
            cursor = col.find(mongo_filter).limit(remaining)
            for doc in cursor:
                doc_id = str(doc.get("_id", doc.get("id", "")))
                uid = f"{col.name}:{doc_id}" if doc_id else f"{col.name}:{len(results)}"
                if uid not in seen_unique_ids:
                    seen_unique_ids.add(uid)
                    clean_record = format_mongo_document(doc, collection_name=col.name)
                    # Project requested fields if specific lookup
                    if return_fields and "*" not in return_fields:
                        allowed_canonicals = set(return_fields)
                        allowed_canonicals.update(["company_name", "contact_person", "id", "source_collection"])
                        projected = {k: v for k, v in clean_record.items() if k in allowed_canonicals}
                        results.append(projected if projected else clean_record)
                    else:
                        results.append(clean_record)
        except Exception as err:
            print(f"[MongoDB Search Warning] Could not query collection '{col.name}': {err}")

    return results

