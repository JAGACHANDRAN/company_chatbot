import io
import math
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from ..schemas import (
    DatasetUploadResponse,
    DatasetInspectResponse,
    DatasetListResponse,
    DatasetSummary,
    DatasetPreviewResponse,
    DatasetConfirmRequest,
    DatasetConfirmResponse,
    ChangesPageResponse
)
from ..services.file_parser import parse_uploaded_file, inspect_excel_sheets, detect_file_extension
from ..services.schema_detector import build_schema_metadata, normalize_records
from ..services.mongo_dataset import (
    save_dataset,
    save_cleaned_dataset,
    list_datasets,
    get_dataset,
    delete_dataset,
    get_dataset_sample
)
from ..services.auth import require_role, ROLE_DATA_UPLOADER
from ..services import data_cleaner
from ..services.contact_search import invalidate_vocab
from ..services.preview_cache import store_preview, get_preview, delete_preview

# Role guards
require_uploader = require_role(ROLE_DATA_UPLOADER, "You do not have permission to upload files.")
require_deleter = require_role(ROLE_DATA_UPLOADER, "You do not have permission to delete datasets.")

router = APIRouter(prefix="/api/datasets", tags=["Dataset Management & Upload"])
alias_router = APIRouter(prefix="/api", tags=["Upload Alias"])


def sanitize_for_json(val: Any) -> Any:
    """
    Recursively sanitize objects for valid RFC 8259 JSON serialization:
    - Replaces float('nan'), float('inf'), -float('inf') with ""
    - Converts datetime, date, pd.Timestamp to ISO strings
    - Converts numpy scalars / types to native Python types
    - Converts dicts and lists recursively
    """
    if val is None:
        return ""
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return ""
        return val
    if hasattr(val, "item"):
        try:
            return sanitize_for_json(val.item())
        except Exception:
            pass
    if isinstance(val, (datetime, date, pd.Timestamp)):
        return val.isoformat()
    if isinstance(val, dict):
        return {str(k): sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [sanitize_for_json(v) for v in val]
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    return val


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


@router.post("/upload/preview", response_model=DatasetPreviewResponse, dependencies=[Depends(require_uploader)])
async def preview_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_uploader)
):
    """
    Step 1 of Cleaning Pipeline:
    - Reads file bytes into server memory (no raw disk/MongoDB storage).
    - Cleans records deterministically using data_cleaner.
    - Builds a detailed audit report.
    - Caches CleanResult in memory keyed by preview_id (15-min TTL, per-user limit).
    - Returns report and first 50 cleaned rows without saving to MongoDB.
    """
    filename = file.filename or "uploaded_data"
    ext = detect_file_extension(filename)
    if ext not in (".csv", ".xlsx", ".xlsm", ".xls"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported formats: .xlsx, .xls, .csv."
        )

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        clean_result = data_cleaner.clean_file(content, filename)
        report = data_cleaner.build_report(clean_result)

        preview_id = store_preview(
            user_id=current_user.get("user_id", "default_uploader"),
            filename=filename,
            file_bytes=content,
            clean_result=clean_result,
            report=report
        )

        has_usable = len(clean_result.rows) > 0
        msg = None
        if not has_usable:
            msg = "Warning: Zero usable contact records were detected in this file."

        # Safe logging: log ONLY file name and row counts, never cell values
        print(f"[Upload Preview] File: {filename} | Rows in: {report['summary']['rows_in']} | Rows out: {report['summary']['rows_out']} | Needs review: {report['summary']['needs_review']}")

        all_changes = report["changes"]
        total_changes = len(all_changes)
        preview_changes = all_changes[:1000]
        cleaned_preview = clean_result.rows[:50]

        return DatasetPreviewResponse(
            success=True,
            preview_id=preview_id,
            filename=filename,
            summary=sanitize_for_json(report["summary"]),
            column_mapping=sanitize_for_json(report["column_mapping"]),
            changes=sanitize_for_json(preview_changes),
            total_changes=total_changes,
            needs_review=sanitize_for_json(report["needs_review"]),
            cleaned_preview=sanitize_for_json(cleaned_preview),
            cleaned_rows=sanitize_for_json(cleaned_preview),
            has_usable_rows=has_usable,
            message=msg,
            is_fully_clean=report.get("is_fully_clean", len(all_changes) == 0)
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Upload Preview Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to preview dataset: {str(e)}")


@router.get("/upload/preview/{preview_id}/changes", response_model=ChangesPageResponse, dependencies=[Depends(require_uploader)])
async def get_preview_changes(
    preview_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    action: Optional[str] = Query(None),
    current_user: dict = Depends(require_uploader)
):
    """
    Paginated changes for large files so UI remains smooth and responsive.
    """
    item = get_preview(preview_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Preview expired or not found. Please upload the file again."
        )

    all_changes = item["report"].get("changes", [])
    if action and action != "all":
        all_changes = [c for c in all_changes if c.get("action") == action]

    total = len(all_changes)
    paged = all_changes[offset : offset + limit]

    return ChangesPageResponse(
        success=True,
        total=total,
        offset=offset,
        limit=limit,
        changes=sanitize_for_json(paged)
    )


@router.get("/upload/preview/{preview_id}/report.xlsx", dependencies=[Depends(require_uploader)])
async def download_preview_report(
    preview_id: str,
    current_user: dict = Depends(require_uploader)
):
    """
    Generates and downloads the multi-sheet Excel audit report from in-memory preview cache.
    """
    item = get_preview(preview_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Preview expired or not found. Please upload the file again."
        )

    buffer = io.BytesIO()
    data_cleaner.write_report_xlsx(item["report"], buffer)
    buffer.seek(0)

    clean_stem = Path(item["filename"]).stem
    download_filename = f"{clean_stem}_report.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'}
    )


