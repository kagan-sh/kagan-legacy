from collections.abc import Mapping

from sqlalchemy import Engine
from sqlmodel import select

from kagan.core._db_helpers import _db_async
from kagan.core.models import Setting


class Settings:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def get(self) -> dict[str, str]:
        def op(s):
            rows = s.exec(select(Setting)).all()
            return {row.key: row.value for row in rows}

        return await _db_async(self._engine, op)

    async def set(self, updates: Mapping[str, str]) -> None:
        data = dict(updates)

        def op(s):
            for key, value in data.items():
                existing = s.get(Setting, key)
                if existing:
                    existing.value = value
                    s.add(existing)
                else:
                    s.add(Setting(key=key, value=value))

        await _db_async(self._engine, op, commit=True)


__all__ = ["Settings"]
