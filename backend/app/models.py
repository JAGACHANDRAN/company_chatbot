import re
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

# Comprehensive list of columns across all collections
CANONICAL_COLUMNS = [
    "company_name",
    "contact_person",
    "designation",
    "linkedin_url",
    "mobile_no",
    "landline_telephone",
    "landline_other_no",
    "telephone_1",
    "telephone_2",
    "email",
    "email_1",
    "email_2",
    "address",
    "city",
    "state",
    "pin",
    "group",
    "records_merged",
    "review_required",
    "sources",
    "remarks",
]

# Mapping of normalized alphanumeric keys to canonical keys
NORMALIZED_KEY_MAP = {
    "companyname": "company_name",
    "company": "company_name",
    "contactperson": "contact_person",
    "designation": "designation",
    "mobileno": "mobile_no",
    "mobile": "mobile_no",
    "landlinetelephone": "landline_telephone",
    "landlineotherno": "landline_other_no",
    "landline": "landline_telephone",
    "telephone": "telephone_1",
    "telephone1": "telephone_1",
    "telephone2": "telephone_2",
    "email": "email",
    "email1": "email_1",
    "email2": "email_2",
    "address": "address",
    "city": "city",
    "state": "state",
    "pin": "pin",
    "pincode": "pin",
    "group": "group",
    "recordsmerged": "records_merged",
    "reviewrequired": "review_required",
    "sources": "sources",
    "source": "sources",
    "remarks": "remarks",
    "remark": "remarks",
    "linkedin": "linkedin_url",
    "linkedinurl": "linkedin_url",
    "linkedinprofile": "linkedin_url",
}


def is_valid_value(val: Any) -> bool:
    """Returns True if the value is non-empty, non-null, and meaningful."""
    if val is None:
        return False
    if isinstance(val, str):
        cleaned = val.strip().lower()
        if not cleaned or cleaned in ("none", "null", "n/a", "na", "-", "undefined", "nan"):
            return False
    return True


class CompanyRecord(BaseModel):
    """Pydantic model representing a company record with dynamic row fields."""
    id: Optional[str] = None
    source_collection: Optional[str] = Field(None, description="The MongoDB collection name this record belongs to")
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    designation: Optional[str] = None
    linkedin_url: Optional[str] = None
    mobile_no: Optional[str] = None
    landline_telephone: Optional[str] = None
    landline_other_no: Optional[str] = None
    telephone_1: Optional[str] = None
    telephone_2: Optional[str] = None
    email: Optional[str] = None
    email_1: Optional[str] = None
    email_2: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pin: Optional[str] = None
    group: Optional[str] = None
    records_merged: Optional[Any] = None
    review_required: Optional[Any] = None
    sources: Optional[Any] = None
    remarks: Optional[str] = None


def format_mongo_document(doc: Dict[str, Any], collection_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalizes a MongoDB document and ONLY includes fields that actually have a row value.
    Missing, empty, or null columns are omitted so only populated row values are shown.
    """
    if not doc or not isinstance(doc, dict):
        return {}

    result: Dict[str, Any] = {}

    # Extract ID
    if "_id" in doc:
        result["id"] = str(doc["_id"])
    elif "id" in doc:
        result["id"] = str(doc["id"])

    # Source collection tag
    src_col = (
        collection_name 
        or doc.get("source_collection") 
        or doc.get("_collection") 
        or None
    )
    if src_col:
        result["source_collection"] = src_col

    # Create mapping of normalized keys to original values
    doc_index = {}
    for k, v in doc.items():
        if k in ("_id", "created_at", "updated_at", "source_collection", "_collection"):
            continue
        if is_valid_value(v):
            norm_k = re.sub(r"[^a-zA-Z0-9]", "", k.lower())
            doc_index[norm_k] = v

    # Populate canonical fields ONLY if they have a valid value
    for col in CANONICAL_COLUMNS:
        norm = re.sub(r"[^a-zA-Z0-9]", "", col.lower())
        if norm in doc_index:
            val = doc_index[norm]
            if is_valid_value(val):
                result[col] = val

    # Include any additional extra keys present in document with valid values
    for k, v in doc.items():
        if k in ("_id", "created_at", "updated_at", "id", "source_collection", "_collection"):
            continue
        if is_valid_value(v):
            norm_k = re.sub(r"[^a-zA-Z0-9]", "", k.lower())
            canonical_name = NORMALIZED_KEY_MAP.get(norm_k)
            if not canonical_name or canonical_name not in result:
                result[k] = v

    return result
