"""Single place that builds API response payloads.

Every response in the project (success, error, 404, 500, paginated lists) is
produced by :class:`ResponseHandler` so the client always sees the same
envelope:

``{"success": bool, "message": str, "data": ..., "meta": {...}, "errors": {...},
"error_code": str}``
"""

from typing import Any

from rest_framework.response import Response


class ResponseHandler:
    """Factory for consistent success and error responses."""

    @staticmethod
    def success_payload(
        data: Any = None,
        message: str = "",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the raw dict used for successful responses.

        Args:
            data: Payload returned to the client.
            message: Short human readable summary.
            meta: Optional metadata, e.g. pagination details.

        Returns:
            A JSON serialisable dictionary.
        """
        payload: dict[str, Any] = {
            "success": True,
            "message": message,
            "data": data,
        }
        if meta is not None:
            payload["meta"] = meta
        return payload

    @staticmethod
    def error_payload(
        message: str,
        errors: dict[str, Any] | list[Any] | None = None,
        error_code: str = "error",
    ) -> dict[str, Any]:
        """Build the raw dict used for error responses.

        Args:
            message: Human readable error message.
            errors: Optional field level error details.
            error_code: Machine readable error code.

        Returns:
            A JSON serialisable dictionary.
        """
        return {
            "success": False,
            "message": message,
            "errors": errors or {},
            "error_code": error_code,
        }

    @classmethod
    def success(
        cls,
        data: Any = None,
        message: str = "",
        status_code: int = 200,
        meta: dict[str, Any] | None = None,
    ) -> Response:
        """Return a DRF ``Response`` using the success envelope.

        Args:
            data: Payload returned to the client.
            message: Short human readable summary.
            status_code: HTTP status code to use.
            meta: Optional metadata, e.g. pagination details.

        Returns:
            A DRF ``Response`` instance.
        """
        return Response(
            cls.success_payload(data=data, message=message, meta=meta),
            status=status_code,
        )

    @classmethod
    def created(cls, data: Any = None, message: str = "") -> Response:
        """Return a ``201 Created`` response using the success envelope."""
        return cls.success(data=data, message=message, status_code=201)

    @classmethod
    def no_content(cls) -> Response:
        """Return a ``204 No Content`` response.

        Returns:
            A DRF ``Response`` instance without a response body.
        """
        return Response(status=204)

    @classmethod
    def error(
        cls,
        message: str,
        errors: dict[str, Any] | list[Any] | None = None,
        error_code: str = "error",
        status_code: int = 400,
    ) -> Response:
        """Return a DRF ``Response`` using the error envelope.

        Args:
            message: Human readable error message.
            errors: Optional field level error details.
            error_code: Machine readable error code.
            status_code: HTTP status code to use.

        Returns:
            A DRF ``Response`` instance.
        """
        return Response(
            cls.error_payload(message=message, errors=errors, error_code=error_code),
            status=status_code,
        )
