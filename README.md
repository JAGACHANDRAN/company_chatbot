# Calispec AI — Company & Contact Search Chatbot

An enterprise-grade, full-stack AI search assistant designed for querying, retrieving, and inspecting **company and contact intelligence** across **MongoDB Atlas** collections and uploaded Excel/CSV datasets.

The system combines **Natural Language Query Understanding**, **Intelligent Search Routing**, **Structured MongoDB Queries**, and **Vector Semantic Search**, delivering accurate, hallucination-free results with **strict source schema preservation** and interactive clickable hyperlinks.

---

## 🏛️ System Architecture

```text
                                 User Query
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │    Query Understanding      │
                      │  (Entity & Intent Parser)   │
                      └──────────────┬──────────────┘
                                     │ StructuredQuery (companies, people, locations, roles)
                                     ▼
                      ┌─────────────────────────────┐
                      │        Query Router         │
                      │  (Search Plan Formulation)  │
                      └──────────────┬──────────────┘
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
┌─────────────────────────────┐               ┌─────────────────────────────┐
│   Structured Mongo Search   │               │   Vector / Semantic Search  │
│  (Exact Entity, Word-Bound, │               │   (Atlas Vector Search /    │
│   Normalized Search Match)  │               │    Ollama Embeddings)       │
└────────────┬────────────────┘               └──────────────┬──────────────┘
             │                                               │
             └───────────────────────┬───────────────────────┘
                                     │ Candidate Records
                                     ▼
                      ┌─────────────────────────────┐
                      │  Relevance & Entity Guards  │
                      │  (Strict Multi-Company &    │
                      │   Exact-Match Priority)     │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │ Deduplication & Reranking   │
                      └──────────────┬──────────────┘
                                     │ Verified Records Grouped by Source
                                     ▼
                      ┌─────────────────────────────┐
                      │ Final Response Generator    │
                      │ • Strict Source Columns     │
                      │ • Source File Attribution   │
                      │ • Clickable Hyperlinks      │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │   React + Vite Frontend     │
                      │ (Dark Glassmorphism, Links, │
                      │  Dynamic Dataset Selector)  │
                      └─────────────────────────────┘
```

---

## ✨ Key Features

- **Exact Entity Guarding**: Exact company/contact searches prioritize deterministic entity matching so exact queries are never polluted with unrelated semantic matches.
- **Strict Source Schema Preservation**: Dynamically outputs only the actual columns present in each source file/collection. Non-existent fields are never fabricated or shown as *"Not Available"*.
- **Multi-Dataset Source Attribution**: Results clearly indicate `Source File` (and `Source Sheet` / `Source Row` when available) at the top of each section. Multiple sources are cleanly separated with markdown dividers (`---`).
- **Clickable Hyperlinks**: Emails are rendered as `mailto:` links, and LinkedIn/website URLs are rendered as interactive `target="_blank"` links in both markdown narrative and UI cards.
- **Internal Field Concealment**: Search tokens (`norm_company_name`, `norm_person_name`, `search_text`, `embedding`, raw objects) are strictly internal and never exposed to the user.
- **Dynamic Dataset Uploads**: Live upload for Excel (`.xlsx`) and CSV files with automatic schema inference, indexing, and immediate integration into the search pool.
- **Deterministic Fallback Engine**: If the LLM service is offline or unavailable, an intelligent deterministic response synthesizer formats retrieved records without downtime.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.10+, FastAPI, Uvicorn, Pydantic v2, HTTPX, OpenPyXL |
| **Database** | MongoDB Atlas (PyMongo, Motor async driver, Atlas Vector Search) |
| **AI / NLP** | Ollama (Local or Cloud API) / Heuristic Query Parser Fallback |
| **Frontend** | React 18, Vite, Tailwind CSS, Google Material Symbols |

---

## 📂 Project Structure

