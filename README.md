# Calispec AI — Enterprise Company & Contact Search Chatbot

An enterprise-grade, full-stack AI search assistant designed for querying, retrieving, inspecting, and managing **company and contact intelligence** across **MongoDB Atlas** collections and uploaded Excel/CSV datasets.

The system combines **Natural Language Query Understanding**, **Intelligent Search Routing**, **Structured MongoDB Queries**, **Vector Semantic Search**, and **Deterministic Response Synthesis** — delivering accurate, hallucination-free results with **strict source schema preservation**, **clickable hyperlinks**, **role-based access control (RBAC)**, **admin data cleaning**, and **100% offline privacy mode**.

---

## 🏛️ System Architecture

```text
                                 User Query / Action
                                         │
                        ┌────────────────┴────────────────┐
                        │   Authentication & RBAC Guard   │
                        │    (JWT Tokens / User Roles)    │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────┐
                        │       Query Understanding       │
                        │   (Entity & Intent Extraction)  │
                        └────────────────┬────────────────┘
                                         │ StructuredQuery (company, person, location, role)
                                         ▼
                        ┌─────────────────────────────────┐
                        │          Query Router           │
                        │    (Search Plan Formulation)    │
                        └────────────────┬────────────────┘
                                         │
              ┌──────────────────────────┴──────────────────────────┐
              ▼                                                     ▼
 ┌─────────────────────────────┐                       ┌─────────────────────────────┐
 │   Structured Mongo Search   │                       │   Vector / Semantic Search  │
 │  (Exact Entity, Word-Bound, │                       │   (Atlas Vector Search /    │
 │   Normalized Regex Match)   │                       │    Ollama Embeddings)       │
 └────────────┬────────────────┘                       └──────────────┬──────────────┘
              │                                                       │
              └──────────────────────────┬────────────────────────────┘
                                         │ Candidate Records
                                         ▼
                        ┌─────────────────────────────────┐
                        │    Relevance & Entity Guards    │
                        │  (Strict Multi-Company Match &  │
                        │   Exact Entity Prioritization)  │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────┐
                        │    Deduplication & Reranking    │
                        └────────────────┬────────────────┘
                                         │ Verified Records Grouped by Source
                                         ▼
                        ┌─────────────────────────────────┐
                        │     Final Response Synthesizer  │
                        │ • Strict Source Columns         │
                        │ • Source Attribution Dividers   │
                        │ • Clickable Hyperlinks          │
                        │ • Deterministic Privacy Engine  │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────┐
                        │      React + Vite Frontend      │
                        │ • Dark Glassmorphic Design      │
                        │ • Dataset Selector & Data View  │
                        │ • PDF Export & Voice Input      │
                        │ • Admin Data Cleaning Studio    │
                        └─────────────────────────────────┘
```

---

## ✨ Key Features

- **Exact Entity Guarding**: Prioritizes deterministic entity matching so exact company or person name queries are never polluted with unrelated semantic matches.
- **Strict Source Schema Preservation**: Dynamically outputs only the actual columns present in each source file/collection. Non-existent fields are never fabricated or shown as *"Not Available"*.
- **Multi-Dataset Source Attribution**: Results clearly indicate `Source File` (and `Source Sheet` / `Source Row` when available) at the top of each section. Multiple sources are cleanly separated with visual markdown dividers (`---`).
- **Clickable Hyperlinks**: Emails are rendered as `mailto:` links, and LinkedIn/website URLs are rendered as interactive `target="_blank"` links in both markdown narrative and UI cards.
- **Strict Privacy Mode (`PRIVACY_MODE=true`)**: Zero external leakage of confidential contact data. Blocks external LLM and vector API calls, performing all searches via local regex and MongoDB text indexes with 100% deterministic synthesis.
- **Enterprise Role-Based Access Control (RBAC)**:
  - Unified MongoDB `users` collection.
  - JWT Bearer token authentication with verified role claims (`DATA_UPLOADER` vs `CHAT_USER`).
  - Strict endpoint security: Only authenticated uploaders can upload datasets, delete files, or apply data cleaning transformations.
- **In-Place Admin Data Cleaning & Normalization Studio**:
  - Interactive collection inspection with uncleaned record detection.
  - In-memory dry-run cleaning preview (15-minute TTL) with anomaly and correction breakdown.
  - Multi-sheet Excel audit report export (`.xlsx`).
  - Safe application modes: `new_collection` (side-by-side) or verified `replace` (with required typing confirmation, automatic backup collection, index copying, count verification, and instant rollback on error).
