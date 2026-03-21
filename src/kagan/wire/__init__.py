"""kagan.wire — Backward-compatible re-exports.

The wire model layer has been removed. SQLModel classes serialize directly
via ``model_dump(mode="json")``. This module re-exports the envelope types
from their canonical location for any remaining callers.
"""

from kagan.server._envelope import WireEnvelope, WireRequest, WireResponse

__all__ = [
    "WireEnvelope",
    "WireRequest",
    "WireResponse",
]
