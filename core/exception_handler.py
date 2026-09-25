"""Project wide exception handling.

The DRF exception handler catches every exception raised while serving an API
request and renders it through :class:`core.responses.ResponseHandler`, so
framework errors, business errors and unexpected errors all share one envelope.
The module also provides the root ``404``/``500`` handlers wired in
``config/urls.py`` for requests that never reach DRF (unknown paths, crashes in
middleware, etc.).
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed as DRFAuthenticationFailed
from rest_framework.exceptions import NotFound as DRFNotFound
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from core.exceptions import AppException
from core.responses import ResponseHandler

logger = logging.getLogger(__name__)


def _normalise_errors(detail: Any) -> dict[str, Any] | list[Any]:
    """Convert DRF error detail into a simple JSON serialisable structure.

    Args:
        detail: The ``detail`` payload attached to a DRF ``APIException``.

    Returns:
        Either a mapping of field name to messages or a list of messages.
    """
    if isinstance(detail, dict):
        normalised: dict[str, Any] = {}
        for field, messages in detail.items():
            if isinstance(messages, (list, tuple)):
                normalised[field] = [str(message) for message in messages]
            else:
                normalised[field] = [str(messages)]
        return normalised
    if isinstance(detail, (list, tuple)):
        return [str(message) for message in detail]
    return [str(detail)]


def _first_message(errors: Any) -> str:
    """Derive a human readable message from normalised error details.

    Args:
        errors: Normalised error details.

    Returns:
        The first available message, or a generic fallback.
    """
    if isinstance(errors, dict):
        for messages in errors.values():
            if isinstance(messages, list) and messages:
                return str(messages[0])
            if messages:
                return str(messages)
    if isinstance(errors, list) and errors:
        return str(errors[0])
    return "The submitted data is invalid."


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Render any exception using the project response envelope.

    Args:
        exc: The exception raised during request handling.
        context: DRF exception context (request, view, etc.).

    Returns:
        A DRF ``Response`` for handled errors, or ``None`` to let Django's
        default handling take over (only used as a defensive fallback).
    """
    if isinstance(exc, AppException):
        return Response(
            exc.get_payload(),
            status=exc.status_code,
        )

    if isinstance(exc, DRFValidationError):
        errors = _normalise_errors(exc.detail)
        return ResponseHandler.error(
            message=_first_message(errors),
            errors=errors,
            error_code="validation_error",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, DjangoValidationError):
        errors = _normalise_errors(getattr(exc, "message_dict", None) or exc.messages)
        return ResponseHandler.error(
            message=_first_message(errors),
            errors=errors,
            error_code="validation_error",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, (DRFNotFound, Http404)):
        return ResponseHandler.error(
            message="The requested resource was not found.",
            error_code="not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, (DRFPermissionDenied, DjangoPermissionDenied)):
        return ResponseHandler.error(
            message="You do not have permission to perform this action.",
            error_code="permission_denied",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, (DRFAuthenticationFailed,)):
        return ResponseHandler.error(
            message="Authentication credentials were not provided or are invalid.",
            error_code="authentication_failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if isinstance(exc, IntegrityError):
        logger.warning("Database integrity error: %s", exc)
        return ResponseHandler.error(
            message="The request conflicts with existing data.",
            error_code="conflict",
            status_code=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        errors = _normalise_errors(response.data)
        return ResponseHandler.error(
            message=_first_message(errors),
            errors=errors,
            error_code=_default_code_for_status(response.status_code),
            status_code=response.status_code,
        )

    logger.exception("Unhandled exception in API request")
    return ResponseHandler.error(
        message="An unexpected error occurred. Please try again later.",
        error_code="internal_server_error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _default_code_for_status(status_code: int) -> str:
    """Map an HTTP status code to a machine readable error code.

    Args:
        status_code: HTTP status code returned by DRF.

    Returns:
        A snake_case error code.
    """
    codes = {
        400: "bad_request",
        401: "authentication_failed",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        406: "not_acceptable",
        409: "conflict",
        415: "unsupported_media_type",
        429: "throttled",
    }
    return codes.get(status_code, "error")


def api_not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    """Root ``404`` handler for URLs that do not resolve to any view.

    Args:
        request: The incoming request.
        exception: The exception that triggered the handler (unused).

    Returns:
        A ``JsonResponse`` using the standard error envelope.
    """
    return JsonResponse(
        ResponseHandler.error_payload(
            message="The requested endpoint does not exist.",
            error_code="not_found",
        ),
        status=status.HTTP_404_NOT_FOUND,
    )


def api_internal_server_error(request: HttpRequest) -> JsonResponse:
    """Root ``500`` handler used when an exception escapes the view layer.

    Args:
        request: The incoming request.

    Returns:
        A ``JsonResponse`` using the standard error envelope with no internal
        details leaked to the client.
    """
    logger.exception("Unhandled server error for %s %s", request.method, request.path)
    return JsonResponse(
        ResponseHandler.error_payload(
            message="An unexpected error occurred. Please try again later.",
            error_code="internal_server_error",
        ),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


__all__ = [
    "api_exception_handler",
    "api_internal_server_error",
    "api_not_found",
]