```text
Calispec chatbot project/
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── chat.py             # /api/chat and /api/search endpoints
│   │   │   └── datasets.py         # /api/datasets upload, list & delete
│   │   ├── services/
│   │   │   ├── query_understanding.py  # Structured query & entity extraction
│   │   │   ├── query_router.py         # Search plan generator
│   │   │   ├── retrieval_service.py    # Hybrid retrieval, merge, & dedup
│   │   │   ├── mongo_search.py         # MongoDB queries & structured filters
│   │   │   ├── vector_search.py        # Vector embedding & semantic search
│   │   │   ├── response_generator.py   # Final answer synthesizer & link formatter
│   │   │   └── mongo_dataset.py        # Dataset indexing & collection management
│   │   ├── utils/
│   │   │   └── normalization.py    # String normalization & source field extraction
│   │   ├── database.py             # MongoDB connection manager
│   │   ├── main.py                 # FastAPI application & CORS setup
│   │   └── schemas.py              # Pydantic request & response models
│   ├── tests/                      # Unit and integration test suite (35+ tests)
│   ├── requirements.txt            # Python dependencies
│   └── .env.example                # Backend configuration template
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chat.jsx            # Chat message feed and orchestration
│   │   │   ├── ChatMessage.jsx     # Message bubbles, markdown link parser & telemetry
│   │   │   ├── DatasetSelector.jsx # Active dataset filtering dropdown
│   │   │   ├── DataView.jsx        # Tabular data inspection view
│   │   │   ├── InputBox.jsx        # Search bar & voice input
│   │   │   ├── ResultCard.jsx      # Formatted record display card
│   │   │   └── UploadModal.jsx     # Dataset upload dialog (CSV/XLSX)
│   │   ├── api.js                  # Frontend API client
│   │   ├── App.jsx                 # Root layout & state
│   │   ├── main.jsx                # Entry point
│   │   └── index.css               # Design system & dark glassmorphic styles
│   ├── package.json
│   └── vite.config.js
│
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- **Python**: Version 3.10 or higher
- **Node.js**: Version 18 or higher (with `npm`)
- **MongoDB Atlas**: An active cluster URI with read/write permissions
- *(Optional)* **Ollama**: For local LLM parsing, or an Ollama Cloud API key

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
     MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority
     MONGODB_DB_NAME=calispec

     # Pre-configured collections
     MONGODB_COLLECTIONS=metrology, Expo_Acme, ECG_Contact, ECG_Marposs, Cleaned_Met_Sales

     # LLM Settings (Ollama Cloud or Local)
     OLLAMA_BASE_URL=https://api.ollama.com
     OLLAMA_API_KEY=your_api_key_here
     LLM_MODEL=gpt-oss:120b

     # Embedding Settings
     EMBEDDING_PROVIDER=ollama
     EMBEDDING_MODEL=nomic-embed-text
     VECTOR_INDEX_NAME=vector_index

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

### Chat & Search

- `POST /api/chat`
  Main hybrid search endpoint used by the chatbot.
  - **Body**:
    ```json
    {
      "message": "TVS Motor Company",
      "dataset_id": "all",
      "conversation_history": []
    }
    ```
  - **Response**: Returns synthesized answer with source attribution, clean records, and clickable hyperlinks.

- `GET /api/search?q={query}&field={field}&dataset_id={id}`
  Direct search endpoint supporting target field scoping (`company_name`, `person`, `email`, `phone`, `city`, `designation`).

### Datasets Management

- `GET /api/datasets`
  Returns all indexed datasets and their metadata (record count, columns, filename).

- `POST /api/datasets/upload`
  Upload an Excel (`.xlsx`) or CSV (`.csv`) file for automated indexing into MongoDB.

- `DELETE /api/datasets/{dataset_id}`
  Removes an uploaded dataset and deletes its indexed records from MongoDB.

- `GET /api/collections`
  Returns active MongoDB collections and document counts.

---

## 🧪 Testing

The backend includes a comprehensive test suite covering query understanding, exact matching, vector guards, source schema preservation, and link formatting:

Run all tests:
```powershell
cd backend
python -m unittest discover tests
```

Run schema preservation tests specifically:
```powershell
python -m unittest tests/test_source_schema_preservation.py
```

---

## 🛡️ License

Private enterprise repository — all rights reserved.
