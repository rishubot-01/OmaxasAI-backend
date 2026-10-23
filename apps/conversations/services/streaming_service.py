"""Server-Sent Events (SSE) utilities for streaming chat responses."""

import json
import logging
from collections.abc import Iterable, Iterator
from typing import Any

from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)


def encode_sse_event(
    event: str,
    data: dict[str, Any],
) -> str:
    """Encode data as a Server-Sent Events message."""

    if not event or "\n" in event or "\r" in event:
        raise ValueError("Invalid SSE event name.")

    payload = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return f"event: {event}\ndata: {payload}\n\n"


def stream_sse_events(
    chunks: Iterable[str],
    *,
    request_id: str | None = None,
) -> Iterator[str]:
    """
    Convert text chunks into SSE events.

    Expected events:
        start  - the response stream has started
        delta  - a text fragment is available
        done   - the stream has completed
        error  - the stream failed
    """

    yield encode_sse_event(
        "start",
        {"request_id": request_id},
    )

    try:
        for chunk in chunks:
            if not isinstance(chunk, str):
                raise TypeError("Stream chunks must be strings.")

            if not chunk:
                continue

            yield encode_sse_event(
                "delta",
                {"text": chunk},
            )

        yield encode_sse_event(
            "done",
            {"request_id": request_id},
        )

    except Exception:
        logger.exception(
            "An error occurred while streaming an AI response. "
            "Request ID: %s",
            request_id,
        )

        yield encode_sse_event(
            "error",
            {
                "request_id": request_id,
                "message": "The response stream failed.",
            },
        )


def create_sse_response(
    chunks: Iterable[str],
    *,
    request_id: str | None = None,
) -> StreamingHttpResponse:
    """Create an HTTP response that streams text as SSE events."""

    response = StreamingHttpResponse(
        streaming_content=stream_sse_events(
            chunks,
            request_id=request_id,
        ),
        content_type="text/event-stream; charset=utf-8",
        status=200,
    )

    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"

    return response
