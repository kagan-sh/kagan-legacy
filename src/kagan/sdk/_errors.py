"""SDK error hierarchy for Kagan."""

from __future__ import annotations


class SDKError(Exception):
    """Base exception for all SDK errors."""

    code: str = "SDK_ERROR"
    message: str = "An SDK error occurred"
    hint: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.hint = hint or self.hint
        super().__init__(self.message)


class ConnectionError(SDKError):
    """Raised when the SDK cannot connect to the core."""

    code = "CONNECTION_ERROR"

    def __init__(
        self,
        message: str = "Cannot connect to Kagan core",
        *,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, hint=hint)


class RequestError(SDKError):
    """Raised when a request to the core fails."""

    code = "REQUEST_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, code=code, hint=hint)


class NotFoundError(RequestError):
    """Raised when a requested resource is not found."""

    code = "NOT_FOUND"


class ValidationError(RequestError):
    """Raised when request parameters are invalid."""

    code = "VALIDATION_ERROR"


class PermissionError(RequestError):
    """Raised when the caller lacks permission."""

    code = "PERMISSION_DENIED"


class TimeoutError(SDKError):
    """Raised when a request times out."""

    code = "TIMEOUT"


class CoreFailureError(RequestError):
    """Raised when the core returns a failure response."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "CORE_FAILURE",
        hint: str | None = None,
        capability: str | None = None,
        method: str | None = None,
    ) -> None:
        super().__init__(message, code=code, hint=hint)
        self.capability = capability
        self.method = method


__all__ = [
    "ConnectionError",
    "CoreFailureError",
    "NotFoundError",
    "PermissionError",
    "RequestError",
    "SDKError",
    "TimeoutError",
    "ValidationError",
]
