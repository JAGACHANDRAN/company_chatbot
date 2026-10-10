import os
import re
import json
from collections import Counter
from typing import List, Dict, Any, Optional
from ..config import (
    PRIVACY_MODE,
    OLLAMA_BASE_URL,
    OLLAMA_API_KEY,
    LLM_MODEL,
)
from .query_understanding import StructuredQuery, FollowupFilter
from ..utils.normalization import normalize_company_name, normalize_person_name, normalize_company
from .source_resolver import (
    get_record_sources,
    get_record_source_display,
    get_company_sources_summary
)

FINAL_ANSWER_SYSTEM_PROMPT = """You are a STRICT RESPONSE FORMATTER for retrieved company/contact data.

IMPORTANT:
- Do NOT change, summarize, rewrite, infer, or remove any retrieved information.
- Preserve the retrieved result in the same structure and order.
- The ONLY additional information you are allowed to add is the SOURCE FILE NAME.
- Do not expose database names, collection names, internal IDs, metadata, embeddings, search scores, or technical retrieval information.

SOURCE FILE RULE:

For every retrieved result, display the source file name at the very top.

Use exactly:

Source File: <actual source file name>

Then immediately display the retrieved result in the existing format.

Example:

Source File: Company Leadership Database - Sheet1.csv

Company Name: TVS Motor Company

Contact Person 1:
- Name: Ravi Kumar
- Designation: Quality Manager
- Contact Number 1: +91 XXXXX XXXXX
- Email 1: ravi@example.com
- City: Chennai
- State: Tamil Nadu

DO NOT change the existing result structure.

MULTIPLE SOURCE FILES:

If retrieved records come from different source files, preserve the association between the result and its source file.

Example:

Source File: Company Leadership Database - Sheet1.csv

Company Name: ABC Industries

Contact Person 1:
- Name: Ravi Kumar
- Designation: Quality Manager
- Contact Number 1: +91 XXXXX XXXXX
- Email 1: ravi@example.com
- City: Chennai
- State: Tamil Nadu


Source File: ACMEE 2025.xlsx

Company Name: ABC Industries

Contact Person 1:
- Name: Arun Kumar
- Designation: Quality Head
- Contact Number 1: Not Available
- Email 1: arun@example.com
- State: Tamil Nadu

IMPORTANT SOURCE RULES:

1. Use the exact source filename provided by the backend.
2. Never invent a source filename.
3. Never rename or shorten the source filename.
4. Never display the MongoDB collection name as the source.
5. Never display database names.
6. Never display internal dataset IDs.
7. Never display retrieval metadata.
8. Never display raw MongoDB objects.
9. Do not merge records from different source files if doing so would lose their source association.
10. If multiple records come from the same source file, show the source file name once at the beginning of that grouped result.
11. The source filename is the ONLY additional information to add.
12. Everything else must remain in the existing retrieved-result format.

FINAL RULE:

Preserve the existing retrieved result exactly as it is.

Only add:

Source File: <source filename>

at the top of the relevant result."""

NULL_INDICATORS = {
    "", "none", "null", "nan", "n/a", "na", "-", "--", "undefined",
    "not available", "not_available", "not publicly available", "."
}


