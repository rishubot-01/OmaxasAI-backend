
"""Shared success-response utilities for the OmaxasAI REST API."""

from typing import Any

from rest_framework import status
from rest_framework.response import Response


def success_response(
    data: Any = None,
    *,
    message: str = "Request completed successfully.",
    status_code: int = status.HTTP_200_OK,
    meta: dict | None = None,
) -> Response:
    """
    Build a consistent successful API response.

    Example:
        {
            "success": true,
            "message": "User profile retrieved.",
            "data": {"id": 1},
            "meta": {}
        }
    """

    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string.")

    if (
        isinstance(status_code, bool)
        or not isinstance(status_code, int)
        or not 200 <= status_code < 300
        or status_code == status.HTTP_204_NO_CONTENT
    ):
        raise ValueError(
            "status_code must be a successful HTTP status "
            "other than 204 No Content."
        )

    if meta is not None and not isinstance(meta, dict):
        raise ValueError("meta must be a dictionary or None.")

    payload = {
        "success": True,
        "message": message.strip(),
        "data": data,
    }

    if meta is not None:
        payload["meta"] = meta

    return Response(
        payload,
        status=status_code,
    )


def created_response(
    data: Any = None,
    *,
    message: str = "Resource created successfully.",
    meta: dict | None = None,
) -> Response:
    """Build a 201 Created response."""

    return success_response(
        data,
        message=message,
        status_code=status.HTTP_201_CREATED,
        meta=meta,
    )


def accepted_response(
    data: Any = None,
    *,
    message: str = "Request accepted for processing.",
    meta: dict | None = None,
) -> Response:
    """Build a 202 Accepted response for asynchronous operations."""

    return success_response(
        data,
        message=message,
        status_code=status.HTTP_202_ACCEPTED,
        meta=meta,
    )


def no_content_response() -> Response:
    """Build a 204 No Content response without a response body."""

    return Response(status=status.HTTP_204_NO_CONTENT)

