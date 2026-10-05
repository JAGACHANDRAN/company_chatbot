import re
from typing import List, Dict, Any, Optional
from ..database import get_database, get_collections, get_database_name
from ..utils.normalization import (
    normalize_record_fields,
    normalize_company_search_variants,
    normalize_text,
    COMPANY_SUFFIX_PATTERN,
)
from .mongo_dataset import list_datasets, DATASET_RECORDS_COLLECTION
from .query_understanding import StructuredQuery


DISALLOWED_MONGO_OPERATORS = ["$where", "$function", "$expr", "$exec", "$eval"]


def sanitize_value(val: str) -> str:
    """Sanitizes search string to prevent regex injection or operator injection."""
    if not val:
        return ""
    cleaned = str(val).strip()
    for op in DISALLOWED_MONGO_OPERATORS:
        cleaned = cleaned.replace(op, "")
    return cleaned.strip()


def build_regex_clause(val: str, exact: bool = False) -> Dict[str, Any]:
    """
    Builds a case-insensitive, whitespace-flexible MongoDB regex clause.
    """
    clean_val = sanitize_value(val)
    if not clean_val:
        return {"$regex": ".*", "$options": "i"}

    # Escape regex special characters
    escaped = re.escape(clean_val)
    # Allow flexible whitespace
    flexible = re.sub(r"\\\s+", r"\\s+", escaped)

    if exact:
        pattern = f"^{flexible}$"
    else:
        pattern = flexible

    return {"$regex": pattern, "$options": "i"}


