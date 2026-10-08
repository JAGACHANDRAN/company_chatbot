import re
import json
from app.database import get_database

db = get_database()

# 1. Inspect 10 sample documents
docs = list(db['dataset_records'].find({}, {'embedding': 0}).limit(10))
print("=== 10 SAMPLE DOCUMENTS ===")
for i, d in enumerate(docs, 1):
    print(f"--- Doc {i} ---")
    keys_to_show = [
        '_id', 'dataset_id', 'dataset_name', 'company', 'norm_company',
        'person', 'designation', 'department', 'phone', 'phone_2',
        'email', 'email_2', 'location', 'city', 'state', 'linkedin'
    ]
    for k in keys_to_show:
        print(f"  {k}: {repr(d.get(k))}")

# 2. Inspect datasets collection schema
ds_docs = list(db['datasets'].find({}).limit(5))
print("\n=== DATASETS COLLECTION SAMPLES ===")
for d in ds_docs:
    print(f"  _id: {d.get('_id')}, dataset_id: {repr(d.get('dataset_id'))}, dataset_name: {repr(d.get('dataset_name'))}, filename: {repr(d.get('filename'))}")

# 3. Check for missing or orphaned dataset_id in dataset_records
total_records = db['dataset_records'].count_documents({})
known_dataset_ids = set()
for d in db['datasets'].find({}, {'dataset_id': 1, '_id': 1}):
    if d.get('dataset_id'):
        known_dataset_ids.add(str(d['dataset_id']))
    if d.get('_id'):
        known_dataset_ids.add(str(d['_id']))

missing_dataset_id_count = db['dataset_records'].count_documents({
    '$or': [
        {'dataset_id': {'$exists': False}},
        {'dataset_id': None},
        {'dataset_id': ''}
    ]
})

orphaned_dataset_id_count = 0
for r in db['dataset_records'].find({}, {'dataset_id': 1}):
    did = r.get('dataset_id')
    if did and str(did) not in known_dataset_ids:
        orphaned_dataset_id_count += 1

print(f"\n=== DATASET INTEGRITY CHECK ===")
print(f"Total dataset_records: {total_records}")
print(f"Records with missing dataset_id: {missing_dataset_id_count}")
print(f"Records with orphaned dataset_id: {orphaned_dataset_id_count}")

# 4. Check TVS records in DB
tvs_recs = list(db['dataset_records'].find({
    '$or': [
        {'norm_company': {'$regex': r'\btvs\b', '$options': 'i'}},
        {'company': {'$regex': r'\btvs\b', '$options': 'i'}}
    ]
}, {'company': 1, 'norm_company': 1, 'dataset_name': 1, '_id': 0}))

print(f"\n=== TVS RECORDS IN DB (count={len(tvs_recs)}) ===")
distinct_tvs_companies = sorted(list(set(r.get('company') for r in tvs_recs if r.get('company'))))
distinct_norm_tvs = sorted(list(set(r.get('norm_company') for r in tvs_recs if r.get('norm_company'))))
print(f"Distinct company names ({len(distinct_tvs_companies)}): {distinct_tvs_companies}")
print(f"Distinct norm_company names ({len(distinct_norm_tvs)}): {distinct_norm_tvs}")
