"""Unified runtime service.

Combines persisted startup/session context, in-memory runtime task projection,
AUTO output readiness/recovery orchestration, process control primitives,
idempotency cache, and runtime snapshot serialization.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypedDict

from sqlalchemy.exc import OperationalError

from kagan.core.adapters.db.repositories.base import RepositoryClosing
from kagan.core.adapters.db.schema import AppState
from kagan.core.adapters.db.session import AsyncSessionFactory, get_session
from kagan.core.adapters.process import spawn_detached
from kagan.core.domain.enums import ExecutionStatus, TaskType
from kagan.core.git_utils import has_git_repo
from kagan.core.ipc.discovery import CoreEndpoint, discover_core_endpoint
from kagan.core.paths import (
    get_config_path,
    get_core_runtime_dir,
    get_data_dir,
    get_database_path,
)
from kagan.core.process_liveness import pid_exists
from kagan.core.time import utc_now

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from kagan.core.acp import Agent
    from kagan.core.adapters.db.repositories import ExecutionRepository
    from kagan.core.config import KaganConfig
    from kagan.core.services.automation import AutomationServiceImpl
    from kagan.core.services.projects import ProjectServiceImpl
    from kagan.core.services.types import TaskLike


@dataclass(frozen=True)
class RuntimeContextState:
    """Persisted runtime context and in-memory projection."""

    project_id: str | None = None
    repo_id: str | None = None


class RuntimeSessionEvent(StrEnum):
    """Session transition events."""

    PROJECT_SELECTED = "project_selected"
    REPO_SELECTED = "repo_selected"
    REPO_CLEARED = "repo_cleared"
    RESET = "reset"


@dataclass(frozen=True)
class StartupSessionDecision:
    """Startup decision produced from persisted state + CWD."""

    project_id: str | None = None
    preferred_repo_id: str | None = None
    preferred_path: Path | None = None
    suggest_cwd: bool = False
    cwd_path: str | None = None
    cwd_is_git_repo: bool = False

    @property
    def should_open_project(self) -> bool:
        return self.project_id is not None


class RuntimeTaskPhase(StrEnum):
    """Live runtime phase for AUTO task execution."""

    IDLE = "idle"
    RUNNING = "running"
    REVIEWING = "reviewing"


@dataclass(slots=True)
class RuntimeTaskView:
    """Projected runtime view for a single task."""

    task_id: str
    phase: RuntimeTaskPhase = RuntimeTaskPhase.IDLE
    execution_id: str | None = None
    run_count: int = 0
    running_agent: Agent | None = None
    review_agent: Agent | None = None
    blocked_reason: str | None = None
    blocked_by_task_ids: tuple[str, ...] = ()
    overlap_hints: tuple[str, ...] = ()
    blocked_at: datetime | None = None
    pending_reason: str | None = None
    pending_at: datetime | None = None

    @property
    def is_running(self) -> bool:
        return self.phase is not RuntimeTaskPhase.IDLE

    @property
    def is_reviewing(self) -> bool:
        return self.phase is RuntimeTaskPhase.REVIEWING

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None

    @property
    def is_pending(self) -> bool:
        return self.pending_reason is not None


class AutoOutputMode(StrEnum):
    """Resolved AUTO output delivery mode."""

    LIVE = "live"
    BACKFILL = "backfill"
    WAITING = "waiting"
    UNAVAILABLE = "unavailable"


@dataclass(slots=True)
class AutoOutputReadiness:
    """Decision payload for AUTO output modal readiness."""

    can_open_output: bool
    execution_id: str | None
    running_agent: Agent | None
    is_running: bool
    recovered_stale_execution: bool
    message: str | None
    output_mode: AutoOutputMode = AutoOutputMode.UNAVAILABLE


@dataclass(slots=True)
class AutoOutputRecoveryResult:
    """Result payload for stale AUTO output recovery command."""

    success: bool
    message: str


@dataclass(slots=True)
class _LiveRuntimeState:
    execution_id: str | None = None
    running_agent: Agent | None = None
    is_running: bool = False


class RuntimeServiceImpl:
    """Unified runtime service implementation."""

    _RUNTIME_CONTEXT_KEY = "runtime_context"

    _NO_LOGS_MESSAGE = "No agent logs available for this task"
    _NON_AUTO_MESSAGE = "Output stream is only available for AUTO tasks"
    _STALE_RECOVERY_ERROR = "Recovered stale running execution without live agent"
    _STALE_RECOVERY_MESSAGE = "Recovered stale execution; starting a fresh agent run."
    _STALE_RECOVERY_READY_MESSAGE = (
        "Stale running execution detected. Recover output to restart the agent."
    )
    _STALE_RECOVERY_NOT_REQUIRED_MESSAGE = "Stale AUTO output recovery is not required."
    _STALE_RECOVERY_SPAWN_FAILED_MESSAGE = (
        "Recovered stale execution, but failed to start a fresh agent run."
    )
    _STALE_RECOVERY_NO_AUTOMATION_MESSAGE = (
        "Recovered stale execution, but automation service is unavailable."
    )
    _STALE_RECOVERY_NO_LIVE_RUNTIME_MESSAGE = (
        "Recovered stale execution, but no live agent stream is available yet."
    )
    _RUNNING_ATTACH_TIMEOUT_SECONDS = 2.0
    _RUNNING_WITHOUT_AGENT_MESSAGE = "Agent is starting. Opening output while live stream attaches."

    def __init__(
        self,
        project_service: ProjectServiceImpl,
        session_factory: AsyncSessionFactory,
        execution_service: ExecutionRepository,
        automation_resolver: Callable[[], AutomationServiceImpl | None] | None = None,
    ) -> None:
        self._projects = project_service
        self._session_factory = session_factory
        self._executions = execution_service
        self._automation_resolver = automation_resolver

        self._state = RuntimeContextState()
        self._views: dict[str, RuntimeTaskView] = {}
        self._task_locks: dict[str, asyncio.Lock] = {}

    @property
    def state(self) -> RuntimeContextState:
        return self._state

    async def get_last_active_context(self) -> RuntimeContextState:
        async with get_session(self._session_factory) as session:
            row = await session.get(AppState, self._RUNTIME_CONTEXT_KEY)
            if row is None:
                self._state = RuntimeContextState()
                return self._state
            self._state = RuntimeContextState(
                project_id=row.last_active_project_id,
                repo_id=row.last_active_repo_id,
            )
            return self._state

    async def set_last_active_context(self, project_id: str | None, repo_id: str | None) -> None:
        async with get_session(self._session_factory) as session:
            row = await session.get(AppState, self._RUNTIME_CONTEXT_KEY)
            if row is None:
                row = AppState(
                    key=self._RUNTIME_CONTEXT_KEY,
                    last_active_project_id=project_id,
                    last_active_repo_id=repo_id,
                )
                session.add(row)
            else:
                row.last_active_project_id = project_id
                row.last_active_repo_id = repo_id
                row.updated_at = utc_now()
                session.add(row)
            await session.commit()
        self._state = RuntimeContextState(project_id=project_id, repo_id=repo_id)

    def _resolve_context_transition(
        self,
        event: RuntimeSessionEvent,
        *,
        project_id: str | None = None,
        repo_id: str | None = None,
    ) -> RuntimeContextState:
        if event is RuntimeSessionEvent.RESET:
            return RuntimeContextState()
        if event is RuntimeSessionEvent.PROJECT_SELECTED:
            if project_id is None:
                raise ValueError("project_id is required for PROJECT_SELECTED")
            return RuntimeContextState(project_id=project_id, repo_id=None)
        if event is RuntimeSessionEvent.REPO_SELECTED:
            if repo_id is None:
                raise ValueError("repo_id is required for REPO_SELECTED")
            return RuntimeContextState(
                project_id=project_id or self._state.project_id,
                repo_id=repo_id,
            )
        if event is RuntimeSessionEvent.REPO_CLEARED:
            return RuntimeContextState(project_id=self._state.project_id, repo_id=None)
        return self._state

    async def dispatch(
        self,
        event: RuntimeSessionEvent,
        *,
        project_id: str | None = None,
        repo_id: str | None = None,
    ) -> RuntimeContextState:
        next_state = self._resolve_context_transition(
            event,
            project_id=project_id,
            repo_id=repo_id,
        )
        await self.set_last_active_context(next_state.project_id, next_state.repo_id)
        return self._state

    async def reconcile_startup_state(self) -> RuntimeContextState:
        persisted = await self.get_last_active_context()
        if persisted.project_id is not None:
            project = await self._projects.get_project(persisted.project_id)
            if project is None:
                await self.set_last_active_context(None, None)
                return self._state
        return self._state

    async def decide_startup(self, cwd: Path) -> StartupSessionDecision:
        persisted = await self.reconcile_startup_state()
        if persisted.project_id is not None:
            return StartupSessionDecision(
                project_id=persisted.project_id,
                preferred_repo_id=persisted.repo_id,
            )

        project = await self._projects.find_project_by_repo_path(str(cwd))
        if project is not None:
            return StartupSessionDecision(
                project_id=project.id,
                preferred_path=cwd,
            )

        suggest_cwd = await has_git_repo(cwd)
        return StartupSessionDecision(
            suggest_cwd=True,
            cwd_path=str(cwd),
            cwd_is_git_repo=suggest_cwd,
        )

    def get(self, task_id: str) -> RuntimeTaskView | None:
        return self._views.get(task_id)

    def running_tasks(self) -> set[str]:
        return {task_id for task_id, view in self._views.items() if view.is_running}

    async def reconcile_running_tasks(self, task_ids: Sequence[str]) -> None:
        """Sync runtime views from persisted RUNNING executions."""
        unique_task_ids = tuple(dict.fromkeys(task_ids))
        if not unique_task_ids:
            return

        try:
            latest_running = await self._executions.get_latest_running_executions_for_tasks(
                unique_task_ids
            )
        except (RepositoryClosing, OperationalError, ValueError):
            return
        running_task_ids = set(latest_running.keys())

        for task_id, execution_id in latest_running.items():
            view = self._get_or_create(task_id)
            view.phase = RuntimeTaskPhase.RUNNING
            if view.execution_id is None:
                view.execution_id = execution_id

        for task_id in unique_task_ids:
            if task_id in running_task_ids:
                continue
            view = self._views.get(task_id)
            if view is None:
                continue
            if (
                view.execution_id is not None
                and view.running_agent is None
                and view.review_agent is None
                and not view.is_blocked
                and not view.is_pending
            ):
                self._views.pop(task_id, None)

    def _get_or_create(self, task_id: str) -> RuntimeTaskView:
        view = self._views.get(task_id)
        if view is None:
            view = RuntimeTaskView(task_id=task_id)
            self._views[task_id] = view
        return view

    def mark_started(self, task_id: str) -> None:
        view = self._get_or_create(task_id)
        view.phase = RuntimeTaskPhase.RUNNING
        view.blocked_reason = None
        view.blocked_by_task_ids = ()
        view.overlap_hints = ()
        view.blocked_at = None
        view.pending_reason = None
        view.pending_at = None

    def set_execution(self, task_id: str, execution_id: str | None, run_count: int) -> None:
        view = self._get_or_create(task_id)
        view.execution_id = execution_id
        view.run_count = run_count

    def attach_running_agent(self, task_id: str, agent: Agent) -> None:
        view = self._get_or_create(task_id)
        view.running_agent = agent
        if view.phase is RuntimeTaskPhase.IDLE:
            view.phase = RuntimeTaskPhase.RUNNING
        view.blocked_reason = None
        view.blocked_by_task_ids = ()
        view.overlap_hints = ()
        view.blocked_at = None
        view.pending_reason = None
        view.pending_at = None

    def attach_review_agent(self, task_id: str, agent: Agent) -> None:
        view = self._get_or_create(task_id)
        view.review_agent = agent
        view.phase = RuntimeTaskPhase.REVIEWING
        view.blocked_reason = None
        view.blocked_by_task_ids = ()
        view.overlap_hints = ()
        view.blocked_at = None
        view.pending_reason = None
        view.pending_at = None

    def clear_review_agent(self, task_id: str) -> None:
        view = self._views.get(task_id)
        if view is None:
            return
        view.review_agent = None
        if view.running_agent is not None:
            view.phase = RuntimeTaskPhase.RUNNING

    def mark_blocked(
        self,
        task_id: str,
        *,
        reason: str,
        blocked_by_task_ids: tuple[str, ...] = (),
        overlap_hints: tuple[str, ...] = (),
    ) -> None:
        view = self._get_or_create(task_id)
        view.phase = RuntimeTaskPhase.IDLE
        view.running_agent = None
        view.review_agent = None
        view.blocked_reason = reason
        view.blocked_by_task_ids = blocked_by_task_ids
        view.overlap_hints = overlap_hints
        view.blocked_at = utc_now()
        view.pending_reason = None
        view.pending_at = None

    def mark_pending(self, task_id: str, *, reason: str) -> None:
        view = self._get_or_create(task_id)
        if not view.is_running:
            view.phase = RuntimeTaskPhase.IDLE
        view.pending_reason = reason
        view.pending_at = utc_now()

    def clear_pending(self, task_id: str) -> None:
        view = self._views.get(task_id)
        if view is None:
            return
        view.pending_reason = None
        view.pending_at = None
        if (
            view.phase is RuntimeTaskPhase.IDLE
            and view.execution_id is None
            and view.running_agent is None
            and view.review_agent is None
            and not view.is_blocked
        ):
            self._views.pop(task_id, None)

    def clear_blocked(self, task_id: str) -> None:
        view = self._views.get(task_id)
        if view is None:
            return
        view.blocked_reason = None
        view.blocked_by_task_ids = ()
        view.overlap_hints = ()
        view.blocked_at = None
        if (
            view.phase is RuntimeTaskPhase.IDLE
            and view.execution_id is None
            and view.running_agent is None
            and view.review_agent is None
            and not view.is_pending
        ):
            self._views.pop(task_id, None)

    def mark_ended(self, task_id: str) -> None:
        self._views.pop(task_id, None)

    def _get_task_lock(self, task_id: str) -> asyncio.Lock:
        lock = self._task_locks.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            self._task_locks[task_id] = lock
        return lock

    def _resolve_live_runtime(self, task_id: str) -> _LiveRuntimeState:
        runtime_view = self.get(task_id)
        if runtime_view is not None and runtime_view.is_running:
            return _LiveRuntimeState(
                execution_id=runtime_view.execution_id,
                running_agent=runtime_view.running_agent,
                is_running=True,
            )

        return _LiveRuntimeState()

    def _resolve_automation_service(self) -> AutomationServiceImpl | None:
        if self._automation_resolver is None:
            return None
        try:
            return self._automation_resolver()
        except Exception:  # quality-allow-broad-except
            return None

    async def _has_persisted_execution_logs(self, execution_id: str) -> bool:
        entries = await self._executions.get_execution_log_entries(execution_id)
        return any(entry.logs for entry in entries)

    @classmethod
    def _readiness(
        cls,
        *,
        output_mode: AutoOutputMode,
        execution_id: str | None = None,
        running_agent: Agent | None = None,
        is_running: bool = False,
        recovered_stale_execution: bool = False,
        message: str | None = None,
    ) -> AutoOutputReadiness:
        can_open_output = output_mode in (AutoOutputMode.LIVE, AutoOutputMode.BACKFILL)
        if output_mode is AutoOutputMode.WAITING and is_running:
            can_open_output = True
        return AutoOutputReadiness(
            can_open_output=can_open_output,
            execution_id=execution_id,
            running_agent=running_agent,
            is_running=is_running,
            recovered_stale_execution=recovered_stale_execution,
            message=message,
            output_mode=output_mode,
        )

    @classmethod
    def _running_result(
        cls,
        live: _LiveRuntimeState,
        *,
        recovered_stale_execution: bool = False,
        message: str | None = None,
    ) -> AutoOutputReadiness:
        return cls._readiness(
            output_mode=AutoOutputMode.LIVE,
            execution_id=live.execution_id,
            is_running=True,
            running_agent=live.running_agent,
            recovered_stale_execution=recovered_stale_execution,
            message=message,
        )

    async def prepare_auto_output(self, task: TaskLike) -> AutoOutputReadiness:
        if task.task_type is not TaskType.AUTO:
            return self._readiness(
                output_mode=AutoOutputMode.UNAVAILABLE,
                message=self._NON_AUTO_MESSAGE,
            )

        async with self._get_task_lock(task.id):
            live = self._resolve_live_runtime(task.id)
            blocked_view = self.get(task.id)
            blocked_message = (
                blocked_view.blocked_reason
                if blocked_view is not None and blocked_view.is_blocked
                else None
            )
            pending_message = (
                blocked_view.pending_reason
                if blocked_view is not None and blocked_view.is_pending
                else None
            )

            if live.is_running and live.running_agent is not None:
                return self._running_result(live)

            if live.is_running and live.execution_id is not None:
                execution = await self._executions.get_execution(live.execution_id)
                if execution is None or execution.status is not ExecutionStatus.RUNNING:
                    self.mark_ended(task.id)
                    live = self._resolve_live_runtime(task.id)
                else:
                    has_running_logs = await self._has_persisted_execution_logs(live.execution_id)
                    if has_running_logs:
                        return self._readiness(
                            output_mode=AutoOutputMode.BACKFILL,
                            execution_id=live.execution_id,
                            is_running=True,
                            message=blocked_message,
                        )
                    return self._readiness(
                        output_mode=AutoOutputMode.WAITING,
                        execution_id=live.execution_id,
                        is_running=True,
                        message=self._RUNNING_WITHOUT_AGENT_MESSAGE,
                    )

            if live.is_running:
                return self._readiness(
                    output_mode=AutoOutputMode.WAITING,
                    execution_id=live.execution_id,
                    is_running=True,
                    message=self._RUNNING_WITHOUT_AGENT_MESSAGE,
                )

            latest = await self._executions.get_latest_execution_for_task(task.id)
            if latest is None:
                return self._readiness(
                    output_mode=AutoOutputMode.UNAVAILABLE,
                    message=blocked_message or pending_message or self._NO_LOGS_MESSAGE,
                )

            has_logs = await self._has_persisted_execution_logs(latest.id)
            if has_logs:
                return self._readiness(
                    output_mode=AutoOutputMode.BACKFILL,
                    execution_id=latest.id,
                    message=blocked_message or pending_message,
                )

            if latest.status is ExecutionStatus.RUNNING:
                return self._readiness(
                    output_mode=AutoOutputMode.WAITING,
                    execution_id=latest.id,
                    message=self._STALE_RECOVERY_READY_MESSAGE,
                )

            return self._readiness(
                output_mode=AutoOutputMode.UNAVAILABLE,
                message=blocked_message or pending_message or self._NO_LOGS_MESSAGE,
            )

    async def recover_stale_auto_output(self, task: TaskLike) -> AutoOutputRecoveryResult:
        if task.task_type is not TaskType.AUTO:
            return AutoOutputRecoveryResult(success=False, message=self._NON_AUTO_MESSAGE)

        async with self._get_task_lock(task.id):
            live = self._resolve_live_runtime(task.id)
            if live.is_running:
                return AutoOutputRecoveryResult(
                    success=False,
                    message=self._STALE_RECOVERY_NOT_REQUIRED_MESSAGE,
                )

            latest = await self._executions.get_latest_execution_for_task(task.id)
            if latest is None or latest.status is not ExecutionStatus.RUNNING:
                return AutoOutputRecoveryResult(
                    success=False,
                    message=self._STALE_RECOVERY_NOT_REQUIRED_MESSAGE,
                )

            has_logs = await self._has_persisted_execution_logs(latest.id)
            if has_logs:
                return AutoOutputRecoveryResult(
                    success=False,
                    message=self._STALE_RECOVERY_NOT_REQUIRED_MESSAGE,
                )

            await self._executions.update_execution(
                latest.id,
                status=ExecutionStatus.KILLED,
                completed_at=utc_now(),
                error=self._STALE_RECOVERY_ERROR,
            )

            automation = self._resolve_automation_service()
            if automation is None:
                return AutoOutputRecoveryResult(
                    success=False,
                    message=self._STALE_RECOVERY_NO_AUTOMATION_MESSAGE,
                )

            spawned = await automation.spawn_for_task(task)
            if not spawned:
                return AutoOutputRecoveryResult(
                    success=False,
                    message=self._STALE_RECOVERY_SPAWN_FAILED_MESSAGE,
                )

            await automation.wait_for_running_agent(
                task.id,
                timeout=self._RUNNING_ATTACH_TIMEOUT_SECONDS,
            )

            live_after_spawn = self._resolve_live_runtime(task.id)
            if live_after_spawn.is_running:
                return AutoOutputRecoveryResult(
                    success=True,
                    message=self._STALE_RECOVERY_MESSAGE,
                )

            return AutoOutputRecoveryResult(
                success=False,
                message=self._STALE_RECOVERY_NO_LIVE_RUNTIME_MESSAGE,
            )


# ---------------------------------------------------------------------------
# Idempotency (formerly runtime_helpers)
# ---------------------------------------------------------------------------

IDEMPOTENCY_CACHE_LIMIT = 512

IDEMPOTENT_MUTATION_METHODS: set[tuple[str, str]] = {
    ("tasks", "create"),
    ("tasks", "update"),
    ("tasks", "move"),
    ("tasks", "delete"),
    ("tasks", "update_scratchpad"),
    ("review", "request"),
    ("review", "approve"),
    ("review", "reject"),
    ("review", "merge"),
    ("review", "rebase"),
    ("jobs", "submit"),
    ("jobs", "cancel"),
    ("sessions", "create"),
    ("sessions", "attach"),
    ("sessions", "kill"),
    ("projects", "create"),
    ("projects", "open"),
    ("projects", "add_repo"),
    ("settings", "update"),
}


@dataclass(frozen=True, slots=True)
class CachedResponseEnvelope:
    ok: bool
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None


@dataclass(slots=True)
class IdempotencyRecord:
    fingerprint: str
    response: CachedResponseEnvelope | None = None
    pending: asyncio.Future[CachedResponseEnvelope] | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    cache_key: tuple[str, str]
    fingerprint: str
    pending: asyncio.Future[CachedResponseEnvelope]
    owner: bool


# ---------------------------------------------------------------------------
# Runtime snapshot (formerly runtime_helpers)
# ---------------------------------------------------------------------------


class RuntimeSnapshot(TypedDict):
    """Serialized runtime state exposed to query/command callers."""

    is_running: bool
    is_reviewing: bool
    is_blocked: bool
    blocked_reason: str | None
    blocked_by_task_ids: list[str]
    overlap_hints: list[str]
    blocked_at: str | None
    is_pending: bool
    pending_reason: str | None
    pending_at: str | None


class RuntimeSnapshotSource(Protocol):
    """Minimal runtime service interface required for snapshot lookup."""

    def get(self, task_id: str) -> object | None:
        """Return runtime view for task_id or None when unavailable."""


def empty_runtime_snapshot() -> RuntimeSnapshot:
    """Return default runtime payload when there is no active runtime view."""
    return RuntimeSnapshot(
        is_running=False,
        is_reviewing=False,
        is_blocked=False,
        blocked_reason=None,
        blocked_by_task_ids=[],
        overlap_hints=[],
        blocked_at=None,
        is_pending=False,
        pending_reason=None,
        pending_at=None,
    )


def _iso_or_none(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def serialize_runtime_view(view: object | None) -> RuntimeSnapshot:
    """Serialize runtime view object into a stable dict payload."""
    if view is None:
        return empty_runtime_snapshot()
    return RuntimeSnapshot(
        is_running=bool(getattr(view, "is_running", False)),
        is_reviewing=bool(getattr(view, "is_reviewing", False)),
        is_blocked=bool(getattr(view, "is_blocked", False)),
        blocked_reason=getattr(view, "blocked_reason", None),
        blocked_by_task_ids=[str(task_id) for task_id in getattr(view, "blocked_by_task_ids", ())],
        overlap_hints=[str(hint) for hint in getattr(view, "overlap_hints", ())],
        blocked_at=_iso_or_none(getattr(view, "blocked_at", None)),
        is_pending=bool(getattr(view, "is_pending", False)),
        pending_reason=getattr(view, "pending_reason", None),
        pending_at=_iso_or_none(getattr(view, "pending_at", None)),
    )


def runtime_snapshot_for_task(
    *,
    task_id: str,
    runtime_service: RuntimeSnapshotSource | None,
) -> RuntimeSnapshot:
    """Resolve task runtime snapshot from a runtime service if available."""
    if runtime_service is None:
        return empty_runtime_snapshot()
    return serialize_runtime_view(runtime_service.get(task_id))


# ---------------------------------------------------------------------------
# Process control (formerly runtime_control)
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_CORE_START_LOCK_NAME = "core.start.lock"
_CORE_START_POLL_SECONDS = 0.2
_CORE_START_LOCK_STALE_SECONDS = 60.0
_CORE_LEASE_FILE = "core.lease.json"
_CORE_INSTANCE_LOCK_FILE = "core.instance.lock"


def _build_daemon_command(config_path: Path, db_path: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "kagan.core.daemon",
        "--config-path",
        str(config_path),
        "--db-path",
        str(db_path),
    ]


def _spawn_core_detached(
    *,
    config_path: Path,
    db_path: Path,
    runtime_dir: Path,
) -> subprocess.Popen[bytes]:
    cmd = _build_daemon_command(config_path, db_path)
    env = dict(os.environ)
    env["KAGAN_CORE_RUNTIME_DIR"] = str(runtime_dir)

    if os.name == "nt":
        creationflags = 0
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return spawn_detached(cmd, env=env, windows_creationflags=creationflags)

    return spawn_detached(cmd, env=env)


def _core_start_lock_path(runtime_dir: Path) -> Path:
    return runtime_dir / _CORE_START_LOCK_NAME


def _try_acquire_start_lock(lock_path: Path) -> bool:
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n")
    return True


def _release_start_lock(lock_path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        lock_path.unlink()


def _maybe_clear_stale_start_lock(lock_path: Path, *, stale_after_seconds: float) -> None:
    try:
        lock_age = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return
    if lock_age < stale_after_seconds:
        return
    logger.warning("Removing stale core start lock older than %.1fs", lock_age)
    with contextlib.suppress(FileNotFoundError):
        lock_path.unlink()


def _read_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _has_live_core_instance_lock(runtime_dir: Path) -> bool:
    pid: int | None = None
    lease_path = runtime_dir / _CORE_LEASE_FILE
    try:
        lease_data = json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        lease_data = None
    if isinstance(lease_data, dict):
        raw_owner_pid = lease_data.get("owner_pid")
        if isinstance(raw_owner_pid, int):
            pid = raw_owner_pid
        elif isinstance(raw_owner_pid, str):
            with contextlib.suppress(ValueError):
                pid = int(raw_owner_pid)
    if pid is None:
        pid = _read_pid(runtime_dir / _CORE_INSTANCE_LOCK_FILE)
    return pid is not None and pid_exists(pid)


def discover_running_pid_fallback(*, runtime_dir: Path | None = None) -> int | None:
    resolved_runtime_dir = runtime_dir if runtime_dir is not None else get_core_runtime_dir()
    lease_path = resolved_runtime_dir / _CORE_LEASE_FILE
    try:
        lease_data = json.loads(lease_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        lease_data = None
    if isinstance(lease_data, dict):
        raw_owner_pid = lease_data.get("owner_pid")
        if isinstance(raw_owner_pid, int) and pid_exists(raw_owner_pid):
            return raw_owner_pid
        if isinstance(raw_owner_pid, str):
            with contextlib.suppress(ValueError):
                parsed = int(raw_owner_pid)
                if pid_exists(parsed):
                    return parsed
    pid = _read_pid(resolved_runtime_dir / _CORE_INSTANCE_LOCK_FILE)
    if pid is not None and pid_exists(pid):
        return pid
    return None


def cleanup_stale_runtime_files(*, runtime_dir: Path | None = None) -> None:
    resolved_runtime_dir = runtime_dir if runtime_dir is not None else get_core_runtime_dir()
    for name in ("endpoint.json", "token", _CORE_LEASE_FILE):
        with contextlib.suppress(OSError):
            (resolved_runtime_dir / name).unlink(missing_ok=True)


def _resolve_runtime_dir(config_path: Path, db_path: Path) -> Path:
    override = os.environ.get("KAGAN_CORE_RUNTIME_DIR")
    if override:
        return Path(override).expanduser().resolve(strict=False)

    resolved_config = config_path.expanduser().resolve(strict=False)
    resolved_db = db_path.expanduser().resolve(strict=False)
    default_config = get_config_path().expanduser().resolve(strict=False)
    default_db = get_database_path().expanduser().resolve(strict=False)

    if resolved_config == default_config and resolved_db == default_db:
        return get_core_runtime_dir()

    try:
        resolved_executable = Path(sys.executable).expanduser().resolve(strict=False)
    except OSError:
        resolved_executable = Path(sys.executable)

    key = f"{resolved_config}\n{resolved_db}\n{resolved_executable}".encode()
    suffix = hashlib.sha256(key).hexdigest()[:16]
    if os.name == "nt":
        return get_data_dir() / "core" / "scoped" / suffix
    return Path("/tmp") / "kagan-core" / suffix


async def ensure_core_running(
    *,
    config: KaganConfig | None = None,
    config_path: Path | None = None,
    db_path: Path | None = None,
    timeout: float = 15.0,
) -> CoreEndpoint:
    del config
    config_path = config_path or get_config_path()
    db_path = db_path or get_database_path()
    runtime_dir = _resolve_runtime_dir(config_path, db_path)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _core_start_lock_path(runtime_dir)

    endpoint = discover_core_endpoint(runtime_dir=runtime_dir)
    if endpoint is not None:
        logger.info("Found existing core: %s %s", endpoint.transport, endpoint.address)
        return endpoint

    logger.info("No running core found, starting one...")
    process: subprocess.Popen[bytes] | None = None
    has_start_lock = False

    deadline = asyncio.get_running_loop().time() + timeout
    stale_after = max(_CORE_START_LOCK_STALE_SECONDS, timeout * 2)
    try:
        while asyncio.get_running_loop().time() < deadline:
            endpoint = discover_core_endpoint(runtime_dir=runtime_dir)
            if endpoint is not None:
                return endpoint

            if not has_start_lock:
                has_start_lock = _try_acquire_start_lock(lock_path)
                if has_start_lock:
                    process = _spawn_core_detached(
                        config_path=config_path,
                        db_path=db_path,
                        runtime_dir=runtime_dir,
                    )
                else:
                    _maybe_clear_stale_start_lock(lock_path, stale_after_seconds=stale_after)

            if process is not None and process.poll() is not None:
                if _has_live_core_instance_lock(runtime_dir):
                    process = None
                else:
                    msg = f"Core daemon exited early with code {process.returncode}"
                    raise RuntimeError(msg)

            await asyncio.sleep(_CORE_START_POLL_SECONDS)
    finally:
        if has_start_lock:
            _release_start_lock(lock_path)

    msg = f"Core host did not become available within {timeout}s"
    raise TimeoutError(msg)


def ensure_core_running_sync(
    *,
    config: KaganConfig | None = None,
    config_path: Path | None = None,
    db_path: Path | None = None,
    timeout: float = 15.0,
) -> CoreEndpoint:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            ensure_core_running(
                config=config,
                config_path=config_path,
                db_path=db_path,
                timeout=timeout,
            )
        )
    msg = "ensure_core_running_sync cannot be called from within a running event loop"
    raise RuntimeError(msg)


async def run_core_host(*, config_path: Path | None = None, db_path: Path | None = None) -> None:
    from kagan.core.host import CoreHost

    resolved_config_path = config_path or get_config_path()
    resolved_db_path = db_path or get_database_path()
    host = CoreHost(config_path=resolved_config_path, db_path=resolved_db_path)
    await host.start()
    await host.wait_until_stopped()


def launch_core_subprocess(
    *,
    config_path: Path | None = None,
    db_path: Path | None = None,
) -> int:
    try:
        asyncio.run(run_core_host(config_path=config_path, db_path=db_path))
    except KeyboardInterrupt:
        logger.info("Core host interrupted by user")
    return 0
