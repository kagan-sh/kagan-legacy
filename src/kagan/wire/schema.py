"""JSON-schema export for all wire models."""

from __future__ import annotations

from typing import Any

from kagan.wire.envelopes import WireEnvelope, WireRequest
from kagan.wire.models import (
    WireEvent,
    WireProject,
    WireRepository,
    WireSession,
    WireTask,
    WireTaskActiveSession,
)

WireTaskEnvelope = WireEnvelope[WireTask]
WireTaskListEnvelope = WireEnvelope[list[WireTask]]
WireProjectEnvelope = WireEnvelope[WireProject]
WireProjectListEnvelope = WireEnvelope[list[WireProject]]
WireRepositoryEnvelope = WireEnvelope[WireRepository]
WireRepositoryListEnvelope = WireEnvelope[list[WireRepository]]
WireSessionEnvelope = WireEnvelope[WireSession]
WireSessionListEnvelope = WireEnvelope[list[WireSession]]
WireEventEnvelope = WireEnvelope[WireEvent]
WireEventListEnvelope = WireEnvelope[list[WireEvent]]
WireSettingsEnvelope = WireEnvelope[dict[str, str]]

_SCHEMA_MODELS: dict[str, Any] = {
    "WireTaskActiveSession": WireTaskActiveSession,
    "WireTask": WireTask,
    "WireProject": WireProject,
    "WireRepository": WireRepository,
    "WireSession": WireSession,
    "WireEvent": WireEvent,
    "WireEnvelope": WireEnvelope,
    "WireRequest": WireRequest,
    "WireTaskEnvelope": WireTaskEnvelope,
    "WireTaskListEnvelope": WireTaskListEnvelope,
    "WireProjectEnvelope": WireProjectEnvelope,
    "WireProjectListEnvelope": WireProjectListEnvelope,
    "WireRepositoryEnvelope": WireRepositoryEnvelope,
    "WireRepositoryListEnvelope": WireRepositoryListEnvelope,
    "WireSessionEnvelope": WireSessionEnvelope,
    "WireSessionListEnvelope": WireSessionListEnvelope,
    "WireEventEnvelope": WireEventEnvelope,
    "WireEventListEnvelope": WireEventListEnvelope,
    "WireSettingsEnvelope": WireSettingsEnvelope,
}


def export_schema() -> dict[str, object]:
    """Return a combined JSON-schema document for every wire model."""
    models: dict[str, object] = {}
    for name, model in _SCHEMA_MODELS.items():
        models[name] = model.model_json_schema()
    return {"version": "1", "models": models}
