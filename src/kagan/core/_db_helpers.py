import asyncio
from collections.abc import Callable, Mapping

from sqlalchemy import Engine
from sqlmodel import Session as DBSession
from sqlmodel import select

from kagan.core.models import Session, SessionEvent, TaskNote, Worktree, _utc_now


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


def _delete_task_children(session, task_id: str) -> None:
    for note in session.exec(select(TaskNote).where(TaskNote.task_id == task_id)).all():
        session.delete(note)
    for event in session.exec(select(SessionEvent).where(SessionEvent.task_id == task_id)).all():
        session.delete(event)
    for run in session.exec(select(Session).where(Session.task_id == task_id)).all():
        session.delete(run)
    for ws in session.exec(select(Worktree).where(Worktree.task_id == task_id)).all():
        session.delete(ws)


__all__ = [
    "_add_and_refresh",
    "_db_async",
    "_db_sync",
    "_delete_task_children",
    "_setting_branch",
    "_setting_enabled",
    "_utc_now",
]
