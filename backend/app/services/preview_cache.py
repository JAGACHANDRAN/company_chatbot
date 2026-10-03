import time
import uuid
from typing import Dict, Any, Optional, List
from threading import Lock

PREVIEW_TTL_SECONDS = 60 * 60  # 1 hour
MAX_PREVIEWS_PER_USER = 100

_cache: Dict[str, Dict[str, Any]] = {}
_lock = Lock()


def _prune_expired():
    """Removes all expired preview entries from memory."""
    now = time.time()
    expired_ids = [pid for pid, item in _cache.items() if item["expires_at"] <= now]
    for pid in expired_ids:
        _cache.pop(pid, None)


def store_preview(user_id: str, filename: str, file_bytes: bytes, clean_result: Any, report: Dict[str, Any]) -> str:
    """
    Stores CleanResult and in-memory file bytes for preview.
    Enforces 15-minute TTL and max preview limit per user.
    """
    with _lock:
        _prune_expired()
        
        # Check active preview count for this user
        user_previews = [pid for pid, item in _cache.items() if item.get("user_id") == user_id]
        if len(user_previews) >= MAX_PREVIEWS_PER_USER:
            # Sort by created_at and evict the oldest
            user_previews.sort(key=lambda pid: _cache[pid]["created_at"])
            oldest_id = user_previews[0]
            _cache.pop(oldest_id, None)

        preview_id = f"prev_{uuid.uuid4().hex[:16]}"
        now = time.time()
        _cache[preview_id] = {
            "preview_id": preview_id,
            "user_id": user_id,
            "filename": filename,
            "file_bytes": file_bytes,
            "result": clean_result,
            "report": report,
            "created_at": now,
            "expires_at": now + PREVIEW_TTL_SECONDS,
        }
        return preview_id


def store_collection_preview(
    user_id: str,
    collection: str,
    clean_result: Any,
    report: Dict[str, Any],
    cleaned_rows: List[Dict[str, Any]],
    original_ids: List[str]
) -> str:
    """
    Stores CleanResult and prepared rows for an existing collection preview.
    Enforces 15-minute TTL and max preview limit per user.
    """
    with _lock:
        _prune_expired()
        user_previews = [pid for pid, item in _cache.items() if item.get("user_id") == user_id]
        if len(user_previews) >= MAX_PREVIEWS_PER_USER:
            user_previews.sort(key=lambda pid: _cache[pid]["created_at"])
            _cache.pop(user_previews[0], None)

        preview_id = f"prev_col_{uuid.uuid4().hex[:16]}"
        now = time.time()
        _cache[preview_id] = {
            "preview_id": preview_id,
            "user_id": user_id,
            "collection": collection,
            "filename": f"{collection}.json",
            "result": clean_result,
            "report": report,
            "cleaned_rows": cleaned_rows,
            "original_ids": original_ids,
            "created_at": now,
            "expires_at": now + PREVIEW_TTL_SECONDS,
        }
        return preview_id


def get_preview(preview_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an active, unexpired preview from memory."""
    with _lock:
        _prune_expired()
        item = _cache.get(preview_id)
        if not item:
            return None
        if item["expires_at"] <= time.time():
            _cache.pop(preview_id, None)
            return None
        return item


def delete_preview(preview_id: str) -> bool:
    """Deletes preview and frees in-memory bytes."""
    with _lock:
        if preview_id in _cache:
            _cache.pop(preview_id, None)
            return True
        return False


def clear_all_previews():
    """Clears all previews (used in testing)."""
    with _lock:
        _cache.clear()
