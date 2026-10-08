import re
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_database
from app.utils.normalization import normalize_company

db = get_database()
coll = db["dataset_records"]

def search_company_keyword(name: str):
    n_norm = normalize_company(name)
    if not n_norm:
        return []
    
    tokens = n_norm.split()
    if len(n_norm) <= 3:
        # Whole-word match only for <=3 chars
        regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"
        query = {
            "$or": [
                {"norm_company": {"$regex": regex, "$options": "i"}},
                {"$and": [
                    {"norm_company": {"$in": [None, ""]}},
                    {"company": {"$regex": regex, "$options": "i"}}
                ]}
            ]
        }
    else:
        # Exact, starts-with, whole-word phrase, or all-tokens
        if len(tokens) == 1:
            regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"
            query = {
                "$or": [
                    {"norm_company": {"$regex": regex, "$options": "i"}},
                    {"$and": [
                        {"norm_company": {"$in": [None, ""]}},
                        {"company": {"$regex": regex, "$options": "i"}}
                    ]}
                ]
            }
        else:
            # Multi-word phrase or token-AND
            token_ands = [{"norm_company": {"$regex": rf"(^|\s){re.escape(t)}(\s|$)", "$options": "i"}} for t in tokens]
            query = {
                "$or": [
                    {"norm_company": {"$regex": rf"(^|\s){re.escape(n_norm)}(\s|$)", "$options": "i"}},
                    {"$and": token_ands},
                    {"$and": [
                        {"norm_company": {"$in": [None, ""]}},
                        {"company": {"$regex": rf"(^|\s){re.escape(n_norm)}(\s|$)", "$options": "i"}}
                    ]}
                ]
            }

    docs = list(coll.find(query, {"embedding": 0}))
    return docs

for comp in ["tvs", "ashok leyland", "titan", "bosch", "bhel", "hyundai", "tatamotors", "tata motors"]:
    res = search_company_keyword(comp)
    raw_names = list(set(d.get("company", "") for d in res))
    print(f"[{comp.upper()}]: {len(res)} records across {len(raw_names)} distinct company names")