- **Dynamic Dataset Uploads**: Instant upload for Excel (`.xlsx`) and CSV files with automatic schema inference, indexing, and immediate integration into the search pool.
- **Chat History PDF Export**: One-click generation of formatted PDF conversation transcripts with timestamps, message roles, and source attributions.
- **Internal Field Concealment**: Search tokens (`norm_company_name`, `norm_person_name`, `search_text`, `embedding`, raw objects) are strictly internal and never exposed to the user.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend Framework** | Python 3.10+, FastAPI, Uvicorn, Pydantic v2, HTTPX |
| **Database & Search** | MongoDB Atlas (PyMongo, Motor async driver, Atlas Vector Search) |
| **Authentication & Security** | PyJWT (HMAC-SHA256), Bcrypt password hashing, FastAPI HTTPBearer |
| **Data Processing** | Pandas, NumPy, OpenPyXL (Excel XLSX parser & multi-sheet builder) |
| **AI / NLP** | Ollama (Local or Cloud API) / Heuristic Query Parser & Deterministic Synthesizer |
| **Frontend UI** | React 18, Vite, Tailwind CSS, Google Material Symbols, jsPDF |

---

## 📂 Project Structure

```text
Calispec chatbot project/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── auth.py             # /api/auth login, me, logout endpoints
│   │   │   ├── chat.py             # /api/chat and /api/search endpoints
│   │   │   ├── datasets.py         # /api/datasets upload, list & delete
│   │   │   └── admin_clean.py      # /api/admin/clean preview, report & apply
│   │   ├── services/
│   │   │   ├── auth.py                 # JWT minting, password hashing & RBAC
│   │   │   ├── query_understanding.py  # Structured query & entity extraction
│   │   │   ├── query_router.py         # Search plan generator
│   │   │   ├── retrieval_service.py    # Hybrid retrieval, merge, & dedup
│   │   │   ├── mongo_search.py         # MongoDB queries & structured filters
│   │   │   ├── vector_search.py        # Vector embedding & semantic search
│   │   │   ├── response_generator.py   # Final answer synthesizer & link formatter
│   │   │   ├── mongo_dataset.py        # Dataset indexing & collection management
│   │   │   ├── data_cleaner.py         # Deterministic offline cleaning engine
│   │   │   ├── existing_data_cleaner.py# MongoDB collection cleaning & backup
│   │   │   ├── preview_cache.py        # In-memory preview TTL cache
│   │   │   └── contact_search.py       # High-speed search & vocabulary index
│   │   ├── utils/
│   │   │   ├── normalization.py    # Normalization & source field extraction
│   │   │   └── deduplication.py    # Multi-source aware deduplication
│   │   ├── config.py               # Central environment & privacy configuration
│   │   ├── database.py             # MongoDB connection manager
│   │   ├── main.py                 # FastAPI application & CORS setup
│   │   └── schemas.py              # Pydantic request & response models
│   ├── scripts/                    # Maintenance & automation CLI tools
│   │   ├── manage_users.py         # User management & role provisioning
│   │   ├── clean_mongodb.py        # Offline MongoDB cleaning & replacement
│   │   ├── clean_dataset.py        # Offline spreadsheet batch cleaner
│   │   ├── generate_embeddings.py  # Vector search embedding generator
│   │   └── inspect_and_migrate_db.py# Database schema inspector & migration
│   ├── tests/                      # Unit and integration test suite (35+ tests)
│   ├── requirements.txt            # Backend Python dependencies
│   ├── README.md                   # Backend specific documentation
│   └── .env.example                # Backend configuration template
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatMessage.jsx     # Message bubbles, markdown link parser, cards & PDF export
│   │   │   ├── Sidebar.jsx         # Conversation history, search & new chat controls
│   │   │   ├── FileUploadModal.jsx # Dataset upload dialog (CSV/XLSX) with clean preview
│   │   │   ├── CleanExistingDataModal.jsx # Admin in-place MongoDB collection cleaning
│   │   │   ├── CleaningReportView.jsx # Multi-tab data clean report viewer
│   │   │   ├── DataView.jsx        # Tabular data inspection view
│   │   │   ├── ResultCard.jsx      # Formatted record display card
│   │   │   ├── DatasetSelector.jsx # Active dataset filtering dropdown
│   │   │   ├── LoginModal.jsx      # Uploader login and authentication modal
│   │   │   ├── DocumentInspectorModal.jsx # Raw document metadata inspection
│   │   │   └── CalispecLogo.jsx    # Vector brand icon & SVG typography
│   │   ├── utils/
│   │   │   └── reportPdfExporter.js# Client-side PDF audit report generator
│   │   ├── api.js                  # Frontend API client with JWT bearer handling
│   │   ├── App.jsx                 # Root layout, theme state & RBAC context
│   │   ├── main.jsx                # Entry point
│   │   └── index.css               # Design system & dark glassmorphic styles
│   ├── package.json                # Frontend dependencies (React, Vite, jsPDF)
│   └── vite.config.js
│
├── requirements.txt                # Root requirements pointer
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- **Python**: Version 3.10 or higher
- **Node.js**: Version 18 or higher (with `npm`)
- **MongoDB Atlas**: An active cluster URI with read/write permissions
- *(Optional)* **Ollama**: For optional local LLM parsing when `PRIVACY_MODE=false`

---

### 1. Backend Setup

1. Open PowerShell and navigate to the backend directory:
   ```powershell
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install required Python packages:
   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `.env.example` to `.env`:
     ```powershell
     cp .env.example .env
     ```
   - Edit `backend/.env` with your settings:
     ```env
     # MongoDB Atlas Connection
     MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-address>.mongodb.net/?retryWrites=true&w=majority
     MONGODB_DB_NAME=calispec

     # Pre-configured MongoDB collections to search
     MONGODB_COLLECTIONS=collection_1, collection_2, collection_3

     # Privacy Mode (true enforces zero external data transmission)
     PRIVACY_MODE=true

     # Authentication Settings
     JWT_SECRET=your-secure-jwt-secret-key
     JWT_ALGORITHM=HS256
     ACCESS_TOKEN_EXPIRE_MINUTES=10080

     # (Optional) Pre-configured Data Uploader Credentials
     # UPLOADER_EMAIL=admin@example.com
     # UPLOADER_PASSWORD=your_secure_password

     # Server Configuration
     FRONTEND_URL=http://localhost:5173
     PORT=8000
     ```

