"""Application level exceptions.

Services raise these; the DRF exception handler in
:mod:`core.exception_handler` converts them into HTTP responses using
:class:`core.responses.ResponseHandler`, so the wire format is identical for
business errors and framework errors.
"""

from typing import Any


class AppException(Exception):
    """Base class for every business/domain error raised by the application."""

    status_code: int = 400
    error_code: str = "bad_request"
    default_message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        errors: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        """Store the response details used to build the error payload.

        Args:
            message: Human readable message returned to the client.
            errors: Optional field level details, e.g. ``{"email": ["Required"]}``.
            error_code: Optional machine readable code overriding the class default.
        """
        self.message = message or self.default_message
        self.errors = errors or {}
        self.error_code = error_code or self.error_code
        super().__init__(self.message)

    def get_payload(self) -> dict[str, Any]:
        """Return the serialisable error payload for this exception."""
        return {
            "success": False,
            "message": self.message,
            "errors": self.errors,
            "error_code": self.error_code,
        }


class ValidationException(AppException):
    """Raised when request or domain data fails validation."""

    status_code = 400
    error_code = "validation_error"
    default_message = "The submitted data is invalid."


class AuthenticationException(AppException):
    """Raised when credentials could not be verified."""

    status_code = 401
    error_code = "authentication_failed"
    default_message = "Authentication credentials were not provided or are invalid."


class PermissionDeniedException(AppException):
    """Raised when an authenticated user lacks permission for the operation."""

    status_code = 403
    error_code = "permission_denied"
    default_message = "You do not have permission to perform this action."


class NotFoundException(AppException):
    """Raised when a requested resource does not exist or was soft deleted."""

    status_code = 404
    error_code = "not_found"
    default_message = "The requested resource was not found."


class ConflictException(AppException):
    """Raised when the request conflicts with the current state of the resource."""

    status_code = 409
    error_code = "conflict"
    default_message = "The request conflicts with the current state of the resource."
