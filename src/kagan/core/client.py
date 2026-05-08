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
        self._closed = False

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
        or ``await client.aclose()`` for deterministic cleanup. This method is
        best-effort when called from a running event loop.
        """
        if self._closed:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.aclose())
            return
        logger.warning("close() is best-effort in a running loop; prefer await client.aclose()")
        task = loop.create_task(self.aclose())
        logger.debug("Cleanup task scheduled (fire-and-forget): {}", task)

    async def aclose(self) -> None:
        """Close the client and await spawned-process cleanup."""
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(OSError, RuntimeError, SQLAlchemyError):
            self._engine.dispose()
        await cleanup_all_spawned_processes()
        logger.debug("Client closed")

    async def __aenter__(self) -> "KaganCore":
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: Any,
    ) -> None:
        await self.aclose()

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

    # -------------------------------------------------------------------------
    # Orchestrator-chat overlay helpers (public API)
    # -------------------------------------------------------------------------

    async def resolve_active_session(self, task_id: str):
        """Return the most relevant agent Session for *task_id*, or None.

        Priority: active worker → active reviewer → latest reviewer → latest worker.
        """
        from kagan.core._sessions import list_task_sessions
        from kagan.core._sessions_query import resolve_active_session

        sessions = await list_task_sessions(self._engine, task_id)
        return resolve_active_session(sessions)

    async def list_running_agents(self, project_id: str | None = None):
        """Return all sessions currently in an active status joined with their task.

        Results are sorted by ``started_at DESC``.  Optionally scoped to a project.
        """
        from kagan.core._sessions_query import list_running_agents

        return await list_running_agents(self._engine, project_id=project_id)

    async def attach_chat(
        self,
        chat_session_id: str,
        session_id: str | None,
        *,
        agent_role: str | None = None,
    ) -> None:
        """Attach (or detach) a ChatSession to a specific agent Session.

        Pass ``session_id=None`` to return the chat to orchestrator mode.
        """
        from kagan.core.chat._attach import attach_chat_to_session

        await attach_chat_to_session(
            self._engine,
            chat_session_id,
            session_id,
            agent_role=agent_role,
        )

    async def send_message_to_session(self, session_id: str, text: str) -> None:
        """Inject a user message into a running agent session's event stream.

        The message is recorded as an ``output_chunk`` event with
        ``kind="user"`` so the orchestrator overlay's live stream and replay
        render it as a ``UserInputWidget``.  This is the same event shape the
        agent itself emits when it echoes a user turn.

        Raises :class:`kagan.core.errors.KaganError` if the session does not
        exist or is in a terminal status (COMPLETED, FAILED, CANCELLED).  Only
        sessions with status PENDING or RUNNING accept input — calling this on
        any other status is a programming error from the caller's perspective.

        Args:
            session_id: ID of the agent Session to inject into.
            text: The user message text to inject.
        """
        from kagan.core._db_helpers import _db_async
        from kagan.core.enums import SessionStatus
        from kagan.core.errors import KaganError
        from kagan.core.models import Session, Task

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text is required")

        def _fetch(s) -> tuple[str | None, str | None]:
            """Return (task_id, status_value) for the session, or (None, None)."""
            row = s.get(Session, session_id)
            if row is None:
                return None, None
            task = s.get(Task, row.task_id)
            task_id = task.id if task is not None else None
            return task_id, str(getattr(row.status, "value", row.status))

        task_id, status_str = await _db_async(self._engine, _fetch)
        if task_id is None:
            raise KaganError(f"session not found: id={session_id!r}")

        _active = {SessionStatus.PENDING.value, SessionStatus.RUNNING.value}
        if status_str not in _active:
            raise KaganError(f"session does not accept input: status={status_str}")

        payload: dict = {
            "text": cleaned,
            "kind": "user",
            "acp": {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": cleaned},
            },
        }
        await self.tasks.events.emit(
            task_id,
            "output_chunk",
            payload,
            session_id=session_id,
        )

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
