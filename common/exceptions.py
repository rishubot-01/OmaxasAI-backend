
"""Shared exception handling utilities for the OmaxasAI backend."""

import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class ServiceUnavailableError(APIException):
    """Raise when a required external service is temporarily unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The requested service is temporarily unavailable."
    default_code = "service_unavailable"


class ResourceNotFoundError(APIException):
    """Raise when a requested resource does not exist or is inaccessible."""

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "The requested resource was not found."
    default_code = "resource_not_found"


class ConflictError(APIException):
    """Raise when a request conflicts with the current resource state."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current resource state."
    default_code = "resource_conflict"


class ExternalServiceError(APIException):
    """Raise when a safe, user-facing external service error is required."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "An external service could not complete the request."
    default_code = "external_service_error"


def custom_exception_handler(exc, context):
    """
    Normalize Django REST Framework API errors.

    Expected response shape:
        {
            "success": false,
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": {}
            },
            "status_code": 400
        }

    Unhandled exceptions are returned to Django's normal error handling
    rather than exposing internal exception details to API clients.
    """

    response = drf_exception_handler(exc, context)

    # DRF returns None for exceptions it does not recognize.
    # Do not turn internal exceptions into success responses or expose
    # their raw messages, tracebacks, paths, or credentials.
    if response is None:
        request = context.get("request")
        view = context.get("view")

        logger.error(
            "Unhandled exception in API view.",
            extra={
                "view_name": (
                    view.__class__.__name__
                    if view is not None
                    else "unknown"
                ),
                "request_method": (
                    getattr(request, "method", "unknown")
                    if request is not None
                    else "unknown"
                ),
            },
        )

        return None

    original_data = response.data

    if isinstance(original_data, dict):
        if "detail" in original_data:
            message = str(original_data["detail"])
            details = {}
        else:
            message = "Request validation failed."
            details = original_data

    elif isinstance(original_data, list):
        message = "Request validation failed."
        details = original_data

    else:
        message = "The request could not be completed."
        details = {"detail": original_data}

    error_code = getattr(exc, "default_code", "api_error")

    if hasattr(error_code, "value"):
        error_code = error_code.value

    if not isinstance(error_code, str):
        error_code = "api_error"

    response.data = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details,
        },
        "status_code": response.status_code,
    }

    return response

