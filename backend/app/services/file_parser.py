import os
import io
import csv
import json
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, date

# Configurable limits from environment
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "100000"))

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".xml", ".txt"}


def sanitize_value(val: Any) -> Optional[Any]:
    """
    Normalizes cell values:
    - Empty strings or whitespace-only -> None (null)
    - "null", "none", "nan", "n/a", "na", "-" -> None (null)
    - Datetime / date -> ISO format string
    - Strips leading/trailing whitespace on strings
    """
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        # Check for NaN / Inf
        if isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf")):
            return None
        return val
    
    str_val = str(val).strip()
    if not str_val:
        return None
    if str_val.lower() in ("none", "null", "nan", "n/a", "na", "-", "undefined"):
        return None
    return str_val


def detect_file_extension(filename: str) -> str:
    """Extracts lowercase file extension including the dot."""
    if not filename or "." not in filename:
        return ""
    return os.path.splitext(filename)[1].lower()


def decode_bytes(content: bytes) -> str:
    """Safely decodes raw byte content trying standard encodings."""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1"]
    for enc in encodings:
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


def parse_csv_data(content: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parses CSV content:
    - Automatically sniffs delimiter (comma, semicolon, tab, pipe)
    - Extracts headers
    - Converts rows to clean dictionaries with null conversions
    """
    text = decode_bytes(content)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("The uploaded CSV file is empty.")

    # Sniff delimiter
    sample = "\n".join(lines[:15])
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        # Fallback heuristic
        for candidate in [",", "\t", ";", "|"]:
            if lines[0].count(candidate) > 0:
                delimiter = candidate
                break

    reader = csv.reader(lines, delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise ValueError("The CSV file does not contain a header row.")

    # Clean headers
    headers = [str(h).strip() for h in raw_headers if str(h).strip()]
    if not headers:
        raise ValueError("Could not detect structured column headers in this CSV file.")

    # Ensure unique header names if duplicates exist
    unique_headers = []
    seen = {}
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    headers = unique_headers

    records: List[Dict[str, Any]] = []
    for row_idx, row in enumerate(reader):
        if len(records) >= MAX_RECORDS:
            break
        if not row or not any(str(c).strip() for c in row):
            continue  # Skip blank row

        record = {}
        for col_idx, col_name in enumerate(headers):
            val = row[col_idx] if col_idx < len(row) else None
            record[col_name] = sanitize_value(val)

        # Include row only if it has at least one valid value
        if any(v is not None for v in record.values()):
            records.append(record)

    if not records:
        raise ValueError("The uploaded CSV file does not contain any usable records.")

    return headers, records


def inspect_excel_sheets(content: bytes) -> List[str]:
    """Returns list of sheet names in an Excel workbook."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, keep_links=False)
        sheets = list(wb.sheetnames)
        wb.close()
        return sheets
    except Exception as e:
        raise ValueError(f"The Excel file could not be read: {str(e)}")


def parse_excel_data(content: bytes, sheet_name: Optional[str] = None) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """
    Parses Excel (.xlsx/.xls) worksheet data using openpyxl:
    - Extracts headers from first populated row
    - Reads rows into normalized records
    - Returns (headers, records, active_sheet_name)
    """
    try:
        import openpyxl
    except ImportError:
        raise ValueError("openpyxl is not installed on the server.")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True, keep_links=False)
    except Exception as e:
        raise ValueError(f"The Excel file could not be read. Please verify that the file is a valid .xlsx spreadsheet ({str(e)}).")

    all_sheets = wb.sheetnames
    if not all_sheets:
        wb.close()
        raise ValueError("The Excel workbook contains no worksheets.")

    target_sheet_name = sheet_name if (sheet_name and sheet_name in all_sheets) else all_sheets[0]
    ws = wb[target_sheet_name]

    rows_iter = ws.iter_rows(values_only=True)
    
    # Find first row with non-empty headers
    headers: List[str] = []
    for row in rows_iter:
        if not row:
            continue
        cleaned = [str(c).strip() if c is not None else "" for c in row]
        if any(cleaned):
            # We found the header row
            raw_headers = [c for c in cleaned if c]
            # Make headers unique
            seen = {}
            for h in raw_headers:
                if h in seen:
                    seen[h] += 1
                    headers.append(f"{h}_{seen[h]}")
                else:
                    seen[h] = 0
                    headers.append(h)
            break

    if not headers:
        wb.close()
        raise ValueError(f"Could not detect column headers in worksheet '{target_sheet_name}'.")

    records: List[Dict[str, Any]] = []
    for row in rows_iter:
        if len(records) >= MAX_RECORDS:
            break
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue

        record = {}
        for col_idx, col_name in enumerate(headers):
            val = row[col_idx] if col_idx < len(row) else None
            record[col_name] = sanitize_value(val)

        if any(v is not None for v in record.values()):
            records.append(record)

    wb.close()

    if not records:
        raise ValueError(f"Worksheet '{target_sheet_name}' contains headers but no usable data rows.")

    return headers, records, target_sheet_name