def build_company_clauses(
    company_name: str,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """
    Builds MongoDB query clauses matching a company name across standard fields.
    Supports partial entity matching (e.g. 'ABC Industries' matches 'ABC Industries Pvt Ltd').
    """
    variants = normalize_company_search_variants(company_name)
    clauses = []

    fields_to_check = [
        "Company Name", "company_name", "Company", "company", "business_name", "Organization", "Firm", "norm_company"
    ]

    for v in variants:
        reg = build_regex_clause(v, exact=False)
        for f in fields_to_check:
            if prefix_data:
                clauses.append({f"data.{f}": reg})
                clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
            else:
                clauses.append({f: reg})

    return clauses


def build_person_clauses(
    person_name: str,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """
    Builds clauses matching a person name across standard fields.
    """
    reg = build_regex_clause(person_name, exact=False)
    fields_to_check = [
        "Person Name", "person_name", "Contact Person", "contact_person", "person", "name", "Name", "Full Name", "Employee Name"
    ]
    clauses = []
    for f in fields_to_check:
        if prefix_data:
            clauses.append({f"data.{f}": reg})
            clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
        else:
            clauses.append({f: reg})
    return clauses


def build_location_clauses(
    loc_val: str,
    is_city: bool = False,
    is_state: bool = False,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """
    Builds DYNAMIC location search clauses for ANY state, city, district, country, or location.
    Zero hardcoded values: matches whatever geographic entity was extracted against location columns.
    """
    reg = build_regex_clause(loc_val, exact=False)
    clauses = []

    if is_city:
        fields = ["City", "city", "town", "Town", "district", "District", "Location", "location", "Address", "address"]
    elif is_state:
        fields = ["State", "state", "Territory", "territory", "Region", "region", "Location", "location", "Address", "address"]
    else:
        fields = [
            "State", "state", "City", "city", "Location", "location", "Address", "address",
            "Company Address", "Territory", "territory", "Region", "region", "Country", "country"
        ]

    for f in fields:
        if prefix_data:
            clauses.append({f"data.{f}": reg})
            clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
        else:
            clauses.append({f: reg})

    return clauses


def build_designation_clauses(
    desig_val: str,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """
    Builds clauses matching job designation / title.
    """
    reg = build_regex_clause(desig_val, exact=False)
    fields = ["Designation", "designation", "role", "Role", "Job Title", "job_title", "Position", "Title"]
    clauses = []
    for f in fields:
        if prefix_data:
            clauses.append({f"data.{f}": reg})
            clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
        else:
            clauses.append({f: reg})
    return clauses


def build_department_clauses(
    dept_val: str,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """
    Builds clauses matching department or department keywords in designation.
    """
    reg = build_regex_clause(dept_val, exact=False)
    fields = [
        "Department", "department", "Designation", "designation",
        "role", "Role", "Group", "group", "division", "Division"
    ]
    clauses = []
    for f in fields:
        if prefix_data:
            clauses.append({f"data.{f}": reg})
            clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
        else:
            clauses.append({f: reg})
    return clauses


def build_email_availability_clauses(
    required: bool,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """Builds clauses to filter records by email presence."""
    fields = [
        "Email", "email", "Email ID", "email_id", "Email Address", "email_address",
        "Email 1", "email_1", "Email 2", "email_2", "Personal Mail ID", "personal_mail_id", "norm_email"
    ]
    clauses = []
    if required:
        reg = {"$regex": "@"}
        for f in fields:
            if prefix_data:
                clauses.append({f"data.{f}": reg})
                clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
            else:
                clauses.append({f: reg})
    return clauses


def build_phone_availability_clauses(
    required: bool,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """Builds clauses to filter records by phone presence."""
    fields = [
        "Phone", "phone", "Mobile", "mobile", "Contact", "contact", "Contact Number", "contact_number",
        "Telephone", "telephone", "phone_2", "mobile_no", "telephone_1", "telephone_2", "norm_phone"
    ]
    clauses = []
    if required:
        reg = {"$regex": r"\d{5,}"}
        for f in fields:
            if prefix_data:
                clauses.append({f"data.{f}": reg})
                clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
            else:
                clauses.append({f: reg})
    return clauses


def build_linkedin_availability_clauses(
    required: bool,
    prefix_data: bool = True
) -> List[Dict[str, Any]]:
    """Builds clauses to filter records by LinkedIn profile presence."""
    fields = [
        "LinkedIn", "linkedin", "LinkedIn URL", "linkedin_url", "LinkedIn Profile", "linkedin_profile",
        "profile_url", "Profile URL", "norm_linkedin"
    ]
    clauses = []
    if required:
        reg = {"$regex": r"linkedin\.com|/in/", "$options": "i"}
        for f in fields:
            if prefix_data:
                clauses.append({f"data.{f}": reg})
                clauses.append({f"normalized_data.{re.sub(r'[^a-zA-Z0-9_]', '_', f.lower())}": reg})
            else:
                clauses.append({f: reg})
    return clauses


def build_structured_mongo_filter(
    structured_query: StructuredQuery,
    is_dataset_records: bool = True,
    dataset_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs an injection-safe, highly accurate MongoDB query filter from a StructuredQuery.
    Combines conditions using logical AND across distinct dimensions (companies, people, location, role, availability),
    and logical OR within multi-valued entities (e.g. company A OR company B).
    """
    and_conditions: List[Dict[str, Any]] = []

    # Optional dataset scoping
    if is_dataset_records and dataset_id and dataset_id not in ("all", "default", "*", "companies"):
        and_conditions.append({"dataset_id": dataset_id})

    # 1. Multiple Companies -> IN clause ($or over company variants)
    if structured_query.companies:
        all_company_clauses = []
        for c in structured_query.companies:
            all_company_clauses.extend(build_company_clauses(c, prefix_data=is_dataset_records))
        if all_company_clauses:
            and_conditions.append({"$or": all_company_clauses})

    # 2. People
    if structured_query.people:
        all_people_clauses = []
        for p in structured_query.people:
            all_people_clauses.extend(build_person_clauses(p, prefix_data=is_dataset_records))
        if all_people_clauses:
            and_conditions.append({"$or": all_people_clauses})

    # 3. Dynamic Location (State, City, Country, Location)
    # Search actual location fields dynamically
    loc_clauses = []
    if structured_query.state:
        loc_clauses.extend(build_location_clauses(structured_query.state, is_state=True, prefix_data=is_dataset_records))
    if structured_query.city:
        loc_clauses.extend(build_location_clauses(structured_query.city, is_city=True, prefix_data=is_dataset_records))
    if structured_query.country:
        loc_clauses.extend(build_location_clauses(structured_query.country, prefix_data=is_dataset_records))
    if structured_query.location and not (structured_query.state or structured_query.city):
        loc_clauses.extend(build_location_clauses(structured_query.location, prefix_data=is_dataset_records))

    if loc_clauses:
        and_conditions.append({"$or": loc_clauses})

    # 4. Designation
    if structured_query.designation:
        desig_clauses = build_designation_clauses(structured_query.designation, prefix_data=is_dataset_records)
        if desig_clauses:
            and_conditions.append({"$or": desig_clauses})

    # 5. Department
    if structured_query.department and not structured_query.designation:
        dept_clauses = build_department_clauses(structured_query.department, prefix_data=is_dataset_records)
        if dept_clauses:
            and_conditions.append({"$or": dept_clauses})

    # 6. Availability Filters
    if structured_query.email_required is True:
        email_clauses = build_email_availability_clauses(True, prefix_data=is_dataset_records)
        if email_clauses:
            and_conditions.append({"$or": email_clauses})

    if structured_query.phone_required is True:
        phone_clauses = build_phone_availability_clauses(True, prefix_data=is_dataset_records)
        if phone_clauses:
            and_conditions.append({"$or": phone_clauses})

    if structured_query.linkedin_required is True:
        linkedin_clauses = build_linkedin_availability_clauses(True, prefix_data=is_dataset_records)
        if linkedin_clauses:
            and_conditions.append({"$or": linkedin_clauses})

    if not and_conditions:
        return {}
    if len(and_conditions) == 1:
        return and_conditions[0]
    return {"$and": and_conditions}


def _execute_single_structured_search(
    structured_query: StructuredQuery,
    dataset_id: Optional[str] = "all",
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Internal single-condition structured search across dataset_records and all collections."""
    db = get_database()
    results: List[Dict[str, Any]] = []

    # 1. Search uploaded datasets in `dataset_records`
    uploaded_datasets = list_datasets()
    ds_filter = build_structured_mongo_filter(
        structured_query,
        is_dataset_records=True,
        dataset_id=dataset_id
    )

    if ds_filter:
        try:
            ds_col = db[DATASET_RECORDS_COLLECTION]
            ds_cursor = ds_col.find(ds_filter).limit(limit)
            ds_name_map = {ds.get("dataset_id"): ds.get("filename") for ds in uploaded_datasets}
            ds_sheet_map = {ds.get("dataset_id"): ds.get("sheet_name") for ds in uploaded_datasets}
            db_name = get_database_name()

            for doc in ds_cursor:
                ds_id = doc.get("dataset_id", "")
                ds_name = ds_name_map.get(ds_id)
                doc_copy = dict(doc)
                doc_copy["database_source"] = db_name
                doc_copy["database"] = db_name
                doc_copy["source_collection"] = "dataset_records"
                s_file_col = (
                    doc.get("source_file")
                    or doc.get("Source File")
                    or doc.get("source_filename")
                    or doc.get("Source_File")
                    or doc.get("file_name")
                    or doc.get("filename")
                    or ds_name
                    or None
                )
                doc_copy["source_file"] = s_file_col
                doc_copy["source_sheet"] = ds_sheet_map.get(ds_id)
                norm_rec = normalize_record_fields(
                    doc_copy,
                    source_file=s_file_col,
                    source_row=doc.get("record_index")
                )
                results.append(norm_rec)
        except Exception as e:
            print(f"[Mongo Search Warning - dataset_records] {e}")

    # 2. Search configured MongoDB collections (if searching all or default)
    if dataset_id in ("all", "default", "*", "companies") or not uploaded_datasets:
        col_filter = build_structured_mongo_filter(
            structured_query,
            is_dataset_records=False
        )

        if col_filter:
            try:
                collections = get_collections()
                db_name = get_database_name()
                for col in collections:
                    col_cursor = col.find(col_filter).limit(limit // max(1, len(collections)))
                    for raw_doc in col_cursor:
                        doc_copy = dict(raw_doc)
                        col_db = db_name
                        doc_copy["database_source"] = col_db
                        doc_copy["database"] = col_db
                        doc_copy["source_collection"] = col.name
                        
                        # Only take source_file if an actual source file column exists in the document
                        s_file_col = (
                            raw_doc.get("source_file")
                            or raw_doc.get("Source File")
                            or raw_doc.get("source_filename")
                            or raw_doc.get("Source_File")
                            or raw_doc.get("sourcefile")
                            or raw_doc.get("file_name")
                            or raw_doc.get("filename")
                            or None
                        )
                        # NEVER fabricate a fake .xlsx name
                        doc_copy["source_file"] = s_file_col
                        doc_copy["source_sheet"] = (
                            raw_doc.get("Source Sheet")
                            or raw_doc.get("source_sheet")
                            or raw_doc.get("Source Sheets")
                            or raw_doc.get("source_sheets")
                            or None
                        )
                        norm_rec = normalize_record_fields(
                            doc_copy,
                            source_file=s_file_col,
                            source_row=raw_doc.get("source_row") or raw_doc.get("row") or raw_doc.get("record_index")
                        )
                        results.append(norm_rec)
            except Exception as e:
                print(f"[Mongo Search Warning - collections] {e}")

    return results


def execute_structured_search(
    structured_query: StructuredQuery,
    dataset_id: Optional[str] = "all",
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Executes structured MongoDB search across:
    1. All uploaded datasets in `dataset_records`
    2. All configured database collections (e.g. metrology, Expo_Acme, ECG_Marposs, etc.)
    
    If multiple companies are explicitly requested (e.g. 'ABC, TVS and 2D INC'),
    independently searches each company entity and combines results.
    """
    # Multi-entity independent retrieval requirement:
    # "For 'Give me ABC, TVS and XYZ', the system must independently search each company... Then combine results."
    if structured_query.companies and len(structured_query.companies) > 1:
        all_results: List[Dict[str, Any]] = []
        for comp in structured_query.companies:
            sub_query = structured_query.model_copy(update={"companies": [comp]})
            comp_results = _execute_single_structured_search(sub_query, dataset_id, limit)
            all_results.extend(comp_results)
        return all_results

    return _execute_single_structured_search(structured_query, dataset_id, limit)


def _legacy_search_regex(value: str, operator: str = "contains") -> Dict[str, str]:
    clean_value = sanitize_value(value)
    if operator not in {"equals", "contains", "starts_with", "ends_with"}:
        operator = "contains"

    if re.fullmatch(r"[A-Za-z0-9\s_-]+", clean_value):
        compact_value = re.sub(r"[^A-Za-z0-9]", "", clean_value)
        regex_pattern = r"[\W_]*".join(re.escape(char) for char in compact_value)
    else:
        regex_pattern = re.escape(clean_value)

    if operator == "equals":
        regex_pattern = f"^{regex_pattern}$"
    elif operator == "starts_with":
        regex_pattern = f"^{regex_pattern}"
    elif operator == "ends_with":
        regex_pattern = f"{regex_pattern}$"
    return {"$regex": regex_pattern, "$options": "i"}


def build_safe_dataset_filter(
    dataset_id: Optional[str] = None,
    field: Optional[str] = None,
    value: str = "",
    operator: str = "contains",
    dataset_fields: Optional[List[str]] = None,
    conditions: Optional[List[Dict[str, Any]]] = None,
    logic: str = "AND",
    *args, **kwargs
) -> Dict[str, Any]:
    """
    Backward-compatibility filter builder for dataset_records.
    Validates that explicit fields are present in dataset_fields schema,
    and constructs regex filters matching data.<field>.
    """
    base_query: Dict[str, Any] = {}
    if dataset_id and dataset_id not in ("all", "default", "*", "companies"):
        base_query["dataset_id"] = dataset_id

    fields = dataset_fields or []
    search_conditions = conditions or ([{"field": field, "value": value, "operator": operator}] if value else [])

    if not search_conditions:
        return base_query

    condition_clauses = []
    for cond in search_conditions:
        cond_field = cond.get("field")
        cond_val = cond.get("value")
        cond_op = cond.get("operator", "contains")

        # Validate that explicit field is in schema
        if cond_field and fields and cond_field not in fields and cond_field != "*":
            raise ValueError(f"Field '{cond_field}' is not in the dataset schema.")

        target_field = cond_field or (fields[0] if fields else "Company Name")
        clean_val = sanitize_value(str(cond_val or ""))
        if not clean_val:
            continue

        regex_clause = _legacy_search_regex(clean_val, cond_op)
        sub_clauses = [
            {f"data.{target_field}": regex_clause}
        ]
        condition_clauses.append({"$or": sub_clauses})

    if condition_clauses:
        if logic.upper() == "OR":
            base_query["$or"] = condition_clauses
        else:
            if len(condition_clauses) == 1:
                base_query.update(condition_clauses[0])
            else:
                base_query["$and"] = condition_clauses

    return base_query


def search_dataset_records(
    dataset_id: Optional[str] = None,
    value: str = "",
    operator: str = "contains",
    limit: int = 50,
    conditions: Optional[List[Dict[str, Any]]] = None,
    logic: str = "AND",
    return_fields: Optional[List[str]] = None,
    field: Optional[str] = None,
    *args, **kwargs
) -> List[Dict[str, Any]]:
    """
    Backward compatibility wrapper for legacy callers.
    """
    db = get_database()
    col = db[DATASET_RECORDS_COLLECTION]
    f = build_safe_dataset_filter(
        dataset_id=dataset_id,
        field=field,
        value=value,
        operator=operator,
        conditions=conditions,
        logic=logic
    )
    results = []
    for doc in col.find(f).limit(limit):
        rec = dict(doc.get("data", {}))
        rec["id"] = str(doc.get("_id", ""))
        rec["dataset_id"] = doc.get("dataset_id")
        results.append(rec)
    return results
