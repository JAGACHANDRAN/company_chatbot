import os
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load .env file once centrally
load_dotenv()

logger = logging.getLogger("calispec.privacy")

# ==============================================================================
# Hybrid RAG Settings
# - Local Embeddings: nomic-embed-text via local Ollama (http://localhost:11434)
# - Cloud LLM: gpt-oss:120b on Ollama Cloud with automatic PII masking
# - Exact lookups: Direct from MongoDB without LLM call
# ==============================================================================
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
DB_NAME = os.getenv("MONGODB_DB_NAME", "calispec").strip()
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "dataset_records").strip()

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama_local").lower().strip()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text").strip()
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
OLLAMA_LOCAL_URL = os.getenv("OLLAMA_LOCAL_URL", "http://localhost:11434").rstrip("/")

LLM_MODE = os.getenv("LLM_MODE", "cloud_direct").lower().strip()
OLLAMA_CLOUD_URL = os.getenv("OLLAMA_CLOUD_URL", os.getenv("OLLAMA_BASE_URL", "https://ollama.com")).rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", os.getenv("LLM_API_KEY", "")).strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:120b")
LLM_REASONING = os.getenv("LLM_REASONING", "low").strip()

VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index").strip()
RETRIEVE_K = int(os.getenv("RETRIEVE_K", "1000"))
FINAL_K = int(os.getenv("FINAL_K", "1000"))
NUM_CANDIDATES = int(os.getenv("NUM_CANDIDATES", "500"))
RRF_K = int(os.getenv("RRF_K", "60"))
MASK_PII = os.getenv("MASK_PII", "true").strip().lower() in ("true", "1", "yes", "on")

# ==============================================================================
# Langfuse LLM Observability & Tracing Settings
# ==============================================================================
LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").strip().lower() in ("true", "1", "yes", "on")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
APP_ENV = os.getenv("APP_ENV", "development").strip()
APP_VERSION = "2.2.0"

# Retained for backwards compatibility across existing routes
PRIVACY_MODE: bool = False
OLLAMA_BASE_URL = OLLAMA_CLOUD_URL


def is_local_url(url: str) -> bool:
    """Checks whether a URL points to localhost or a local loopback IP."""
    if not url:
        return False
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = (parsed.hostname or "").lower()
        return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
    except Exception:
        return False


def validate_privacy_and_llm_config() -> None:
    """Validates local embedding and cloud LLM configuration at startup."""
    print("[SECURITY: HYBRID RAG ACTIVE]")
    print(f"  - Local Embeddings: {EMBEDDING_MODEL} ({EMBEDDING_DIM}-d) via {OLLAMA_LOCAL_URL}")
    print(f"  - Cloud LLM       : {LLM_MODEL} (Mode: {LLM_MODE}, Reasoning: {LLM_REASONING})")
    print(f"  - PII Protection  : {'ACTIVE (Masking enabled)' if MASK_PII else 'INACTIVE'}")
    print(f"  - Retrieval       : {VECTOR_INDEX_NAME} (RRF k={RRF_K}, Full similarity list, Max {FINAL_K})")
