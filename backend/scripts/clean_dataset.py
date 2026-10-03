"""
clean_dataset.py - clean contact files in a folder (offline, no AI).

    python clean_dataset.py --input ./data --output ./cleaned
    python clean_dataset.py --input ./data --output ./cleaned --synonyms my_headers.json

For every .xlsx / .xls / .csv it writes:
    <name>_cleaned.xlsx   the cleaned rows
    <name>_report.xlsx    what was cleaned: summary, column mapping, every change, rows to review
and also ALL_cleaned.xlsx (all files combined) and cleaning_report.txt (counts only).
Needs: pip install pandas openpyxl   (optional: rapidfuzz xlrd)
"""
import argparse
import sys
from pathlib import Path

# Add backend directory and scripts directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
scripts_dir = Path(__file__).resolve().parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import pandas as pd

import cleaner_core as cc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="cleaned")
    ap.add_argument("--synonyms", help='JSON with extra header names, e.g. {"company": ["parent org"]}')
    a = ap.parse_args()
    if a.synonyms:
        cc.load_custom_synonyms(a.synonyms)

    src, dst = Path(a.input), Path(a.output)
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".xlsx", ".xlsm", ".xls", ".csv")
                   and not p.name.startswith("~$"))
    if not files:
        sys.exit("No .xlsx/.xls/.csv files found in the input folder.")

    lines, merged = [], cc.CleanResult()
    for f in files:
        try:
            res = cc.clean_file(f)
        except Exception as e:                       # report type only, never data
            lines.append(f"{f.name}: FAILED ({type(e).__name__})")
            continue
        if not res.rows:
            lines.append(f"{f.name}: no usable rows")
            continue
        report = cc.build_report(res)
        cc.to_frame(res.rows).to_excel(dst / f"{f.stem}_cleaned.xlsx", index=False)
        cc.write_report_xlsx(report, dst / f"{f.stem}_report.xlsx")
        s = res.stats
        lines.append(f"{f.name}: rows_in={s['rows_in']} rows_out={s['rows_out']} "
                     f"split_added={s['rows_added_by_split']} phones_from_names={s['phones_pulled_from_names']} "
                     f"duplicates_removed={s['duplicates_removed']} needs_review={s['needs_review']}")
        merged.rows += res.rows
        merged.log += res.log
        merged.mapping += res.mapping
        for k in merged.stats:
            merged.stats[k] += s[k]

    if merged.rows:
        cc._dedupe(merged)                           # duplicates across files
        merged.stats["rows_out"] = len(merged.rows)
        merged.stats["needs_review"] = sum(r["needs_review"] for r in merged.rows)
        cc.write_report_xlsx(cc.build_report(merged), dst / "ALL_report.xlsx")
        big = cc.to_frame(merged.rows)
        with pd.ExcelWriter(dst / "ALL_cleaned.xlsx") as xw:
            big.to_excel(xw, sheet_name="cleaned", index=False)
            big[big["needs_review"]].to_excel(xw, sheet_name="needs_review", index=False)
        lines.append(f"\nTOTAL cleaned rows: {len(big)} | needs_review: {int(big['needs_review'].sum())}")
    (dst / "cleaning_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines), f"\n\nDone. See: {dst.resolve()}")


if __name__ == "__main__":
    main()
