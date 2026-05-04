"""Settings key-value store."""

import functools
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

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
    def op(s):
        for key, value in updates.items():
            existing = s.get(Setting, key)
            if existing:
                existing.value = value
                s.add(existing)
            else:
                s.add(Setting(key=key, value=value))

    await _db_async(engine, op, commit=True)


# ── Typed namespace (replaces SimpleNamespace + Any return) ────────────────────────


@dataclass(slots=True)
class _SettingsNs:
    """Typed delegate for ``KaganCore.settings``.

    Fields are bound callables so the call site ``await client.settings.get()``
    and ``await client.settings.set({...})`` remain unchanged.
    """

    get: Callable[[], Awaitable[dict[str, str]]]
    set: Callable[[Mapping[str, str]], Awaitable[None]]


def _make_settings_ns(engine: Engine) -> _SettingsNs:
    """Build a typed settings delegate bound to *engine*."""
    return _SettingsNs(
        get=functools.partial(get_settings, engine),
        set=functools.partial(set_settings, engine),
    )


__all__ = ["get_settings", "set_settings"]
