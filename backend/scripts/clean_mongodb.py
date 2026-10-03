"""
clean_mongodb.py - clean the data that is ALREADY inside MongoDB (offline cleaning, no AI).

Safe three-stage use:
  1) python clean_mongodb.py --env backend/.env
        DRY RUN. Only reads. Writes one report per collection to ./mongo_reports. Changes nothing.
  2) python clean_mongodb.py --env backend/.env --apply
        Writes cleaned copies to NEW collections named <collection>_cleaned. Originals untouched.
        Test the chatbot by pointing MONGODB_COLLECTIONS at the *_cleaned names.
  3) (optional) python clean_mongodb.py --env backend/.env --replace
        Copies each original to <collection>_backup, then overwrites the original with cleaned data.

Needs: pip install pymongo pandas openpyxl   (optional: rapidfuzz)
Never prints record contents - only counts.
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory and scripts directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
scripts_dir = Path(__file__).resolve().parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import pandas as pd

try:
    from app.services.existing_data_cleaner import (
        clean_collection,
        docs_to_frame,
        collection_names,
        DEFAULT_IGNORE
    )
    from app.services import data_cleaner as cc
except ImportError:
    import cleaner_core as cc
    DEFAULT_IGNORE = {"_id", "search_text", "embedding", "embeddings", "vector"}

    def collection_names(env, override):
        if override:
            return [c.strip() for c in override.split(",") if c.strip()]
        names = [c.strip() for c in env.get("MONGODB_COLLECTIONS", "").split(",") if c.strip()]
        for i in range(1, 7):
            n = env.get(f"MONGODB_COLLECTION_{i}", "").strip()
            if n and n not in names:
                names.append(n)
        return names

    def docs_to_frame(docs, ignore):
        cols, rows = [], []
        for d in docs:
            row = {}
            for k, v in d.items():
                if k in ignore or k.startswith("norm_") or k.startswith("_"):
                    continue
                if k not in cols:
                    cols.append(k)
                row[k] = "" if v is None else (v if isinstance(v, str) else str(v))
            rows.append(row)
        return pd.DataFrame(rows, columns=cols).fillna("")

    def clean_collection(db, name, ignore):
        docs = list(db[name].find({}))
        ids = [str(d["_id"]) for d in docs]
        df = docs_to_frame(docs, ignore)
        if df.empty:
            return None, None, ids
        res = cc.clean_records(df, name)
        for e in res.log:
            idx = e.get("source_row", 2) - 2
            e["source_doc_id"] = ids[idx] if 0 <= idx < len(ids) else ""
        now = datetime.now(timezone.utc)
        out = []
        for r in res.rows:
            d = dict(r)
            idx = r.get("source_row", 2) - 2
            d["source_doc_id"] = ids[idx] if 0 <= idx < len(ids) else ""
            d["cleaned_at"] = now
            d["search_text"] = " ".join(str(d[k]) for k in
                                        ("company", "person", "designation", "phone", "email", "location") if d.get(k))
            out.append(d)
        return res, out, ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="backend/.env")
    ap.add_argument("--collections", help="comma list; default = MONGODB_COLLECTIONS from .env")
    ap.add_argument("--reports", default="mongo_reports")
    ap.add_argument("--suffix", default="_cleaned")
    ap.add_argument("--ignore-fields", default="", help="extra comma-separated field names to ignore")
    ap.add_argument("--apply", action="store_true", help="write <name>_cleaned collections")
    ap.add_argument("--replace", action="store_true", help="backup originals, then overwrite them")
    ap.add_argument("--synonyms")
    a = ap.parse_args()
    if a.synonyms:
        cc.load_custom_synonyms(a.synonyms)

    env = load_env(a.env)
    if "MONGODB_URI" not in env:
        sys.exit("MONGODB_URI not found. Check --env path.")
    db = get_db(env)
    names = collection_names(env, a.collections)
    if not names:
        sys.exit("No collections found. Use --collections a,b,c")
    ignore = DEFAULT_IGNORE | {x.strip() for x in a.ignore_fields.split(",") if x.strip()}
    Path(a.reports).mkdir(parents=True, exist_ok=True)

    if a.replace and input("This overwrites the ORIGINAL collections (backups are made first). "
                           "Type YES to continue: ").strip() != "YES":
        sys.exit("Cancelled.")

    for name in names:
        res, out, ids = clean_collection(db, name, ignore)
        if res is None:
            print(f"{name}: empty or not found, skipped")
            continue
        report = cc.build_report(res)
        cc.write_report_xlsx(report, Path(a.reports) / f"{name}_report.xlsx")
        s = res.stats
        print(f"{name}: docs_in={len(ids)} rows_out={s['rows_out']} split_added={s['rows_added_by_split']} "
              f"phones_from_names={s['phones_pulled_from_names']} duplicates_removed={s['duplicates_removed']} "
              f"needs_review={s['needs_review']}")
        if a.replace:
            bk = f"{name}_backup"
            if bk in db.list_collection_names():
                print(f"  ABORTED for {name}: {bk} already exists. Rename or drop it first.")
                continue
            originals = list(db[name].find({}))
            db[bk].insert_many(originals)
            if db[bk].count_documents({}) != len(originals):
                print(f"  ABORTED for {name}: backup count mismatch, original untouched.")
                continue
            db[name].delete_many({})
            db[name].insert_many(out)
            print(f"  original backed up to {bk}; {name} now holds {len(out)} cleaned rows")
        elif a.apply:
            target = name + a.suffix
            db[target].drop()
            db[target].insert_many(out)
            print(f"  wrote {len(out)} cleaned rows to {target}")
    if not (a.apply or a.replace):
        print(f"\nDRY RUN only. Reports are in {Path(a.reports).resolve()}. Nothing was written to MongoDB.")


if __name__ == "__main__":
    main()
