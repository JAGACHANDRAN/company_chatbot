import hashlib
import re
import time
import logging
import urllib.request
import threading
from typing import Optional, Dict, Any, List, Union
from contextlib import contextmanager

from ..config import (
    LANGFUSE_ENABLED,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LANGFUSE_HOST,
    APP_ENV,
    APP_VERSION
)

logger = logging.getLogger("calispec.observability")

# Singleton client instance
_langfuse_client = None
_langfuse_initialized = False

# Strict Deny-list and Allow-list for Langfuse payloads
FORBIDDEN_KEYS = {
    "company",
    "person",
    "contact",
    "designation",
    "email",
    "phone",
    "linkedin",
    "address",
    "city",
    "state",
    "dataset_name",
    "dataset_id",
    "search_text",
    "embedding",
    "embeddings",
    "company_name",
    "person_name",
    "contact_person",
    "phone_number",
    "email_address",
    "dataset",
}

ALLOWED_KEYS = {
    # Trace root & metadata
    "env",
    "app_version",
    "explain",
    "tags",
    "name",
    "value",
    "comment",
    "status",
    "metadata",
    "input",
    "output",
    # Chat trace output (Requirement 3)
    "total_results",
    "with_email_count",
    # Query Planner
    "tasks",
    "intent",
    "companies",
    "must_have",
    "must_not_have",
    "fields",
    "used_fallback",
    "filters_removed_by_guard",
    "planner_fallback",
    # Keyword Search (Requirement 2)
    "companies_count",
    "company_count",
    "keyword_hits",
    "hits_per_name",
    "duplicates_removed",
    # Vector Search (Requirement 2)
    "query",
    "hit_count",
    "hits_after_threshold",
    "top_10",
    "_id",
    "score",
    "filter_retried_without_filter",
    "fallback_used",
    # Merge & Filter
    "records_before_filter",
    "records_after_filter",
    "filters",
    "filter",
    "count_before",
    "count_after",
    "matched_phrase",
    # Response Build
    "records_shown",
    "has_email_count",
    "has_phone_count",
    "has_linkedin_count",
    # LLM Generation
    "model",
    "records_sent_count",
    "latency_ms",
}

CONTAINS_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_DIGITS_REGEX = re.compile(r"^(\+?\d{1,4}[-.\s]?)?(\(?\d{2,5}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}$")


def looks_like_email_or_phone(val: Any) -> bool:
    """Checks whether a string value looks like an email or phone number."""
    if not isinstance(val, str):
        return False
    clean = val.strip()
    if not clean:
        return False
    # Check email
    if "@" in clean and CONTAINS_EMAIL_REGEX.search(clean):
        return True
    # Check phone (7+ digits formatted as phone)
    digits = re.sub(r"\D", "", clean)
    if len(digits) >= 7:
        non_phone_chars = re.sub(r"[\d\s\-().+]", "", clean)
        if len(non_phone_chars) == 0:
            return True
        if PHONE_DIGITS_REGEX.match(clean):
            return True
    return False


def sanitize(payload: Any, parent_key: Optional[str] = None) -> Any:
    """
    Central Sanitizer: Walks any dict/list, drops forbidden keys, drops unknown keys
    unless they are on an explicit allow-list, and drops any string value that looks
    like an email or phone number.
    """
    if payload is None:
        return None
    if isinstance(payload, bool) or isinstance(payload, (int, float)):
        return payload
    if isinstance(payload, dict):
        sanitized_dict = {}
        for k, v in payload.items():
            k_str = str(k).strip()
            k_lower = k_str.lower()
            if k_lower in FORBIDDEN_KEYS:
                continue
            # Handle hits_per_name: {typed_name: count}
            if parent_key == "hits_per_name":
                if isinstance(v, (int, float)) and not looks_like_email_or_phone(k_str):
                    sanitized_dict[k_str] = int(v)
                continue
            # Unknown keys are dropped unless on explicit allow-list
            if k_lower not in ALLOWED_KEYS:
                continue
            if isinstance(v, str) and looks_like_email_or_phone(v):
                continue
            cleaned_v = sanitize(v, parent_key=k_lower)
            if cleaned_v is not None:
                sanitized_dict[k_str] = cleaned_v
        return sanitized_dict
    elif isinstance(payload, list):
        sanitized_list = []
        for item in payload:
            if isinstance(item, str) and looks_like_email_or_phone(item):
                continue
            cleaned_item = sanitize(item, parent_key=parent_key)
            if cleaned_item is not None:
                sanitized_list.append(cleaned_item)
        return sanitized_list
    elif isinstance(payload, str):
        if looks_like_email_or_phone(payload):
            return None
        return mask_text(payload)
    return None


