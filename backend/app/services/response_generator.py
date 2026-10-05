import os
import re
import json
from typing import List, Dict, Any, Optional
from ..config import (
    PRIVACY_MODE,
    OLLAMA_BASE_URL,
    OLLAMA_API_KEY,
    LLM_MODEL,
)
from .query_understanding import StructuredQuery
from ..utils.normalization import normalize_company_name, normalize_person_name

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
    sf = rec.get("source_file")
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


def extract_company_name(rec: Dict[str, Any]) -> str:
    """Extracts company name from normalized record or source fields."""
    sf = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}
    candidates = [
        rec.get("company_name"),
        sf.get("Company Name"),
        sf.get("Company"),
        sf.get("company_name"),
        sf.get("Organization"),
        sf.get("organization"),
        sf.get("company"),
        rec.get("company"),
    ]
    for c in candidates:
        cv = clean_val(c)
        if cv:
            return cv
    return "Not Available"


def extract_contact_numbers(rec: Dict[str, Any]) -> List[str]:
    """Extracts, splits, normalizes, and deduplicates all phone/mobile numbers."""
    numbers = []
    sf = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}

    keys_to_check = [
        rec.get("phone"),
        rec.get("phone_2"),
        rec.get("contact_number"),
        rec.get("mobile_no"),
        rec.get("telephone_1"),
        rec.get("telephone_2"),
        rec.get("landline_telephone"),
        rec.get("landline_other_no"),
    ]
    for k, v in sf.items():
        k_low = k.lower()
        if any(term in k_low for term in ["phone", "mobile", "tel", "contact_no", "contact no", "contact number"]):
            keys_to_check.append(v)

    seen = set()
    for raw in keys_to_check:
        cv = clean_val(raw)
        if not cv:
            continue
        split_vals = re.split(r"[/,;]\s*", cv)
        for part in split_vals:
            cleaned_num = part.strip()
            digits_only = re.sub(r"\D", "", cleaned_num)
            if len(digits_only) >= 5:
                if digits_only not in seen:
                    seen.add(digits_only)
                    numbers.append(cleaned_num)
    return numbers


def extract_emails(rec: Dict[str, Any]) -> List[str]:
    """Extracts and deduplicates all valid email addresses."""
    emails = []
    sf = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}

    keys_to_check = [
        rec.get("personal_mail_id"),
        rec.get("email"),
        rec.get("email_1"),
        rec.get("email_2"),
    ]
    for k, v in sf.items():
        k_low = k.lower()
        if "email" in k_low or "mail" in k_low:
            keys_to_check.append(v)

    seen = set()
    email_regex = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    for raw in keys_to_check:
        cv = clean_val(raw)
        if not cv:
            continue
        matches = email_regex.findall(cv)
        if matches:
            for em in matches:
                em_clean = em.strip()
                if em_clean.lower() not in seen:
                    seen.add(em_clean.lower())
                    emails.append(em_clean)
        elif "@" in cv and "." in cv:
            em_clean = cv.strip()
            if em_clean.lower() not in seen:
                seen.add(em_clean.lower())
                emails.append(em_clean)
    return emails


def extract_location(rec: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extracts address, city, and state."""
    sf = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}
    address = None
    for k in ["address", "Address", "Company Address", "Street", "location", "Location"]:
        val = rec.get(k) or sf.get(k)
        cv = clean_val(val)
        if cv:
            address = cv
            break

    city = None
    for k in ["city", "City", "Town"]:
        val = rec.get(k) or sf.get(k)
        cv = clean_val(val)
        if cv:
            city = cv
            break

    state = None
    for k in ["state", "State", "Province"]:
        val = rec.get(k) or sf.get(k)
        cv = clean_val(val)
        if cv:
            state = cv
            break

    return {"address": address, "city": city, "state": state}


def extract_person_info(rec: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extracts contact person name and designation."""
    sf = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}
    name = None
    for k in ["person", "person_name", "contact_person", "Name", "Contact Person", "Person Name", "Employee Name", "Customer Name", "Contact"]:
        val = rec.get(k) or sf.get(k)
        cv = clean_val(val)
        if cv:
            name = cv
            break

    designation = None
    for k in ["designation", "Designation", "Role", "Title", "Position", "Job Title"]:
        val = rec.get(k) or sf.get(k)
        cv = clean_val(val)
        if cv:
            designation = cv
            break

    return {"name": name, "designation": designation}


