# Company Search Chatbot — Backend (FastAPI + PostgreSQL + Ollama)

FastAPI-powered backend serving structured search queries across ~5,000 PostgreSQL company records.

## Architecture
- **FastAPI**: High performance REST API endpoints (`/api/chat`, `/api/search`, `/health`).
- **SQLAlchemy + psycopg**: Parameterized, SQL-injection safe queries to PostgreSQL.
- **Ollama**: Local LLM query parser that converts natural language requests into structured `{ field, value }` JSON without touching database or generating SQL.
- **PostgreSQL**: Absolute source of truth for all 5,000+ records.

---

## Prerequisites
1. **Python 3.10+ / 3.11+**
2. **PostgreSQL** running locally or via Docker
3. **Ollama** installed with your chosen model (e.g., `llama3.2` or `llama3`)

---

## Setup Instructions

### 1. Create Virtual Environment
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
python -m pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env` and adjust your credentials:
```env
DATABASE_URL=postgresql+psycopg://postgres:yourpassword@localhost:5432/company_chatbot
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.2
FRONTEND_URL=http://localhost:5173
```

### 4. Setup PostgreSQL Database & Table
Run the provided SQL script `backend/schema.sql` inside **pgAdmin** or via psql:
```sql
CREATE DATABASE company_chatbot;
-- Run schema.sql inside company_chatbot database
```

### 5. Start Ollama
Make sure Ollama is running and pull the model:
```powershell
ollama run llama3.2
```

### 6. Run FastAPI Server
```powershell
uvicorn app.main:app --reload --port 8000
```
- API Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

## API Endpoints

### `GET /health`
Returns system status and PostgreSQL connectivity:
```json
{
  "status": "ok",
  "database_connected": true,
  "details": "PostgreSQL operational"
}
```

### `POST /api/chat`
Searches using natural language or direct term:
```json
// Request
{
  "message": "Find the company with abc@gmail.com"
}

// Response
{
  "success": true,
  "found": true,
  "count": 1,
  "data": [
    {
      "id": 104,
      "company_name": "ABC Industries",
      "phone": "9876543210",
      "email": "abc@gmail.com",
      "address": "Chennai, Tamil Nadu",
      "website": "https://abcindustries.example.com"
    }
  ],
  "query_intent": {
    "field": "email",
    "value": "abc@gmail.com"
  }
}
```

### `GET /api/search?q=abc@gmail.com`
Direct parameter search for testing without LLM.