def mask_text(text: Optional[str]) -> str:
    """
    Masks PII (Emails and 7+ digit phone numbers) from user input and comments.
    """
    if not text or not isinstance(text, str):
        return ""
    # Mask emails
    masked = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL]", text)
    # Mask phone numbers with 7+ digits (supporting international +, dashes, parentheses, spaces)
    masked = re.sub(r"(\+?\d{1,4}[-.\s]?)?(\(?\d{2,5}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}", "[PHONE]", masked)
    return masked


def init_langfuse() -> bool:
    """
    Initializes the Langfuse client singleton at application startup.
    Returns True if initialized successfully, False otherwise.
    """
    global _langfuse_client, _langfuse_initialized
    if _langfuse_initialized and _langfuse_client is not None:
        return True

    if not LANGFUSE_ENABLED:
        logger.info("[Langfuse] disabled via LANGFUSE_ENABLED=false")
        _langfuse_initialized = True
        return False

    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        logger.warning("[Langfuse] keys missing; tracing disabled")
        _langfuse_initialized = True
        return False

    try:
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
        _langfuse_initialized = True
        logger.info(f"[Langfuse] enabled host={LANGFUSE_HOST}")
        return True
    except Exception as e:
        logger.warning(f"[Langfuse] failed to initialize client: {e}")
        _langfuse_client = None
        _langfuse_initialized = True
        return False


def get_langfuse_client():
    """Returns the singleton Langfuse client if initialized, else None."""
    global _langfuse_client, _langfuse_initialized
    if not _langfuse_initialized:
        init_langfuse()
    return _langfuse_client


def is_langfuse_enabled() -> bool:
    """Checks if Langfuse is configured and enabled."""
    return bool(LANGFUSE_ENABLED and LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)


