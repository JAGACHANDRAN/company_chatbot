"""
contact_search.py - deterministic contact search for Calispec AI (no embeddings, no LLM, no internet).

Why this exists:
  Typing several companies ("Tata Motors, JBM Group and ABC Ltd"), a company plus a role
  ("quality managers at Kappa Motors in Pune"), or only a designation must all return the right
  rows. Instead of guessing with embeddings, the query is understood against the REAL values in
  your cleaned database (company names, designations, locations), then fetched with exact
  MongoDB filters.

Main functions:
  vocab = build_vocab(db, ["metrology", "Expo_Acme", ...])      # call once, cache, refresh after uploads
  parsed = parse_query("quality managers at Tata Motors, JBM Group in Pune", vocab)
  result = search(db, collections, parsed, vocab)                 # dict, JSON friendly
  text   = format_markdown(result)                                # strict-schema answer, no LLM needed

Works on CLEANED data (fields: company, norm_company, person, designation, phone, phone_2,
email, email_2, location, ...) produced by cleaner_core.py.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
LEGAL = re.compile(r"\b(pvt\.?|private|ltd\.?|limited|llp|inc\.?|corp\.?|corporation|co\.?|company|"
                   r"group|industries)\b", re.I)
STOP = set("""find show get give list display search fetch tell me us the a an all any contact contacts
details detail info information who whom is are person persons people phone phones number numbers email
emails mail id ids please need want about which working works work employee employees staff team
having has have with data record records named called""".split()) - {"works"}   # 'works' kept: Zeta Works
LEGAL_WORDS = {"pvt", "private", "ltd", "limited", "llp", "inc", "corp", "corporation", "co", "company",
               "group", "industries"}
SEP_PUNCT = set(",;|/&\n")
SEP_WORDS = {"and", "or", "at", "in", "from", "of", "for", "under", "with"}

ROLE_WORDS = {"manager", "mgr", "head", "director", "engineer", "engg", "executive", "officer", "buyer",
              "purchase", "purchasing", "procurement", "owner", "proprietor", "ceo", "cto", "cfo", "coo",
              "md", "gm", "agm", "dgm", "vp", "president", "partner", "supervisor", "incharge", "lead",
              "analyst", "consultant", "assistant", "chief", "founder", "hod", "technician", "operator",
              "designer", "qa", "qc", "hr"}

# role word (stem) -> regex prefixes that should match in the stored designation
SYNONYMS = {
    "manager": ["manager", "mgr"], "mgr": ["manager", "mgr"],
    "head": ["head", "hod", "lead"], "lead": ["lead", "head"],
    "purchase": ["purchas", "procure", "buyer"], "purchasing": ["purchas", "procure", "buyer"],
    "procurement": ["procure", "purchas", "buyer"], "buyer": ["buyer", "purchas", "procure"],
    "qa": ["qa", "quality assurance", "quality"], "qc": ["qc", "quality control", "quality"],
    "quality": ["quality", "qa", "qc"],
    "md": ["md", "managing director"], "ceo": ["ceo", "chief executive"],
    "gm": ["gm", "general manager"], "owner": ["owner", "proprietor", "founder"],
    "proprietor": ["proprietor", "owner"], "engineer": ["engineer", "engg"], "engg": ["engineer", "engg"],
    "hr": ["hr", "human resource"], "maintenance": ["maintenance", "maint"],
}
INTERNAL_FIELDS = {"_id", "search_text", "embedding", "needs_review", "review_reasons", "source_doc_id",
                   "cleaned_at", "uploaded_at", "norm_company", "sheet_name", "source_row"}
SHOW_ORDER = ["person", "designation", "phone", "phone_2", "email", "email_2", "location", "linkedin"]


def stem(w):
    w = w.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(text):
    return re.findall(r"[a-z0-9]+", str(text).lower())


def norm_company(s):
    return re.sub(r"[^a-z0-9]+", " ", LEGAL.sub(" ", str(s).lower())).strip()


def similarity(a, b):
    sa = str(a).strip().lower()
    sb = str(b).strip().lower()
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 1.0
    if fuzz is not None:
        # Use exact full Levenshtein ratio, NOT WRatio which causes false matches
        return fuzz.ratio(sa, sb) / 100.0
    return SequenceMatcher(None, sa, sb).ratio()


# ---------------------------------------------------------------------------
# Schema detection & field extraction helpers (multi-format support)
# ---------------------------------------------------------------------------
COMPANY_KEYS = (
    "company", "norm_company", "Company Name", "company_name", "Company", "Firm",
    "firm_name", "Organization", "organization", "Organisation", "organisation",
    "Client", "client", "business_name", "Vendor", "vendor"
)

PERSON_KEYS = (
    "person", "Person Name", "person_name", "Contact Person", "contact_person",
    "name", "Name", "Full Name", "Employee Name", "first_name"
)

DESIGNATION_KEYS = (
    "designation", "Designation", "Role", "role", "Job Title", "job_title",
    "Position", "position", "Title", "title"
)

LOCATION_KEYS = (
    "location", "Location", "City", "city", "State", "state", "Address", "address",
    "Country", "country", "Plant", "plant"
)

PHONE_KEYS = (
    "phone", "Phone", "Phone Number", "phone_number", "Mobile", "mobile",
    "Contact Number", "contact_number", "Contact No", "contact_no", "Tel", "telephone"
)

EMAIL_KEYS = (
    "email", "Email", "Email Address", "email_address", "Mail ID", "mail_id", "Mail", "mail"
)

LINKEDIN_KEYS = (
    "linkedin", "LinkedIn", "LinkedIn URL", "linkedin_url", "Linkedin",
    "LinkedIn Profile", "linkedin_profile", "Profile URL", "profile_url",
    "LinkedIn Link", "linkedin_link"
)


def _get_val(doc: dict, keys: tuple) -> str:
    """Extracts first matching non-empty string value for keys from doc or nested sub-dictionaries."""
    if not isinstance(doc, dict):
        return ""
    # 1. Top-level
    for k in keys:
        v = doc.get(k)
        if v and not isinstance(v, (dict, list)):
            s = str(v).strip()
            if s and s.lower() not in ("none", "null", "nan", "not available", "-"):
                return s
    # 2. Nested dicts (data, normalized_data, raw_data)
    for sub_key in ("data", "normalized_data", "raw_data"):
        sub = doc.get(sub_key)
        if isinstance(sub, dict):
            for k in keys:
                v = sub.get(k)
                if v and not isinstance(v, (dict, list)):
                    s = str(v).strip()
                    if s and s.lower() not in ("none", "null", "nan", "not available", "-"):
                        return s
    return ""


# ---------------------------------------------------------------------------
# Vocabulary built from the database itself
# ---------------------------------------------------------------------------
@dataclass
class Vocab:
    companies: dict = field(default_factory=dict)       # norm_company -> display name
    comp_stems: dict = field(default_factory=dict)      # norm_company -> tuple(stems)
    designations: Counter = field(default_factory=Counter)
    desig_stems: set = field(default_factory=set)
    locations: dict = field(default_factory=dict)       # lower text -> display
    loc_stems: dict = field(default_factory=dict)       # lower text -> tuple(stems)


def build_vocab(db, collections):
    v = Vocab()
    names = defaultdict(Counter)

    search_cols = list(collections or [])
    try:
        internal_cols = {"user", "users", "uploaders", "datasets", "fs.files", "fs.chunks"}
        for existing in db.list_collection_names():
            if not existing.startswith("system.") and existing.lower() not in internal_cols and existing not in search_cols:
                search_cols.append(existing)
    except Exception:
        pass

    projection = {
        "company": 1, "norm_company": 1, "designation": 1, "location": 1, "person": 1,
        "Company Name": 1, "Company": 1, "company_name": 1, "Firm": 1, "Organization": 1, "Client": 1,
        "Person Name": 1, "Contact Person": 1, "name": 1, "Name": 1,
        "Designation": 1, "Role": 1, "Job Title": 1,
        "Location": 1, "City": 1, "State": 1, "city": 1, "state": 1,
        "data": 1, "normalized_data": 1, "raw_data": 1
    }

    for c in search_cols:
        try:
            if c not in db.list_collection_names():
                continue
            for d in db[c].find({}, projection):
                comp = _get_val(d, COMPANY_KEYS)
                nc = (d.get("norm_company") or (d.get("normalized_data") or {}).get("norm_company") or norm_company(comp)) if comp else ""
                if nc:
                    names[nc][comp] += 1
                des = _get_val(d, DESIGNATION_KEYS)
                if des:
                    v.designations[des] += 1
                loc_raw = _get_val(d, LOCATION_KEYS)
                for loc in re.split(r"[\s/,;|]+", loc_raw):
                    loc = loc.strip()
                    if len(loc) >= 2 and loc.lower() not in STOP:
                        v.locations.setdefault(loc.lower(), loc)
        except Exception:
            continue

    for nc, cnt in names.items():
        v.companies[nc] = cnt.most_common(1)[0][0]
        v.comp_stems[nc] = tuple(stem(t) for t in tokens(nc))
    for des in v.designations:
        v.desig_stems |= {stem(t) for t in tokens(des)}
    for loc in v.locations:
        v.loc_stems[loc] = tuple(stem(t) for t in tokens(loc))
    return v


# ---------------------------------------------------------------------------
# Query understanding
# ---------------------------------------------------------------------------
@dataclass
class Parsed:
    raw: str
    companies: list = field(default_factory=list)       # [{"text", "norms": [..], "how"}]
    designations: list = field(default_factory=list)    # [[stem, ...], ...]  OR between phrases
    designation_text: list = field(default_factory=list)  # what the user typed, for display
    locations: list = field(default_factory=list)
    free_text: list = field(default_factory=list)       # unresolved words -> searched in person names
    unresolved_companies: list = field(default_factory=list)


def _find_full_companies(words, vocab):
    """Companies whose whole (suffix-free) name appears in the query words, longest first."""
    qs = [stem(t) for t in words]
    used, found = [False] * len(qs), []
    stems_to_norms = defaultdict(list)
    for nc_k, cs_k in vocab.comp_stems.items():
        stems_to_norms[cs_k].append(nc_k)

    for nc, cs in sorted(vocab.comp_stems.items(), key=lambda x: -len(x[1])):
        k = len(cs)
        if k == 0 or (k == 1 and len(cs[0]) < 2):
            continue
        for i in range(len(qs) - k + 1):
            if tuple(qs[i:i + k]) == cs and not any(used[i:i + k]):
                for j in range(i, i + k):
                    used[j] = True
                matched_norms = stems_to_norms.get(cs, [nc])
                query_sub = " ".join(words[i:i + k]).lower()
                best_display = vocab.companies[nc]
                for nm in matched_norms:
                    disp = vocab.companies.get(nm, "")
                    if disp.lower() == query_sub or disp.lower().startswith(query_sub):
                        best_display = disp
                        break
                found.append({"text": best_display, "norms": matched_norms, "how": "exact"})
                break
    return found, used


def _company_candidates(words, vocab, limit=30):
    """Partial or misspelt company mention -> (norms, how). Strict matching avoids false positives."""
    ws = {stem(w) for w in words if w and w not in STOP}
    if not ws:
        return [], ""

    # 1. Exact stems subset matching (e.g. 'tvs' in 'tvs motor', or 'delphi tvs' in 'delphi tvs diesel')
    contained = [
        nc for nc, cs in vocab.comp_stems.items()
        if (ws <= set(cs))
    ]
    if contained:
        return sorted(contained, key=len)[:limit], "partial"

    # 2. Prefix matching on company tokens
    prefix_matches = [
        nc for nc, cs in vocab.comp_stems.items()
        if (all(any(c.startswith(w) for c in cs if len(c) >= len(w)) for w in ws) if len(ws) > 1
            else any(c.startswith(w) for w in ws for c in cs if len(w) >= 3 and len(c) >= 3))
           or nc.startswith(" ".join(words))
    ]
    if prefix_matches:
        return sorted(prefix_matches, key=len)[:limit], "partial"

    # 3. Fuzzy matching with typo tolerance ONLY for longer words (>= 4 chars) with high similarity (>= 0.82)
    # Never apply fuzzy typo matching to 2- or 3-letter acronyms (like 'tvs') to prevent false matches
    phrase = " ".join(words)
    if len(phrase) >= 4 and all(len(w) >= 3 for w in words):
        scored = sorted(((similarity(phrase, nc), nc) for nc in vocab.companies), reverse=True)[:5]
        good = [nc for s_, nc in scored if s_ >= 0.82]
        if good:
            return good, "fuzzy"

    return [], ""


def parse_query(q, vocab):
    p = Parsed(raw=q)
    toks = [t for t in re.findall(r"[a-z0-9]+|[,;|/&\n]", q.lower()) if t not in LEGAL_WORDS]
    word_idx = [i for i, t in enumerate(toks) if t[0].isalnum()]
    full, used_w = _find_full_companies([toks[i] for i in word_idx], vocab)
    p.companies.extend(full)
    used = {word_idx[j] for j, u in enumerate(used_w) if u}

    chunks, cur = [], []
    for i, t in enumerate(toks):
        if i in used or t in SEP_PUNCT or t in SEP_WORDS:
            if cur:
                chunks.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        chunks.append(cur)

    all_remaining_words = []
    for chunk in chunks:
        words = [w for w in chunk if w not in STOP]
        if not words:
            continue
        has_role = any(stem(w) in ROLE_WORDS for w in words)
        if has_role:
            role = [w for w in words if stem(w) in ROLE_WORDS or stem(w) in vocab.desig_stems]
        elif all(stem(w) in vocab.desig_stems for w in words):
            role = list(words)
        else:
            role = []
        others = [w for w in words if w not in role]
        if role:
            p.designations.append([stem(w) for w in role])
            p.designation_text.append(" ".join(role))
        if others:
            all_remaining_words.extend(others)
            norms, how = _company_candidates(others, vocab)
            if norms:
                p.companies.append({"text": " ".join(others), "norms": norms, "how": how})
            else:
                p.unresolved_companies.append(" ".join(others))

    # If no companies resolved via chunks, try all remaining words combined as one company query
    if not p.companies and all_remaining_words:
        norms, how = _company_candidates(all_remaining_words, vocab)
        if norms:
            p.companies.append({"text": " ".join(all_remaining_words), "norms": norms, "how": how})
            p.unresolved_companies = [u for u in p.unresolved_companies if u not in " ".join(all_remaining_words)]

    return p


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def _desig_regex(stems_):
    parts = []
    for s in stems_:
        alts = SYNONYMS.get(s, [s])
        parts.append("(?:" + "|".join(re.escape(a) for a in dict.fromkeys(alts)) + ")")
    return parts


def _build_filter(norms, parsed, use_desig=True, use_loc=False, extra_filter=None, vocab=None):
    conds = []
    if extra_filter:
        conds.append(extra_filter)
    if norms is not None:
        comp_ors = [{"norm_company": {"$in": norms}}]
        for n in norms:
            disp = vocab.companies.get(n) if vocab else None
            parts = tokens(n)
            pat = (r"\b" + r"\s+".join(re.escape(p) for p in parts) + r"\b") if parts else re.escape(n)

            if disp:
                comp_ors.append({"company": disp})
                comp_ors.append({"Company Name": disp})
                comp_ors.append({"data.Company Name": disp})

            for field_name in ["company", "Company Name", "Company", "company_name", "Firm"]:
                comp_ors.append({field_name: {"$regex": pat, "$options": "i"}})
                comp_ors.append({f"data.{field_name}": {"$regex": pat, "$options": "i"}})
            comp_ors.append({"normalized_data.company_name": {"$regex": pat, "$options": "i"}})
            comp_ors.append({"raw_data.Company Name": {"$regex": pat, "$options": "i"}})

        conds.append({"$or": comp_ors} if len(comp_ors) > 1 else comp_ors[0])

    if norms is None and parsed.unresolved_companies:
        u_ors = []
        for u in parsed.unresolved_companies:
            u_toks = tokens(u)
            if not u_toks:
                continue
            pat = r"\b" + r"\s+".join(re.escape(x) for x in u_toks)
            for field_name in ["company", "Company Name", "Company", "company_name", "Firm"]:
                u_ors.append({field_name: {"$regex": pat, "$options": "i"}})
                u_ors.append({f"data.{field_name}": {"$regex": pat, "$options": "i"}})
            u_ors.append({"norm_company": {"$regex": re.escape(norm_company(u)), "$options": "i"}})
            u_ors.append({"normalized_data.company_name": {"$regex": pat, "$options": "i"}})
            u_ors.append({"raw_data.Company Name": {"$regex": pat, "$options": "i"}})
        if u_ors:
            conds.append({"$or": u_ors})

    if use_desig and parsed.designations:
        desig_ors = []
        for stems_ in parsed.designations:
            ands = []
            for part in _desig_regex(stems_):
                pat = r"\b" + part
                field_ors = [
                    {"designation": {"$regex": pat, "$options": "i"}},
                    {"Designation": {"$regex": pat, "$options": "i"}},
                    {"Role": {"$regex": pat, "$options": "i"}},
                    {"Job Title": {"$regex": pat, "$options": "i"}},
                    {"data.Designation": {"$regex": pat, "$options": "i"}},
                    {"data.Role": {"$regex": pat, "$options": "i"}},
                    {"data.Job Title": {"$regex": pat, "$options": "i"}},
                    {"normalized_data.designation": {"$regex": pat, "$options": "i"}},
                ]
                ands.append({"$or": field_ors})
            desig_ors.append({"$and": ands} if len(ands) > 1 else ands[0])
        conds.append({"$or": desig_ors} if len(desig_ors) > 1 else desig_ors[0])

    return {"$and": conds} if len(conds) > 1 else (conds[0] if conds else {})


def _clean_designation(d):
    if not d:
        return "Not Available"
    parts = [p.strip() for p in re.split(r"[/;]+", str(d)) if p.strip()]
    valid = [
        p for p in parts
        if p.lower() not in {
            "not available", "not publicly available", "publicly not available",
            "not available publicly", "not provided", "not mentioned", "n/a", "na",
            "null", "none", "-", "--", "nil", "unknown", "."
        }
        and not re.search(r"\bnot\s+publicly\s+available\b|\bpublicly\s+not\s+available\b|\bnot\s+available\b", p, re.I)
    ]
    return " / ".join(valid) if valid else "Not Available"


def _public(doc, collection):
    rec = {}

    # 1. Nested dictionaries (data, normalized_data, raw_data)
    for sub_key in ("data", "normalized_data", "raw_data"):
        sub = doc.get(sub_key)
        if isinstance(sub, dict):
            for k, v in sub.items():
                if k not in INTERNAL_FIELDS and not k.startswith("norm_") and v not in ("", None):
                    rec[k] = v

    # 2. Top-level keys
    for k, v in doc.items():
        if k not in INTERNAL_FIELDS and k not in ("data", "normalized_data", "raw_data") and not k.startswith("norm_") and v not in ("", None):
            rec[k] = v

    # 3. Standardized fields for uniform card & answer formatting
    comp = _get_val(doc, COMPANY_KEYS)
    person = _get_val(doc, PERSON_KEYS)
    desig = _get_val(doc, DESIGNATION_KEYS)
    phone = _get_val(doc, PHONE_KEYS)
    phone_2 = doc.get("phone_2") or (doc.get("data") or {}).get("phone_2") or (doc.get("data") or {}).get("Phone 2")
    email = _get_val(doc, EMAIL_KEYS)
    email_2 = doc.get("email_2") or (doc.get("data") or {}).get("email_2") or (doc.get("data") or {}).get("Email 2")
    loc = _get_val(doc, LOCATION_KEYS)
    addr = _get_val(doc, ("Address", "address", "street", "Street"))
    city = _get_val(doc, ("City", "city", "Town", "town"))
    state = _get_val(doc, ("State", "state", "Province", "province"))
    loc_parts = []
    if addr:
        loc_parts.append(addr)
    if city and city not in loc_parts:
        loc_parts.append(city)
    if state and state not in loc_parts:
        loc_parts.append(state)
    combined_loc = ", ".join(loc_parts) if loc_parts else loc

    linkedin = _get_val(doc, LINKEDIN_KEYS)

    if comp:
        rec.setdefault("company", comp)
    if person:
        rec.setdefault("person", person)
    if desig:
        clean_d = _clean_designation(desig)
        rec.setdefault("designation", clean_d)
    if phone:
        rec.setdefault("phone", phone)
    if phone_2:
        rec.setdefault("phone_2", phone_2)
    if email:
        rec.setdefault("email", email)
    if email_2:
        rec.setdefault("email_2", email_2)
    if combined_loc:
        rec.setdefault("location", combined_loc)
    if linkedin:
        rec.setdefault("linkedin", linkedin)

    s_file = _get_val(doc, ("source_file", "source_filename", "Source File", "Source_File", "file_name", "filename", "dataset_name"))
    if s_file:
        rec.setdefault("source_file", s_file)

    rec["_collection"] = collection
    return rec


def _dedupe(records):
    seen, out = set(), []
    for r in records:
        key = (norm_company(r.get("company", "")), str(r.get("person", "")).lower(),
               r.get("phone") or r.get("email") or r.get("designation", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _fetch(db, collections, flt, limit):
    docs = []
    for c in collections:
        if c not in db.list_collection_names():
            continue
        docs += [_public(d, c) for d in db[c].find(flt).limit(limit)]
    return _dedupe(docs)


def search(db, collections, parsed, vocab, limit=500, extra_filter=None):
    interp = []
    if parsed.companies:
        interp.append("companies: " + ", ".join(c["text"] for c in parsed.companies))
    if parsed.designations:
        interp.append("designation: " + " / ".join(parsed.designation_text))

    groups, not_found = [], []
    if parsed.companies:
        parsed = Parsed(**{**parsed.__dict__, "free_text": []})
        for comp in parsed.companies:
            recs = _fetch(db, collections, _build_filter(comp["norms"], parsed, extra_filter=extra_filter, vocab=vocab), limit)
            if not recs and parsed.designations:
                # Relax designation to show contacts at company
                recs = _fetch(db, collections, _build_filter(comp["norms"], parsed, use_desig=False, extra_filter=extra_filter, vocab=vocab), limit)
            if recs:
                by_co = defaultdict(list)
                for r in recs:
                    co_name = r.get("company") or comp["text"]
                    by_co[co_name].append(r)
                for co, rs in by_co.items():
                    srcs = [r.get("source_file") or r.get("dataset_name") or r.get("_collection") for r in rs]
                    srcs = [s for s in srcs if s and not str(s).lower().startswith("mongodb") and str(s).lower() not in ("dataset_records", "null", "none", "not available")]
                    uniq_srcs = list(dict.fromkeys(srcs))
                    src_str = ", ".join(uniq_srcs) if uniq_srcs else ""
                    groups.append({
                        "company": co,
                        "source_file": src_str,
                        "count": len(rs),
                        "records": rs,
                        "matched_by": comp["how"]
                    })
            else:
                not_found.append(comp["text"])
    else:
        # Search by designation or unresolved company names
        recs = _fetch(db, collections, _build_filter(None, parsed, extra_filter=extra_filter, vocab=vocab), limit)
        by_co = defaultdict(list)
        for r in recs:
            co_name = r.get("company") or "Company"
            by_co[co_name].append(r)
        for co, rs in sorted(by_co.items()):
            srcs = [r.get("source_file") or r.get("dataset_name") or r.get("_collection") for r in rs]
            srcs = [s for s in srcs if s and not str(s).lower().startswith("mongodb") and str(s).lower() not in ("dataset_records", "null", "none", "not available")]
            uniq_srcs = list(dict.fromkeys(srcs))
            src_str = ", ".join(uniq_srcs) if uniq_srcs else ""
            groups.append({
                "company": co,
                "source_file": src_str,
                "count": len(rs),
                "records": rs,
                "matched_by": "filter"
            })

    report_unresolved = parsed.unresolved_companies if (parsed.companies or not groups) else []
    suggestions = {}
    for name in not_found + [u for u in report_unresolved if u not in not_found]:
        near = sorted(((similarity(norm_company(name), nc), nc) for nc in vocab.companies), reverse=True)[:3]
        suggestions[name] = [vocab.companies[nc] for s, nc in near if s >= 0.80]
    if not groups and parsed.designations and not parsed.companies:
        near = sorted(((similarity(" ".join(parsed.designations[0]), d.lower()), d)
                       for d in vocab.designations), reverse=True)[:5]
        suggestions["designation"] = [d for s, d in near if s >= 0.75]

    return {"query": parsed.raw, "understood_as": interp, "groups": groups,
            "total": sum(g["count"] for g in groups), "companies_found": len(groups),
            "not_found": not_found, "unresolved": report_unresolved,
            "suggestions": suggestions, "notes": []}


# ---------------------------------------------------------------------------
# Answer text (strict schema: only fields that have a value)
# ---------------------------------------------------------------------------
def _fmt(rec):
    parts = []
    for k in SHOW_ORDER:
        v = rec.get(k)
        if not v:
            continue
        if k.startswith("email"):
            v = f"[{v}](mailto:{v})"
        label = {"phone_2": "Phone 2", "email_2": "Email 2"}.get(k, k.capitalize())
        parts.append(f"**{label}:** {v}")
    return " | ".join(parts)


def format_markdown(res, per_company=15):
    try:
        limit = int(per_company)
    except (TypeError, ValueError):
        limit = 15
    lines = []

    for g_idx, g in enumerate(res.get("groups", [])):
        if g_idx > 0:
            lines.append("---")
            lines.append("")

        comp_name = g.get("company", "Company")
        records = g.get("records", [])
        primary_source = (
            g.get("source_file") or
            (records[0].get("source_file") if records else "") or
            (records[0].get("dataset_name") if records else "") or
            (records[0].get("_collection") if records else "") or
            (records[0].get("source_collection") if records else "") or
            ""
        )

        lines.append(f"Company Name: {comp_name}")
        if primary_source:
            lines.append(f"Source: {primary_source}")
        lines.append("")

        for r_idx, r in enumerate(records[:limit], 1):
            if r_idx > 1:
                lines.append("")
            lines.append(f"Contact Person {r_idx}:")
            lines.append(f"- Name: {r.get('person') or 'Not Available'}")
            lines.append(f"- Designation: {_clean_designation(r.get('designation'))}")

            # Location formatting: Address, City, State
            addr = r.get("address")
            city = r.get("city")
            state = r.get("state")
            if addr or city or state:
                if addr:
                    lines.append(f"- Address: {addr}")
                if city:
                    lines.append(f"- City: {city}")
                if state:
                    lines.append(f"- State: {state}")
            elif r.get("location"):
                raw_loc = str(r["location"])
                parts = [p.strip() for p in re.split(r"[;/]+", raw_loc) if p.strip()]
                if len(parts) >= 3:
                    lines.append(f"- Address: {parts[0]}")
                    lines.append(f"- City: {parts[1]}")
                    lines.append(f"- State: {parts[2]}")
                elif len(parts) == 2:
                    lines.append(f"- City: {parts[0]}")
                    lines.append(f"- State: {parts[1]}")
                else:
                    lines.append(f"- Location: {raw_loc}")
            else:
                lines.append("- Location: Not Available")

            e1 = r.get("email")
            e2 = r.get("email_2")
            if e1 and e2:
                lines.append(f"- Email 1: {e1}")
                lines.append(f"- Email 2: {e2}")
            elif e1:
                lines.append(f"- Email: {e1}")
            else:
                lines.append("- Email: Not Available")

            p1 = r.get("phone")
            p2 = r.get("phone_2")
            if p1 and p2:
                lines.append(f"- Contact Number 1: {p1}")
                lines.append(f"- Contact Number 2: {p2}")
            elif p1:
                lines.append(f"- Contact Number: {p1}")
            else:
                lines.append("- Contact Number: Not Available")

            lines.append(f"- LinkedIn URL: {r.get('linkedin') or 'Not Available'}")

        if len(records) > per_company:
            lines.append("")
            lines.append(f"- ...and {len(records) - per_company} more contacts.")
        lines.append("")

    for name in res.get("not_found", []) + [u for u in res.get("unresolved", []) if u not in res.get("not_found", [])]:
        sug = res.get("suggestions", {}).get(name)
        if sug:
            lines.append(f"**No records found for \"{name}\".** Data is not available in the database. Did you mean: {', '.join(sug)}?")
        else:
            lines.append(f"**No records found for \"{name}\".** Data is not available in the database.")
    if res.get("suggestions", {}).get("designation"):
        lines.append("**No matching designation.** Similar designations: " + ", ".join(res["suggestions"]["designation"]))
    if not res.get("groups") and not lines:
        lines.append("No records matched your search. Data is not available.")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Vocabulary Cache & Startup Integration Helpers
# ---------------------------------------------------------------------------
_cached_vocab: Optional[Vocab] = None


def get_cached_vocab() -> Optional[Vocab]:
    """Returns the cached vocab or None."""
    global _cached_vocab
    return _cached_vocab


def invalidate_vocab():
    """Invalidates the in-memory vocabulary cache."""
    global _cached_vocab
    _cached_vocab = None


def get_or_build_vocab(db, collections: List[str], force: bool = False) -> Vocab:
    """
    Returns the cached vocabulary if available; builds and caches it otherwise.
    """
    global _cached_vocab
    if _cached_vocab is not None and not force:
        return _cached_vocab
    _cached_vocab = build_vocab(db, collections)
    return _cached_vocab


def ensure_contact_indexes(db, collections: List[str]):
    """
    Creates indexes on norm_company, designation, location, and person across all collections.
    """
    for col_name in collections:
        if col_name not in db.list_collection_names():
            continue
        col = db[col_name]
        for field_name in ["norm_company", "designation", "location", "person"]:
            try:
                col.create_index([(field_name, 1)], background=True)
            except Exception:
                pass


def check_uncleaned_collections(db, collections: List[str]) -> List[str]:
    """
    Checks if any configured collection with documents lacks the norm_company field.
    Logs warning (counts only, NEVER values).
    Returns list of uncleaned collection names.
    """
    uncleaned = []
    existing = set(db.list_collection_names())
    for col_name in collections:
        if col_name not in existing:
            continue
        try:
            total = db[col_name].count_documents({})
            if total > 0:
                cleaned_count = db[col_name].count_documents({"norm_company": {"$exists": True, "$ne": ""}})
                if cleaned_count == 0:
                    uncleaned.append(col_name)
                    # Privacy rule: Log counts only, never cell values or record content
                    print(f"[WARNING] Collection '{col_name}' ({total} docs) has no 'norm_company' field. "
                          f"This dataset is not cleaned yet; search quality is reduced. Clean it first.")
        except Exception:
            pass
    return uncleaned
