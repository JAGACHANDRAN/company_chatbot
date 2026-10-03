import io
import os
import math
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse

from ..schemas import (
    AdminCollectionsResponse,
    AdminCleanPreviewRequest,
    AdminCleanPreviewResponse,
    AdminCleanApplyRequest,
    AdminCleanApplyResponse,
    ChangesPageResponse
)
from ..config import PRIVACY_MODE
from ..database import get_database, get_configured_collection_names
from ..services.auth import require_role, ROLE_DATA_UPLOADER
from ..services import data_cleaner
from ..services.contact_search import invalidate_vocab, check_uncleaned_collections
from ..services.existing_data_cleaner import (
    clean_collection,
    get_configured_collections_with_counts,
    copy_collection_indexes,
    DEFAULT_IGNORE
)
from ..services.preview_cache import (
    store_collection_preview,
    get_preview,
    delete_preview
)

# Admin / Uploader Role Guard
require_admin_or_uploader = require_role(
    ROLE_DATA_UPLOADER,
    "Admin or data uploader privileges required."
)

router = APIRouter(prefix="/api/admin/clean", tags=["Admin Data Cleaning"])


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


@router.get("/collections", response_model=AdminCollectionsResponse, dependencies=[Depends(require_admin_or_uploader)])
async def get_admin_collections(
    current_user: dict = Depends(require_admin_or_uploader)
):
    """
    Returns all configured MongoDB collections along with document counts,
    backup flags, and cleaned status flags.
    """
    db = get_database()
    results = get_configured_collections_with_counts(db, os.environ)
    return AdminCollectionsResponse(success=True, collections=results)


@router.post("/preview", response_model=AdminCleanPreviewResponse, dependencies=[Depends(require_admin_or_uploader)])
async def preview_clean_existing_collection(
    body: AdminCleanPreviewRequest,
    current_user: dict = Depends(require_admin_or_uploader)
):
    """
    READ-ONLY: Runs deterministic offline data cleaner over the selected collection.
    Attaches source_doc_id to every change and cleaned row.
    Caches the result in memory (15-min TTL) and returns the report without modifying MongoDB.
    Never logs record contents.
    """
    db = get_database()
    collection_name = body.collection.strip()

    if collection_name not in db.list_collection_names():
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{collection_name}' not found in MongoDB database."
        )

    ignore = set(DEFAULT_IGNORE)
    if body.ignore_fields:
        ignore.update(f.strip() for f in body.ignore_fields if f.strip())

    clean_result, out_rows, doc_ids = clean_collection(db, collection_name, ignore=ignore)
    if clean_result is None or not out_rows:
        raise HTTPException(
            status_code=400,
            detail=f"Collection '{collection_name}' is empty or contains zero usable records."
        )

    report = data_cleaner.build_report(clean_result)

    preview_id = store_collection_preview(
        user_id=current_user.get("user_id", "admin_user"),
        collection=collection_name,
        clean_result=clean_result,
        report=report,
        cleaned_rows=out_rows,
        original_ids=doc_ids
    )

    all_changes = report["changes"]
    total_changes = len(all_changes)
    preview_changes = all_changes[:1000]
    cleaned_preview = out_rows[:50]

    # Safe log: only print collection name and row counts, never record values
    print(
        f"[Admin Clean Preview] Collection: {collection_name} | "
        f"Docs in: {report['summary']['rows_in']} | Rows out: {report['summary']['rows_out']} | "
        f"Needs review: {report['summary']['needs_review']}"
    )

    return AdminCleanPreviewResponse(
        success=True,
        preview_id=preview_id,
        collection=collection_name,
        summary=sanitize_for_json(report["summary"]),
        column_mapping=sanitize_for_json(report["column_mapping"]),
        changes=sanitize_for_json(preview_changes),
        total_changes=total_changes,
        needs_review=sanitize_for_json(report["needs_review"]),
        cleaned_preview=sanitize_for_json(cleaned_preview),
        message=f"Preview generated for '{collection_name}'. Review changes before confirming."
    )