@router.post("/upload/confirm", response_model=DatasetConfirmResponse, dependencies=[Depends(require_uploader)])
async def confirm_upload(
    body: DatasetConfirmRequest,
    current_user: dict = Depends(require_uploader)
):
    """
    Step 2/3 of Cleaning Pipeline:
    - If user provides corrected column_mapping: re-cleans the cached upload in memory,
      returns a NEW preview and report so the user sees the effect before saving.
    - If confirmed unchanged: inserts ONLY cleaned rows into MongoDB, updates uploaded_at,
      and removes the preview from memory.
    - 'append' mode skips rows already in the collection (same norm_company + person + phone/email).
    - Blocks saving when the file has zero usable rows.
    """
    item = get_preview(body.preview_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Preview expired or not found. Please upload the file again."
        )

    # 1. If corrected column mapping provided, re-clean and return new preview
    if body.column_mapping:
        try:
            new_result = data_cleaner.clean_file(
                item["file_bytes"],
                item["filename"],
                custom_mapping=body.column_mapping
            )
            new_report = data_cleaner.build_report(new_result)
            new_preview_id = store_preview(
                user_id=current_user.get("user_id", "default_uploader"),
                filename=item["filename"],
                file_bytes=item["file_bytes"],
                clean_result=new_result,
                report=new_report
            )
            # Remove previous preview
            delete_preview(body.preview_id)

            new_all_changes = new_report["changes"]
            new_total_changes = len(new_all_changes)
            new_preview_changes = new_all_changes[:1000]
            new_cleaned_preview = new_result.rows[:50]

            return DatasetConfirmResponse(
                success=True,
                re_preview=True,
                preview_id=new_preview_id,
                filename=item["filename"],
                summary=sanitize_for_json(new_report["summary"]),
                column_mapping=sanitize_for_json(new_report["column_mapping"]),
                changes=sanitize_for_json(new_preview_changes),
                total_changes=new_total_changes,
                needs_review=sanitize_for_json(new_report["needs_review"]),
                cleaned_preview=sanitize_for_json(new_cleaned_preview),
                cleaned_rows=sanitize_for_json(new_cleaned_preview),
                has_usable_rows=len(new_result.rows) > 0,
                message="Preview re-analyzed with updated column mapping. Review the changes before saving."
            )
        except Exception as e:
            print(f"[Re-clean Error] {e}")
            raise HTTPException(status_code=500, detail=f"Failed to re-clean dataset: {str(e)}")

    # 2. Block saving if file has zero usable rows
    clean_rows = item["result"].rows
    if not clean_rows:
        raise HTTPException(
            status_code=400,
            detail="Cannot save dataset: the uploaded file contains zero usable records."
        )

    try:
        save_res = save_cleaned_dataset(
            filename=item["filename"],
            cleaned_rows=clean_rows,
            dataset_name=body.dataset_name,
            mode=body.mode
        )

        # Free preview from memory
        delete_preview(body.preview_id)

        # Invalidate cached vocabulary
        invalidate_vocab()

        return DatasetConfirmResponse(
            success=True,
            dataset_id=save_res.get("dataset_id"),
            dataset_name=save_res.get("dataset_name"),
            filename=save_res.get("filename"),
            inserted=save_res.get("inserted", 0),
            skipped=save_res.get("skipped", 0),
            total_records=save_res.get("total_records", 0),
            message=save_res.get("message", "Dataset successfully cleaned and saved to MongoDB.")
        )
    except Exception as e:
        print(f"[Confirm Upload Error] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save cleaned dataset: {str(e)}")


