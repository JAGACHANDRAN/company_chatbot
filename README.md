# Company Search AI Chatbot (PostgreSQL + Ollama + FastAPI + React)

A full-stack, enterprise-grade AI Search Assistant designed to query **~5,000 clean company records stored in PostgreSQL**.

The application uses **Ollama** strictly for natural language query understanding (extracting search field and search value into structured JSON) and executes fast, parameterized, SQL-injection safe queries directly on **PostgreSQL**.

---

## 🏛️ Architecture Overview

```text
                    Excel (.xlsx)
                         ↓
                    Save As CSV (UTF-8)
                         ↓
               PostgreSQL (5,000+ records)
                         ↓
                   FastAPI Backend
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
        Ollama LLM            PostgreSQL
    Query Understanding      Search Query
              └──────────┬──────────┘
                         ↓
                    JSON Result
                         ↓
                   React Chatbot
```

### Core Design Rules
1. **PostgreSQL is the Source of Truth**: All company records reside exclusively in PostgreSQL.
2. **Ollama LLM Responsibility**: Parses natural language requests (e.g., *"Find the company with abc@gmail.com"*) into structured JSON `{"field": "email", "value": "abc@gmail.com"}`. The LLM **never** generates SQL and **never** invents missing data.
3. **No RAG / No Vectors**: The data is relational; standard B-Tree indexing and parameterized queries provide instant, exact results.
4. **No Pandas/Numpy**: Database import is executed via native PostgreSQL tools (pgAdmin / `\copy`).
5. **Preserves Missing Data (NULL)**: Database `NULL` values are preserved in the JSON API and cleanly presented as *"Not available"* in the UI.
6. **Dynamic Columns**: Displays any additional columns present in the dataset automatically.

---

## 📂 Project Structure

```text
company-search-chatbot/
│
├── frontend/                     # React + Vite Application
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chat.jsx          # Message stream and coordinator
│   │   │   ├── ChatMessage.jsx   # Message bubbles & search intent tags
│   │   │   ├── InputBox.jsx      # Floating search dock
│   │   │   ├── ResultCard.jsx    # Dynamic company details card
│   │   │   └── EmptyState.jsx    # Hero welcome and prompt chips
│   │   │
│   │   ├── api.js                # Backend API connector
│   │   ├── App.jsx               # Root state and header
│   │   ├── main.jsx              # Entry point
│   │   └── index.css             # Enterprise styling system
│   │
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── .env.example
│   └── README.md
│
├── backend/                      # Python + FastAPI Application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI entry, CORS & health checks
│   │   ├── database.py           # SQLAlchemy engine & session pool
│   │   ├── models.py             # Company SQLAlchemy model
│   │   ├── schemas.py            # Pydantic schemas
│   │   ├── search.py             # Parameterized search engine
│   │   ├── llm.py                # Ollama query parser
│   │   │
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── chat.py           # /api/chat, /api/search, /api/fields
│   │
│   ├── schema.sql                # PostgreSQL table & index creation script
│   ├── requirements.txt          # Python dependencies (no pandas)
│   ├── .env.example              # Backend environment template
│   └── README.md
│
├── .gitignore
└── README.md
```

---

## 🗄️ PostgreSQL Setup & CSV Import Guide

### 1. Manual Excel to CSV Conversion
1. Open your Excel workbook (`.xlsx`) containing the ~5,000 company records.
2. Click **File** > **Save As**.
3. Select file format: **CSV UTF-8 (Comma delimited) (*.csv)**.
4. Save the file as `companies.csv`.

### 2. Create Database & Table in pgAdmin
1. Open **pgAdmin** and connect to your local PostgreSQL server.
2. Right-click **Databases** > **Create** > **Database...**, name it `company_chatbot`.
3. Right-click `company_chatbot` > **Query Tool**.
4. Open and execute [`backend/schema.sql`](file:///c:/Users/Jagathchandran/OneDrive/Pictures/Documents/Desktop/Calispec%20chatbot%20project/backend/schema.sql):

```sql
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    company_name TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    website TEXT,
    contact_person TEXT,
    designation TEXT,
    category TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    pincode TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Search Indexes
CREATE INDEX IF NOT EXISTS idx_companies_name_lower ON companies (LOWER(company_name));
CREATE INDEX IF NOT EXISTS idx_companies_email_lower ON companies (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_companies_phone ON companies (phone);
CREATE INDEX IF NOT EXISTS idx_companies_address_lower ON companies (LOWER(address));
```

### 3. Import CSV Data into pgAdmin
1. In pgAdmin, navigate to **Schemas** > **public** > **Tables** > right-click **companies** > **Import/Export Data...**
2. Toggle slider to **Import**.
3. Select your `companies.csv` file.
4. Under **Options**:
   - Format: `csv`
   - Encoding: `UTF8`
   - Header: `Yes`
   - Delimiter: `,`
   - Quote: `"`
5. Under **Columns**, map CSV columns to the table columns.
6. Click **OK** to run the import.

### 4. Verify Row Count
Run in pgAdmin Query Tool:
```sql
SELECT COUNT(*) FROM companies;
-- Should return ~5,000 rows

SELECT * FROM companies LIMIT 10;
```

---

## 🤖 Ollama LLM Setup

1. Install [Ollama](https://ollama.com) on your system.
2. Pull your preferred model (e.g. `llama3.2` or `llama3`):
   ```powershell
   ollama pull llama3.2
   ```
3. Ollama runs automatically as a background service at `http://localhost:11434`.

---

## 🚀 Running the Backend

Open a PowerShell terminal:

```powershell
cd backend

# Create & activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install requirements (FastAPI, SQLAlchemy, psycopg, httpx)
python -m pip install -r requirements.txt

# Start backend server
uvicorn app.main:app --reload --port 8000
```

- **API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 💻 Running the Frontend

Open a second PowerShell terminal:

```powershell
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```

- **Frontend Chatbot**: [http://localhost:5173](http://localhost:5173)

---

## 🔍 Example Search Queries to Test

Try entering any of the following queries in the chatbot:

1. **Company Name**:
   - `Show me ABC Industries`
   - `ABC Industries`
2. **Email Address**:
   - `Find the company with abc@gmail.com`
   - `abc@gmail.com`
3. **Phone Number**:
   - `Which company has 9876543210?`
   - `9876543210`
4. **Address / City**:
   - `Companies located in Chennai`
   - `Chennai`
5. **No Match Record**:
   - `unknown-company@example.com`
   *(Verifies that no false information is hallucinated; UI shows "No matching record was found")*

---

## 🛠️ Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **"PostgreSQL Offline" pill in UI** | Invalid database credentials or PostgreSQL service stopped | Verify credentials in `backend/.env` (`DATABASE_URL`) and check that PostgreSQL service is running in Windows Services. |
| **Ollama connection warning** | Ollama service not running | Run `ollama serve` or open the Ollama desktop application. The system will fall back to intelligent heuristic parsing automatically until Ollama connects. |
| **Phone number loses leading zero** | Column typed as INTEGER | In PostgreSQL, ensure `phone` column is `TEXT` (as provided in `backend/schema.sql`). |
| **CORS error in browser** | Port mismatch | Ensure `FRONTEND_URL=http://localhost:5173` is specified in `backend/.env`. |
