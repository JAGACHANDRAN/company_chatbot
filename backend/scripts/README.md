# Offline Data Cleaning Tools (No AI, Local & Deterministic)

This directory contains offline data cleaning utilities for the Calispec AI project:
1. `clean_mongodb.py`: Clean and normalize existing collections already inside MongoDB.
2. `clean_dataset.py`: Clean raw `.csv` and `.xlsx` files in an input directory.
3. `cleaner_core.py`: Imports and exposes the cleaning engine from `app.services.data_cleaner`.

---

## 1. Cleaning Data Already Inside MongoDB (`clean_mongodb.py`)

The cleaning script operates in three progressive, safe stages:

### Stage 1: DRY RUN (Zero writes, report only)
```bash
python clean_mongodb.py --env ../.env
```
- **What it does**: Reads each collection listed in your `.env` (`MONGODB_COLLECTIONS`), processes records offline, and writes an Excel audit report for each collection into `./mongo_reports/` (e.g. `metrology_report.xlsx`).
- **Safety**: **Nothing** is modified or written to MongoDB.

### Stage 2: APPLY (Create separate `*_cleaned` collections)
```bash
python clean_mongodb.py --env ../.env --apply
```
- **What it does**: Cleans all collections and writes the normalized results to new collections named `<collection>_cleaned` (e.g., `metrology_cleaned`).
- **Safety**: Your original collections remain completely untouched.
- **Verification**: Point your `.env`'s `MONGODB_COLLECTIONS` to the `*_cleaned` collections and test the chatbot queries to verify search quality.

### Stage 3: REPLACE (Backup originals, then overwrite in-place)
```bash
python clean_mongodb.py --env ../.env --replace
```
- **What it does**:
  1. Creates a full backup copy of each collection to `<collection>_backup`.
  2. Verifies the backup record count matches the original count.
  3. Replaces the original collection with the cleaned records.
- **Confirmation prompt**: Requires typing `YES` to proceed.

---

## 2. Cleaning Files in a Folder (`clean_dataset.py`)

To batch clean raw contact spreadsheets before uploading:
```bash
python clean_dataset.py --input ./raw_data --output ./cleaned_output
```
Outputs:
- `<filename>_cleaned.xlsx`: Cleaned data rows.
- `<filename>_report.xlsx`: Multi-sheet audit report (Summary, Column mapping, Changes, Needs review).
- `ALL_cleaned.xlsx`: All processed files merged and deduplicated.
- `cleaning_report.txt`: Summary statistics log.

---

## ⚠️ Important Post-Migration Note: Vector Embeddings
If vector search or semantic embeddings (`vector_search.py`) are enabled in your configuration (`PRIVACY_MODE=false`), remember to **regenerate vector embeddings** for the new or cleaned collections so the vector search index matches the newly cleaned text fields (`company`, `person`, `designation`, `location`, `phone`, `email`).
