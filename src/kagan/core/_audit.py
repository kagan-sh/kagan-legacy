"""Audit log persistence."""

import functools
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async, _sa_col
from kagan.core.models import AuditEntry

# ── Module-level functions (canonical API) ─────────────────────────


async def list_audit(engine: Engine, *, limit: int | None = None) -> list[AuditEntry]:
    stmt = select(AuditEntry).order_by(_sa_col(AuditEntry.created_at).desc())
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


# ── Typed namespace (replaces SimpleNamespace + Any return) ────────────────────────


@dataclass(slots=True)
class _AuditLogNs:
    """Typed delegate for ``KaganCore.audit_log``.

    Fields are bound callables so ``await client.audit_log.list()`` and
    ``await client.audit_log.record(...)`` remain unchanged.
    """

    list: Callable[..., Awaitable[list[AuditEntry]]]
    record: Callable[..., Awaitable[AuditEntry]]


def _make_audit_log_ns(engine: Engine) -> _AuditLogNs:
    """Build a typed audit-log delegate bound to *engine*."""
    return _AuditLogNs(
        list=functools.partial(list_audit, engine),
        record=functools.partial(record_audit, engine),
    )


__all__ = ["list_audit", "record_audit"]
