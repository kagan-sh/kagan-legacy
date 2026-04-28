"""Generic wire envelopes for request / response framing."""

from pydantic import BaseModel


class WireEnvelope[T](BaseModel):
    """Generic wrapper for all wire responses."""

    ok: bool = True
    data: T | None = None
    error: str | None = None
