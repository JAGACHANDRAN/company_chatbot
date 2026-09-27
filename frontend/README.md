# Company Search Chatbot — Frontend (React + Vite)

A modern, responsive React web interface for the Company Data Search Chatbot.

## Features
- **Intelligent Search Interface**: Natural language search powered by Ollama and PostgreSQL.
- **Dynamic Field Display**: Dynamically parses and displays all columns returned from the database (`company_name`, `phone`, `email`, `address`, `website`, etc.).
- **Missing Data (NULL) Handling**: Preserves `null` database values and renders clean "Not available" indicators.
- **One-Click Copy**: Copy company contact information directly to clipboard.
- **Direct Contact Links**: Instant `mailto:`, `tel:`, and website links.
- **Live Status Monitoring**: Real-time heartbeat checking FastAPI and PostgreSQL connectivity.

---

## Setup & Running

### 1. Install Dependencies
```powershell
cd frontend
npm install
```

### 2. Configure Environment (Optional)
If your backend is running on a port other than 8000, update `.env`:
```env
VITE_API_URL=http://localhost:8000
```

### 3. Start Development Server
```powershell
npm run dev
```
Open `http://localhost:5173` in your browser.

### 4. Build for Production
```powershell
npm run build
```
The compiled assets will be in `dist/`.