@router.post("/upload/cancel", dependencies=[Depends(require_uploader)])
async def cancel_upload(
    body: Dict[str, str],
    current_user: dict = Depends(require_uploader)
):
    """
    Discards the cached preview from server memory immediately.
    """
    pid = body.get("preview_id", "")
    if pid:
        delete_preview(pid)
    return {"success": True, "message": "Preview discarded from memory."}


@router.post("/upload", response_model=DatasetUploadResponse, dependencies=[Depends(require_uploader)])
async def upload_dataset_file(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    current_user: dict = Depends(require_uploader)
):
    """
    Direct Data Upload Endpoint.
    Requires DATA_UPLOADER role.
    Cleans file deterministically and stores ONLY cleaned records in MongoDB.
    Raw original rows or temporary files are NEVER persisted.
    """
    filename = file.filename or "uploaded_dataset"
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        ext = detect_file_extension(filename)
        if ext not in (".csv", ".xlsx", ".xlsm", ".xls"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Supported formats: .xlsx, .xls, .csv."
            )

        # Clean file offline deterministically
        clean_result = data_cleaner.clean_file(content, filename)
        if not clean_result.rows:
            raise HTTPException(
                status_code=400,
                detail="Cannot save dataset: the uploaded file contains zero usable records."
            )

        saved = save_cleaned_dataset(
            filename=filename,
            cleaned_rows=clean_result.rows,
            dataset_name=filename,
            mode="append"
        )
        invalidate_vocab()

        sample_preview = [
            {
                "Company Name": r.get("company", ""),
                "Person Name": r.get("person", ""),
                "Designation": r.get("designation", ""),
                "Contact Number": r.get("phone", ""),
                "Email": r.get("email", ""),
            }
            for r in clean_result.rows[:3]
        ]

        return DatasetUploadResponse(
            success=True,
            dataset_id=saved["dataset_id"],
            filename=saved["filename"],
            original_type=ext.lstrip("."),
            sheet_name=sheet_name,
            record_count=saved["inserted"],
            fields=list(data_cleaner.STANDARD_ORDER),
            normalized_fields=list(data_cleaner.STANDARD_ORDER),
            sample_records=sample_preview,
            message=f"Dataset '{filename}' ({saved['inserted']:,} cleaned records saved) ready for AI search."
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
    invalidate_vocab()
    return {
        "success": True,
        "dataset_id": dataset_id,
        "message": "Dataset and all associated records have been permanently deleted."
    }
