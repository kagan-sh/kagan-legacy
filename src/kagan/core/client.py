"""KaganCore — thin engine factory and convenience namespace.

Usage::

    async with KaganCore() as client:
        project = await client.projects.create("My Project")
        task = await client.tasks.create("Fix the bug")
"""

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel

from kagan.core._agent import cleanup_all_spawned_processes
from kagan.core._analytics import Analytics
from kagan.core._audit import _make_audit_log_ns
from kagan.core._db import create_db_engine, default_db_path, get_db_version
from kagan.core._events import Events
from kagan.core._persona import PersonaPresetOps
from kagan.core._preflight import PreflightCheckResult, run_all_checks
from kagan.core._projects import Projects
from kagan.core._reviews import _make_reviews_ns
from kagan.core._sessions import Sessions
from kagan.core._settings import _make_settings_ns
from kagan.core._tasks import Tasks
from kagan.core._watcher import DBWatcher
from kagan.core._worktrees import Worktrees
from kagan.core.chat import ChatEngine, ChatSessions, make_spawn_per_turn_acp_factory


class KaganCore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        resolved = Path(db_path) if db_path is not None else default_db_path()
        self._db_path: Path = resolved
        self._engine = create_db_engine(resolved)
        self._signals: dict[str, asyncio.Event] = {}
        self.tasks = Tasks(self._engine, self._signals, client=self, db_path=resolved)
        self.projects = Projects(self._engine, self)
        self.worktrees = Worktrees(self._engine, self)
        self.settings = _make_settings_ns(self._engine)
        self.audit_log = _make_audit_log_ns(self._engine)
        self.analytics = Analytics(self._engine)
        self.persona_presets = PersonaPresetOps(self.settings, self.audit_log)
        self.chat_sessions = ChatSessions(self._engine, self.settings)
        self.chat = ChatEngine(
            sessions=self.chat_sessions,
            acp_factory=make_spawn_per_turn_acp_factory(client=self),
            title_generator=self._make_default_title_generator(),
        )

        self.active_project_id: str | None = None
        # reviews namespace must be built after tasks/worktrees are set
        self.reviews = _make_reviews_ns(self._engine, self)
        logger.info("KaganCore initialized")

    @property
    def engine(self) -> "Engine":
        """Public access to the SQLAlchemy engine for module-function callers."""
        return self._engine

    def close(self) -> None:
        """Close the client synchronously.

        Prefer the async context manager (``async with KaganCore() as client``)
        for deterministic cleanup.  This method is best-effort: when called from
        a running event loop the spawned-process cleanup is scheduled as a
        fire-and-forget task and may not complete before the loop exits.
        """
        logger.warning("close() is best-effort; prefer the async context manager")
        with contextlib.suppress(OSError, RuntimeError, SQLAlchemyError):
            self._engine.dispose()
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(cleanup_all_spawned_processes())
            logger.debug("Cleanup task scheduled (fire-and-forget): {}", task)
        except RuntimeError:
            asyncio.run(cleanup_all_spawned_processes())
        logger.debug("Client closed")

    async def __aenter__(self) -> "KaganCore":
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: Any,
    ) -> None:
        with contextlib.suppress(OSError, RuntimeError, SQLAlchemyError):
            self._engine.dispose()
        await cleanup_all_spawned_processes()
        logger.debug("Client closed")

    def _make_default_title_generator(self) -> Any:
        """Build a best-effort title generator wired through ``cli.chat._title``.

        The closure resolves the active agent backend lazily so that backend
        changes after ``KaganCore`` construction are honoured. Returns ``None``
        on any failure — the engine swallows the error and keeps the default
        label.
        """

        async def _generate(user_text: str, reply: str) -> str | None:
            from kagan.cli.chat._title import generate_session_title
            from kagan.core import resolve_default_agent_backend

            try:
                settings = await self.settings.get()
                backend = resolve_default_agent_backend(settings)
            except Exception:
                logger.debug("Title generator: failed to resolve default backend")
                return None
            if not backend:
                return None
            return await generate_session_title(
                self,
                user_message=user_text,
                assistant_reply=reply,
                agent_backend=backend,
            )

        return _generate

    async def preflight(self, *, agent_backend: str | None = None) -> list[PreflightCheckResult]:
        return await asyncio.to_thread(run_all_checks, self._db_path, agent_backend)

    async def db_version(self) -> int:
        return await asyncio.to_thread(get_db_version, self._engine)

    async def reset(self) -> None:
        await asyncio.to_thread(self._wipe_all)
        logger.info("Database reset complete")

    def _wipe_all(self) -> None:
        with self._engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            try:
                SQLModel.metadata.drop_all(conn)
            finally:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")

        with self._engine.begin() as conn:
            SQLModel.metadata.create_all(conn)
        self.active_project_id = None
        self.tasks._active_project_id = None


__all__ = [
    "DBWatcher",
    "Events",
    "KaganCore",
    "Projects",
    "Sessions",
    "Tasks",
    "Worktrees",
]