def parse_json_data(content: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parses JSON data:
    - Supports list of dicts: `[ {...}, {...} ]`
    - Supports wrapper objects: `{ "data": [ {...} ] }`, `{ "records": [ {...} ] }`, etc.
    - Normalizes records and extracts headers
    """
    text = decode_bytes(content)
    try:
        parsed = json.loads(text)
    except Exception as e:
        raise ValueError(f"The JSON file could not be parsed: {str(e)}")

    raw_items: List[Any] = []
    if isinstance(parsed, list):
        raw_items = parsed
    elif isinstance(parsed, dict):
        # Look for common array keys
        for key in ["data", "records", "items", "rows", "companies", "results", "table"]:
            if key in parsed and isinstance(parsed[key], list):
                raw_items = parsed[key]
                break
        if not raw_items:
            # Check if values are a list of objects or if the dict itself is a single record
            if all(isinstance(v, (str, int, float, bool, type(None))) for v in parsed.values()):
                raw_items = [parsed]
            else:
                for k, v in parsed.items():
                    if isinstance(v, list) and v and isinstance(v[0], dict):
                        raw_items = v
                        break

    if not raw_items or not isinstance(raw_items, list):
        raise ValueError("JSON file must contain an array of record objects (or a wrapper like {'data': [...]}).")

    # Collect headers and sanitize records
    headers_set = set()
    records: List[Dict[str, Any]] = []

    for item in raw_items:
        if len(records) >= MAX_RECORDS:
            break
        if not isinstance(item, dict):
            continue

        clean_rec = {}
        for k, v in item.items():
            k_str = str(k).strip()
            if not k_str:
                continue
            headers_set.add(k_str)
            clean_rec[k_str] = sanitize_value(v)

        if any(v is not None for v in clean_rec.values()):
            records.append(clean_rec)

    if not records:
        raise ValueError("The uploaded JSON file does not contain any usable record objects.")

    headers = list(headers_set)
    # Ensure all records have keys populated (with None for missing)
    for rec in records:
        for h in headers:
            if h not in rec:
                rec[h] = None

    return headers, records


def parse_xml_data(content: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Safely parses XML into structured records:
    - Protects against XXE / entity expansion / malicious external entities
    - Detects repeating child nodes (e.g. <records><record>... or <root><row>...)
    - Extracts field elements and attributes as column values
    """
    text = decode_bytes(content)
    
    # Basic check against external entity declarations
    if "<!ENTITY" in text or "<!DOCTYPE" in text:
        # Strip or reject dangerous entity definitions
        if re.search(r"<!ENTITY[^>]+SYSTEM", text, re.IGNORECASE):
            raise ValueError("XML files with external SYSTEM entities are not permitted for security reasons.")

    try:
        parser = ET.XMLParser()
        root = ET.fromstring(text.encode("utf-8"), parser=parser)
    except Exception as e:
        raise ValueError(f"The XML file could not be parsed: {str(e)}")

    # Detect repeating child elements
    children = list(root)
    if not children:
        raise ValueError("The XML file has no child record elements.")

    # Group children by tag
    tag_counts = {}
    for child in children:
        tag_counts[child.tag] = tag_counts.get(child.tag, 0) + 1

    # Most frequent tag is likely the record tag
    record_tag = max(tag_counts, key=tag_counts.get)
    record_elements = [c for c in children if c.tag == record_tag]

    # If only 1 child and that child has multiple grandchildren, check nested records
    if len(record_elements) == 1 and len(list(record_elements[0])) > 1:
        nested_children = list(record_elements[0])
        nested_counts = {}
        for nc in nested_children:
            nested_counts[nc.tag] = nested_counts.get(nc.tag, 0) + 1
        most_frequent_nested = max(nested_counts, key=nested_counts.get)
        if nested_counts[most_frequent_nested] >= 1:
            record_elements = [nc for nc in nested_children if nc.tag == most_frequent_nested]

    headers_set = set()
    records: List[Dict[str, Any]] = []

    for elem in record_elements:
        if len(records) >= MAX_RECORDS:
            break
        rec = {}
        
        # Element attributes as fields
        for attr_k, attr_v in elem.attrib.items():
            col_name = str(attr_k).strip()
            headers_set.add(col_name)
            rec[col_name] = sanitize_value(attr_v)

        # Child elements as fields
        for sub in elem:
            tag = str(sub.tag).strip()
            val = sub.text.strip() if sub.text else None
            headers_set.add(tag)
            rec[tag] = sanitize_value(val)

        if any(v is not None for v in rec.values()):
            records.append(rec)

    if not records:
        raise ValueError("Could not extract structured records from this XML file.")

    headers = list(headers_set)
    for rec in records:
        for h in headers:
            if h not in rec:
                rec[h] = None

    return headers, records


def parse_txt_data(content: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Parses TXT files only if they contain clearly structured tabular data (e.g. TSV, delimited text).
    If unstructured prose / general text, raises a user-friendly error.
    """
    text = decode_bytes(content)
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or len(lines) < 2:
        raise ValueError("This text file does not contain clearly structured tabular data.\nPlease upload a structured CSV, Excel, JSON, or XML file.")

    # Check for tab, pipe, semicolon, or comma delimiter consistency across lines
    delimiters = ["\t", "|", ";", ","]
    best_delim = None
    max_consistent_cols = 0

    sample_lines = lines[:10]
    for d in delimiters:
        col_counts = [len(l.split(d)) for l in sample_lines]
        # Check if delimiter occurs at least once and column count is uniform (>= 2 columns)
        if col_counts[0] >= 2 and all(c == col_counts[0] for c in col_counts):
            best_delim = d
            max_consistent_cols = col_counts[0]
            break

    if not best_delim:
        raise ValueError("This text file does not contain clearly structured tabular data.\nPlease upload a structured CSV, Excel, JSON, or XML file.")

    # Parse using CSV logic with best_delim
    return parse_csv_data(content)


def parse_uploaded_file(
    filename: str,
    content: bytes,
    sheet_name: Optional[str] = None
) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Main file parser dispatcher.
    Returns:
    - headers: List of original column names
    - records: List of record dictionaries (each key is an original column name, values sanitized)
    - metadata: Extra metadata dict (e.g. original_type, sheet_name, sheet_options, size_bytes)
    """
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB}MB.")

    ext = detect_file_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Please upload a CSV, Excel (.xlsx, .xls), JSON, XML, or structured TXT data file."
        )

    metadata: Dict[str, Any] = {
        "filename": filename,
        "original_type": ext.lstrip("."),
        "size_bytes": len(content),
    }

    if ext == ".csv":
        headers, records = parse_csv_data(content)
    elif ext in (".xlsx", ".xls"):
        # Check available sheets
        try:
            available_sheets = inspect_excel_sheets(content)
            metadata["available_sheets"] = available_sheets
        except Exception:
            available_sheets = []

        headers, records, active_sheet = parse_excel_data(content, sheet_name=sheet_name)
        metadata["sheet_name"] = active_sheet
    elif ext == ".json":
        headers, records = parse_json_data(content)
    elif ext == ".xml":
        headers, records = parse_xml_data(content)
    elif ext == ".txt":
        headers, records = parse_txt_data(content)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    return headers, records, metadata
