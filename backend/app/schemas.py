from typing import Optional, Any, List, Union, Dict, Literal
from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Natural language search query or direct search term from user")
    dataset_id: Optional[str] = Field(None, description="Optional dataset ID to scope search to a specific uploaded dataset")
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Optional recent chat history turns")
    explain: Optional[bool] = Field(False, description="Optional flag to return retrieval stage breakdown in meta.stages")
    conversation_id: Optional[str] = Field(None, description="Optional conversation/session ID")
    session_id: Optional[str] = Field(None, description="Optional session ID")


class FeedbackRequest(BaseModel):
    conversation_id: str = Field(..., description="Conversation or session ID of the trace")
    message_id: Optional[str] = Field(None, description="Optional message ID")
    rating: Literal["up", "down"] = Field(..., description="Thumbs up or thumbs down rating")
    comment: Optional[str] = Field(None, description="Optional user comment (will be PII masked)")


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
    understood_as: Optional[List[str]] = None
    groups: Optional[List[Dict[str, Any]]] = None
    not_found: Optional[List[str]] = None
    suggestions: Optional[Union[List[str], Dict[str, Any]]] = None
    notes: Optional[List[str]] = None
    retrieval_mode: Optional[str] = None
    total: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


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


class LoginRequest(BaseModel):
    email: str = Field(..., description="Authorized user email address")
    password: str = Field(..., description="User password")


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class DatasetPreviewResponse(BaseModel):
    success: bool = True
    preview_id: str
    filename: str
    summary: Dict[str, Any]
    column_mapping: List[Dict[str, Any]]
    changes: List[Dict[str, Any]]
    total_changes: int = 0
    needs_review: List[Dict[str, Any]]
    cleaned_preview: List[Dict[str, Any]] = Field(default_factory=list)
    cleaned_rows: Optional[List[Dict[str, Any]]] = None
    has_usable_rows: bool = True
    message: Optional[str] = None
    re_preview: Optional[bool] = False
    is_fully_clean: bool = False


class ChangesPageResponse(BaseModel):
    success: bool = True
    total: int = 0
    offset: int = 0
    limit: int = 100
    changes: List[Dict[str, Any]] = Field(default_factory=list)


class DatasetConfirmRequest(BaseModel):
    preview_id: str
    dataset_name: Optional[str] = None
    mode: str = "append"  # "append" or "replace"
    column_mapping: Optional[Dict[str, Optional[str]]] = None


class DatasetConfirmResponse(BaseModel):
    success: bool = True
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    filename: Optional[str] = None
    inserted: int = 0
    skipped: int = 0
    total_records: int = 0
    message: str = "Dataset successfully confirmed and saved to MongoDB."
    re_preview: Optional[bool] = False
    preview_id: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    column_mapping: Optional[List[Dict[str, Any]]] = None
    changes: Optional[List[Dict[str, Any]]] = None
    total_changes: Optional[int] = 0
    needs_review: Optional[List[Dict[str, Any]]] = None
    cleaned_preview: Optional[List[Dict[str, Any]]] = None
    cleaned_rows: Optional[List[Dict[str, Any]]] = None
    has_usable_rows: Optional[bool] = True


class AdminCollectionInfo(BaseModel):
    name: str
    count: int = 0
    exists: bool = True
    is_backup: bool = False
    is_cleaned: bool = False
    has_backup: bool = False
    has_cleaned: bool = False


class AdminCollectionsResponse(BaseModel):
    success: bool = True
    collections: List[AdminCollectionInfo]


class AdminCleanPreviewRequest(BaseModel):
    collection: str = Field(..., description="Target MongoDB collection to preview cleaning for")
    ignore_fields: Optional[List[str]] = Field(default=None, description="Optional extra field names to ignore")


class AdminCleanPreviewResponse(BaseModel):
    success: bool = True
    preview_id: str
    collection: str
    summary: Dict[str, Any]
    column_mapping: List[Dict[str, Any]]
    changes: List[Dict[str, Any]]
    total_changes: int = 0
    needs_review: List[Dict[str, Any]]
    cleaned_preview: List[Dict[str, Any]] = Field(default_factory=list)
    message: Optional[str] = None


class AdminCleanApplyRequest(BaseModel):
    preview_id: str
    mode: str = Field(..., description="'new_collection' or 'replace'")
    confirm_name: Optional[str] = Field(default=None, description="Exact collection name must be typed for 'replace' mode")


class AdminCleanApplyResponse(BaseModel):
    success: bool = True
    mode: str
    collection: str
    target_collection: str
    rows_written: int = 0
    backup_collection: Optional[str] = None
    message: str
    next_steps: List[str] = Field(default_factory=list)
    privacy_mode_active: bool = False
    requires_embedding_rebuild: bool = False


