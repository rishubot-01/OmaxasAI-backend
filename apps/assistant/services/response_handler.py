
"""
Response handler for OmaxasAI.

Normalizes AI-provider results into a consistent application
response format. Monetary cost is deliberately excluded.
"""

from typing import Any
from uuid import UUID


VALID_CATEGORIES = {
    "general",
    "coding",
    "research",
    "reasoning",
    "writing",
    "vision",
    "other",
}

VALID_MODES = {"auto", "think"}


class InvalidAIResponseError(ValueError):
    """Raised when an AI service returns an invalid response."""


def _safe_text(value: Any, *, max_length: int = 500) -> str:
    """Return a bounded string or an empty string."""

    if not isinstance(value, str):
        return ""

    return value.strip()[:max_length]


def _safe_count(value: Any) -> int | None:
    """Normalize a non-negative integer usage or timing value."""

    if value is None or isinstance(value, bool):
        return None

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if number < 0:
        return None

    return number


def normalize_ai_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a result returned by an AI provider service.

    Expected minimum field:
        {"reply": "AI-generated answer"}

    Optional fields:
        provider, model, category, web_search_used,
        fallback_used, input_tokens, output_tokens,
        response_time_ms
    """

    if not isinstance(result, dict):
        raise InvalidAIResponseError(
            "AI service must return a dictionary."
        )

    reply = result.get("reply")

    if not isinstance(reply, str) or not reply.strip():
        raise InvalidAIResponseError(
            "AI service returned an empty or invalid reply."
        )

    category = result.get("category", "general")

    if category not in VALID_CATEGORIES:
        category = "other"

    return {
        "reply": reply.strip(),
        "provider": _safe_text(
            result.get("provider"),
            max_length=50,
        ),
        "model": _safe_text(
            result.get("model"),
            max_length=255,
        ),
        "category": category,
        "web_search_used": bool(
            result.get("web_search_used", False)
        ),
        "fallback_used": bool(
            result.get("fallback_used", False)
        ),
        "input_tokens": _safe_count(
            result.get("input_tokens")
        ),
        "output_tokens": _safe_count(
            result.get("output_tokens")
        ),
        "response_time_ms": _safe_count(
            result.get("response_time_ms")
        ),
    }


def build_success_payload(
    *,
    request_id: UUID | str,
    result: dict[str, Any],
    mode: str = "auto",
) -> dict[str, Any]:
    """
    Build the consistent API response returned to a client.

    This function does not save database records; the view or
    application service remains responsible for persistence.
    """

    mode = mode.strip().lower() if isinstance(mode, str) else ""

    if mode not in VALID_MODES:
        raise ValueError("Mode must be 'auto' or 'think'.")

    normalized = normalize_ai_result(result)

    return {
        "request_id": str(request_id),
        "reply": normalized["reply"],
        "mode": mode,
        "task_category": normalized["category"],
        "provider": normalized["provider"],
        "model": normalized["model"],
        "web_search_used": normalized["web_search_used"],
        "fallback_used": normalized["fallback_used"],
        "usage": {
            "input_tokens": normalized["input_tokens"],
            "output_tokens": normalized["output_tokens"],
        },
        "response_time_ms": normalized["response_time_ms"],
    }


def build_error_payload(
    *,
    request_id: UUID | str,
    message: str,
    error_code: str,
) -> dict[str, Any]:
    """
    Build a safe public error response.

    Do not pass provider exception text, API keys, prompts,
    or other confidential diagnostic details in these fields.
    """

    safe_message = _safe_text(message, max_length=300)
    safe_code = _safe_text(
        error_code,
        max_length=100,
    )

    return {
        "request_id": str(request_id),
        "detail": safe_message or "OmaxasAI could not complete the request.",
        "error_code": safe_code or "AI_REQUEST_FAILED",
    }