def clean_val(v: Any) -> Optional[str]:
    """Returns trimmed string or None if empty / null placeholder."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in NULL_INDICATORS:
        return None
    return s


def is_valid_source_row(row_val: Any) -> Optional[str]:
    """Returns clean string row representation if it is a genuine row number, else None."""
    if row_val in (None, "", "None", "null", "NaN", "Not Available"):
        return None
    s = str(row_val).strip()
    if len(s) == 24 and all(c in "0123456789abcdefABCDEF" for c in s):
        return None
    return s


def extract_single_source_file(rec: Dict[str, Any]) -> Optional[str]:
    """
    Extracts genuine source file name from a record if provided.
    Adheres strictly to SOURCE RULES:
    - Uses exact source filename provided by backend.
    - Never displays internal database names (MongoDB Atlas) or collection names.
    """
    sf = rec.get("source_file") or rec.get("Source File") or rec.get("filename") or rec.get("file_name")
    if not sf:
        raw_s = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}
        sf = (
            raw_s.get("Source File")
            or raw_s.get("source_file")
            or raw_s.get("source_filename")
            or raw_s.get("Source_File")
            or raw_s.get("sourcefile")
            or raw_s.get("file_name")
            or raw_s.get("filename")
        )

    cv = clean_val(sf)
    if not cv:
        return None

    cv_clean = cv.strip()
    low = cv_clean.lower()
    if low in ("mongodb", "mongodb atlas", "dataset_records", "none", "not available", "null"):
        return None
    if cv_clean.startswith("MongoDB:"):
        return None

    return cv_clean


def is_empty_val(v: Any) -> bool:
    """Returns True if value is None, empty string, or standard null placeholder."""
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.lower() in NULL_INDICATORS


def get_contact_fields(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    SINGLE SOURCE OF TRUTH for all contact and entity fields.
    Checks candidate containers in strict order:
      top-level -> normalized_data{} -> data{} -> source_fields{}
    Collects every non-empty value, dedupes (case-insensitive, strip spaces).
    Returns dict:
      company: str
      contact_persons: List[str]
      designations: List[str]
      emails: List[str]
      phones: List[str]
      linkedin: List[str]
      address: str
      city: str
      state: str
      dataset_name: str
    """
    if not isinstance(record, dict):
        return {
            "company": "No data available",
            "contact_persons": [],
            "designations": [],
            "emails": [],
            "phones": [],
            "linkedin": [],
            "address": "No data available",
            "city": "No data available",
            "state": "No data available",
            "dataset_name": "No data available"
        }

    containers = [
        record,
        record.get("normalized_data") if isinstance(record.get("normalized_data"), dict) else {},
        record.get("data") if isinstance(record.get("data"), dict) else {},
        record.get("source_fields") if isinstance(record.get("source_fields"), dict) else {},
    ]

    def collect_values(candidate_keys: List[str], is_email: bool = False, is_phone: bool = False) -> List[str]:
        results = []
        seen = set()
        for c in containers:
            if not isinstance(c, dict):
                continue
            for k in candidate_keys:
                if k in c:
                    raw = c[k]
                    if is_empty_val(raw):
                        continue
                    parts = [str(x) for x in raw] if isinstance(raw, list) else [str(raw)]
                    for p in parts:
                        p_str = p.strip()
                        if is_empty_val(p_str):
                            continue
                        if is_email:
                            found = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", p_str)
                            if found:
                                for em in found:
                                    em_c = em.strip()
                                    if em_c.lower() not in seen and not is_empty_val(em_c):
                                        seen.add(em_c.lower())
                                        results.append(em_c)
                            elif "@" in p_str and "." in p_str:
                                em_c = p_str.strip()
                                if em_c.lower() not in seen and not is_empty_val(em_c):
                                    seen.add(em_c.lower())
                                    results.append(em_c)
                        elif is_phone:
                            sub_phones = re.split(r"[/,;]\s*", p_str)
                            for ph in sub_phones:
                                ph_c = ph.strip()
                                digits = re.sub(r"\D", "", ph_c)
                                if len(digits) >= 5 and digits not in seen and not is_empty_val(ph_c):
                                    seen.add(digits)
                                    results.append(ph_c)
                        else:
                            p_c = p_str.strip()
                            if p_c.lower() not in seen and not is_empty_val(p_c):
                                seen.add(p_c.lower())
                                results.append(p_c)
        return results

    # 1. Company Name
    comp_cand = ["company", "Company Name", "company_name", "Company", "organization", "firm", "business name", "customer"]
    comp_list = collect_values(comp_cand)
    company_val = comp_list[0] if comp_list else "No data available"

    # 2. Contact Person
    person_cand = ["person", "Person Name", "person_name", "Contact Person", "contact_person", "Name", "name", "employee_name", "full name", "client name"]
    persons = collect_values(person_cand)

    # 3. Designation
    desig_cand = ["designation", "Designation", "role", "Role", "job title", "title", "Title", "position"]
    designations = collect_values(desig_cand)

    # 4. Emails
    email_cand = ["email", "Email", "email_2", "Email 2", "Email 1", "email_1", "e-mail", "E-mail", "Mail", "mail", "Email Address"]
    emails = collect_values(email_cand, is_email=True)

    # 5. Phones
    phone_cand = ["phone", "Contact Number", "contact_number", "phone_2", "Phone 2", "Phone", "Phone 1", "mobile", "Mobile", "Mobile No.", "tel", "telephone", "landline", "contact_no", "cell"]
    phones = collect_values(phone_cand, is_phone=True)

    # 6. LinkedIn
    linkedin_cand = ["linkedin", "LinkedIn", "LinkedIn URL", "linkedin_url", "LinkedIn Profile", "linkedin_profile", "linkedin_link"]
    linkedins = collect_values(linkedin_cand)

    # 7. Location (Address, City, State)
    addr_val = None
    city_val = None
    state_val = None

    for c in containers:
        if not isinstance(c, dict):
            continue
        if not city_val:
            for k in ["City", "city", "town", "Town"]:
                if k in c and not is_empty_val(c[k]):
                    city_val = str(c[k]).strip()
                    break
        if not state_val:
            for k in ["State", "state", "province", "Province"]:
                if k in c and not is_empty_val(c[k]):
                    state_val = str(c[k]).strip()
                    break
        if not addr_val:
            for k in ["Address", "address", "Location", "location", "street", "Street"]:
                if k in c and not is_empty_val(c[k]):
                    addr_val = str(c[k]).strip()
                    break

    # Parse address string if city / state are missing
    if addr_val and (not city_val or not state_val):
        addr_low = addr_val.lower()
        known_cities = [
            "chennai", "mumbai", "bangalore", "bengaluru", "coimbatore",
            "hyderabad", "pune", "delhi", "kolkata", "hosur", "gurgaon",
            "noida", "faridabad", "ahmedabad", "madurai", "salem", "trichy",
            "doddaballapur", "kanchipuram", "aurangabad", "gangapur", "pithampur"
        ]
        known_states = [
            "tamil nadu", "andhra pradesh", "karnataka", "maharashtra",
            "kerala", "gujarat", "haryana", "uttar pradesh", "telangana", "madhya pradesh"
        ]
        if not city_val:
            for c_name in known_cities:
                if re.search(rf"\b{re.escape(c_name)}\b", addr_low):
                    city_val = c_name.title()
                    break
        if not state_val:
            for s_name in known_states:
                if re.search(rf"\b{re.escape(s_name)}\b", addr_low):
                    state_val = s_name.title()
                    break

    dataset_name = get_record_source_display(record)

    return {
        "company": company_val,
        "contact_persons": persons,
        "designations": designations,
        "emails": emails,
        "phones": phones,
        "linkedin": linkedins,
        "address": addr_val or "No data available",
        "city": city_val or "No data available",
        "state": state_val or "No data available",
        "dataset_name": dataset_name
    }


