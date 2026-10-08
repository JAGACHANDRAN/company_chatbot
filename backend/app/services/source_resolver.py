import re
import time
from typing import List, Dict, Any, Optional
from threading import Lock

from ..database import get_database

_DATASET_MAP_LOCK = Lock()
_DATASET_ID_TO_NAME: Dict[str, str] = {}
_LAST_DATASET_CACHE_TIME: float = 0
_DATASET_CACHE_TTL: float = 300  # 5 minutes

NULL_INDICATORS = {
    "", "none", "null", "nan", "n/a", "na", "-", "--", "undefined",
    "not available", "not_available", "not publicly available", "no data available", ".",
    "mongodb", "mongodb atlas", "dataset_records"
}


def refresh_dataset_map() -> None:
    """Forces refresh of the dataset_id -> dataset_name cache."""
    global _DATASET_ID_TO_NAME, _LAST_DATASET_CACHE_TIME
    with _DATASET_MAP_LOCK:
        _build_dataset_map()


def _build_dataset_map() -> None:
    """Internal builder of dataset_id -> dataset_name mapping."""
    global _DATASET_ID_TO_NAME, _LAST_DATASET_CACHE_TIME
    try:
        db = get_database()
        cursor = db["datasets"].find({}, {"dataset_id": 1, "dataset_name": 1, "filename": 1, "name": 1, "_id": 1})
        ds_map: Dict[str, str] = {}
        for d in cursor:
            name = d.get("dataset_name") or d.get("name") or d.get("filename") or "No data available"
            # Strip file extension if present (e.g. .xlsx, .csv)
            clean_name = re.sub(r"\.(xlsx|xls|csv|json)$", "", str(name).strip(), flags=re.IGNORECASE)
            
            if d.get("dataset_id"):
                ds_map[str(d["dataset_id"]).strip()] = clean_name
            if d.get("_id"):
                ds_map[str(d["_id"]).strip()] = clean_name

        _DATASET_ID_TO_NAME = ds_map
        _LAST_DATASET_CACHE_TIME = time.time()
    except Exception:
        pass


def set_cached_dataset_map(mapping: Dict[str, str]) -> None:
    """Explicitly sets in-memory dataset mapping for testing or updates."""
    global _DATASET_ID_TO_NAME, _LAST_DATASET_CACHE_TIME
    with _DATASET_MAP_LOCK:
        _DATASET_ID_TO_NAME = dict(mapping)
        _LAST_DATASET_CACHE_TIME = time.time()


def get_cached_dataset_map() -> Dict[str, str]:
    """Returns in-memory cached map of dataset_id to dataset_name."""
    global _DATASET_ID_TO_NAME, _LAST_DATASET_CACHE_TIME
    with _DATASET_MAP_LOCK:
        if not _DATASET_ID_TO_NAME or (time.time() - _LAST_DATASET_CACHE_TIME > _DATASET_CACHE_TTL):
            _build_dataset_map()
        return dict(_DATASET_ID_TO_NAME)


def get_dataset_name(record: Dict[str, Any]) -> str:
    """
    R3: Returns the dataset name resolved per record via dataset_id looked up in datasets collection.
    Missing or orphaned dataset -> 'No data available'.
    Computed per record at the moment the row is built.
    """
    if not isinstance(record, dict):
        return "No data available"

    ds_map = get_cached_dataset_map()

    # Look for dataset_id on record or nested dicts
    d_id = (
        record.get("dataset_id")
        or (record.get("data", {}).get("dataset_id") if isinstance(record.get("data"), dict) else None)
        or (record.get("raw_data", {}).get("dataset_id") if isinstance(record.get("raw_data"), dict) else None)
        or (record.get("source_fields", {}).get("dataset_id") if isinstance(record.get("source_fields"), dict) else None)
    )

    if d_id is not None:
        d_id_str = str(d_id).strip()
        if d_id_str in ds_map:
            name = ds_map[d_id_str]
            clean = re.sub(r"\.(xlsx|xls|csv|json)$", "", str(name).strip(), flags=re.IGNORECASE).strip()
            if clean and clean.lower() not in NULL_INDICATORS:
                return clean

    # Check if explicit clean dataset_name was passed (e.g. Injected in test)
    d_name = record.get("dataset_name")
    if d_name and isinstance(d_name, str):
        clean = re.sub(r"\.(xlsx|xls|csv|json)$", "", str(d_name).strip(), flags=re.IGNORECASE).strip()
        if clean and clean.lower() not in NULL_INDICATORS:
            return clean

    return "No data available"


def get_record_sources(record: Dict[str, Any]) -> List[str]:
    """Returns list of dataset names for a single record."""
    d_name = get_dataset_name(record)
    if d_name == "No data available":
        return ["No data available"]
    return [p.strip() for p in d_name.split(",") if p.strip()]


def get_record_source_display(record: Dict[str, Any]) -> str:
    """Returns clean dataset_name string for a single record."""
    return get_dataset_name(record)


def get_company_sources_summary(records: List[Dict[str, Any]]) -> str:
    """
    R3: Company-level summaries show unique dataset names with counts,
    e.g. 'ACMEE 2023 (4), IMTEX (2)'.
    """
    if not records:
        return "No data available"

    from collections import Counter
    counts = Counter()

    for rec in records:
        d_name = get_dataset_name(rec)
        if d_name and d_name != "No data available":
            counts[d_name] += 1

    if not counts:
        return "No data available"

    parts = [f"{name} ({count})" for name, count in counts.items()]
    return ", ".join(parts)