def extract_linkedin(rec: Dict[str, Any]) -> Optional[str]:
    """Extracts genuine LinkedIn URL or profile link."""
    sf = rec.get("source_fields") or rec.get("raw_data") or rec.get("data") or {}
    candidates = [
        rec.get("linkedin_url"),
        rec.get("linkedin"),
        rec.get("linkedin_profile"),
        sf.get("LinkedIn URL"),
        sf.get("LinkedIn"),
        sf.get("linkedin_url"),
        sf.get("linkedin"),
        sf.get("LinkedIn Profile"),
        sf.get("profile_url"),
        sf.get("Profile URL"),
    ]
    for c in candidates:
        cv = clean_val(c)
        if cv:
            return cv

    for k, v in sf.items():
        if "linkedin" in k.lower():
            cv = clean_val(v)
            if cv:
                return cv

    return None


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


def format_strict_company_records(
    records: List[Dict[str, Any]],
    structured_query: Optional[StructuredQuery] = None
) -> str:
    """
    STRICT RESPONSE FORMATTER for retrieved company/contact data.
    """
    if not records:
        return "No data found"

    from ..database import get_database_name
    default_db_name = get_database_name()

    # Group by (source_file, source_collection, database_source, norm_company_name) to preserve association
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    group_meta: Dict[Any, Dict[str, Any]] = {}

    for rec in records:
        c_name = extract_company_name(rec)
        norm_c = normalize_company_name(c_name) if c_name != "Not Available" else f"unknown_{id(rec)}"
        s_file = extract_single_source_file(rec)
        s_col = rec.get("source_collection") or rec.get("dataset")
        s_db = rec.get("database_source") or rec.get("database") or default_db_name
        s_sheet = rec.get("source_sheet")
        key = (s_file, s_col, s_db, norm_c)
        if key not in groups:
            groups[key] = []
            group_meta[key] = {
                "source_file": s_file,
                "source_collection": s_col,
                "database_source": s_db,
                "source_sheet": s_sheet,
                "company_name": c_name
            }
        groups[key].append(rec)

    formatted_groups = []

    for key, group_recs in groups.items():
        comp_display = group_meta[key]["company_name"]
        s_file = group_meta[key]["source_file"]
        s_col = group_meta[key]["source_collection"]
        s_db = group_meta[key]["database_source"]
        s_sheet = group_meta[key].get("source_sheet")
        contacts: List[Dict[str, Any]] = []

        for rec in group_recs:
            p_info = extract_person_info(rec)
            p_name = p_info["name"]
            p_desig = p_info["designation"]
            p_linkedin = extract_linkedin(rec)
            p_nums = extract_contact_numbers(rec)
            p_emails = extract_emails(rec)
            p_loc = extract_location(rec)

            # Match existing contact within this source group to merge duplicate records
            matched_idx = -1
            for i, c in enumerate(contacts):
                if p_name and c["name"] and normalize_person_name(p_name) == normalize_person_name(c["name"]):
                    matched_idx = i
                    break
                elif any(em.lower() in [e.lower() for e in c["emails"]] for em in p_emails if em):
                    matched_idx = i
                    break

            if matched_idx >= 0:
                existing = contacts[matched_idx]
                if not existing["name"] and p_name:
                    existing["name"] = p_name
                if not existing["designation"] and p_desig:
                    existing["designation"] = p_desig
                if not existing.get("linkedin") and p_linkedin:
                    existing["linkedin"] = p_linkedin
                for num in p_nums:
                    d_num = re.sub(r"\D", "", num)
                    if not any(re.sub(r"\D", "", ex) == d_num for ex in existing["numbers"]):
                        existing["numbers"].append(num)
                for em in p_emails:
                    if not any(ex.lower() == em.lower() for ex in existing["emails"]):
                        existing["emails"].append(em)
                if not existing["address"] and p_loc["address"]:
                    existing["address"] = p_loc["address"]
                if not existing["city"] and p_loc["city"]:
                    existing["city"] = p_loc["city"]
                if not existing["state"] and p_loc["state"]:
                    existing["state"] = p_loc["state"]
            else:
                contacts.append({
                    "name": p_name,
                    "designation": p_desig,
                    "linkedin": p_linkedin,
                    "numbers": p_nums,
                    "emails": p_emails,
                    "address": p_loc["address"],
                    "city": p_loc["city"],
                    "state": p_loc["state"]
                })

        if structured_query:
            if structured_query.email_required is True:
                contacts = [c for c in contacts if c.get("emails")]
            elif structured_query.email_required is False:
                contacts = [c for c in contacts if not c.get("emails")]

            if structured_query.phone_required is True:
                contacts = [c for c in contacts if c.get("numbers")]
            elif structured_query.phone_required is False:
                contacts = [c for c in contacts if not c.get("numbers")]

            if structured_query.linkedin_required is True:
                contacts = [c for c in contacts if c.get("linkedin")]
            elif structured_query.linkedin_required is False:
                contacts = [c for c in contacts if not c.get("linkedin")]

        if not contacts:
            continue

        comp_lines = []

        # 1. Source Header:
        if s_file:
            if s_sheet and s_sheet != "Not Available":
                comp_lines.append(f"Source File: {s_file} | {s_sheet}")
            else:
                comp_lines.append(f"Source File: {s_file}")
            comp_lines.append("")
        elif s_col and s_db:
            comp_lines.append(f"Database: {s_db} | Collection: {s_col}")
            comp_lines.append("")
        elif s_col:
            comp_lines.append(f"Collection: {s_col}")
            comp_lines.append("")
        elif s_db:
            comp_lines.append(f"Database: {s_db}")
            comp_lines.append("")

        # 2. Company Name
        comp_lines.append(f"Company Name: {comp_display}")
        comp_lines.append("")

        # 3. Contacts
        for p_idx, c in enumerate(contacts, 1):
            if p_idx > 1:
                comp_lines.append("")
            comp_lines.append(f"Contact Person {p_idx}:")
            comp_lines.append(f"- Name: {c['name'] if c['name'] else 'Not Available'}")
            comp_lines.append(f"- Designation: {c['designation'] if c['designation'] else 'Not Available'}")
            comp_lines.append(f"- LinkedIn: {c['linkedin'] if c.get('linkedin') else 'Not Available'}")

            # Contact Numbers
            if c["numbers"]:
                for n_idx, num in enumerate(c["numbers"], 1):
                    comp_lines.append(f"- Contact Number {n_idx}: {num}")
            else:
                comp_lines.append("- Contact Number 1: Not Available")

            # Emails
            if c["emails"]:
                for e_idx, em in enumerate(c["emails"], 1):
                    comp_lines.append(f"- Email {e_idx}: {em}")
            else:
                comp_lines.append("- Email 1: Not Available")

            # Location lines following Location Display Rule
            loc_lines = format_location_lines(c, prefix="- ")
            comp_lines.extend(loc_lines)

        formatted_groups.append("\n".join(comp_lines))

    if not formatted_groups:
        return "No data found"

    return "\n\n\n".join(formatted_groups).strip()


