# Calispec AI Search Chatbot — Backend (FastAPI + MongoDB Atlas)

High-performance FastAPI backend delivering secure Hybrid RAG search across **MongoDB Atlas** collections and uploaded tabular datasets (CSV / Excel).

---

## 🔒 Secure Hybrid RAG Architecture & Highlights

- **Local Embeddings (Strict Zero Leakage)**: 100% of record vector embeddings are generated locally via `http://localhost:11434` using `nomic-embed-text` (768 dimensions). No database record is ever transmitted to a cloud embedding API.
- **Reciprocal Rank Fusion (RRF k=60)**: Merges vector semantic matches and lexical structured matches, deduplicating records and returning the full list of similar candidates.
- **Strict PII Masking**: The cloud LLM (`gpt-oss:120b` on Ollama Cloud) receives only: question + short chat history (3 turns) + records with only `company`, `person`, `designation`, and `city`. Phone numbers and emails are replaced with `[PHONE_1]`, `[EMAIL_1]`... placeholders before transmission and restored in the backend afterwards.
- **Zero-LLM Exact Lookup**: Phone, email, and exact name queries are answered directly from MongoDB without invoking the LLM.
- **Admin Data Cleaning & In-Place Normalization**:
  - Interactive dry-run cleaning preview cached in memory with a 15-minute TTL.
  - Multi-sheet Excel audit report export.
  - Safe application via `new_collection` or confirmed `replace` with automated verified backups and instant rollback.
- **Role-Based Access Control (RBAC)**:
  - Unified MongoDB `users` collection.
  - JWT Bearer authentication issuing signed access tokens with verified role claims (`DATA_UPLOADER` vs `CHAT_USER`).

---

## 🚀 RAG Setup & Quickstart

Follow these 5 steps to initialize the secure Hybrid RAG system:

### 1. Pull Local Embedding Model in Ollama
Ensure local Ollama is running and pull `nomic-embed-text`:
```bash
ollama pull nomic-embed-text
```

### 2. Configure `.env`
Ensure your `backend/.env` contains your MongoDB Atlas URI and Ollama Cloud settings:
```env
MONGODB_URI=mongodb+srv://<user>:<pwd>@cluster0.mongodb.net/
MONGODB_DB_NAME=calispec
COLLECTION_NAME=dataset_records

EMBEDDING_PROVIDER=ollama_local
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
OLLAMA_LOCAL_URL=http://localhost:11434

LLM_MODE=cloud_direct
OLLAMA_CLOUD_URL=https://ollama.com
OLLAMA_API_KEY=your_ollama_cloud_api_key_here
LLM_MODEL=gpt-oss:120b
LLM_REASONING=low

VECTOR_INDEX_NAME=vector_index
RETRIEVE_K=20
FINAL_K=5
NUM_CANDIDATES=200
RRF_K=60
MASK_PII=true
```

### 3. Setup MongoDB Atlas Vector Search Index
Create the 768-d cosine vector index and B-tree search indexes:
```bash
python setup_mongodb.py
```

### 4. Re-embed All Records (Resumable)
Embed all ~12,199 records with 768-d local vectors:
```bash
python scripts/reembed_all.py
```

### 5. Check RAG Health Status
Verify the system status via the diagnostics endpoint:
```bash
# In your browser or terminal:
curl http://127.0.0.1:8000/api/health/rag
```
Expect `"status": "green"`, `"index_status": "READY"`, `"embedded_count": 12199`, and `"fallback_used_recently": "no"`.

---

## 📋 Full Installation Instructions

# Privacy Mode (Set to true to disable all external LLM / API calls)
PRIVACY_MODE=true

# JWT Authentication
JWT_SECRET=your-secure-jwt-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# CORS & Server
FRONTEND_URL=http://localhost:5173
PORT=8000
```

### 4. Start the FastAPI Server

```powershell
uvicorn app.main:app --reload --port 8000
```

- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Endpoints Overview

### 🔐 Authentication (`/api/auth`)
- `POST /api/auth/login` — Sign in and receive signed JWT access token.
- `GET /api/auth/me` — Retrieve current authenticated user profile & role.
- `POST /api/auth/logout` — Invalidate client-side authentication session.

### 💬 Chat & Search (`/api/chat`, `/api/search`)
- `POST /api/chat` — Main natural language hybrid search and response synthesis.
- `GET /api/search` — Direct scoped query endpoint for specific fields (`company_name`, `person`, `email`, `phone`, `city`, `designation`).

### 📁 Dataset Management (`/api/datasets`)
- `GET /api/datasets` — List all uploaded datasets and schema metadata.
- `POST /api/datasets/upload` — Upload and index `.csv` or `.xlsx` files into MongoDB (*requires `DATA_UPLOADER` role*).
- `DELETE /api/datasets/{dataset_id}` — Remove uploaded dataset and delete associated records (*requires `DATA_UPLOADER` role*).
- `GET /api/collections` — List active MongoDB collections and document counts.

### 🧹 Admin Data Cleaning (`/api/admin/clean`)
- `GET /api/admin/clean/collections` — Inspect configured collections, uncleaned flags, and backup status.
- `POST /api/admin/clean/preview` — Read-only dry-run cleaning report generator with memory cache.
- `GET /api/admin/clean/preview/{id}/changes` — Paginated list of detected anomalies and proposed changes.
- `GET /api/admin/clean/preview/{id}/report.xlsx` — Download multi-sheet Excel audit report.
- `POST /api/admin/clean/apply` — Apply clean in `new_collection` or confirmed `replace` mode with auto-backup & rollback.
- `GET /api/admin/clean/status` — Real-time dataset cleanliness check.

---

## 🧪 Testing

Run backend test suite:

```powershell
cd backend
python -m unittest discover tests
```
