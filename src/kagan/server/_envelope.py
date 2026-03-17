"""Generic wire envelopes for request / response framing."""

from uuid import uuid4

from pydantic import BaseModel, Field


class WireEnvelope[T](BaseModel):
    """Generic wrapper for all wire responses."""

    ok: bool = True
    data: T | None = None
    error: str | None = None


class WireRequest(BaseModel):
    version: str = "1"
    trace_id: str = Field(default_factory=lambda: uuid4().hex)


WireResponse = WireEnvelope