5. Launch the FastAPI server:
   ```powershell
   uvicorn app.main:app --reload --port 8000
   ```

   - **API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### 2. Frontend Setup

1. Open a second PowerShell terminal and navigate to the frontend directory:
   ```powershell
   cd frontend
   ```

2. Install Node dependencies:
   ```powershell
   npm install
   ```

3. Launch the Vite development server:
   ```powershell
   npm run dev
   ```

4. Open your browser and navigate to:
   **[http://localhost:5173](http://localhost:5173)**

---

## 📡 API Reference

### 🔐 Authentication & Access Control

- `POST /api/auth/login`
  Authenticates user credentials and returns a signed JWT bearer token.
  - **Body**:
    ```json
    {
      "email": "user@example.com",
      "password": "yourpassword"
    }
    ```

- `GET /api/auth/me`
  Returns authenticated user identity and verified role (`DATA_UPLOADER` or `CHAT_USER`).

- `POST /api/auth/logout`
  Clears client session token.

---

### 💬 Chat & Search

- `POST /api/chat`
  Main hybrid search endpoint used by the chatbot.
  - **Body**:
    ```json
    {
      "message": "Find contacts in Bangalore with quality manager designation",
      "dataset_id": "all",
      "conversation_history": []
    }
    ```
  - **Response**: Returns synthesized answer with source attribution, clean records, and clickable hyperlinks.

- `GET /api/search?q={query}&field={field}&dataset_id={id}`
  Direct search endpoint supporting target field scoping (`company_name`, `person`, `email`, `phone`, `city`, `designation`).

---

### 📁 Datasets Management

- `GET /api/datasets`
  Returns all indexed datasets and their metadata (record count, columns, filename).

- `POST /api/datasets/upload` *(Requires `DATA_UPLOADER` role)*
  Upload an Excel (`.xlsx`) or CSV (`.csv`) file for automated indexing into MongoDB.

- `DELETE /api/datasets/{dataset_id}` *(Requires `DATA_UPLOADER` role)*
  Removes an uploaded dataset and deletes its indexed records from MongoDB.

- `GET /api/collections`
  Returns active MongoDB collections and document counts.

---

### 🧹 Admin Data Cleaning

- `GET /api/admin/clean/collections` *(Requires `DATA_UPLOADER` role)*
  Lists configured MongoDB collections with record counts and clean status flags.

- `POST /api/admin/clean/preview` *(Requires `DATA_UPLOADER` role)*
  Generates a dry-run in-memory cleaning report without modifying MongoDB.

- `GET /api/admin/clean/preview/{id}/report.xlsx` *(Requires `DATA_UPLOADER` role)*
  Downloads the multi-sheet Excel audit report of anomalies and proposed corrections.

- `POST /api/admin/clean/apply` *(Requires `DATA_UPLOADER` role)*
  Applies changes via `new_collection` or confirmed `replace` mode (with auto-backup and atomic rollback).

- `GET /api/admin/clean/status`
  Returns quick status indicating if any collections contain uncleaned records.

---

## 🧪 Testing

The backend includes a comprehensive test suite covering query understanding, exact matching, vector guards, source schema preservation, RBAC security, and privacy mode:

Run all tests:
```powershell
cd backend
python -m unittest discover tests
```

Run specific test modules:
```powershell
# RBAC Security Tests
python -m unittest tests/test_rbac_security.py

# Source Schema Preservation Tests
python -m unittest tests/test_source_schema_preservation.py

# Query Parser Tests
python -m unittest tests/test_query_parser.py
```

---

## 🛡️ License

Private enterprise repository — all rights reserved.
