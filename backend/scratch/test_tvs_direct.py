import re
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import get_database
from app.utils.normalization import normalize_company

db = get_database()
coll = db["dataset_records"]

name = "tvs"
n_norm = normalize_company(name)
regex = rf"(^|\s){re.escape(n_norm)}(\s|$)"

docs = list(coll.find({
    "$or": [
        {"norm_company": {"$regex": regex, "$options": "i"}},
        {"$and": [
            {"norm_company": {"$in": [None, ""]}},
            {"company": {"$regex": regex, "$options": "i"}}
        ]}
    ]
}, {"embedding": 0}))

print(f"Total TVS records matching rule: {len(docs)}")
unique_companies = sorted(list(set(d.get("company", "") for d in docs)))
print(f"Distinct raw company names: {len(unique_companies)}")
for c in unique_companies:
    print(" -", c)
