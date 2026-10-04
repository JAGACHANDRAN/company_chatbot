# Backend Automation & Maintenance Scripts

This directory contains utility scripts for offline data cleaning, user management, and MongoDB maintenance for the Calispec AI project:

1. **`manage_users.py`**: CLI for provisioning authorized uploaders and chat users in the unified MongoDB `users` collection.
2. **`clean_mongodb.py`**: Offline cleaning and in-place normalization for collections in MongoDB.
3. **`clean_dataset.py`**: Batch cleaning of raw `.csv` and `.xlsx` files in local directories.
4. **`generate_embeddings.py`**: Vector embedding generator tool for Atlas vector search.
5. **`inspect_and_migrate_db.py`**: Database inspection and schema validation utility.

---

## 1. User Management (`manage_users.py`)

Provision, inspect, or modify user roles:

```bash
# List all registered users
python manage_users.py list

# Create a new data uploader
python manage_users.py add admin@example.com DATA_UPLOADER StrongPassword123

# Change user role
python manage_users.py change-role user@example.com DATA_UPLOADER

# Delete user
python manage_users.py delete user@example.com
```

---

## 2. MongoDB In-Place Data Cleaning (`clean_mongodb.py`)

Safe three-stage offline cleaning:

### Stage 1: DRY RUN (Zero writes, generates Excel reports)
```bash
python clean_mongodb.py --env ../.env
```

### Stage 2: APPLY (Creates side-by-side `<collection>_cleaned` collections)
```bash
python clean_mongodb.py --env ../.env --apply
```

### Stage 3: REPLACE (Creates `<collection>_backup`, then safely overwrites in-place)
```bash
python clean_mongodb.py --env ../.env --replace
```

---

## 3. Batch Spreadsheet Cleaning (`clean_dataset.py`)

Batch clean raw contact spreadsheets before uploading:

```bash
python clean_dataset.py --input ./raw_data --output ./cleaned_output
```

---

## 4. Vector Embedding Generation (`generate_embeddings.py`)

If `PRIVACY_MODE=false` and Atlas Vector Search is enabled:

```bash
python generate_embeddings.py --force
```
