"""Audit log persistence."""

import functools
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Engine
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _col, _db_async
from kagan.core.models import AuditEntry

# ── Module-level functions (canonical API) ─────────────────────────


async def list_audit(engine: Engine, *, limit: int | None = None) -> list[AuditEntry]:
    stmt = select(AuditEntry).order_by(_col(AuditEntry.created_at).desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return await _db_async(engine, lambda s: list(s.exec(stmt).all()))


async def record_audit(
    engine: Engine,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: Mapping[str, Any] | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=dict(detail or {}),
    )
    return await _db_async(engine, lambda s: _add_and_refresh(s, entry))


# ── Namespace factory (replaces AuditLog wrapper class) ────────────────────────


def _make_audit_log_ns(engine: Engine) -> Any:
    """Build a SimpleNamespace whose attributes delegate to module functions."""
    return SimpleNamespace(
        list=functools.partial(list_audit, engine),
        record=functools.partial(record_audit, engine),
    )


__all__ = ["list_audit", "record_audit"]
