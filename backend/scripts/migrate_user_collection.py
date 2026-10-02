import os
from pymongo import ASCENDING
from app.database import get_database

def init_user_collection():
    db = get_database()
    user_col = db["user"]
    user_col.create_index([("email", ASCENDING)], unique=True, background=True)

    # 1. Migrate existing uploaders into 'user'
    if "uploaders" in db.list_collection_names():
        for up in db["uploaders"].find():
            email = up.get("email", "").strip().lower()
            if email:
                user_col.update_one(
                    {"email": email},
                    {"$set": {
                        "email": email,
                        "role": up.get("role", "DATA_UPLOADER"),
                        "user_type": "uploader",
                        "created_at": up.get("created_at"),
                        "last_login": up.get("last_login"),
                        "user_id": up.get("user_id", f"usr_{email}")
                    }},
                    upsert=True
                )

    # 2. Migrate existing users into 'user'
    if "users" in db.list_collection_names():
        for u in db["users"].find():
            email = u.get("email", "").strip().lower()
            if email:
                user_col.update_one(
                    {"email": email},
                    {"$set": {
                        "email": email,
                        "role": u.get("role", "CHAT_USER"),
                        "user_type": "uploader" if u.get("role") == "DATA_UPLOADER" else "chat_user",
                        "password_hash": u.get("password_hash"),
                        "created_at": u.get("created_at"),
                        "last_login": u.get("last_login"),
                        "user_id": u.get("user_id", f"usr_{email}")
                    }},
                    upsert=True
                )

    print("Success! Collection 'user' initialized in MongoDB.")
    print("Total documents in 'user' collection:", user_col.count_documents({}))
    for doc in user_col.find({}, {"_id": 0, "password_hash": 0}):
        print(" -", doc)

if __name__ == "__main__":
    init_user_collection()
