"""JSON-schema export for all wire models."""

from __future__ import annotations

from kagan.wire.envelopes import WireEnvelope, WireRequest
from kagan.wire.models import (
    WireEvent,
    WireProject,
    WireSession,
    WireTask,
    WireTaskActiveSession,
)

_ALL_MODELS = (
    WireTaskActiveSession,
    WireTask,
    WireProject,
    WireSession,
    WireEvent,
    WireEnvelope,
    WireRequest,
)


def export_schema() -> dict[str, object]:
    """Return a combined JSON-schema document for every wire model.

    Returns a dict of the form::

        {
            "version": "1",
            "models": {
                "WireTask": { ... json schema ... },
                ...
            }
        }
    """
    models: dict[str, object] = {}
    for cls in _ALL_MODELS:
        models[cls.__name__] = cls.model_json_schema()
    return {"version": "1", "models": models}
