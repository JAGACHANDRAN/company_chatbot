import re
import io
import csv
from typing import List, Dict, Any, Tuple, Optional


def normalize_field_name(name: str) -> str:
    """
    Normalizes a column header into a clean snake_case identifier:
    - 'Company Name' -> 'company_name'
    - 'E-mail Address' -> 'email_address'
    - 'Phone Number (Primary)' -> 'phone_number_primary'
    - 'Employee ID #' -> 'employee_id'
    - 'Designation / Role' -> 'designation_role'
    """
    if not name:
        return "field"
    # Replace non-alphanumeric with underscores
    s = re.sub(r"[^\w\s]", "_", str(name).strip())
    # Replace whitespace with underscore
    s = re.sub(r"\s+", "_", s)
    # Collapse consecutive underscores
    s = re.sub(r"_+", "_", s)
    # Strip leading/trailing underscores and lowercase
    s = s.strip("_").lower()
    return s if s else "field"


def detect_field_type(values: List[Any]) -> str:
    """Infers high-level field type from sample values."""
    non_nulls = [v for v in values if v is not None]
    if not non_nulls:
        return "string"

    sample = non_nulls[:50]
    
    # Check boolean
    if all(isinstance(v, bool) or str(v).lower() in ("true", "false", "yes", "no") for v in sample):
        return "boolean"

    # Check numeric
    all_num = True
    for v in sample:
        try:
            float(str(v).replace(",", ""))
        except ValueError:
            all_num = False
            break
    if all_num:
        return "number"

    # Check email
    if all(re.match(r"[^@]+@[^@]+\.[^@]+", str(v)) for v in sample):
        return "email"

    return "string"


def build_schema_metadata(headers: List[str], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Builds comprehensive schema metadata for a dataset:
    - original_fields: exact header strings from file
    - normalized_fields: snake_case column names
    - field_mapping: dict mapping normalized -> original
    - field_types: inferred types per column
    """
    original_fields = list(headers)
    normalized_fields = []
    field_mapping = {}
    normalized_to_original = {}

    seen_norm = {}
    for orig in original_fields:
        norm = normalize_field_name(orig)
        if norm in seen_norm:
            seen_norm[norm] += 1
            norm = f"{norm}_{seen_norm[norm]}"
        else:
            seen_norm[norm] = 0

        normalized_fields.append(norm)
        field_mapping[orig] = norm
        normalized_to_original[norm] = orig

    # Infer field types
    field_types = {}
    for orig in original_fields:
        vals = [r.get(orig) for r in records[:100]]
        norm = field_mapping[orig]
        field_types[norm] = detect_field_type(vals)

    return {
        "original_fields": original_fields,
        "normalized_fields": normalized_fields,
        "field_mapping": field_mapping,
        "normalized_to_original": normalized_to_original,
        "field_types": field_types,
    }


def normalize_records(
    headers: List[str],
    records: List[Dict[str, Any]],
    field_mapping: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Normalizes each record into a structured item containing:
    - data: exact original keys & values
    - normalized_data: normalized snake_case keys & values
    """
    normalized_list = []
    for idx, raw in enumerate(records):
        data_dict = {}
        norm_dict = {}

        for orig_key, val in raw.items():
            norm_key = field_mapping.get(orig_key, normalize_field_name(orig_key))
            data_dict[orig_key] = val
            norm_dict[norm_key] = val

        normalized_list.append({
            "record_index": idx,
            "data": data_dict,
            "normalized_data": norm_dict
        })

    return normalized_list


def convert_records_to_csv(headers: List[str], records: List[Dict[str, Any]], max_rows: int = 500) -> str:
    """Converts records back to CSV representation for preview, validation, or export."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for rec in records[:max_rows]:
        row = [rec.get(h) if rec.get(h) is not None else "" for h in headers]
        writer.writerow(row)

    return output.getvalue()
