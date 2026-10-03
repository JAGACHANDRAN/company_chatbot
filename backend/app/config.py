import os
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load .env file once centrally
load_dotenv()

logger = logging.getLogger("calispec.privacy")

# ==============================================================================
# Central PRIVACY_MODE Setting
# When True:
# - External LLM calls are strictly blocked (llm.py raises RuntimeError).
# - Vector/embedding search is skipped; regex and text-index search are used.
# - Response synthesizer runs in 100% deterministic mode without calling llm.py.
# - Logs never contain full user queries or raw database records.
# ==============================================================================
PRIVACY_MODE_RAW = os.getenv("PRIVACY_MODE", "true").strip().lower()
PRIVACY_MODE: bool = PRIVACY_MODE_RAW in ("true", "1", "yes", "on")

# LLM and Service URLs
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", os.getenv("LLM_API_KEY", "")).strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:120b")

# Embedding & Vector Search Settings
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower().strip()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text").strip()
VECTOR_INDEX_NAME = os.getenv("VECTOR_INDEX_NAME", "vector_index").strip()


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
    """
    Validates privacy mode and Ollama/LLM configuration at application startup:
    1. If PRIVACY_MODE is True: logs that privacy protection is active and external
       calls are disabled.
    2. If PRIVACY_MODE is False and OLLAMA_BASE_URL is local: allows local LLM.
    3. If PRIVACY_MODE is False and OLLAMA_BASE_URL is non-local: logs a prominent warning.
    """
    if PRIVACY_MODE:
        print("[PRIVACY_MODE: ACTIVE] Confidential contact data protection is ENABLED.")
        print("  - LLM and external embedding calls are strictly DISABLED.")
        print("  - Search runs via regex and MongoDB text-index matching.")
        print("  - Responses are formatted via deterministic synthesis.")
        print("  - Query and record privacy logging guards are ACTIVE.")
    else:
        if is_local_url(OLLAMA_BASE_URL):
            print(f"[LOCAL_LLM MODE: ACTIVE] LLM enabled with local endpoint: {OLLAMA_BASE_URL}")
        else:
            warning_msg = (
                f"[SECURITY WARNING] PRIVACY_MODE is false and OLLAMA_BASE_URL ({OLLAMA_BASE_URL}) "
                "points to a NON-LOCAL host! External services may receive confidential contact data. "
                "Set PRIVACY_MODE=true in backend/.env to prevent external transmission."
            )
            print("=" * 70)
            print(warning_msg)
            print("=" * 70)
            logger.warning(warning_msg)