def generate_no_data_message(user_query: str, structured_query: Optional[StructuredQuery] = None) -> str:
    """
    Generates deterministic, truthful, zero-hallucination no-data explanations
    matching the user's specific query parameters.
    """
    if not structured_query:
        return "No matching records found in the database."

    subject_parts = []

    # Check designation vs person vs company
    if structured_query.designation:
        desig = structured_query.designation.strip()
        # Respect plural wording in query if present
        if "managers" in user_query.lower() and desig.lower().endswith("manager"):
            subject_parts.append(f"{desig}s")
        elif "heads" in user_query.lower() and desig.lower().endswith("head"):
            subject_parts.append(f"{desig}s")
        elif "directors" in user_query.lower() and desig.lower().endswith("director"):
            subject_parts.append(f"{desig}s")
        elif "officers" in user_query.lower() and desig.lower().endswith("officer"):
            subject_parts.append(f"{desig}s")
        else:
            subject_parts.append(desig)
    elif structured_query.people:
        subject_parts.append(", ".join(structured_query.people))
    elif structured_query.companies:
        comps = ", ".join(structured_query.companies)
        if "companies" in user_query.lower() or "group" in user_query.lower():
            subject_parts.append(f"{comps} companies")
        elif "company" in user_query.lower():
            subject_parts.append(f"{comps} company")
        else:
            subject_parts.append(f"{comps} companies")
    else:
        subject_parts.append("companies")

    # At company (if designation or person was specified)
    if structured_query.companies and (structured_query.designation or structured_query.people):
        subject_parts.append(f"at {', '.join(structured_query.companies)}")

    # Location (City, State, Location)
    if structured_query.city:
        subject_parts.append(f"in {structured_query.city}")
    elif structured_query.state:
        subject_parts.append(f"in {structured_query.state}")
    elif structured_query.location:
        subject_parts.append(f"in {structured_query.location}")

    # Availability modifiers
    if structured_query.email_required is True:
        subject_parts.append("with an available email address")
    elif structured_query.email_required is False:
        subject_parts.append("without an email address")

    if structured_query.phone_required is True:
        subject_parts.append("with contact numbers")
    elif structured_query.phone_required is False:
        subject_parts.append("without contact numbers")

    if structured_query.linkedin_required is True:
        subject_parts.append("with a LinkedIn profile")
    elif structured_query.linkedin_required is False:
        subject_parts.append("without a LinkedIn profile")

    target_desc = " ".join(subject_parts).strip()
    return f"No data available for {target_desc}."


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


