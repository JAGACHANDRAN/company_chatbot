"""
existing_data_cleaner.py - Service for cleaning data ALREADY stored inside MongoDB collections.
Offline, local, deterministic cleaning without external AI or external network calls.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional, Set
import pandas as pd
from pymongo.collection import Collection
from pymongo.database import Database

from . import data_cleaner as cc

DEFAULT_IGNORE: Set[str] = {
    "_id", "search_text", "embedding", "embeddings", "vector",
    "data", "normalized_data", "raw_data", "source_fields"
}


def collection_names(env: Dict[str, str], override: Optional[str] = None) -> List[str]:
    """Resolves collection names from env or comma-separated override string."""
    if override:
        return [c.strip() for c in override.split(",") if c.strip()]
    names: List[str] = [c.strip() for c in env.get("MONGODB_COLLECTIONS", "").split(",") if c.strip()]
    for i in range(1, 7):
        n = env.get(f"MONGODB_COLLECTION_{i}", "").strip()
        if n and n not in names:
            names.append(n)
        n_alt = env.get(f"MONGODB_COLLECTION_NAME_{i}", "").strip()
        if n_alt and n_alt not in names:
            names.append(n_alt)
    return names


def docs_to_frame(docs: List[Dict[str, Any]], ignore: Set[str]) -> pd.DataFrame:
    """Converts a list of MongoDB documents into a DataFrame, omitting ignored/internal fields."""
    cols: List[str] = []
    rows: List[Dict[str, Any]] = []
    for d in docs:
        row: Dict[str, Any] = {}
        for k, v in d.items():
            if k in ignore or k.startswith("norm_") or k.startswith("_"):
                continue
            if k not in cols:
                cols.append(k)
            row[k] = "" if v is None else (v if isinstance(v, str) else str(v))
        rows.append(row)
    return pd.DataFrame(rows, columns=cols).fillna("")


def clean_collection(
    db: Database,
    name: str,
    ignore: Optional[Set[str]] = None,
    custom_mapping: Optional[Dict[str, Optional[str]]] = None
) -> Tuple[Optional[Any], Optional[List[Dict[str, Any]]], List[str]]:
    """
    Reads all documents from a collection and runs deterministic cleaning.
    Attaches source_doc_id to every change in log and to every cleaned document.
    Returns: (CleanResult, cleaned_documents_list, original_doc_ids)
    """
    effective_ignore = set(DEFAULT_IGNORE if ignore is None else ignore)
    docs = list(db[name].find({}))
    ids = [str(d.get("_id", "")) for d in docs]
    if not docs:
        return None, None, ids

    df = docs_to_frame(docs, effective_ignore)
    if df.empty:
        return None, None, ids

    res = cc.clean_records(df, name, custom_mapping=custom_mapping)

    # Point every change in log to the original document ID
    for e in res.log:
        idx = e.get("source_row", 2) - 2
        e["source_doc_id"] = ids[idx] if 0 <= idx < len(ids) else ""
        if "what_happened" not in e:
            e["what_happened"] = cc.ACTION_LABELS.get(e.get("action", ""), e.get("action", ""))

    now = datetime.now(timezone.utc).isoformat()
    out: List[Dict[str, Any]] = []
    for r in res.rows:
        d = dict(r)
        idx = r.get("source_row", 2) - 2
        d["source_doc_id"] = ids[idx] if 0 <= idx < len(ids) else ""
        d["cleaned_at"] = now
        d["search_text"] = " ".join(
            str(d[k]) for k in ("company", "person", "designation", "phone", "email", "location")
            if d.get(k)
        )
        out.append(d)

    return res, out, ids


def copy_collection_indexes(source_col: Collection, target_col: Collection) -> None:
    """Copies all non-_id indexes from source collection to target collection."""
    try:
        index_info = source_col.index_information()
        for idx_name, idx_spec in index_info.items():
            if idx_name == "_id_":
                continue
            keys = idx_spec["key"]
            # Filter standard options
            options: Dict[str, Any] = {"name": idx_name, "background": True}
            if "unique" in idx_spec:
                options["unique"] = idx_spec["unique"]
            if "sparse" in idx_spec:
                options["sparse"] = idx_spec["sparse"]
            try:
                target_col.create_index(keys, **options)
            except Exception:
                pass
    except Exception as e:
        print(f"[Index Copy Warning] {e}")


def get_configured_collections_with_counts(db: Database, env: Dict[str, str]) -> List[Dict[str, Any]]:
    """Returns all configured collections along with document counts and status tags."""
    names = collection_names(env)
    
    # If no collections in env, discover from db (excluding system and internal app collections)
    if not names:
        internal_cols = {"user", "users", "uploaders", "dataset_records", "datasets"}
        names = [
            c for c in db.list_collection_names()
            if not c.startswith("system.") and c.lower() not in internal_cols
        ]

    existing_names = set(db.list_collection_names())
    results: List[Dict[str, Any]] = []

    for name in names:
        doc_count = db[name].count_documents({}) if name in existing_names else 0
        has_backup = f"{name}_backup" in existing_names
        has_cleaned = f"{name}_cleaned" in existing_names
        results.append({
            "name": name,
            "count": doc_count,
            "exists": name in existing_names,
            "is_backup": name.endswith("_backup"),
            "is_cleaned": name.endswith("_cleaned"),
            "has_backup": has_backup,
            "has_cleaned": has_cleaned,
        })
    return results
