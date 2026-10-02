"""
Calispec User Management CLI Script
Allows administrator to provision and manage authorized users (DATA_UPLOADER and CHAT_USER).
Usage:
    python scripts/manage_users.py list
    python scripts/manage_users.py add <email> <role> <password>
    python scripts/manage_users.py delete <email>
    python scripts/manage_users.py change-role <email> <new_role>
"""
import sys
import os

# Add parent directory to sys.path so app modules can be loaded
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.auth import (
    create_user,
    get_users_collection,
    ensure_user_indexes,
    ROLE_DATA_UPLOADER,
    ROLE_CHAT_USER,
    ALLOWED_ROLES
)


def list_users():
    col = get_users_collection()
    ensure_user_indexes()
    users = list(col.find({}, {"_id": 0, "password_hash": 0}))
    print("\n--- Calispec Authorized Users ---")
    if not users:
        print("No users found in database.")
    for idx, u in enumerate(users, 1):
        print(f"[{idx}] Email: {u.get('email')} | Role: {u.get('role')} | UserID: {u.get('user_id')}")
    print("---------------------------------\n")


def add_user(email, role, password):
    role_upper = role.upper().strip()
    if role_upper not in ALLOWED_ROLES:
        print(f"Error: Invalid role '{role}'. Allowed roles: {', '.join(ALLOWED_ROLES)}")
        sys.exit(1)
    try:
        res = create_user(email=email, password=password, role=role_upper)
        print(f"[SUCCESS] User created: {res['email']} ({res['role']})")
    except Exception as e:
        print(f"[ERROR] Could not create user: {e}")
        sys.exit(1)


def delete_user(email):
    col = get_users_collection()
    res = col.delete_one({"email": email.strip().lower()})
    if res.deleted_count > 0:
        print(f"[SUCCESS] User '{email}' was deleted.")
    else:
        print(f"[NOTICE] No user found with email '{email}'.")


def change_role(email, new_role):
    new_role_upper = new_role.upper().strip()
    if new_role_upper not in ALLOWED_ROLES:
        print(f"Error: Invalid role '{new_role}'. Allowed roles: {', '.join(ALLOWED_ROLES)}")
        sys.exit(1)
    col = get_users_collection()
    res = col.update_one(
        {"email": email.strip().lower()},
        {"$set": {"role": new_role_upper}}
    )
    if res.modified_count > 0:
        print(f"[SUCCESS] Role for '{email}' updated to {new_role_upper}.")
    else:
        print(f"[NOTICE] No user updated. Verify email '{email}'.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/manage_users.py [list | add <email> <role> <password> | delete <email> | change-role <email> <role>]")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd == "list":
        list_users()
    elif cmd == "add":
        if len(sys.argv) < 5:
            print("Usage: python scripts/manage_users.py add <email> <DATA_UPLOADER|CHAT_USER> <password>")
            sys.exit(1)
        add_user(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python scripts/manage_users.py delete <email>")
            sys.exit(1)
        delete_user(sys.argv[2])
    elif cmd == "change-role":
        if len(sys.argv) < 4:
            print("Usage: python scripts/manage_users.py change-role <email> <DATA_UPLOADER|CHAT_USER>")
            sys.exit(1)
        change_role(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command '{cmd}'. Available: list, add, delete, change-role")
