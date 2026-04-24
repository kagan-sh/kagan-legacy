import asyncio
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session as DBSession

from kagan.core.models import _utc_now


def _col(x: Any) -> Any:
    """Typed passthrough for SQLModel column expressions.

    SQLModel's Mapped[...] columns trip pyrefly when used with
    .like / .in_ / .desc — historically wrapped in cast("Any", x).
    Centralised here so changes (e.g. an SQLModel bump) touch one place.
    """
    return x


def _setting_enabled(settings: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _setting_branch(settings: Mapping[str, str], key: str, *, default: str) -> str:
    value = settings.get(key)
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


def _db_sync(engine: Engine, fn: Callable, *, commit: bool = False):
    with DBSession(engine) as session:
        result = fn(session)
        if commit:
            session.commit()
        return result


async def _db_async(engine: Engine, fn: Callable, *, commit: bool = False):
    return await asyncio.to_thread(_db_sync, engine, fn, commit=commit)


def _add_and_refresh(s, obj):
    s.add(obj)
    s.commit()
    s.refresh(obj)
    return obj


__all__ = [
    "_add_and_refresh",
    "_col",
    "_db_async",
    "_db_sync",
    "_setting_branch",
    "_setting_enabled",
    "_utc_now",
]
