import time
from typing import List, Dict, Any, Optional
from threading import Lock

_LOCK = Lock()
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_MAX_STORED_IDS = 1000
_TTL_SECONDS = 3600 * 4  # 4 hours


def _clean_session_id(session_id: Optional[str]) -> str:
    if not session_id or not str(session_id).strip():
        return "default_session"
    return str(session_id).strip()


def store_last_result_set(
    session_id: Optional[str],
    records: List[Dict[str, Any]],
    company: Optional[str] = None,
    entities: Optional[Dict[str, Any]] = None,
    columns_shown: Optional[List[str]] = None
) -> None:
    """
    Stores up to 1000 record _ids and query context for follow-up filtering.
    """
    sid = _clean_session_id(session_id)
    
    # Extract IDs safely
    record_ids: List[str] = []
    for r in records[:_MAX_STORED_IDS]:
        rid = r.get("_id") or r.get("id") or r.get("doc_id")
        if rid is not None:
            record_ids.append(str(rid))

    with _LOCK:
        _SESSIONS[sid] = {
            "original_ids": list(record_ids),
            "current_ids": list(record_ids),
            "company": company or "",
            "entities": entities or {},
            "columns_shown": list(columns_shown or []),
            "filter_stack": [],
            "timestamp": time.time(),
            "total_original": len(record_ids)
        }


def get_last_result_set(session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Retrieves session state if available and not expired."""
    sid = _clean_session_id(session_id)
    with _LOCK:
        data = _SESSIONS.get(sid)
        if not data:
            # Fallback to default_session if specific sid not found
            data = _SESSIONS.get("default_session")
        if not data:
            return None
        if time.time() - data.get("timestamp", 0) > _TTL_SECONDS:
            return None
        return dict(data)


def update_current_result_set(
    session_id: Optional[str],
    filtered_ids: List[str],
    filter_label: str
) -> None:
    """Updates active filtered IDs and records the filter step in the stack."""
    sid = _clean_session_id(session_id)
    with _LOCK:
        if sid not in _SESSIONS and "default_session" in _SESSIONS:
            sid = "default_session"
        if sid in _SESSIONS:
            _SESSIONS[sid]["current_ids"] = list(filtered_ids[:_MAX_STORED_IDS])
            _SESSIONS[sid]["filter_stack"].append({
                "label": filter_label,
                "count": len(filtered_ids),
                "timestamp": time.time()
            })
            _SESSIONS[sid]["timestamp"] = time.time()


def reset_session_filter(session_id: Optional[str]) -> Optional[List[str]]:
    """Restores the original full result set from the initial search."""
    sid = _clean_session_id(session_id)
    with _LOCK:
        if sid not in _SESSIONS and "default_session" in _SESSIONS:
            sid = "default_session"
        if sid in _SESSIONS:
            orig = list(_SESSIONS[sid]["original_ids"])
            _SESSIONS[sid]["current_ids"] = list(orig)
            _SESSIONS[sid]["filter_stack"] = []
            _SESSIONS[sid]["timestamp"] = time.time()
            return orig
    return None


def clear_session(session_id: Optional[str]) -> None:
    sid = _clean_session_id(session_id)
    with _LOCK:
        _SESSIONS.pop(sid, None)
