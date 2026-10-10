import os
import sys
import time
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Initialize unified logging for Calispec backend
def _init_logging():
    formatter = logging.Formatter("INFO:     [%(name)s] %(message)s")
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    for log_name in ["calispec", "uvicorn", "uvicorn.access"]:
        l = logging.getLogger(log_name)
        l.setLevel(logging.INFO)
        if not any(isinstance(h, logging.StreamHandler) for h in l.handlers):
            l.addHandler(stream_handler)

    # Ensure root logger passes INFO
    root_l = logging.getLogger()
    root_l.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in root_l.handlers):
        root_l.addHandler(stream_handler)

_init_logging()
logger = logging.getLogger("calispec.main")

from .config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    OLLAMA_LOCAL_URL,
    LLM_MODE,
    LLM_MODEL,
    OLLAMA_API_KEY,
    VECTOR_INDEX_NAME,
    COLLECTION_NAME,
    validate_privacy_and_llm_config,
)
from .database import check_db_connection, get_database, get_configured_collection_names
from .services.contact_search import ensure_contact_indexes, get_or_build_vocab, check_uncleaned_collections
from .services.mongo_dataset import ensure_dataset_indexes, list_datasets
from .services.auth import ensure_user_indexes
from .services.embeddings import is_ollama_available, backfill_missing_embeddings_job
from .services.vector_search import execute_vector_search, get_fallback_used_recently
from .routes.chat import router as chat_router
from .routes.datasets import router as datasets_router, alias_router
from .routes.auth import router as auth_router, google_router
from .routes.admin_clean import router as admin_clean_router
from .services.observability import (
    init_langfuse,
    flush_langfuse,
    shutdown_langfuse,
    is_langfuse_enabled,
    is_langfuse_reachable,
)
from .schemas import HealthResponse

app = FastAPI(
    title="Calispec AI Search Chatbot API",
    description="FastAPI Backend for dynamic dataset uploads and secure hybrid RAG search with Ollama nomic-embed-text & gpt-oss:120b",
    version="2.2.0"
)

# HTTP Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start_time) * 1000)
    path = request.url.path
    if path.startswith("/api") or path in ("/health", "/chat"):
        logger.info(f"{request.method} {path} -> Status {response.status_code} ({duration_ms}ms)")
    return response

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
app.include_router(google_router)
app.include_router(chat_router)
app.include_router(datasets_router)
app.include_router(alias_router)
app.include_router(admin_clean_router)


async def periodic_backfill_loop():
    """Runs on startup and every 10 minutes to backfill missing/pending embeddings."""
    await asyncio.sleep(2)  # Initial slight delay on startup
    while True:
        try:
            await backfill_missing_embeddings_job(32)
        except Exception as e:
            print(f"[Embedding Backfill Background Task Error] {e}")
        await asyncio.sleep(600)  # 10 minutes


@app.on_event("startup")
async def on_startup():
    """Verify MongoDB Cloud connection, ensure indexes, validate privacy config, and initialize Langfuse."""
    print("=" * 60)
    print("Initializing Calispec AI Search Backend (Hybrid RAG + RBAC + Observability)")
    validate_privacy_and_llm_config()
    init_langfuse()
    db_connected, msg = check_db_connection()
    if db_connected:
        print(f"[OK] {msg}")
        ensure_dataset_indexes()
        ensure_user_indexes()
        try:
            db = get_database()
            configured = get_configured_collection_names()
            all_cols = list(dict.fromkeys(configured + ["dataset_records"]))
            ensure_contact_indexes(db, all_cols)
            get_or_build_vocab(db, all_cols)
            uncleaned = check_uncleaned_collections(db, configured)
            if uncleaned:
                print(f"[WARNING] {len(uncleaned)} dataset(s) need cleaning: {', '.join(uncleaned)}")
        except Exception as startup_err:
            print(f"[WARNING] Contact search initialization notice: {startup_err}")
        datasets = list_datasets()
        print(f"[INFO] Active Uploaded Datasets: {len(datasets)}")
    else:
        print(f"[WARNING] MongoDB Status: {msg}")
        print("Hint: Paste your MongoDB Atlas URI into backend/.env under MONGODB_URI")
    print("=" * 60)
    # Launch background backfill worker
    asyncio.create_task(periodic_backfill_loop())


