"""
cleaner_core.py - the cleaning engine (offline, no AI, no internet).

Used by:
  clean_dataset.py   clean files in a folder
  clean_mongodb.py   clean data that is already inside MongoDB
  your backend       backend/app/services/data_cleaner.py

Main functions
  clean_file(path_or_bytes, filename)         -> CleanResult   (xlsx / xls / csv)
  clean_dataframe(raw_df, source_file, sheet) -> CleanResult   (header row inside raw_df)
  build_report(result)                        -> dict          (show this to the user BEFORE saving)
  write_report_xlsx(report, path_or_buffer)   -> downloadable Excel report

Needs: pandas, openpyxl.  Optional: rapidfuzz (better header matching), xlrd (.xls)
"""
import io
import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font

try:
    from rapidfuzz import fuzz, process
except ImportError:  # works without it
    fuzz = process = None

# ---------------------------------------------------------------------------
# Header knowledge
# ---------------------------------------------------------------------------
SYNONYMS = {
    "company": ["company", "company name", "firm", "firm name", "organisation", "organization",
                "org", "client", "customer", "customer name", "account", "account name",
                "business", "business name", "party name", "name of company"],
    "person": ["name", "person", "person name", "contact person", "contact name", "contact",
               "customer contact", "representative", "spoc", "poc", "full name", "owner"],
    "designation": ["designation", "desg", "desig", "desgn", "title", "job title", "role",
                    "position", "post", "job role", "designation name"],
    "phone": ["phone", "phone no", "phone number", "mobile", "mobile no", "mobile number",
              "contact no", "contact number", "tel", "telephone", "cell", "phn", "phn no",
              "whatsapp", "mob"],
    "email": ["email", "e-mail", "email id", "mail", "mail id", "email address", "emailid"],
    "location": ["location", "city", "state", "address", "place", "region", "area", "district"],
    "linkedin": ["linkedin", "linkedin url", "linkedin profile", "profile link"],
}
STANDARD_ORDER = ["company", "person", "designation", "phone", "phone_2",
                  "email", "email_2", "location", "linkedin"]
META = ["source_file", "sheet_name", "source_row", "needs_review", "review_reasons"]
INTERNAL = {"norm_company"}

