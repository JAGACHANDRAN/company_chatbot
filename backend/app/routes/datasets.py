from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from ..schemas import (
    DatasetUploadResponse,
    DatasetInspectResponse,
    DatasetListResponse,
    DatasetSummary
)
from ..services.file_parser import parse_uploaded_file, inspect_excel_sheets, detect_file_extension
from ..services.schema_detector import build_schema_metadata, normalize_records
from ..services.mongo_dataset import (
    save_dataset,
    list_datasets,
    get_dataset,
    delete_dataset,
    get_dataset_sample
)
from ..services.auth import require_role, ROLE_DATA_UPLOADER

# Role guards
require_uploader = require_role(ROLE_DATA_UPLOADER, "You do not have permission to upload files.")
require_deleter = require_role(ROLE_DATA_UPLOADER, "You do not have permission to delete datasets.")

router = APIRouter(prefix="/api/datasets", tags=["Dataset Management & Upload"])
alias_router = APIRouter(prefix="/api", tags=["Upload Alias"])


@router.post("/inspect", response_model=DatasetInspectResponse, dependencies=[Depends(require_uploader)])
async def inspect_dataset_file(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    current_user: dict = Depends(require_uploader)
):
    """
    Inspects an uploaded data file without saving to database.
    Requires DATA_UPLOADER role. Rejects unauthorized attempts with HTTP 403 / 401.
    """
    filename = file.filename or "uploaded_data"
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        ext = detect_file_extension(filename)
        available_sheets = []
        if ext in (".xlsx", ".xls"):
            try:
                available_sheets = inspect_excel_sheets(content)
            except Exception:
                available_sheets = []

        headers, records, metadata = parse_uploaded_file(filename, content, sheet_name=sheet_name)

        return DatasetInspectResponse(
            success=True,
            filename=filename,
            original_type=metadata.get("original_type", ext.lstrip(".")),
            available_sheets=available_sheets if len(available_sheets) > 1 else None,
            fields=headers,
            sample_records=records[:5],
            total_records_detected=len(records)
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Dataset Inspect Error] {e}")
        raise HTTPException(status_code=500, detail="Could not inspect the file. Please check file format.")


@router.post("/upload", response_model=DatasetUploadResponse, dependencies=[Depends(require_uploader)])
async def upload_dataset_file(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    current_user: dict = Depends(require_uploader)
):
    """
    Main Data Upload Endpoint.
    Requires DATA_UPLOADER role.
    Order of operations:
    1. Authenticate user.
    2. Retrieve trusted user role from token.
    3. Check DATA_UPLOADER permission (done before reading or processing file).
    4. Clean and parse uploaded file.
    5. Build schema and normalize fields.
    6. Store dataset records safely in MongoDB.
    """
    filename = file.filename or "uploaded_dataset"
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        # 1. Parse file safely
        headers, records, metadata = parse_uploaded_file(filename, content, sheet_name=sheet_name)

        # 2. Build schema & normalize fields
        schema_meta = build_schema_metadata(headers, records)
        normalized_records = normalize_records(
            headers=headers,
            records=records,
            field_mapping=schema_meta["field_mapping"]
        )

        # 3. Store in MongoDB
        saved = save_dataset(
            filename=filename,
            original_type=metadata.get("original_type", "data"),
            original_fields=schema_meta["original_fields"],
            normalized_fields=schema_meta["normalized_fields"],
            field_mapping=schema_meta["field_mapping"],
            field_types=schema_meta["field_types"],
            normalized_records=normalized_records,
            sheet_name=metadata.get("sheet_name"),
            size_bytes=len(content)
        )

        # Get first 3 sample records for preview in frontend
        sample_preview = [r["data"] for r in normalized_records[:3]]

        return DatasetUploadResponse(
            success=True,
            dataset_id=saved["dataset_id"],
            filename=saved["filename"],
            original_type=saved["original_type"],
            sheet_name=saved.get("sheet_name"),
            record_count=saved["record_count"],
            fields=saved["fields"],
            normalized_fields=saved["normalized_fields"],
            sample_records=sample_preview,
            message=f"Dataset '{filename}' ({saved['record_count']:,} records, {len(saved['fields'])} columns) ready for AI search."
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Dataset Upload Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process and save dataset: {str(e)}")


@alias_router.post("/upload", response_model=DatasetUploadResponse, dependencies=[Depends(require_uploader)])
async def direct_upload_alias(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    current_user: dict = Depends(require_uploader)
):
    """
    Direct alias endpoint at /api/upload.
    Enforces identical strict DATA_UPLOADER check and authorization flow.
    """
    return await upload_dataset_file(file=file, sheet_name=sheet_name, current_user=current_user)


@router.get("", response_model=DatasetListResponse)
def get_all_datasets():
    """Returns list of all uploaded datasets."""
    try:
        datasets = list_datasets()
        return DatasetListResponse(
            success=True,
            count=len(datasets),
            datasets=datasets
        )
    except Exception as e:
        print(f"[List Datasets Error] {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve datasets from MongoDB.")


@router.get("/{dataset_id}")
def get_dataset_details(dataset_id: str):
    """Returns metadata and sample records for a specific dataset."""
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    
    samples = get_dataset_sample(dataset_id, limit=8)
    return {
        "success": True,
        "dataset": dataset,
        "samples": samples
    }


@router.delete("/{dataset_id}", dependencies=[Depends(require_deleter)])
def delete_dataset_endpoint(
    dataset_id: str,
    current_user: dict = Depends(require_deleter)
):
    """
    Deletes an uploaded dataset and its associated records from MongoDB.
    Requires DATA_UPLOADER role.
    """
    success = delete_dataset(dataset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dataset not found or could not be deleted.")
    return {
        "success": True,
        "dataset_id": dataset_id,
        "message": "Dataset and all associated records have been permanently deleted."
    }
