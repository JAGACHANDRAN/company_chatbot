import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import PRIVACY_MODE, validate_privacy_and_llm_config
from .database import check_db_connection
from .services.mongo_dataset import ensure_dataset_indexes, list_datasets
from .services.auth import ensure_user_indexes
from .routes.chat import router as chat_router
from .routes.datasets import router as datasets_router, alias_router
from .routes.auth import router as auth_router
from .schemas import HealthResponse

app = FastAPI(
    title="Calispec AI Search Chatbot API",
    description="FastAPI Backend for dynamic dataset uploads and private MongoDB search with structured query parser",
    version="2.1.0"
)

# CORS configuration
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins = [
    frontend_url,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(datasets_router)
app.include_router(alias_router)


@app.on_event("startup")
def on_startup():
    """Verify MongoDB Cloud connection, ensure indexes, and validate privacy config on startup."""
    print("=" * 60)
    print("Initializing Calispec AI Search Backend (MongoDB + Private Search + RBAC)")
    validate_privacy_and_llm_config()
    db_connected, msg = check_db_connection()
    if db_connected:
        print(f"[OK] {msg}")
        ensure_dataset_indexes()
        ensure_user_indexes()
        datasets = list_datasets()
        print(f"[INFO] Active Uploaded Datasets: {len(datasets)}")
    else:
        print(f"[WARNING] MongoDB Status: {msg}")
        print("Hint: Paste your MongoDB Atlas URI into backend/.env under MONGODB_URI")
    print("=" * 60)


@app.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint returning system status, MongoDB connectivity, and dataset counts.
    """
    is_db_ok, msg = check_db_connection()
    datasets_count = 0
    if is_db_ok:
        try:
            datasets_count = len(list_datasets())
        except Exception:
            datasets_count = 0

    return HealthResponse(
        status="ok",
        database_connected=is_db_ok,
        details=msg,
        total_uploaded_datasets=datasets_count
    )


@app.get("/")
def root():
    return {
        "name": "Calispec AI Search Chatbot API",
        "version": "2.1.0",
        "database": "MongoDB Cloud (Atlas)",
        "docs_url": "/docs",
        "health_url": "/health",
        "privacy_mode": PRIVACY_MODE,
        "privacy": "Strict (zero confidential contact data or database records sent to external services)"
    }
