from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import Engine
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async
from kagan.core.models import AuditEntry


class AuditLog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def list(self, *, limit: int | None = None) -> list[AuditEntry]:
        stmt = select(AuditEntry).order_by(cast("Any", AuditEntry.created_at).desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))

    async def record(
        self,
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
        return await _db_async(self._engine, lambda s: _add_and_refresh(s, entry))


__all__ = ["AuditLog"]