def extract_company_name(rec: Dict[str, Any]) -> str:
    """Extracts company name using get_contact_fields."""
    return get_contact_fields(rec)["company"]


def extract_contact_numbers(rec: Dict[str, Any]) -> List[str]:
    """Extracts contact numbers using get_contact_fields."""
    return get_contact_fields(rec)["phones"]


def extract_emails(rec: Dict[str, Any]) -> List[str]:
    """Extracts emails using get_contact_fields."""
    return get_contact_fields(rec)["emails"]


def extract_location(rec: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extracts location dict using get_contact_fields."""
    f = get_contact_fields(rec)
    return {
        "address": f["address"] if f["address"] != "No data available" else None,
        "city": f["city"] if f["city"] != "No data available" else None,
        "state": f["state"] if f["state"] != "No data available" else None,
    }


def extract_person_info(rec: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extracts person name and designation using get_contact_fields."""
    f = get_contact_fields(rec)
    return {
        "name": f["contact_persons"][0] if f["contact_persons"] else None,
        "designation": f["designations"][0] if f["designations"] else None
    }


def extract_linkedin(rec: Dict[str, Any]) -> Optional[str]:
    """Extracts LinkedIn URL using get_contact_fields."""
    f = get_contact_fields(rec)
    return f["linkedin"][0] if f["linkedin"] else None


def format_location_lines(loc: Dict[str, Optional[str]], prefix: str = "- ") -> List[str]:
    """
    Implements the STRICT Location Display Rule:
    - If Address, City, and State are all available -> display all three.
    - If only Address is available -> display only Address.
    - If only City is available -> display only City.
    - If only State is available -> display only State.
    - If Address and City are available -> display Address and City only.
    - If City and State are available -> display City and State only.
    - If Address and State are available -> display Address and State only.
    - If none of the location information is available -> display: Location: Not Available
    DO NOT display individual fields as 'Not Available' when another location field is available.
    """
    has_addr = bool(loc.get("address"))
    has_city = bool(loc.get("city"))
    has_state = bool(loc.get("state"))

    if not has_addr and not has_city and not has_state:
        return [f"{prefix}Location: Not Available"]

    lines = []
    if has_addr:
        lines.append(f"{prefix}Address: {loc['address']}")
    if has_city:
        lines.append(f"{prefix}City: {loc['city']}")
    if has_state:
        lines.append(f"{prefix}State: {loc['state']}")

    return lines


def format_field_specific_answer(
    records: List[Dict[str, Any]],
    structured_query: StructuredQuery
) -> str:
    """
    Renders a clean, field-specific answer with exact matching header:
    'Found {N} companies matching '{company}'. {X} have an {field}, {Y} do not.'
    Displays only Company Name + requested fields (with 'Not Available' for missing values).
    """
    if not records:
        return "No data found"

    req_fields = structured_query.requested_fields or []
    missing_filter = structured_query.missing_filter
    comp_target = ", ".join(structured_query.companies) if structured_query.companies else "the query"
    total_docs = len(records)

    # Determine availability metrics
    primary_field = req_fields[0] if req_fields else (missing_filter or "contact details")
    
    def has_field_val(rec: Dict[str, Any], f: str) -> bool:
        if f == "email":
            return bool(extract_emails(rec))
        elif f == "phone":
            return bool(extract_contact_numbers(rec))
        elif f == "linkedin":
            return bool(extract_linkedin(rec))
        elif f == "city":
            return bool(extract_location(rec).get("city"))
        elif f == "state":
            return bool(extract_location(rec).get("state"))
        elif f == "address":
            return bool(extract_location(rec).get("address"))
        elif f == "designation":
            return bool(extract_person_info(rec).get("designation"))
        elif f == "person":
            return bool(extract_person_info(rec).get("name"))
        return False

    with_field_count = sum(1 for r in records if has_field_val(r, primary_field))
    without_field_count = total_docs - with_field_count

    # Build Header
    field_label = primary_field.title() if primary_field != "linkedin" else "LinkedIn profile"
    article = "an" if primary_field.lower().startswith(("e", "a", "i", "o")) else "a"
    if primary_field == "phone":
        field_label_phrase = "a contact number"
    elif primary_field == "email":
        field_label_phrase = "an email"
    elif primary_field == "linkedin":
        field_label_phrase = "a LinkedIn profile"
    else:
        field_label_phrase = f"{article} {primary_field}"

    if structured_query.is_count_query:
        return f"Found {total_docs} companies matching '{comp_target}'. {with_field_count} have {field_label_phrase}, {without_field_count} do not."

    if missing_filter:
        header = f"Found {without_field_count} companies matching '{comp_target}' with no {missing_filter}."
        target_records = [r for r in records if not has_field_val(r, missing_filter)]
        if not target_records:
            return f"All {total_docs} companies matching '{comp_target}' have {missing_filter} available."
    else:
        header = f"Found {total_docs} companies matching '{comp_target}'. {with_field_count} have {field_label_phrase}, {without_field_count} do not."
        target_records = records

    lines = [header, ""]

    # Format record cards with ONLY requested fields
    for idx, rec in enumerate(target_records, 1):
        c_name = extract_company_name(rec)
        s_file = extract_single_source_file(rec)
        
        lines.append(f"Source File: {s_file}")
        lines.append(f"Company Name: {c_name}")

        p_info = extract_person_info(rec)
        emails = extract_emails(rec)
        phones = extract_contact_numbers(rec)
        loc = extract_location(rec)
        linkedin = extract_linkedin(rec)

        if "person" in req_fields:
            lines.append(f"- Person Name: {p_info['name'] if p_info['name'] else 'Not Available'}")
        if "designation" in req_fields:
            lines.append(f"- Designation: {p_info['designation'] if p_info['designation'] else 'Not Available'}")
        if "email" in req_fields:
            if emails:
                for e_i, em in enumerate(emails, 1):
                    lines.append(f"- Email {e_i}: {em}")
            else:
                lines.append("- Email 1: Not Available")
        if "phone" in req_fields:
            if phones:
                for p_i, ph in enumerate(phones, 1):
                    lines.append(f"- Contact Number {p_i}: {ph}")
            else:
                lines.append("- Contact Number 1: Not Available")
        if "city" in req_fields:
            lines.append(f"- City: {loc['city'] if loc['city'] else 'Not Available'}")
        if "state" in req_fields:
            lines.append(f"- State: {loc['state'] if loc['state'] else 'Not Available'}")
        if "address" in req_fields:
            lines.append(f"- Address: {loc['address'] if loc['address'] else 'Not Available'}")
        if "linkedin" in req_fields:
            lines.append(f"- LinkedIn: {linkedin if linkedin else 'Not Available'}")

        lines.append("")

    return "\n".join(lines).strip()


def extract_single_source_file(rec: Dict[str, Any]) -> str:
    """
    Extracts genuine source file name(s) from a record.
    Adheres strictly to SOURCE RULES:
    - Merged records show all origin sources.
    - If no source is stored, returns 'Not available'.
    """
    return get_record_source_display(rec)


def format_followup_answer(
    records: List[Dict[str, Any]],
    total_prev_count: int,
    followup_filter: FollowupFilter,
    company_name: Optional[str] = None
) -> str:
    """
    Renders deterministic follow-up availability filter results with exact header:
    '{K} of {N} previous {company} results have an {field}. {M} excluded.'
    If K == 0:
    '0 of {N} previous {company} results have an {field}. All {N} records were excluded.'
    """
    K = len(records)
    N = total_prev_count
    M = N - K
    comp_label = f" {company_name}" if company_name else ""

    # Build field phrase from conditions / location / fields
    cond_phrases = []
    for c in followup_filter.conditions:
        f = c["field"]
        req = c["required"]
        if f == "email":
            cond_phrases.append("an email" if req else "no email")
        elif f == "phone":
            cond_phrases.append("a contact number" if req else "no contact number")
        elif f == "linkedin":
            cond_phrases.append("a LinkedIn profile" if req else "no LinkedIn profile")
        elif f == "address":
            cond_phrases.append("an address" if req else "no address")
        elif f == "person":
            cond_phrases.append("a contact person" if req else "no contact person")
        elif f == "designation":
            cond_phrases.append("a designation" if req else "no designation")

    if followup_filter.location_filter:
        cond_phrases.append(f"located in {followup_filter.location_filter}")

    op_str = f" {followup_filter.operator.lower()} "
    field_phrase = op_str.join(cond_phrases) if cond_phrases else "the requested criteria"

    if K == 0:
        return f"0 of {N} previous{comp_label} results have {field_phrase}. All {N} records were excluded."

    if M == 0:
        header = f"All {K} of {N} previous{comp_label} results have {field_phrase}."
    else:
        header = f"{K} of {N} previous{comp_label} results have {field_phrase}. {M} excluded."

    if followup_filter.is_count_query:
        return header

    lines = [header, ""]

    # Render filtered records
    for idx, rec in enumerate(records, 1):
        c_name = extract_company_name(rec)
        s_file = get_record_source_display(rec)
        lines.append(f"Source File: {s_file}")
        lines.append(f"Company Name: {c_name}")

        p_info = extract_person_info(rec)
        emails = extract_emails(rec)
        phones = extract_contact_numbers(rec)
        loc = extract_location(rec)
        linkedin = extract_linkedin(rec)

        lines.append(f"Contact Person 1:")
        lines.append(f"- Name: {p_info['name'] if p_info['name'] else 'Not Available'}")
        lines.append(f"- Designation: {p_info['designation'] if p_info['designation'] else 'Not Available'}")
        lines.append(f"- LinkedIn: {linkedin if linkedin else 'Not Available'}")

        if phones:
            for p_i, ph in enumerate(phones, 1):
                lines.append(f"- Contact Number {p_i}: {ph}")
        else:
            lines.append("- Contact Number 1: Not Available")

        if emails:
            for e_i, em in enumerate(emails, 1):
                lines.append(f"- Email {e_i}: {em}")
        else:
            lines.append("- Email 1: Not Available")

        loc_lines = format_location_lines(loc, prefix="- ")
        lines.extend(loc_lines)
        lines.append("")

    return "\n".join(lines).strip()


def group_and_deduplicate_records(
    records: List[Dict[str, Any]],
    structured_query: Optional[StructuredQuery] = None
) -> List[Dict[str, Any]]:
    """
    Groups and deduplicates records:
    1. Extracts fields using get_contact_fields(rec).
    2. Filters records by structured_query (must_have/must_not_have emails, phones, linkedin, etc.).
    3. Identifies exact duplicates (all field values match: company, location, person, designation, emails, phones, linkedin, dataset) and removes them.
    4. Groups records having the SAME company name AND the EXACT SAME location (address + city + state) AND same dataset_name into a single company group with multiple contact persons.
    5. Records with different company names OR different locations remain separate company entries.
    """
    if not records:
        return []

    seen_exact_signatures = set()
    grouped_companies: List[Dict[str, Any]] = []
    group_lookup: Dict[str, Dict[str, Any]] = {}

    for rec in records:
        fields = get_contact_fields(rec)
        c_name = fields["company"]
        rec_source = fields["dataset_name"]
        p_name = ", ".join(fields["contact_persons"]) if fields["contact_persons"] else "No data available"
        p_desig = ", ".join(fields["designations"]) if fields["designations"] else "No data available"
        p_linkedin = ", ".join(fields["linkedin"]) if fields["linkedin"] else "No data available"
        p_nums = fields["phones"]
        p_emails = fields["emails"]
        addr = fields["address"]
        city = fields["city"]
        state = fields["state"]

        # Apply query-level contact filters if specified
        if structured_query:
            if structured_query.email_required is True and not p_emails:
                continue
            if structured_query.email_required is False and p_emails:
                continue
            if structured_query.phone_required is True and not p_nums:
                continue
            if structured_query.phone_required is False and p_nums:
                continue
            if structured_query.linkedin_required is True and not fields["linkedin"]:
                continue
            if structured_query.linkedin_required is False and fields["linkedin"]:
                continue

        # Exact duplicate check (include _id when available so distinct DB docs are never dropped)
        rec_id = str(rec.get("_id") or "")
        exact_sig = (
            rec_id if rec_id else (
                c_name.lower().strip(),
                addr.lower().strip(),
                city.lower().strip(),
                state.lower().strip(),
                p_name.lower().strip(),
                p_desig.lower().strip(),
                p_linkedin.lower().strip(),
                ", ".join(sorted(p_emails)),
                ", ".join(sorted(re.sub(r'\D', '', n) for n in p_nums)),
                rec_source.lower().strip()
            )
        )
        if exact_sig in seen_exact_signatures:
            continue
        seen_exact_signatures.add(exact_sig)

        # Company + Location group key (same company name AND exact same location)
        group_key = f"{c_name.lower().strip()}::{addr.lower().strip()}::{city.lower().strip()}::{state.lower().strip()}::{rec_source.lower().strip()}"

        contact_entry = {
            "name": p_name,
            "designation": p_desig,
            "linkedin": p_linkedin,
            "phones": p_nums,
            "emails": p_emails,
            "address": addr if addr != "No data available" else None,
            "city": city if city != "No data available" else None,
            "state": state if state != "No data available" else None,
        }

        # If both contacts have no person name and no contact info, keep them as separate company blocks
        has_real_contact = (p_name != "No data available" and p_name != "Not Available") or bool(p_nums) or bool(p_emails)
        if group_key in group_lookup and has_real_contact:
            group_lookup[group_key]["contacts"].append(contact_entry)
        else:
            comp_group = {
                "company": c_name,
                "source_file": rec_source,
                "dataset_name": rec_source,
                "address": addr,
                "city": city,
                "state": state,
                "contacts": [contact_entry]
            }
            if has_real_contact:
                group_lookup[group_key] = comp_group
            grouped_companies.append(comp_group)

    return grouped_companies


def report_database_duplicates(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bug A Step 3:
    Separately reports how many records have an identical (norm_company, contact person, email, phone)
    in the database, so developers can see whether the DB itself holds duplicates.
    Does NOT delete anything; just reports.
    """
    sig_counts = Counter()
    for rec in records:
        f = get_contact_fields(rec)
        norm_c = normalize_company(f["company"])
        p_name = (f["contact_persons"][0] if f["contact_persons"] else "").strip().lower()
        e_mail = (f["emails"][0] if f["emails"] else "").strip().lower()
        p_phone = re.sub(r"\D", "", f["phones"][0]) if f["phones"] else ""
        sig = (norm_c, p_name, e_mail, p_phone)
        sig_counts[sig] += 1

    duplicate_groups = {str(k): count for k, count in sig_counts.items() if count > 1}
    total_dup_records = sum(count for count in sig_counts.values() if count > 1)
    return {
        "total_records_checked": len(records),
        "duplicate_groups_count": len(duplicate_groups),
        "total_records_in_duplicate_groups": total_dup_records,
        "duplicate_signatures": duplicate_groups
    }


def format_strict_company_records(
    records: List[Dict[str, Any]],
    structured_query: Optional[StructuredQuery] = None
) -> str:
    """
    STRICT RESPONSE FORMATTER for retrieved company/contact data.
    - Formats every unique document (by str(_id)) into its own card block so that:
      header count == cards shown == raw distinct count == export count.
    - Eliminates any later deduplication in display code that hides rows silently.
    """
    if not records:
        return "No data found"

    # If user asked for field-only projection ('alone', 'only', 'just') with specific fields, counts, or missing fields:
    has_specific_field_projection = bool(
        structured_query and structured_query.requested_fields and not (
            structured_query.email_required is True or structured_query.phone_required is True or structured_query.linkedin_required is True
        )
    )
    should_use_field_layout = bool(
        structured_query and (
            has_specific_field_projection
            or structured_query.is_count_query
            or bool(structured_query.missing_filter)
        )
    )
    if should_use_field_layout:
        return format_field_specific_answer(records, structured_query)

    # Deduplicate strictly by str(_id)
    seen_ids = set()
    deduped_records = []
    for r in records:
        rid = str(r.get("_id") or id(r))
        if rid not in seen_ids:
            seen_ids.add(rid)
            deduped_records.append(r)

    if not deduped_records:
        return "No data found"

    formatted_entries = []

    for rec in deduped_records:
        f = get_contact_fields(rec)
        c_name = f["company"]
        rec_source = f["dataset_name"]
        p_name = f["contact_persons"][0] if f["contact_persons"] else "No data available"
        p_desig = f["designations"][0] if f["designations"] else "No data available"
        p_linkedin = f["linkedin"][0] if f["linkedin"] else "No data available"
        phones = f["phones"]
        emails = f["emails"]

        entry_lines = []
        entry_lines.append(f"Source File: {rec_source}")
        entry_lines.append(f"Company Name: {c_name}")
        entry_lines.append(f"Contact Person 1:")
        entry_lines.append(f"- Name: {p_name}")
        entry_lines.append(f"- Designation: {p_desig}")
        entry_lines.append(f"- LinkedIn: {p_linkedin}")

        if phones:
            for p_i, ph in enumerate(phones, 1):
                label = f"- Contact Number {p_i}:" if len(phones) > 1 else "- Contact Number 1:"
                entry_lines.append(f"{label} {ph}")
        else:
            entry_lines.append("- Contact Number 1: No data available")

        if emails:
            for e_i, em in enumerate(emails, 1):
                label = f"- Email {e_i}:" if len(emails) > 1 else "- Email 1:"
                entry_lines.append(f"{label} {em}")
        else:
            entry_lines.append("- Email 1: No data available")

        loc_dict = {
            "address": f["address"] if f["address"] != "No data available" else None,
            "city": f["city"] if f["city"] != "No data available" else None,
            "state": f["state"] if f["state"] != "No data available" else None,
        }
        loc_lines = format_location_lines(loc_dict, prefix="- ")
        entry_lines.extend(loc_lines)

        formatted_entries.append("\n".join(entry_lines))

    return "\n\n---\n\n".join(formatted_entries).strip()


def generate_no_data_message(
    user_query: str,
    structured_query: Optional[StructuredQuery] = None,
    suggestions: Optional[List[str]] = None
) -> str:
    """
    Generates professional, clear, zero-hallucination no-data explanations
    explaining that files in the database were searched and the entity was not found.
    """
    if not structured_query or not (structured_query.companies or structured_query.people or structured_query.designation or structured_query.location or structured_query.city or structured_query.state):
        clean_q = user_query.strip()
        msg = f"I searched across all uploaded files in the database, but no records or contact details regarding '{clean_q}' were found."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        return msg

    target_entity = None
    if structured_query.companies:
        target_entity = ", ".join(structured_query.companies)
    elif structured_query.people:
        target_entity = ", ".join(structured_query.people)
    elif structured_query.designation:
        target_entity = structured_query.designation
    elif structured_query.city:
        target_entity = f"companies in {structured_query.city}"
    elif structured_query.state:
        target_entity = f"companies in {structured_query.state}"
    elif structured_query.location:
        target_entity = f"companies in {structured_query.location}"
    else:
        target_entity = user_query.strip()

    criteria = []
    if structured_query.designation and structured_query.companies:
        criteria.append(f"with designation '{structured_query.designation}'")
    if structured_query.city and not target_entity.startswith("companies in"):
        criteria.append(f"in {structured_query.city}")
    elif structured_query.state and not target_entity.startswith("companies in"):
        criteria.append(f"in {structured_query.state}")
    elif structured_query.location and not target_entity.startswith("companies in"):
        criteria.append(f"in {structured_query.location}")

    if structured_query.email_required is True:
        criteria.append("having an available email address")
    elif structured_query.email_required is False:
        criteria.append("without an email address")

    if structured_query.phone_required is True:
        criteria.append("having contact numbers")
    elif structured_query.phone_required is False:
        criteria.append("without contact numbers")

    if structured_query.linkedin_required is True:
        criteria.append("having a LinkedIn profile")
    elif structured_query.linkedin_required is False:
        criteria.append("without a LinkedIn profile")

    crit_str = f" ({', '.join(criteria)})" if criteria else ""
    msg = f"I searched across all uploaded files in the database, but no records or contact details regarding '{target_entity}'{crit_str} were found."
    if suggestions:
        msg += f" Did you mean: {', '.join(suggestions)}?"
    return msg


def deterministic_synthesize(
    records: List[Dict[str, Any]],
    structured_query: Optional[StructuredQuery] = None
) -> str:
    """
    Deterministic fallback synthesizer formatting retrieved company/contact records
    strictly preserving source attribution, hyperlinks, sequential numbering, and
    hiding internal database fields without calling any LLM.
    """
    if not records:
        return "No data found"
    return format_strict_company_records(records, structured_query=structured_query)


def generate_deterministic_answer(
    user_query: str,
    structured_query: StructuredQuery,
    records: List[Dict[str, Any]]
) -> str:
    """
    Deterministic synthesis enforcing the STRICT RESPONSE FORMATTER specification.
    """
    if not records:
        return "No data found"
    res = deterministic_synthesize(records, structured_query=structured_query)
    if res == "No data found":
        return generate_no_data_message(user_query, structured_query)
    return res


def generate_response(
    query: str,
    records: List[Dict[str, Any]],
    structured_query: Optional[StructuredQuery] = None,
    **kwargs
) -> str:
    """
    Unified response generation entry point.
    When PRIVACY_MODE is true: ALWAYS uses the deterministic fallback synthesizer
    and NEVER calls llm.py or any external model.
    """
    if not records:
        return generate_no_data_message(query, structured_query)
    res = deterministic_synthesize(records, structured_query=structured_query)
    if res == "No data found":
        return generate_no_data_message(query, structured_query)
    return res


async def generate_final_answer(
    user_query: str,
    structured_query: StructuredQuery,
    records: List[Dict[str, Any]]
) -> str:
    """
    Generates the final strictly-formatted response for the user's query.
    Guarantees strict compliance with security rules, source file preservation, and display structure.
    When PRIVACY_MODE is true, always uses deterministic synthesis and never calls llm.py.
    """
    if not records:
        return generate_no_data_message(user_query, structured_query)

    res = deterministic_synthesize(records, structured_query=structured_query)
    if res == "No data found":
        return generate_no_data_message(user_query, structured_query)

    return res