TOKEN_RULES = [
    ("email", {"email", "mail", "emailid"}),
    ("phone", {"phone", "ph", "mobile", "mob", "cell", "tel", "telephone", "whatsapp", "phn", "mobno"}),
    ("linkedin", {"linkedin"}),
    ("designation", {"designation", "desg", "desig", "title", "role", "job", "position", "post"}),
    ("company", {"company", "firm", "org", "organisation", "organization", "client",
                 "customer", "account", "business", "enterprise"}),
    ("location", {"location", "city", "state", "address", "place", "region", "district", "area"}),
    ("person", {"name", "person", "contact", "spoc", "poc", "mgr", "manager", "owner", "representative"}),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
PHONE_RE = re.compile(r"(?<![\w@])(?:\+?\d[\d\s\-().]{6,}\d)(?![\w@])")
LEGAL_SUFFIX = re.compile(
    r"\b(pvt\.?|private|ltd\.?|limited|llp|inc\.?|corp\.?|corporation|co\.?|company|group|industries)\b", re.I)
COMPANY_WORDS = re.compile(r"\b(ltd|limited|pvt|private|llp|inc|corp|corporation|industries|enterprises|group|"
                           r"motors|works|solutions|technologies|engineering|systems|steels?|auto|tools|"
                           r"exports?|traders?|associates|company|co)\b", re.I)
TITLE_WORDS = re.compile(r"\b(manager|head|director|engineer|executive|officer|buyer|purchase|quality|sales|"
                         r"owner|proprietor|ceo|cto|cfo|md|gm|vp|president|partner|supervisor|incharge|"
                         r"in-charge|lead|analyst|consultant|assistant|chief|founder|production|maintenance|"
                         r"procurement|metrology|qa|qc)\b", re.I)
# Split multiple companies ONLY on newlines or explicit semicolons; NEVER on '&', '/', or '-'
SPLIT_COMPANY = re.compile(r"[\r\n]+|\s*;\s*")

ACTION_LABELS = {
    "company_split": "Separated multiple companies listed on different lines into individual rows",
    "phone_extracted_from_name": "Phone number found inside the name and moved to the phone field",
    "phone_extracted_from_company": "Separated contact number found inside company name",
    "email_extracted_from_name": "Separated email address found inside person's name",
    "phone_formatted": "Formatted contact number into standard phone format",
    "multiple_phones_split": "Separated multiple contact numbers into Primary Phone and Phone 2",
    "email_cleaned": "Cleaned email address format",
    "multiple_emails_split": "Separated multiple email addresses into Primary Email and Email 2",
    "name_cleaned": "Tidied spacing in person's name",
    "person_split": "Separated multiple contact persons listed with ';' into distinct contact records",
    "location_split": "Separated address, city, and state listed with ';' into distinct fields",
    "duplicate_removed": "Merged duplicate contact record into primary record",
    "empty_row_removed": "Removed empty row",
}


# ---------------------------------------------------------------------------
# Header matching
# ---------------------------------------------------------------------------
def _norm_header(h):
    s = re.sub(r"[^a-z0-9 ]", " ", str(h).lower().replace("_", " "))
    return re.sub(r"\s+", " ", s).strip()


LOOKUP = {_norm_header(n): f for f, names in SYNONYMS.items() for n in names}


def load_custom_synonyms(path):
    """JSON like {"company": ["parent org"], "phone": ["reach at"]}"""
    import json
    for f, names in json.loads(Path(path).read_text(encoding="utf-8")).items():
        for n in names:
            LOOKUP[_norm_header(n)] = f


def match_header(h):
    """-> (field, method) ; method is 'exact', 'fuzzy', 'keyword' or ''"""
    key = _norm_header(h)
    if not key or key.startswith("unnamed") or key.startswith("col "):
        return None, ""
    if key in LOOKUP:
        return LOOKUP[key], "exact"
    if process is not None:
        res = process.extractOne(key, list(LOOKUP), scorer=fuzz.WRatio)
        if res and res[1] >= 88:
            return LOOKUP[res[0]], "fuzzy"
    else:
        res = get_close_matches(key, list(LOOKUP), n=1, cutoff=0.85)
        if res:
            return LOOKUP[res[0]], "fuzzy"
    words = set(key.split())
    for f, toks in TOKEN_RULES:
        if words & toks:
            return f, "keyword"
    return None, ""


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------
EMPTY_PLACEHOLDERS = {
    "nan", "none", "null", "n/a", "na", "-", "--", "nil", ".", "undefined",
    "not available", "not publicly available", "publicly not available",
    "not available publicly", "not provided", "not mentioned", "unknown"
}


def clean_text(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if s.lower() in EMPTY_PLACEHOLDERS:
        return ""
    s = re.sub(r"[\x00-\x08\x0b-\x1f\u200b\ufeff]", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def clean_designation_text(d):
    if not d:
        return None
    parts = [p.strip() for p in re.split(r"[/;]+", str(d)) if p.strip()]
    valid = [
        p for p in parts
        if p.lower() not in EMPTY_PLACEHOLDERS
        and not re.search(r"\bnot\s+publicly\s+available\b|\bpublicly\s+not\s+available\b|\bnot\s+available\b", p, re.I)
    ]
    return " / ".join(valid) if valid else None


def digits_to_phone(raw):
    """-> (formatted, is_valid)"""
    d = re.sub(r"\D", "", str(raw))
    if d.startswith("0091"):
        d = d[4:]
    elif d.startswith("91") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11 and d[1] in "6789":
        d = d[1:]
    if len(d) == 10 and d[0] in "6789":
        return "+91" + d, True
    if d.startswith("0") and 9 <= len(d) <= 12:      # landline with STD code
        return d, True
    return d, False


def extract_phones(text):
    """-> (phones, text_without_phones, has_invalid)"""
    phones, invalid = [], False
    for m in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if 8 <= len(digits) <= 13:
            p, ok = digits_to_phone(m)
            if p and p not in phones:
                phones.append(p)
            invalid = invalid or not ok
    return phones, (PHONE_RE.sub(" ", text) if phones else text), invalid


def extract_emails(text):
    found = []
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".,;")
        if e not in found:
            found.append(e)
    return found, EMAIL_RE.sub(" ", text)


def tidy_name(s):
    s = re.sub(r"^[\s,;:\-|/()\[\]]+|[\s,;:\-|/()\[\]]+$", "", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def split_companies(text):
    protected = re.sub(r"\bM/s\b", "M_S_", text, flags=re.I)
    parts = [p.replace("M_S_", "M/s").strip(" ,.-") for p in SPLIT_COMPANY.split(protected)]
    return [p for p in parts if p]


def norm_company(s):
    return re.sub(r"[^a-z0-9]+", " ", LEGAL_SUFFIX.sub(" ", s.lower())).strip()


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------
def read_any(src, filename=None):
    """src = path or bytes. Yields (sheet_name, DataFrame without header)."""
    name = filename or (Path(src).name if not isinstance(src, (bytes, bytearray)) else "")
    ext = Path(name).suffix.lower()
    handle = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    if ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                if hasattr(handle, "seek"):
                    handle.seek(0)
                yield "csv", pd.read_csv(handle, header=None, dtype=str, encoding=enc,
                                         keep_default_na=False, on_bad_lines="skip", engine="python")
                return
            except UnicodeDecodeError:
                continue
    elif ext in (".xlsx", ".xlsm", ".xls"):
        for sheet, df in pd.read_excel(handle, sheet_name=None, header=None, dtype=str).items():
            yield sheet, df.fillna("")
    else:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")


def _row_looks_like_data(row):
    return any(EMAIL_RE.search(v) or extract_phones(v)[0] for v in map(clean_text, row) if v)


def find_header_row(df, scan=15):
    """Header row index, or -1 when the sheet has no header row."""
    best_i, best = -1, 1
    for i in range(min(scan, len(df))):
        if _row_looks_like_data(df.iloc[i]):
            continue
        score = sum(1 for v in df.iloc[i] if match_header(v)[0])
        if score > best:
            best_i, best = i, score
    return best_i


def content_kind(series):
    vals = [clean_text(v) for v in series if clean_text(v)][:60]
    if not vals:
        return None
    n = len(vals)

    def only(v, kind):
        rest = EMAIL_RE.sub("", v) if kind == "email" else PHONE_RE.sub("", v)
        return len(re.sub(r"[^A-Za-z]", "", rest)) <= 3

    if sum(1 for v in vals if EMAIL_RE.search(v) and only(v, "email")) / n > 0.6:
        return "email"
    if sum(1 for v in vals if extract_phones(v)[0] and only(v, "phone")) / n > 0.6:
        return "phone"
    return None


def guess_text_field(series):
    vals = [clean_text(v) for v in series if clean_text(v)][:60]
    if not vals:
        return None
    n = len(vals)
    if sum(1 for v in vals if COMPANY_WORDS.search(v)) / n > 0.4:
        return "company"
    if sum(1 for v in vals if TITLE_WORDS.search(v)) / n > 0.4:
        return "designation"
    namey = sum(1 for v in vals if re.fullmatch(r"[A-Za-z.\s']{3,40}", v) and len(v.split()) <= 4) / n
    return "person" if namey > 0.7 else None


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class CleanResult:
    rows: list = field(default_factory=list)       # cleaned rows
    log: list = field(default_factory=list)        # every change, row by row
    mapping: list = field(default_factory=list)    # how each column was understood
    stats: dict = field(default_factory=lambda: dict(
        rows_in=0, rows_out=0, empty_rows=0, rows_added_by_split=0, phones_pulled_from_names=0,
        duplicates_removed=0, needs_review=0, headerless_sheets=0))


def _log(res, f, sh, row, action, fld, before, after, note=""):
    res.log.append(dict(source_file=f, sheet_name=str(sh), source_row=row, action=action,
                        field=fld, before=before, after=after, note=note))


# ---------------------------------------------------------------------------
# Cleaning one sheet
# ---------------------------------------------------------------------------
def _clean_sheet(raw, source_file, sheet, res, custom_mapping=None):
    if raw.empty:
        return
    h = find_header_row(raw)
    if h == -1:
        headers = [f"col {i}" for i in range(raw.shape[1])]
        body = raw.reset_index(drop=True)
        generic = re.compile(r"^(col|column|field|unnamed)[\s_:.-]*[a-z0-9]*$", re.I)
        first = [clean_text(x) for x in body.iloc[0]]
        h = -1
        res.stats["headerless_sheets"] += 1
        if sum(1 for x in first if x and generic.match(x)) >= max(2, len(first) // 2):
            body, h = body.iloc[1:].reset_index(drop=True), 0
    else:
        headers = [clean_text(x) or f"unnamed_{i}" for i, x in enumerate(raw.iloc[h])]
        headers = [x if headers[:i].count(x) == 0 else f"{x}_{i}" for i, x in enumerate(headers)]
        body = raw.iloc[h + 1:].reset_index(drop=True)
    body.columns = headers
    _clean_body(body, headers, h, source_file, sheet, res, custom_mapping=custom_mapping)


def _clean_body(body, headers, h, source_file, sheet, res, custom_mapping=None):
    """h = index of the header row in the sheet (0 for database records, -1 = none)."""
    mapping, method = {}, {}
    for col in headers:
        if custom_mapping and col in custom_mapping:
            mapping[col] = custom_mapping[col]
            method[col] = "user override"
            continue
        f, m = match_header(col)
        kind = content_kind(body[col])
        if kind and f != kind and f in (None, "person", "company", "phone", "email"):
            f, m = kind, "content"
        mapping[col], method[col] = f, m
    for col in headers:
        if mapping[col] is None:
            g = guess_text_field(body[col])
            if g and g not in mapping.values():
                mapping[col], method[col] = g, "content guess"
    for col in headers:
        res.mapping.append(dict(source_file=source_file, sheet_name=str(sheet), column=col,
                                mapped_to=mapping[col] or "(kept as extra column)",
                                method=method[col] or "-"))

    for idx, r in body.iterrows():
        src_row = int(idx) + h + 2
        L = lambda a, f_, b, af, n="": _log(res, source_file, sheet, src_row, a, f_, b, af, n)
        cells, extras = {f: [] for f in SYNONYMS}, {}
        for col in headers:
            v = clean_text(r[col])
            if v:
                if mapping[col]:
                    cells[mapping[col]].append(v)
                else:
                    extras[col] = v
        if not any(cells.values()) and not extras:
            res.stats["empty_rows"] += 1
            _log(res, source_file, sheet, src_row, "empty_row_removed", "", "", "")
            continue
        res.stats["rows_in"] += 1

        reasons = []
        company_raw = " ; ".join(cells["company"])
        person_orig = " ; ".join(cells["person"])
        phone_raw = " ; ".join(cells["phone"])
        email_raw = " ; ".join(cells["email"])

        p_name, person_txt, bad1 = extract_phones(person_orig)
        e_name, person_txt = extract_emails(person_txt)
        p_comp, company_txt, bad_c = extract_phones(company_raw)
        p_cols, _, bad2 = extract_phones(phone_raw)
        e_cols, _ = extract_emails(email_raw)
        phones = list(dict.fromkeys(p_cols + p_name + p_comp))
        emails = list(dict.fromkeys(e_cols + e_name))
        if bad1 or bad2 or bad_c:
            reasons.append("phone_format")
        if email_raw and not e_cols:
            reasons.append("invalid_email")

        # Split multiple persons if separated by semicolons (e.g. Ram; John; Das)
        persons = [tidy_name(x) for x in person_txt.split(";") if tidy_name(x)]
        if not persons:
            persons = [None]
        elif len(persons) > 1:
            L("person_split", "person", person_orig, " | ".join(persons), f"{len(persons)} contacts created")

        clean_desigs_list = [clean_designation_text(d) for d in cells["designation"] if clean_designation_text(d)]
        desig_raw = " / ".join(dict.fromkeys(clean_desigs_list))
        desigs = [tidy_name(x) for x in desig_raw.split(";") if tidy_name(x) and clean_designation_text(x)]
        if not desigs:
            desigs = [tidy_name(desig_raw) if clean_designation_text(desig_raw) else None]

        # Location splitting on semicolons or newlines
        loc_raw = " ; ".join(cells["location"])
        loc_items = [x.strip() for x in re.split(r"[;\n]+", loc_raw) if x.strip()]
        if len(loc_items) > 1 and ";" in loc_raw:
            L("location_split", "location", loc_raw, ", ".join(loc_items))

        addr_val, city_val, state_val = None, None, None
        if len(loc_items) >= 3:
            addr_val = loc_items[0]
            city_val = loc_items[1]
            state_val = ", ".join(loc_items[2:])
        elif len(loc_items) == 2:
            city_val = loc_items[0]
            state_val = loc_items[1]
        elif len(loc_items) == 1:
            parts = [p.strip() for p in loc_items[0].split("/") if p.strip()]
            if len(parts) >= 3:
                addr_val = parts[0]
                city_val = parts[1]
                state_val = ", ".join(parts[2:])
            elif len(parts) == 2:
                city_val = parts[0]
                state_val = parts[1]

        # ---- change log -------------------------------------------------
        if p_name:
            res.stats["phones_pulled_from_names"] += 1
            L("phone_extracted_from_name", "person", person_orig, f"name: {', '.join(persons)} | phone: {', '.join(p_name)}")
        if p_comp:
            res.stats["phones_pulled_from_names"] += 1
            L("phone_extracted_from_company", "company", company_raw, f"company: {company_txt.strip()} | phone: {', '.join(p_comp)}")
        if e_name:
            L("email_extracted_from_name", "person", person_orig, f"name: {', '.join(persons)} | email: {', '.join(e_name)}")
        if p_cols and ", ".join(p_cols) != phone_raw.strip():
            L("phone_formatted", "phone", phone_raw, ", ".join(p_cols))
        if len(phones) > 1:
            L("multiple_phones_split", "phone", ", ".join(phones), f"phone: {phones[0]} | phone_2: {', '.join(phones[1:])}")
        if e_cols and ", ".join(e_cols) != email_raw.strip():
            L("email_cleaned", "email", email_raw, ", ".join(e_cols))
        if len(emails) > 1:
            L("multiple_emails_split", "email", ", ".join(emails), f"email: {emails[0]} | email_2: {', '.join(emails[1:])}")
        if len(persons) == 1 and persons[0] and not (p_name or e_name) and persons[0] != person_orig.strip():
            L("name_cleaned", "person", person_orig, persons[0])

        companies = split_companies(company_txt) or [""]
        if len(companies) > 1:
            res.stats["rows_added_by_split"] += len(companies) - 1
            L("company_split", "company", company_raw, " | ".join(companies), f"{len(companies)} rows created")

        for c in companies:
            for p_idx, p_single in enumerate(persons):
                rr = list(reasons)
                if "," in c:
                    rr.append("comma_in_company")
                if not c:
                    rr.append("no_company")
                if not (phones or emails):
                    rr.append("no_contact_detail")

                phone_1 = phones[p_idx] if p_idx < len(phones) else (phones[0] if len(phones) == 1 else None)
                phone_2_val = phones[p_idx + 1] if p_idx + 1 < len(phones) else (phones[1] if len(phones) > 1 and len(persons) == 1 else None)
                email_1 = emails[p_idx] if p_idx < len(emails) else (emails[0] if len(emails) == 1 else None)
                email_2_val = emails[p_idx + 1] if p_idx + 1 < len(emails) else (emails[1] if len(emails) > 1 and len(persons) == 1 else None)
                desig_val = desigs[p_idx] if p_idx < len(desigs) else desigs[0]

                rec = {
                    "company": c if c else None,
                    "person": p_single,
                    "designation": desig_val,
                    "phone": phone_1,
                    "phone_2": phone_2_val,
                    "email": email_1,
                    "email_2": email_2_val,
                    "location": ", ".join(loc_items) if loc_items else None,
                    "address": addr_val,
                    "city": city_val,
                    "state": state_val,
                    "linkedin": cells["linkedin"][0] if cells["linkedin"] else None
                }
                for k, v in extras.items():
                    rec[k] = v if (v and str(v).strip().lower() not in {"nan", "none", "null", "n/a", "na", "-", "--", "nil"}) else None
                rec.update(norm_company=norm_company(c) if c else "", source_file=source_file, sheet_name=str(sheet),
                           source_row=src_row, needs_review=bool(rr), review_reasons=", ".join(sorted(set(rr))))
                res.rows.append(rec)


def _dedupe(res):
    groups, out = {}, []
    for r in res.rows:
        key = (r["norm_company"], (r["person"] or "").lower())
        ids_r = {x for x in (r["phone"], r["email"]) if x}
        dup = None
        if key[0] and key[1]:
            for kept in groups.get(key, []):
                ids_k = {x for x in (kept["phone"], kept["email"]) if x}
                if not ids_r or not ids_k or ids_r & ids_k:
                    dup = kept
                    break
        if dup is None:
            groups.setdefault(key, []).append(r)
            out.append(r)
            continue
        filled = [f for f in ("phone", "email", "designation", "location") if not dup[f] and r[f]]
        for f in filled:
            dup[f] = r[f]
        res.stats["duplicates_removed"] += 1
        _log(res, r["source_file"], r["sheet_name"], r["source_row"], "duplicate_removed", "",
             f"{r['company']} / {r['person']}", f"merged into row {dup['source_row']}",
             ("filled missing: " + ", ".join(filled)) if filled else "")
    res.rows = out


def _finish(res):
    _dedupe(res)
    res.stats["rows_out"] = len(res.rows)
    res.stats["needs_review"] = sum(1 for r in res.rows if r["needs_review"])
    return res


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def clean_dataframe(raw, source_file, sheet_name="sheet", custom_mapping=None):
    """raw = DataFrame WITHOUT header handling (first rows may hold the header)."""
    res = CleanResult()
    _clean_sheet(raw, source_file, sheet_name, res, custom_mapping=custom_mapping)
    return _finish(res)


def clean_records(df, source_file, sheet_name="records", custom_mapping=None):
    """For data that already has proper column names (e.g. documents read from MongoDB).
    source_row = position in df + 2 (so df.iloc[source_row - 2] is the original record)."""
    res = CleanResult()
    df = df.astype(str).reset_index(drop=True)
    _clean_body(df, [str(c) for c in df.columns], 0, source_file, sheet_name, res, custom_mapping=custom_mapping)
    return _finish(res)


def clean_file(src, filename=None, custom_mapping=None):
    """src = file path or raw bytes (upload). Nothing is written anywhere."""
    name = filename or Path(src).name
    res = CleanResult()
    for sheet, raw in read_any(src, name):
        _clean_sheet(raw, name, sheet, res, custom_mapping=custom_mapping)
    return _finish(res)


def to_frame(rows, include_internal=False):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    std = [c for c in STANDARD_ORDER if c in df.columns]
    skip = set(META) | (set() if include_internal else INTERNAL)
    extra = [c for c in df.columns if c not in std and c not in skip and c not in INTERNAL]
    cols = std + extra + META + (["norm_company"] if include_internal and "norm_company" in df else [])
    return df[cols]


# ---------------------------------------------------------------------------
# Report (what was cleaned, which rows, what changed)
# ---------------------------------------------------------------------------
def build_report(res):
    s = res.stats
    counts = {}
    changes = []
    for e in res.log:
        counts[e["action"]] = counts.get(e["action"], 0) + 1
        entry = dict(e)
        entry["what_happened"] = ACTION_LABELS.get(e.get("action", ""), e.get("action", ""))
        changes.append(entry)
    plain = [f"{s['rows_in']} data rows were read and {s['rows_out']} clean rows will be saved."]
    for a, n in sorted(counts.items(), key=lambda x: -x[1]):
        plain.append(f"{n} x {ACTION_LABELS.get(a, a)}")
    if s["needs_review"]:
        plain.append(f"{s['needs_review']} rows need your review (see 'needs review').")
    if s["headerless_sheets"]:
        plain.append("A sheet had no header row; columns were detected from their contents.")
    # Structural changes are those where mixed fields were separated (phone in company, company split, etc.)
    structural_actions = {
        "phone_extracted_from_company",
        "phone_extracted_from_name",
        "email_extracted_from_name",
        "company_split",
        "person_split",
        "location_split",
        "multiple_phones_split",
        "multiple_emails_split",
    }
    structural_changes = [c for c in changes if c.get("action") in structural_actions]
    is_fully_clean = len(structural_changes) == 0
    return {
        "summary": {**s, "changes_by_type": counts, "plain_language": plain, "is_fully_clean": is_fully_clean, "total_changes": len(changes), "structural_changes": len(structural_changes)},
        "column_mapping": res.mapping,
        "changes": changes,
        "needs_review": [r for r in res.rows if r.get("needs_review")],
        "cleaned_rows": res.rows,
        "cleaned_preview": res.rows[:50],
        "is_fully_clean": is_fully_clean,
    }


def write_report_xlsx(report, target):
    """target = file path or BytesIO. Sheets: Summary, Column mapping, Changes, Needs review, Cleaned data."""
    sm = report["summary"]
    summary = pd.DataFrame(
        [["What happened", line] for line in sm["plain_language"]] +
        [["", ""]] + [[k, v] for k, v in sm.items() if k not in ("plain_language", "changes_by_type")],
        columns=["Item", "Detail"])
    changes = pd.DataFrame(report["changes"])
    if not changes.empty and "what_happened" not in changes.columns:
        changes.insert(4, "what_happened", changes["action"].map(lambda a: ACTION_LABELS.get(a, a)))
    sheets = {
        "Summary": summary,
        "Column mapping": pd.DataFrame(report["column_mapping"]),
        "Changes": changes,
        "Needs review": to_frame(report["needs_review"]),
        "Cleaned data": to_frame(report["cleaned_rows"]),
    }
    with pd.ExcelWriter(target, engine="openpyxl") as xw:
        for name, df in sheets.items():
            (df if not df.empty else pd.DataFrame({"info": ["nothing to show"]})).to_excel(
                xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes = "A2"
            for c in ws[1]:
                c.font = Font(bold=True)
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)