@app.on_event("shutdown")
def on_shutdown():
    """Flush and shut down Langfuse background threads gracefully."""
    flush_langfuse()
    shutdown_langfuse()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint returning system status, MongoDB connectivity, and dataset counts."""
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


@app.get("/api/health/rag")
async def rag_health_check():
    """
    RAG diagnostics endpoint for monitoring Hybrid RAG readiness.
    """
    is_db_ok, db_msg = check_db_connection()
    if not is_db_ok:
        return {
            "status": "red",
            "mongo_connected": False,
            "langfuse_enabled": is_langfuse_enabled(),
            "langfuse_reachable": False,
            "details": db_msg,
            "total_docs": 0,
            "embedded_valid": 0,
            "pending": 0,
            "failed": 0
        }

    db = get_database()
    col = db[COLLECTION_NAME]
    doc_count = col.estimated_document_count()

    # Query embedded docs count
    try:
        embedded_valid = col.count_documents({
            "embedding": {"$exists": True, "$ne": None},
            "$expr": {"$eq": [{"$size": {"$ifNull": ["$embedding", []]}}, 768]}
        })
    except Exception:
        embedded_valid = col.count_documents({"embedding": {"$exists": True, "$ne": None}})

    pending_count = col.count_documents({
        "$or": [
            {"embedding_status": "pending"},
            {"embedding": None},
            {"embedding": {"$exists": False}}
        ]
    })
    failed_count = col.count_documents({"embedding_status": "failed"})
    missing_count = max(0, doc_count - embedded_valid)

    # Search index status from MongoDB Atlas driver
    index_status = "UNKNOWN"
    index_queryable = False
    try:
        indexes = list(col.list_search_indexes())
        target_idx = next((i for i in indexes if i.get("name") == VECTOR_INDEX_NAME), None)
        if target_idx:
            index_status = target_idx.get("status", "UNKNOWN").upper()
            index_queryable = target_idx.get("queryable", False)
    except Exception as idx_err:
        index_status = f"ERROR: {idx_err}"

    # Ollama availability
    local_ollama_ok = is_ollama_available()

    # LLM configuration
    llm_configured = bool(OLLAMA_API_KEY) or LLM_MODE == "local_signed_in"

    # Fallback tracking
    fallback_used = get_fallback_used_recently()

    # Test Query Execution
    t0 = time.time()
    test_query_str = "calibration labs"
    test_results, test_fallback = await execute_vector_search(test_query_str, limit=3)
    test_latency_ms = round((time.time() - t0) * 1000, 2)

    # Calculate overall health status: "green", "yellow", or "red"
    if index_queryable and embedded_valid >= doc_count and len(test_results) > 0 and not test_fallback:
        overall_status = "green"
    elif local_ollama_ok and is_db_ok and len(test_results) > 0:
        overall_status = "yellow"
    else:
        overall_status = "red"

    return {
        "status": overall_status,
        "mongo_connected": is_db_ok,
        "langfuse_enabled": is_langfuse_enabled(),
        "langfuse_reachable": is_langfuse_reachable(timeout_seconds=3.0),
        "total_docs": doc_count,
        "embedded_valid": embedded_valid,
        "pending": pending_count,
        "failed": failed_count,
        "doc_count": doc_count,
        "embedded_count": embedded_valid,
        "missing_embedding_count": missing_count,
        "index_name": VECTOR_INDEX_NAME,
        "index_status": index_status,
        "index_queryable": index_queryable,
        "ollama_local_available": local_ollama_ok,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "llm_configured": llm_configured,
        "llm_model": LLM_MODEL,
        "llm_mode": LLM_MODE,
        "fallback_used_recently": "yes" if fallback_used else "no",
        "test_query": {
            "query": test_query_str,
            "results_count": len(test_results),
            "latency_ms": test_latency_ms,
            "fallback_used": test_fallback
        }
    }


@app.get("/")
def root():
    return {
        "name": "Calispec AI Search Chatbot API",
        "version": "2.2.0",
        "database": "MongoDB Cloud (Atlas)",
        "rag_mode": "Secure Hybrid RAG",
        "embedding_model": f"{EMBEDDING_MODEL} (Local {EMBEDDING_DIM}-d)",
        "llm_model": f"{LLM_MODEL} ({LLM_MODE})",
        "docs_url": "/docs",
        "health_url": "/health",
        "rag_health_url": "/api/health/rag"
    }
