import re
from typing import Dict, Any, Optional, List

# Common corporate suffixes for company name normalization
COMPANY_SUFFIX_PATTERN = re.compile(
    r"\s+\b(pvt\s+ltd|private\s+limited|pvt|ltd|limited|corp|corporation|inc|incorporated|llc|llp|group|enterprises?|industries|tech|technologies|solutions)\b\.?$",
    re.IGNORECASE,
)

# Standard empty / null indicator values
NULL_STRINGS = {
    "", "none", "null", "n/a", "na", "-", "--", "undefined", "nan", ".", "not available", "not publicly available"
}


def normalize_text(text: Optional[str]) -> str:
    """
    Standard text normalization:
    - trim whitespace
    - lowercase
    - collapse multiple spaces
    """
    if text is None:
        return ""
    s = str(text).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def clean_display_value(val: Any, default: str = "Not Available") -> str:
    """
    Returns original string value or 'Not Available' if null/empty/placeholder.
    """
    if val is None:
        return default
    s = str(val).strip()
    if s.lower() in NULL_STRINGS:
        return default
    return s


def is_valid_field_value(val: Any) -> bool:
    """
    Returns True if the field has a genuine, non-null, non-empty value.
    """
    if val is None:
        return False
    if isinstance(val, (int, float, bool)):
        return True
    s = str(val).strip().lower()
    return s not in NULL_STRINGS


import unicodedata


