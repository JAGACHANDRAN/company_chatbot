from typing import Optional, Any, List, Union, Dict, Literal
from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Natural language search query or direct search term from user")
    dataset_id: Optional[str] = Field(None, description="Optional dataset ID to scope search to a specific uploaded dataset")


class QueryCondition(BaseModel):
    concept: Optional[str] = Field(None, description="Semantic concept e.g. location, company, person, designation, email, phone")
    field: Optional[str] = Field(None, description="Validated dataset field used as a search condition")
    operator: str = Field("contains", description="Operator: equals, contains, starts_with, ends_with")
    value: str = Field(..., description="Extracted search value")

    @model_validator(mode="before")
    @classmethod
    def populate_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # If field is provided but concept isn't, or vice-versa
            if not data.get("field") and not data.get("concept"):
                data["concept"] = "company"
            if not data.get("operator"):
                data["operator"] = "contains"
        return data


class QueryIntent(BaseModel):
    intent: str = Field("search_records", description="Intent: search_records, lookup_field, person_search, company_search")
    conditions: List[QueryCondition] = Field(default_factory=list)
    logic: str = Field("AND", description="Logic operator: AND, OR")
    return_fields: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def adapt_legacy_intent(cls, value: Any) -> Any:
        if isinstance(value, dict) and "conditions" not in value and value.get("field") and value.get("value"):
            value = dict(value)
            value["conditions"] = [{
                "concept": value.get("concept"),
                "field": value["field"],
                "operator": value.get("operator") or "contains",
                "value": value["value"],
            }]
        return value

    @property
    def field(self) -> Optional[str]:
        return self.conditions[0].field if self.conditions else None

    @property
    def operator(self) -> Optional[str]:
        return self.conditions[0].operator if self.conditions else None

    @property
    def value(self) -> Optional[str]:
        return self.conditions[0].value if self.conditions else None


class LookupResult(BaseModel):
    """Used when intent=lookup_field — a field-scoped answer extracted directly from MongoDB."""
    matched_entity: Optional[str] = None          # e.g. "2D Inc"
    requested_fields: Optional[List[str]] = None   # e.g. ["Email"]
    field_values: Optional[Dict[str, Any]] = None  # e.g. {"Email": "contact@2dinc.com"}


class ChatResponse(BaseModel):
    success: bool = True
    found: bool = False
    count: int = 0
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    database: Optional[str] = "MongoDB Atlas"
    dataset: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    data: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    query_intent: Optional[Any] = None
    lookup_result: Optional[LookupResult] = None
    message: Optional[str] = None


class DatasetUploadResponse(BaseModel):
    success: bool = True
    dataset_id: str
    filename: str
    original_type: str
    sheet_name: Optional[str] = None
    record_count: int
    fields: List[str]
    normalized_fields: Optional[List[str]] = None
    sample_records: Optional[List[Dict[str, Any]]] = None
    message: str = "Dataset uploaded and processed successfully."


class DatasetInspectResponse(BaseModel):
    success: bool = True
    filename: str
    original_type: str
    available_sheets: Optional[List[str]] = None
    fields: List[str]
    sample_records: List[Dict[str, Any]]
    total_records_detected: int


class DatasetSummary(BaseModel):
    dataset_id: str
    filename: str
    original_type: str
    sheet_name: Optional[str] = None
    created_at: str
    record_count: int
    fields: List[str]
    normalized_fields: Optional[List[str]] = None


class DatasetListResponse(BaseModel):
    success: bool = True
    count: int = 0
    datasets: List[Dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    details: Optional[str] = None
    total_uploaded_datasets: Optional[int] = 0
