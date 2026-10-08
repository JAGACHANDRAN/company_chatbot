import json
from app.database import get_database
from app.config import COLLECTION_NAME

def check_multi_merged():
    db = get_database()
    col = db[COLLECTION_NAME]
    
    count_multi = col.count_documents({"Records Merged": {"$gt": 1}})
    print(f"Records with Records Merged > 1: {count_multi}")
    
    if count_multi > 0:
        samples = list(col.find({"Records Merged": {"$gt": 1}}, {"embedding": 0}).limit(3))
        for idx, d in enumerate(samples, 1):
            print(f"\nMulti-Merged Doc {idx}:")
            print(f"  company: {d.get('company')}")
            print(f"  source_file: {d.get('source_file')}")
            print(f"  Source File: {d.get('Source File')}")
            print(f"  Sources: {d.get('Sources')}")
            print(f"  Records Merged: {d.get('Records Merged')}")

if __name__ == "__main__":
    check_multi_merged()