@router.get("/preview/{preview_id}/changes", response_model=ChangesPageResponse, dependencies=[Depends(require_admin_or_uploader)])
async def get_admin_preview_changes(
    preview_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    action: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin_or_uploader)
):
    """
    Paginated changes for active collection cleaning preview.
    """
    item = get_preview(preview_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Preview expired or not found. Please run preview again."
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


@router.get("/preview/{preview_id}/report.xlsx", dependencies=[Depends(require_admin_or_uploader)])
async def download_admin_preview_report(
    preview_id: str,
    current_user: dict = Depends(require_admin_or_uploader)
):
    """
    Downloads multi-sheet Excel audit report generated from in-memory preview cache.
    """
    item = get_preview(preview_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Preview expired or not found. Please run preview again."
        )

    buffer = io.BytesIO()
    data_cleaner.write_report_xlsx(item["report"], buffer)
    buffer.seek(0)

    col_name = item.get("collection", "collection")
    download_filename = f"{col_name}_cleaning_report.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_filename}"'}
    )


@router.post("/apply", response_model=AdminCleanApplyResponse, dependencies=[Depends(require_admin_or_uploader)])
async def apply_admin_clean(
    body: AdminCleanApplyRequest,
    current_user: dict = Depends(require_admin_or_uploader)
):
    """
    Applies the cleaning to MongoDB in one of two modes:
    1. 'new_collection': writes <collection>_cleaned (drops first if exists), leaves original untouched.
    2. 'replace':
       - Requires admin to type the exact collection name in confirm_name.
       - Backs up original to <collection>_backup (aborts if backup name already exists).
       - Verifies backup count equals original count.
       - Clears original and inserts cleaned rows.
       - If any step fails, automatically rolls back and restores from backup.
    Never logs record contents.
    """
    item = get_preview(body.preview_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Preview expired or not found. Please run preview again."
        )

    collection_name = item.get("collection", "")
    cleaned_rows = item.get("cleaned_rows", [])
    if not collection_name or not cleaned_rows:
        raise HTTPException(
            status_code=400,
            detail="Preview contains no valid collection or cleaned records."
        )

    mode = body.mode.strip().lower()
    if mode not in ("new_collection", "replace"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{body.mode}'. Supported modes: 'new_collection', 'replace'."
        )

    db = get_database()
    next_steps: List[str] = []

    # ---------------------------------------------------------------------------
    # Mode 1: new_collection (Safe copy)
    # ---------------------------------------------------------------------------
    if mode == "new_collection":
        target_name = f"{collection_name}_cleaned"
        target_col = db[target_name]
        source_col = db[collection_name]

        # Drop target if it already exists
        target_col.drop()

        # Insert cleaned rows in batches
        for i in range(0, len(cleaned_rows), 1000):
            target_col.insert_many(cleaned_rows[i:i + 1000])

        # Copy original collection indexes
        copy_collection_indexes(source_col, target_col)

        # Free preview from memory
        delete_preview(body.preview_id)

        next_steps.append(
            f"Point MONGODB_COLLECTIONS in backend/.env to include '{target_name}' instead of '{collection_name}'."
        )
        if PRIVACY_MODE:
            next_steps.append(
                "PRIVACY_MODE is ON: No embeddings are created. Text-index and regex search will be used immediately."
            )
        else:
            next_steps.append(
                "Vector Search is ENABLED: Remember to rebuild embeddings for the new collection."
            )

        invalidate_vocab()

        print(
            f"[Admin Clean Apply: new_collection] Source: {collection_name} | "
            f"Target: {target_name} | Rows written: {len(cleaned_rows)}"
        )

        return AdminCleanApplyResponse(
            success=True,
            mode=mode,
            collection=collection_name,
            target_collection=target_name,
            rows_written=len(cleaned_rows),
            backup_collection=None,
            message=f"Cleaned records successfully written to '{target_name}'. Original collection '{collection_name}' was left untouched.",
            next_steps=next_steps,
            privacy_mode_active=PRIVACY_MODE,
            requires_embedding_rebuild=not PRIVACY_MODE
        )

    # ---------------------------------------------------------------------------
    # Mode 2: replace (Destructive with verified backup & rollback)
    # ---------------------------------------------------------------------------
    if mode == "replace":
        # Strict validation: admin must type the exact collection name
        typed_confirm = (body.confirm_name or "").strip()
        if typed_confirm != collection_name:
            raise HTTPException(
                status_code=400,
                detail=f"Confirmation mismatch. You typed '{typed_confirm}', but '{collection_name}' is required to confirm replacement."
            )

        backup_name = f"{collection_name}_backup"
        existing_cols = db.list_collection_names()

        # Step 1: Check if backup already exists
        if backup_name in existing_cols:
            raise HTTPException(
                status_code=400,
                detail=f"Backup collection '{backup_name}' already exists. Please rename or drop it first before replacing '{collection_name}'."
            )

        source_col = db[collection_name]
        backup_col = db[backup_name]

        # Copy all original documents
        originals = list(source_col.find({}))
        original_count = len(originals)
        if originals:
            backup_col.insert_many(originals)
        copy_collection_indexes(source_col, backup_col)

        # Step 2: Verify backup count equals original count
        backup_count = backup_col.count_documents({})
        if backup_count != original_count:
            backup_col.drop()
            raise HTTPException(
                status_code=500,
                detail=f"Backup verification failed: expected {original_count} documents in '{backup_name}', found {backup_count}. Original collection '{collection_name}' was left untouched."
            )

        # Step 3: Delete original documents and Step 4: Insert cleaned rows
        try:
            source_col.delete_many({})
            for i in range(0, len(cleaned_rows), 1000):
                source_col.insert_many(cleaned_rows[i:i + 1000])
        except Exception as e:
            # ROLLBACK: restore original documents from backup
            print(f"[REPLACE ERROR - ROLLING BACK] Restoring {collection_name} from {backup_name} due to: {e}")
            try:
                source_col.delete_many({})
                if originals:
                    source_col.insert_many(originals)
            except Exception as rollback_err:
                print(f"[CRITICAL ROLLBACK FAILURE] {rollback_err}")

            raise HTTPException(
                status_code=500,
                detail=f"Error occurred while writing cleaned rows to '{collection_name}': {str(e)}. Original collection was restored from '{backup_name}'."
            )

        # Free preview from memory
        delete_preview(body.preview_id)

        # Invalidate vocabulary cache after data replacement
        invalidate_vocab()

        next_steps.append(
            f"Original documents were safely backed up to '{backup_name}' ({original_count} records)."
        )
        next_steps.append(
            f"Collection '{collection_name}' now contains {len(cleaned_rows)} cleaned records."
        )
        if PRIVACY_MODE:
            next_steps.append(
                "PRIVACY_MODE is ON: Search text indexes are maintained. No external embeddings are needed."
            )
        else:
            next_steps.append(
                "Vector Search is ENABLED: Remember to rebuild embeddings for replaced records."
            )

        print(
            f"[Admin Clean Apply: replace] Collection: {collection_name} | "
            f"Backup: {backup_name} | Rows replaced: {len(cleaned_rows)}"
        )

        return AdminCleanApplyResponse(
            success=True,
            mode=mode,
            collection=collection_name,
            target_collection=collection_name,
            rows_written=len(cleaned_rows),
            backup_collection=backup_name,
            message=f"Collection '{collection_name}' was successfully replaced with {len(cleaned_rows)} cleaned records. Original documents backed up to '{backup_name}'.",
            next_steps=next_steps,
            privacy_mode_active=PRIVACY_MODE,
            requires_embedding_rebuild=not PRIVACY_MODE
        )


@router.get("/status")
def get_clean_status():
    """
    Checks if any configured collection has uncleaned records (missing norm_company).
    Returns uncleaned status for frontend banner warning.
    """
    db = get_database()
    configured = get_configured_collection_names()
    uncleaned = check_uncleaned_collections(db, configured)
    return {
        "has_uncleaned": len(uncleaned) > 0,
        "uncleaned_collections": uncleaned,
        "message": "This dataset is not cleaned yet; search quality is reduced. Clean it first." if uncleaned else "All datasets cleaned."
    }

