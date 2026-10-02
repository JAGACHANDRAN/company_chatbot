import re
from typing import List, Dict, Optional, Set

# Maps semantic concept to list of potential column names across datasets
CONCEPT_COLUMNS: Dict[str, List[str]] = {
    "location": [
        "State", "City", "Location", "Address", "Company Address",
        "state", "city", "location", "address", "company_address",
        "Territory", "territory", "Region", "region", "Place", "place",
        "District", "district", "Town", "town", "Area", "area", "PIN", "pin", "pincode"
    ],
    "company": [
        "Company Name", "Company", "Organization", "Organisation", "Firm", "Client",
        "Vendor", "Business Name", "Group", "company_name", "company", "organization",
        "organisation", "firm", "client", "vendor", "business_name", "group"
    ],
    "person": [
        "Person Name", "Contact Person", "Employee Name", "Name", "Full Name",
        "Contact", "Executive", "Owner", "person_name", "contact_person",
        "employee_name", "name", "full_name", "contact", "executive", "owner"
    ],
    "designation": [
        "Designation", "Job Title", "Role", "Position", "Title",
        "designation", "job_title", "role", "position", "title"
    ],
    "email": [
        "Email", "Email 1", "Email 2", "Email ID", "Personal Email ID",
        "E-mail", "Email Address", "email", "email_1", "email_2", "email_id",
        "personal_email_id", "e_mail", "email_address"
    ],
    "phone": [
        "Mobile No.", "Mobile No", "Mobile", "Contact Number", "Phone",
        "Phone Number", "Landline / Telephone", "Landline / Other No.",
        "Telephone 1", "Telephone 2", "Telephone", "mobile_no", "mobile",
        "contact_number", "phone", "phone_number", "landline_telephone",
        "landline", "telephone"
    ],
    "linkedin": [
        "LinkedIn", "LinkedIn URL", "LinkedIn Profile", "Profile URL",
        "linkedin", "linkedin_url", "linkedin_profile", "profile_url"
    ],
}

# Suffixes stripped for company name normalization
COMPANY_STRIP_SUFFIX_PATTERN = re.compile(
    r"\s+\b(ltd|limited|pvt|private|pvt\s+ltd|private\s+limited|corp|corporation|inc|llc|group|auto|technologies|tech|solutions|industries|enterprises?)\b\.?$",
    re.IGNORECASE
)


def normalize_company_search_terms(raw_value: str) -> List[str]:
    """
    Produces normalized company name variants for robust matching.
    e.g. 'Tata Motors Ltd' -> ['Tata Motors Ltd', 'Tata Motors']
         'JBM Group' -> ['JBM Group', 'JBM']
         'JBM' -> ['JBM']
    """
    clean = raw_value.strip()
    if not clean:
        return []
    terms = [clean]
    stripped = COMPANY_STRIP_SUFFIX_PATTERN.sub("", clean).strip()
    if stripped and stripped.lower() != clean.lower() and len(stripped) >= 2:
        terms.append(stripped)
    return terms


def get_columns_for_concept(concept: str, available_fields: List[str]) -> List[str]:
    """
    Dynamically finds ALL matching columns in available_fields for a semantic concept.
    e.g. concept='location' and fields=['Company Name', 'State', 'City', 'Address']
    returns ['State', 'City', 'Address'].
    """
    if not available_fields or not concept:
        return []

    concept_key = concept.lower().strip()
    candidate_names = CONCEPT_COLUMNS.get(concept_key, [concept_key])
    candidate_norms = {re.sub(r"[^a-z0-9]", "", c.lower()) for c in candidate_names}

    matched: List[str] = []
    for f in available_fields:
        f_norm = re.sub(r"[^a-z0-9]", "", f.lower())
        # Exact normalized match
        if f_norm in candidate_norms:
            matched.append(f)
            continue
        # Substring keyword match for longer words
        for c in candidate_names:
            c_norm = re.sub(r"[^a-z0-9]", "", c.lower())
            if len(c_norm) >= 4 and (c_norm == f_norm or c_norm in f_norm):
                matched.append(f)
                break

    return list(dict.fromkeys(matched))


def resolve_columns_for_condition(
    concept: Optional[str],
    field: Optional[str],
    available_fields: List[str]
) -> List[str]:
    """
    Resolves a condition's concept or field name to a list of actual columns in available_fields.
    """
    if not available_fields:
        return []

    # 1. If concept is provided and recognized, use concept mapping
    if concept:
        cols = get_columns_for_concept(concept, available_fields)
        if cols:
            return cols

    # 2. If field is provided, check if field itself is a concept name (e.g. 'location')
    if field:
        field_lower = field.lower().strip()
        if field_lower in CONCEPT_COLUMNS:
            cols = get_columns_for_concept(field_lower, available_fields)
            if cols:
                return cols

        # Check exact field match in dataset
        if field in available_fields:
            return [field]

        # Check normalized match in dataset
        field_norm = re.sub(r"[^a-z0-9]", "", field_lower)
        for f in available_fields:
            if re.sub(r"[^a-z0-9]", "", f.lower()) == field_norm:
                return [f]

        # Check if field matches any concept synonyms
        for c_key in CONCEPT_COLUMNS:
            if field_norm in {re.sub(r"[^a-z0-9]", "", c.lower()) for c in CONCEPT_COLUMNS[c_key]}:
                cols = get_columns_for_concept(c_key, available_fields)
                if cols:
                    return cols

    return []