def normalize_company_name(name: Optional[str]) -> str:
    """
    Normalizes company name for exact and clean entity matching:
    - Lowercase
    - Trim whitespace
    - Collapse repeated spaces
    - Normalize harmless punctuation (replace punctuation like dots, commas, quotes, parentheses with spaces)
    - Normalize Unicode
    - PRESERVES meaningful legal/company-name tokens:
      INC, LTD, LIMITED, PVT, PVT LTD, PRIVATE LIMITED, LLP, LLC, CORP, CORPORATION, CO, COMPANY.
    Example:
    '2D INC' -> '2d inc'
    'ABC Pvt. Ltd.' -> 'abc pvt ltd'
    'TVS Motor Company' -> 'tvs motor company'
    """
    if name is None:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = s.lower().strip()
    # Normalize harmless punctuation without stripping corporate words
    s = re.sub(r"[\.,;:_()\[\]/\\\'\"]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_company_search_variants(raw_value: str) -> List[str]:
    """
    Returns list of search variants for a company name without stripping identity.
    e.g. '2D INC' -> ['2D INC', '2d inc']
    """
    clean = str(raw_value).strip()
    if not clean:
        return []
    variants = [clean]
    norm = normalize_company_name(clean)
    if norm and norm.lower() != clean.lower():
        variants.append(norm)
    return variants


def is_company_match(query_company: str, record_company: str) -> bool:
    """
    Validates whether a candidate record company matches an explicit query company.
    Strict entity guard:
    - Exact match on normalized names ('2d inc' == '2d inc')
    - Word boundary / controlled entity match ('tvs' matches 'tvs motor company' or 'delphi tvs')
    - REJECTS unrelated companies (e.g. 'accumen automation' for '2d inc').
    """
    if not query_company or not record_company:
        return False
    norm_q = normalize_company_name(query_company)
    norm_r = normalize_company_name(record_company)
    if not norm_q or not norm_r:
        return False
    if norm_q == norm_r:
        return True

    q_words = norm_q.split()
    if len(q_words) == 1:
        q_token = q_words[0]
        pattern = rf"(^|\s|\-){re.escape(q_token)}(\s|\-|$)"
        return bool(re.search(pattern, norm_r))

    pattern = rf"(^|\s|\-){re.escape(norm_q)}(\s|\-|$)"
    if re.search(pattern, norm_r):
        return True

    rec_pattern = rf"(^|\s|\-){re.escape(norm_r)}(\s|\-|$)"
    if re.search(rec_pattern, norm_q):
        return True

    return False


def is_person_match(query_person: str, record_person: str) -> bool:
    """
    Validates whether a candidate record person matches an explicit query person name.
    Strict person relevance guard:
    - Exact normalized match
    - Substring name match (e.g. 'Ravi Kumar' matches 'Dr. Ravi Kumar')
    - Strictly rejects unrelated persons.
    """
    if not query_person or not record_person:
        return False
    norm_q = normalize_person_name(query_person)
    norm_r = normalize_person_name(record_person)
    if not norm_q or not norm_r or norm_r == "not available":
        return False
    if norm_q == norm_r:
        return True
    # Word boundary match for honorifics / middle names
    pattern = rf"(^|\s){re.escape(norm_q)}(\s|$)"
    return bool(re.search(pattern, norm_r))


def normalize_person_name(name: Optional[str]) -> str:
    """
    Normalizes person name:
    'Dr. Ravi   Kumar ' -> 'ravi kumar'
    'Mr. Rajesh' -> 'rajesh'
    """
    base = normalize_text(name)
    if not base:
        return ""
    base = re.sub(r"^(mr\.|ms\.|mrs\.|dr\.|prof\.)\s+", "", base)
    return base.strip()


def normalize_location_string(loc: Optional[str]) -> str:
    """
    Normalizes location (state, city, country, address):
    '  Andhra Pradesh  ' -> 'andhra pradesh'
    'CHENNAI' -> 'chennai'
    """
    return normalize_text(loc)


def normalize_designation(desig: Optional[str]) -> str:
    """
    Normalizes designation/job title:
    'QUALITY MANAGER' -> 'quality manager'
    'Head - Quality' -> 'head quality'
    """
    base = normalize_text(desig)
    base = re.sub(r"[-_/]+", " ", base)
    base = re.sub(r"\s+", " ", base)
    return base.strip()


def infer_department(designation: Optional[str], dept: Optional[str] = None) -> Optional[str]:
    """
    Infers or normalizes department from designation or existing department field.
    e.g. 'Quality Engineer' -> 'Quality'
         'Head of Quality' -> 'Quality'
         'Sales Executive' -> 'Sales'
         'Director - R&D' -> 'R&D'
    """
    if is_valid_field_value(dept):
        return str(dept).strip()

    if not designation:
        return None

    desig_lower = designation.lower()
    if "quality" in desig_lower or "qa" in desig_lower or "qc" in desig_lower:
        return "Quality"
    if "sales" in desig_lower or "marketing" in desig_lower or "business development" in desig_lower:
        return "Sales & Marketing"
    if "purchase" in desig_lower or "procurement" in desig_lower or "supply chain" in desig_lower:
        return "Procurement"
    if "production" in desig_lower or "manufacturing" in desig_lower or "operations" in desig_lower:
        return "Production & Operations"
    if "hr" in desig_lower or "human resource" in desig_lower:
        return "Human Resources"
    if "finance" in desig_lower or "account" in desig_lower:
        return "Finance & Accounts"
    if "r&d" in desig_lower or "research" in desig_lower or "design" in desig_lower:
        return "R&D"
    if "director" in desig_lower or "managing director" in desig_lower or "ceo" in desig_lower or "founder" in desig_lower:
        return "Executive Leadership"

    return None


def extract_field_from_dict(doc: Dict[str, Any], candidates: List[str]) -> Optional[Any]:
    """
    Extracts first non-null matching key from document case-insensitively.
    """
    doc_keys_map = {re.sub(r"[^a-z0-9]", "", k.lower()): k for k in doc.keys()}
    for cand in candidates:
        norm_cand = re.sub(r"[^a-z0-9]", "", cand.lower())
        if norm_cand in doc_keys_map:
            val = doc[doc_keys_map[norm_cand]]
            if is_valid_field_value(val):
                return val
    return None


def normalize_record_fields(
    raw_doc: Dict[str, Any],
    source_file: Optional[str] = None,
    source_row: Any = None
) -> Dict[str, Any]:
    """
    Normalizes any database document or dataset record into the standard logical schema:
    {
      "company_name": "...",
      "person_name": "...",
      "designation": "...",
      "department": "...",
      "state": "...",
      "city": "...",
      "country": "...",
      "location": "...",
      "linkedin_url": "...",
      "linkedin_connections": "...",
      "contact_number": "...",
      "personal_mail_id": "...",
      "last_linkedin_post_date": "...",
      "contact_source": "...",
      "source_file": "...",
      "source_row": "...",
      "search_text": "...",
      "embedding": [...]
    }
    Preserves all original fields and values.
    """
    # If the document is wrapped in a dataset record with 'data' and 'normalized_data'
    data = raw_doc.get("data") if isinstance(raw_doc.get("data"), dict) else raw_doc

    # 1. Company Name
    company_name = extract_field_from_dict(
        data,
        ["company_name", "Company Name", "company", "Company", "business_name", "Organization", "Firm"]
    )
    company_display = str(company_name).strip() if company_name else "Not Available"

    # 2. Person Name
    person_name = extract_field_from_dict(
        data,
        ["person_name", "Person Name", "contact_person", "Contact Person", "name", "Full Name", "Employee Name"]
    )
    person_display = str(person_name).strip() if person_name else "Not Available"

    # 3. Designation
    designation = extract_field_from_dict(
        data,
        ["designation", "Designation", "role", "Role", "job_title", "Job Title", "Position", "Title"]
    )
    designation_display = str(designation).strip() if designation else "Not Available"

    # 4. Department
    raw_dept = extract_field_from_dict(data, ["department", "Department", "division", "Division", "Group"])
    department = infer_department(designation_display if designation else None, raw_dept)
    department_display = department if department else "Not Available"

    # 5. State
    state = extract_field_from_dict(data, ["state", "State", "province", "Province", "Region", "Territory"])
    state_display = str(state).strip() if state else "Not Available"

    # 6. City
    city = extract_field_from_dict(data, ["city", "City", "town", "Town", "district", "District"])
    city_display = str(city).strip() if city else "Not Available"

    # 7. Country
    country = extract_field_from_dict(data, ["country", "Country", "nation", "Nation"])
    country_display = str(country).strip() if country else "Not Available"

    # 8. Address / Location
    address = extract_field_from_dict(data, ["address", "Address", "location", "Location", "Company Address"])
    address_display = str(address).strip() if address else "Not Available"

    # Combined location
    location_parts = []
    if city_display != "Not Available":
        location_parts.append(city_display)
    if state_display != "Not Available":
        location_parts.append(state_display)
    if country_display != "Not Available":
        location_parts.append(country_display)
    if not location_parts and address_display != "Not Available":
        location_parts.append(address_display)
    location_unified = ", ".join(location_parts) if location_parts else "Not Available"

    # 9. LinkedIn URL
    linkedin_url = extract_field_from_dict(data, ["linkedin_url", "LinkedIn URL", "linkedin", "LinkedIn", "profile_url"])
    linkedin_display = str(linkedin_url).strip() if linkedin_url else "Not Available"

    # 10. LinkedIn Connections
    linkedin_conns = extract_field_from_dict(data, ["linkedin_connections", "LinkedIn Connections", "connections", "Connections"])
    linkedin_conns_display = str(linkedin_conns).strip() if linkedin_conns else "Not Available"

    # 11. Contact Number (mobile / phone / telephone)
    contact_number = extract_field_from_dict(
        data,
        ["contact_number", "Contact Number", "mobile_no", "Mobile No.", "Mobile No", "Mobile", "phone", "Phone", "telephone_1", "Telephone 1", "Telephone", "landline_telephone", "Landline / Telephone"]
    )
    contact_number_display = str(contact_number).strip() if contact_number else "Not Available"

    # 12. Personal Mail ID / Email
    personal_mail_id = extract_field_from_dict(
        data,
        ["personal_email_id", "Personal Email ID", "personal_mail_id", "email_1", "Email 1", "email", "Email", "email_2", "Email 2", "mail", "Email Address"]
    )
    personal_mail_id_display = str(personal_mail_id).strip() if personal_mail_id else "Not Available"

    # 13. Last LinkedIn Post Date
    last_post_date = extract_field_from_dict(data, ["last_linkedin_post_date", "Last LinkedIn Post Date", "last_post_date"])
    last_post_date_display = str(last_post_date).strip() if last_post_date else "Not Available"

    # 14. Contact Source
    contact_source = extract_field_from_dict(data, ["contact_source", "Contact Source", "sources", "Sources", "Source Sheets", "Source File"])
    contact_source_display = str(contact_source).strip() if contact_source else "Not Available"

    # 15. Source Metadata
    from ..database import get_database_name
    db_name = get_database_name()

    raw_s_file = (
        raw_doc.get("source_file")
        or data.get("Source File")
        or data.get("source_file")
        or data.get("source_filename")
        or data.get("Source_File")
        or data.get("sourcefile")
        or data.get("file_name")
        or data.get("filename")
        or raw_doc.get("dataset_name")
        or source_file
    )
    if raw_s_file:
        s_clean = str(raw_s_file).strip()
        if s_clean.lower() in ("mongodb", "mongodb atlas", "dataset_records", "none", "not available", "null") or s_clean.startswith("MongoDB:"):
            resolved_source_file = None
        else:
            resolved_source_file = s_clean
    else:
        resolved_source_file = None

    resolved_source_row = raw_doc.get("source_row")
    if resolved_source_row is None and raw_doc.get("record_index") is not None:
        try:
            resolved_source_row = int(raw_doc["record_index"]) + 1
        except Exception:
            resolved_source_row = raw_doc.get("record_index")
    if resolved_source_row is None:
        resolved_source_row = source_row

    resolved_collection = (
        raw_doc.get("source_collection")
        or (source_file.replace("MongoDB: ", "") if source_file and "MongoDB: " in str(source_file) else None)
        or ("dataset_records" if raw_doc.get("dataset_id") else None)
        or "default"
    )
    resolved_sheet = (
        raw_doc.get("sheet_name")
        or raw_doc.get("source_sheet")
        or data.get("Source Sheet")
        or data.get("Source Sheets")
        or None
    )
    resolved_db_source = raw_doc.get("database_source") or raw_doc.get("database") or db_name

    # 16. Build clean source_fields representation containing ONLY original source columns
    source_fields = {}
    source_payload = raw_doc.get("data") if isinstance(raw_doc.get("data"), dict) and raw_doc["data"] else data
    for k, v in source_payload.items():
        if not k or k.startswith("_"):
            continue
        k_lower = k.strip().lower()
        if k_lower in INTERNAL_EXCLUDE_KEYS:
            continue
        # Preserve original source value; if empty/missing in source, use 'Not Available'
        if not is_valid_field_value(v):
            source_fields[k] = "Not Available"
        else:
            source_fields[k] = str(v) if type(v).__name__ == "ObjectId" else v

    # 17. Search Text (for Vector & Semantic Search)
    search_components = [
        company_display if company_display != "Not Available" else "",
        person_display if person_display != "Not Available" else "",
        designation_display if designation_display != "Not Available" else "",
        department_display if department_display != "Not Available" else "",
        city_display if city_display != "Not Available" else "",
        state_display if state_display != "Not Available" else "",
        country_display if country_display != "Not Available" else "",
        address_display if address_display != "Not Available" else "",
    ]
    search_text = " ".join([c for c in search_components if c]).strip()

    # Build clean standardized record
    normalized_rec = {
        "id": str(raw_doc.get("_id", raw_doc.get("id", ""))),
        "company_name": company_display,
        "norm_company_name": normalize_company_name(company_name),
        "person_name": person_display,
        "norm_person_name": normalize_person_name(person_name),
        "designation": designation_display,
        "department": department_display,
        "state": state_display,
        "city": city_display,
        "country": country_display,
        "location": location_unified,
        "linkedin_url": linkedin_display,
        "linkedin_connections": linkedin_conns_display,
        "contact_number": contact_number_display,
        "personal_mail_id": personal_mail_id_display,
        "last_linkedin_post_date": last_post_date_display,
        "contact_source": contact_source_display,
        "source_file": resolved_source_file,
        "source_collection": resolved_collection,
        "source_sheet": resolved_sheet,
        "source_row": resolved_source_row,
        "database_source": resolved_db_source,
        "source_fields": source_fields,
        "raw_data": source_fields,
        "search_text": search_text,
        "embedding": raw_doc.get("embedding"),
        # Normalized searchable values
        "_norm_company_name": normalize_company_name(company_name),
        "_norm_person_name": normalize_person_name(person_name),
        "_norm_designation": normalize_designation(designation),
        "_norm_department": normalize_text(department),
        "_norm_state": normalize_location_string(state),
        "_norm_city": normalize_location_string(city),
        "_norm_country": normalize_location_string(country),
        "_norm_location": normalize_location_string(location_unified),
    }

    return normalized_rec


INTERNAL_EXCLUDE_KEYS = {
    "_id", "id", "embedding", "search_text", "normalized_data", "data", "raw_data",
    "norm_company_name", "norm_person_name", "norm_designation", "norm_department",
    "norm_state", "norm_city", "norm_country", "norm_location",
    "_norm_company_name", "_norm_person_name", "_norm_designation", "_norm_department",
    "_norm_state", "_norm_city", "_norm_country", "_norm_location",
    "vector_score", "similarity_score", "retrieval_score", "chunk_text", "internal_id",
    "database_source", "database", "source_collection", "dataset", "dataset_id", "dataset_name",
    "source_file", "source_sheet", "source_row", "record_index", "source_fields"
}


def extract_original_source_fields(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts the pristine original source columns from a retrieved record.
    Never includes internal normalized fields or standardized filler fields.
    """
    if not isinstance(record, dict):
        return {}

    # 1. Prefer explicit source_fields if available
    sf = record.get("source_fields")
    if isinstance(sf, dict) and sf:
        return {
            k: v for k, v in sf.items()
            if not k.startswith("_") and k.lower() not in INTERNAL_EXCLUDE_KEYS and not isinstance(v, (dict, list))
        }

    # 2. Check raw_data
    raw = record.get("raw_data")
    if isinstance(raw, dict) and raw:
        cleaned = {
            k: v for k, v in raw.items()
            if not k.startswith("_") and k.lower() not in INTERNAL_EXCLUDE_KEYS and not isinstance(v, (dict, list))
        }
        if cleaned:
            return cleaned

    # 3. Check data
    d = record.get("data")
    if isinstance(d, dict) and d:
        cleaned = {
            k: v for k, v in d.items()
            if not k.startswith("_") and k.lower() not in INTERNAL_EXCLUDE_KEYS and not isinstance(v, (dict, list))
        }
        if cleaned:
            return cleaned

    # 4. Fallback to direct keys on record, excluding all internal and meta fields
    return {
        k: v for k, v in record.items()
        if not k.startswith("_") and k.lower() not in INTERNAL_EXCLUDE_KEYS and not isinstance(v, (dict, list))
    }
