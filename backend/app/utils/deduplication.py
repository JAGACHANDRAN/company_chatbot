import re
from typing import List, Dict, Any, Optional
from .normalization import normalize_company_name, normalize_person_name, normalize_designation, normalize_text


def compute_record_identity_key(record: Dict[str, Any], include_source: bool = True) -> str:
    """
    Computes a deduplication key for a record based on:
    [source_file + source_collection] + normalized company + normalized person + normalized designation + contact info
    
    This ensures that:
    1. Records from different sources/files are NOT merged into one artificial record.
    2. Truly identical duplicate records within the same source are deduplicated.
    3. Distinct people at the same company are preserved.
    """
    source_file = normalize_text(record.get("source_file"))
    source_col = normalize_text(record.get("source_collection"))
    company = normalize_company_name(record.get("company_name") or record.get("Company Name"))
    person = normalize_person_name(record.get("person_name") or record.get("Contact Person") or record.get("name"))
    designation = normalize_designation(record.get("designation") or record.get("Designation") or record.get("role"))
    
    contact_phone = normalize_text(record.get("contact_number") or record.get("Mobile No.") or record.get("phone"))
    contact_phone = re.sub(r"[^0-9]", "", contact_phone)
    
    contact_email = normalize_text(record.get("personal_mail_id") or record.get("Email 1") or record.get("email"))
    
    src_prefix = f"src::{source_file}::{source_col}::" if include_source else ""

    # If person is available:
    if person:
        return f"{src_prefix}rec::{company}::{person}::{designation}::{contact_phone or contact_email}"
    
    # If no person name, but contact info or company exists:
    if contact_email or contact_phone:
        return f"{src_prefix}rec::{company}::{designation}::{contact_phone}::{contact_email}"
        
    # Company alone (only if neither person nor contact is present)
    return f"{src_prefix}rec::{company}::{designation}"


def deduplicate_records(records: List[Dict[str, Any]], preserve_source_separation: bool = True) -> List[Dict[str, Any]]:
    """
    Deduplicates a list of records while:
    1. Preserving separate records across different source files/collections (CRITICAL PROBLEM 2).
    2. Deduplicating identical duplicate records within the same source.
    3. Preserving distinct individuals at the same company.
    """
    if not records:
        return []

    seen_keys: Dict[str, Dict[str, Any]] = {}
    deduped: List[Dict[str, Any]] = []

    for rec in records:
        key = compute_record_identity_key(rec, include_source=preserve_source_separation)

        if key in seen_keys:
            # Duplicate within the same source: merge missing non-null fields
            existing = seen_keys[key]
            for field, val in rec.items():
                if field.startswith("_"):
                    continue
                curr_val = existing.get(field)
                if (curr_val is None or curr_val == "Not Available" or curr_val == "") and (val and val != "Not Available"):
                    existing[field] = val
        else:
            rec_copy = dict(rec)
            seen_keys[key] = rec_copy
            deduped.append(rec_copy)

    return deduped
