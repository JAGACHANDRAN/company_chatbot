# Calispec AI Search Chatbot — Backend (FastAPI + MongoDB Atlas)

High-performance FastAPI backend delivering structured and semantic search across **MongoDB Atlas** collections and uploaded tabular datasets (CSV / Excel).

---

## 🏛️ Architecture & Highlights

- **FastAPI Core**: RESTful API endpoints for natural language hybrid search, real-time chat, dataset ingestion, data cleaning, and role-based authentication.
- **MongoDB Atlas Integration**: Query routing across both pre-configured static collections and dynamic uploaded datasets using indexed exact matching, word-bound regex, and vector embeddings.
- **Strict Privacy Mode (`PRIVACY_MODE=true`)**: Zero external leakage of confidential company or contact records. Operates 100% locally with deterministic response synthesis when enabled.
- **Admin Data Cleaning & In-Place Normalization**:
  - Interactive dry-run cleaning preview cached in memory with a 15-minute TTL.
  - Multi-sheet Excel audit report export.
  - Safe application via `new_collection` or confirmed `replace` with automated verified backups and instant rollback.
- **Role-Based Access Control (RBAC)**:
  - Unified MongoDB `users` collection.
  - JWT Bearer authentication issuing signed access tokens with verified role claims (`DATA_UPLOADER` vs `CHAT_USER`).
- **Dynamic Dataset Management**: Live upload of CSV / Excel files with automated schema detection, column normalization, and indexing into MongoDB.

---

## 📋 Prerequisites

1. **Python 3.10+ / 3.11+**
2. **MongoDB Atlas** or self-hosted MongoDB instance (read/write access)
3. *(Optional)* **Ollama** (Local instance or Cloud API key for non-privacy LLM parsing)

---

## 🚀 Setup Instructions

### 1. Create and Activate Virtual Environment

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your MongoDB connection details:

```powershell
cp .env.example .env
```

Key variables in `.env`:
```env
# MongoDB Atlas Connection
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-address>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=calispec
MONGODB_COLLECTIONS=collection_1, collection_2, collection_3

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
