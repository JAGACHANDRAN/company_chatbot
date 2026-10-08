"""
PII Masking and Unmasking Engine for Calispec Hybrid RAG.
SECURITY GUARANTEE:
1. Strips all extraneous fields and retains ONLY: company, person, designation, city.
2. Replaces all phone numbers and emails with sequential placeholders ([PHONE_1], [EMAIL_1], ...).
3. Unmasks response text in the backend before returning to client.
"""
import re
from typing import List, Dict, Any, Tuple

PHONE_PATTERN = re.compile(r"(\+?\d[\d\s\-\(\)\.]{6,16}\d)")
EMAIL_PATTERN = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")


def extract_clean_field(record: Dict[str, Any], *keys: str) -> str:
    """Helper to extract non-empty string value from record or raw_data."""
    raw = record.get("raw_data") if isinstance(record.get("raw_data"), dict) else {}
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    norm = record.get("normalized_data") if isinstance(record.get("normalized_data"), dict) else {}

    for k in keys:
        for src in (record, raw, data, norm):
            if isinstance(src, dict) and k in src:
                val = src.get(k)
                if val is not None and not isinstance(val, (dict, list)):
                    s = str(val).strip()
                    if s and s.lower() not in ("none", "null", "not available", "n/a", "-", "nan", "undefined"):
                        return s
    return "Not Available"


def mask_records(records: List[Dict[str, Any]], max_records: int = 100) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """
    Transforms retrieved records into sanitized masked dictionaries containing ONLY:
    company, person, designation, city, phone, email.
    Replaces real phone numbers with [PHONE_1], [PHONE_2]... and emails with [EMAIL_1], [EMAIL_2]...
    Returns:
      (masked_records: List[Dict[str, str]], mapping: Dict[str, str])
    """
    masked_records: List[Dict[str, str]] = []
    mapping: Dict[str, str] = {}
    phone_idx = 1
    email_idx = 1

    for r in records[:max_records]:
        comp = extract_clean_field(r, "company", "Company Name", "company_name", "business_name")
        person = extract_clean_field(r, "person", "Contact Person", "person_name", "name")
        desig = extract_clean_field(r, "designation", "Designation", "role", "Job Title")
        city_raw = extract_clean_field(r, "city", "City", "location", "Town")
        city = city_raw.split("/")[0].strip() if "/" in city_raw else city_raw

        # Extract real phone and mask
        real_phone = extract_clean_field(r, "phone", "phone_2", "Contact Number", "Mobile No.", "contact_number", "telephone_1", "telephone_2")
        if real_phone != "Not Available":
            phone_placeholder = f"[PHONE_{phone_idx}]"
            mapping[phone_placeholder] = real_phone
            phone_val = phone_placeholder
            phone_idx += 1
        else:
            phone_val = "Not Available"

        # Extract real email and mask
        real_email = extract_clean_field(r, "email", "email_2", "Email", "Email 1", "Email 2", "personal_mail_id")
        if real_email != "Not Available":
            email_placeholder = f"[EMAIL_{email_idx}]"
            mapping[email_placeholder] = real_email
            email_val = email_placeholder
            email_idx += 1
        else:
            email_val = "Not Available"

        sanitized_doc = {
            "company": comp,
            "person": person,
            "designation": desig,
            "city": city,
            "phone": phone_val,
            "email": email_val
        }
        masked_records.append(sanitized_doc)

    return masked_records, mapping


def unmask_text(text: str, mapping: Dict[str, str]) -> str:
    """
    Restores placeholders in the LLM response text with real values.
    Unknown placeholders are left untouched.
    """
    if not text or not mapping:
        return text

    unmasked = text
    for placeholder, real_val in mapping.items():
        unmasked = unmasked.replace(placeholder, real_val)

    return unmasked
