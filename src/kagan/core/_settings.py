"""Settings key-value store."""

import functools
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Engine
from sqlmodel import select

from kagan.core._db_helpers import _db_async
from kagan.core.models import Setting

# ── Module-level functions (canonical API) ─────────────────────────


async def get_settings(engine: Engine) -> dict[str, str]:
    def op(s):
        rows = s.exec(select(Setting)).all()
        return {row.key: row.value for row in rows}

    return await _db_async(engine, op)


async def set_settings(engine: Engine, updates: Mapping[str, str]) -> None:
    data = dict(updates)

    def op(s):
        for key, value in data.items():
            existing = s.get(Setting, key)
            if existing:
                existing.value = value
                s.add(existing)
            else:
                s.add(Setting(key=key, value=value))

    await _db_async(engine, op, commit=True)


# ── Namespace factory (replaces Settings wrapper class) ────────────────────────


def _make_settings_ns(engine: Engine) -> Any:
    """Build a SimpleNamespace whose attributes delegate to module functions."""
    return SimpleNamespace(
        get=functools.partial(get_settings, engine),
        set=functools.partial(set_settings, engine),
    )


__all__ = ["get_settings", "set_settings"]