def is_langfuse_reachable(timeout_seconds: float = 3.0) -> bool:
    """
    Checks if Langfuse server is reachable.
    """
    if not is_langfuse_enabled():
        return False
    try:
        host = LANGFUSE_HOST.rstrip("/")
        # Ping health or public endpoint with short timeout
        health_url = f"{host}/api/public/health"
        req = urllib.request.Request(
            health_url,
            headers={"User-Agent": "Calispec-Health-Check/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            return response.status in (200, 204, 301, 302)
    except Exception:
        try:
            req = urllib.request.Request(
                LANGFUSE_HOST,
                headers={"User-Agent": "Calispec-Health-Check/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                return response.status < 500
        except Exception:
            return False


def flush_langfuse(async_bg: bool = False) -> None:
    """Flushes queued Langfuse events."""
    client = get_langfuse_client()
    if client:
        def _do_flush():
            try:
                client.flush()
            except Exception as e:
                logger.debug(f"[Langfuse] flush error: {e}")

        if async_bg:
            threading.Thread(target=_do_flush, daemon=True).start()
        else:
            _do_flush()


def shutdown_langfuse() -> None:
    """Shuts down Langfuse client background workers."""
    global _langfuse_client
    client = _langfuse_client
    if client:
        try:
            client.shutdown()
        except Exception as e:
            logger.debug(f"[Langfuse] shutdown error: {e}")
        _langfuse_client = None


class SafeSpanWrapper:
    """Wrapper around Langfuse span/generation to guarantee no exceptions bubble up."""

    def __init__(self, raw_span=None, ctx_mgr=None):
        self._span = raw_span
        self._ctx_mgr = ctx_mgr

    def update(self, output: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> "SafeSpanWrapper":
        if self._span is not None:
            try:
                update_kwargs = {}
                if output is not None:
                    update_kwargs["output"] = sanitize(output)
                if metadata is not None:
                    update_kwargs["metadata"] = sanitize(metadata)
                if kwargs:
                    sanitized_kwargs = sanitize(kwargs)
                    if isinstance(sanitized_kwargs, dict):
                        update_kwargs.update(sanitized_kwargs)
                if hasattr(self._span, "update"):
                    self._span.update(**update_kwargs)
            except Exception as e:
                logger.debug(f"[Langfuse] span update error: {e}")
        return self

    def end(self, output: Optional[Any] = None, **kwargs) -> "SafeSpanWrapper":
        if self._span is not None:
            try:
                end_kwargs = {}
                if output is not None:
                    end_kwargs["output"] = sanitize(output)
                if kwargs:
                    sanitized_kwargs = sanitize(kwargs)
                    if isinstance(sanitized_kwargs, dict):
                        end_kwargs.update(sanitized_kwargs)
                if hasattr(self._span, "end"):
                    self._span.end(**end_kwargs)
            except Exception as e:
                logger.debug(f"[Langfuse] span end error: {e}")
        return self


class SafeTraceWrapper:
    """Wrapper around Langfuse root trace / observation to guarantee no exceptions bubble up."""

    def __init__(self, root_ctx=None, root_span=None, trace_id=None):
        self._root_ctx = root_ctx
        self._root_span = root_span
        self._trace_id = trace_id
        self._ended = False

    def score(self, name: str, value: float, comment: Optional[str] = None, **kwargs) -> "SafeTraceWrapper":
        if self._root_span is not None:
            try:
                score_kwargs = {"name": name, "value": float(value)}
                if comment is not None:
                    masked_comment = mask_text(comment)
                    if not looks_like_email_or_phone(masked_comment):
                        score_kwargs["comment"] = masked_comment
                if kwargs:
                    sanitized_kwargs = sanitize(kwargs)
                    if isinstance(sanitized_kwargs, dict):
                        score_kwargs.update(sanitized_kwargs)
                if hasattr(self._root_span, "score_trace"):
                    self._root_span.score_trace(**score_kwargs)
                elif hasattr(self._root_span, "score"):
                    self._root_span.score(**score_kwargs)
            except Exception as e:
                logger.debug(f"[Langfuse] trace score error: {e}")
        return self

    def end(self, output: Optional[Any] = None, **kwargs) -> "SafeTraceWrapper":
        if self._ended:
            return self
        self._ended = True

        if self._root_span is not None:
            try:
                update_kwargs = {}
                if output is not None:
                    update_kwargs["output"] = sanitize(output)
                if kwargs:
                    sanitized_kwargs = sanitize(kwargs)
                    if isinstance(sanitized_kwargs, dict):
                        update_kwargs.update(sanitized_kwargs)
                if hasattr(self._root_span, "update"):
                    self._root_span.update(**update_kwargs)
            except Exception as e:
                logger.debug(f"[Langfuse] trace update error: {e}")

        if self._root_ctx is not None:
            try:
                self._root_ctx.__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"[Langfuse] trace ctx exit error: {e}")

        # Flush in background thread to guarantee fast API response
        flush_langfuse(async_bg=True)
        return self

    def span(self, name: str, input_data: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> SafeSpanWrapper:
        client = get_langfuse_client()
        if client:
            try:
                ctx_mgr = client.start_as_current_observation(
                    name=name,
                    as_type="span",
                    input=sanitize(input_data),
                    metadata=sanitize(metadata)
                )
                span_obj = ctx_mgr.__enter__()
                return SafeSpanWrapper(raw_span=span_obj, ctx_mgr=ctx_mgr)
            except Exception as e:
                logger.debug(f"[Langfuse] create span error: {e}")
        return SafeSpanWrapper(None, None)

    def generation(self, name: str, input_data: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> SafeSpanWrapper:
        client = get_langfuse_client()
        if client:
            try:
                ctx_mgr = client.start_as_current_observation(
                    name=name,
                    as_type="generation",
                    input=sanitize(input_data),
                    metadata=sanitize(metadata)
                )
                span_obj = ctx_mgr.__enter__()
                return SafeSpanWrapper(raw_span=span_obj, ctx_mgr=ctx_mgr)
            except Exception as e:
                logger.debug(f"[Langfuse] create generation error: {e}")
        return SafeSpanWrapper(None, None)


def start_chat_trace(
    user_query: str,
    user_id: str = "anonymous",
    session_id: str = "default_session",
    metadata: Optional[Dict[str, Any]] = None
) -> SafeTraceWrapper:
    """
    Creates root Langfuse trace for chat request with masked input and metadata.
    Never throws an exception. Anonymizes user_id if it contains email/phone.
    """
    client = get_langfuse_client()
    if not client:
        return SafeTraceWrapper(None, None, None)

    try:
        from langfuse.types import TraceContext

        trace_id = client.create_trace_id()
        meta = {
            "env": APP_ENV,
            "app_version": APP_VERSION,
        }
        if metadata:
            meta.update(metadata)

        safe_user_id = str(user_id or "anonymous")
        if "@" in safe_user_id or looks_like_email_or_phone(safe_user_id):
            safe_user_id = hashlib.sha256(safe_user_id.encode("utf-8")).hexdigest()[:12]

        trace_ctx = TraceContext(
            trace_id=trace_id,
            user_id=safe_user_id,
            session_id=session_id,
            tags=["rag", APP_ENV],
            metadata=sanitize(meta)
        )

        root_ctx = client.start_as_current_observation(
            name="chat",
            trace_context=trace_ctx,
            input=mask_text(user_query)
        )
        root_span = root_ctx.__enter__()
        return SafeTraceWrapper(root_ctx=root_ctx, root_span=root_span, trace_id=trace_id)
    except Exception as e:
        logger.debug(f"[Langfuse] start_chat_trace error: {e}")
        return SafeTraceWrapper(None, None, None)


@contextmanager
def trace_step_span(trace: SafeTraceWrapper, name: str, input_data: Optional[Any] = None, as_type: str = "span"):
    """
    Context manager for creating and tracking execution spans safely.
    All inputs are strictly sanitized before passing to Langfuse.
    """
    client = get_langfuse_client()
    ctx_mgr = None
    span_obj = None

    if client:
        try:
            ctx_mgr = client.start_as_current_observation(
                name=name,
                as_type=as_type,
                input=sanitize(input_data)
            )
            span_obj = ctx_mgr.__enter__()
        except Exception as e:
            logger.debug(f"[Langfuse] trace_step_span enter error: {e}")
            ctx_mgr = None
            span_obj = None

    span_wrapper = SafeSpanWrapper(raw_span=span_obj, ctx_mgr=ctx_mgr)

    try:
        yield span_wrapper
    finally:
        if ctx_mgr is not None:
            try:
                ctx_mgr.__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"[Langfuse] trace_step_span exit error: {e}")


def record_feedback_score(
    session_id: str,
    value: float,
    comment: Optional[str] = None,
    user_id: Optional[str] = None
) -> None:
    """
    Records user feedback (thumbs up/down) score against session_id.
    """
    client = get_langfuse_client()
    if not client:
        return

    try:
        score_kwargs = {
            "name": "user_feedback",
            "value": float(value),
            "session_id": session_id,
        }
        if comment:
            masked_comment = mask_text(comment)
            if not looks_like_email_or_phone(masked_comment):
                score_kwargs["comment"] = masked_comment
        if user_id:
            safe_u = str(user_id)
            if "@" in safe_u or looks_like_email_or_phone(safe_u):
                safe_u = hashlib.sha256(safe_u.encode("utf-8")).hexdigest()[:12]
            score_kwargs["user_id"] = safe_u

        if hasattr(client, "create_score"):
            client.create_score(**score_kwargs)
        elif hasattr(client, "score"):
            client.score(**score_kwargs)
        flush_langfuse(async_bg=True)
    except Exception as e:
        logger.debug(f"[Langfuse] record_feedback_score error: {e}")
