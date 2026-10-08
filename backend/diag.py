import os
import sys
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
col = MongoClient(os.getenv("MONGODB_URI"))[os.getenv("DB_NAME", "calispec")]["dataset_records"]
INDEX = os.getenv("VECTOR_INDEX_NAME", "vector_index")

for ix in col.list_search_indexes():
    print("INDEX:", ix["name"], "| status:", ix.get("status"), "| queryable:", ix.get("queryable"))
    print("DEFINITION:", ix.get("latestDefinition"))

try:
    qv_resp = requests.post(
        "http://localhost:11434/api/embed",
        json={
            "model": "nomic-embed-text",
            "input": ["search_query: calibration lab in Pune"]
        },
        timeout=10
    ).json()
    qv = qv_resp["embeddings"][0]
    print("query dim:", len(qv))
except Exception as e:
    print("OLLAMA EMBED ERROR:", type(e).__name__, e)
    qv = None

if qv:
    try:
        res = list(col.aggregate([
            {
                "$vectorSearch": {
                    "index": INDEX,
                    "path": "embedding",
                    "queryVector": qv,
                    "numCandidates": 200,
                    "limit": 3
                }
            },
            {"$project": {"embedding": 0, "score": {"$meta": "vectorSearchScore"}}}
        ]))
        print("RESULTS:", len(res))
        for r in res:
            # Mask phone and email in print if any
            clean_r = {k: v for k, v in r.items() if k not in ("phone", "phone_2", "email", "email_2")}
            print(clean_r)
    except Exception as e:
        print("VECTOR SEARCH ERROR:", type(e).__name__, e)
