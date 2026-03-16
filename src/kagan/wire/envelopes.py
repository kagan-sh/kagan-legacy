"""Generic wire envelopes for request / response framing."""

from uuid import uuid4

from pydantic import BaseModel, Field


class WireEnvelope[T](BaseModel):
    """Generic wrapper for all wire responses.

    ``ok=True`` → ``data`` carries payload.
    ``ok=False`` → ``error`` carries a human-readable message.
    """

    ok: bool = True
    data: T | None = None
    error: str | None = None


class WireRequest(BaseModel):
    """Base request envelope shared by all wire calls."""

    version: str = "1"
    trace_id: str = Field(default_factory=lambda: uuid4().hex)


WireResponse = WireEnvelope
"""Convenience alias — ``WireResponse[T]`` reads better at call sites."""
