"""IPC request/response contract types for Kagan core communication."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_request_id() -> str:
    return uuid4().hex


class CoreRequest(BaseModel):
    """IPC request envelope targeting a capability/method on the core."""

    request_id: str = Field(default_factory=_new_request_id)
    session_id: str
    session_profile: str | None = None
    session_origin: str
    client_version: str
    client_build_hash: str | None = None
    capability: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class CoreErrorDetail(BaseModel):
    """Structured error detail (code + message) inside a CoreResponse."""

    code: str
    message: str


class CoreResponse(BaseModel):
    """IPC response envelope from the core to a client."""

    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: CoreErrorDetail | None = None

    @staticmethod
    def success(
        request_id: str,
        result: dict[str, Any] | None = None,
    ) -> CoreResponse:
        """Create a successful response."""
        return CoreResponse(request_id=request_id, ok=True, result=result)

    @staticmethod
    def failure(
        request_id: str,
        *,
        code: str,
        message: str,
    ) -> CoreResponse:
        """Create a failure response with an error detail."""
        return CoreResponse(
            request_id=request_id,
            ok=False,
            error=CoreErrorDetail(code=code, message=message),
        )


__all__ = [
    "CoreErrorDetail",
    "CoreRequest",
    "CoreResponse",
]
