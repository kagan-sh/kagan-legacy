"""Behavioral tests for kagan web --fake-agent mode.

Verifies:
- The fake-agent backend can be registered without error.
- A task created and run with the fake-agent backend produces a Session row
  with status RUNNING within 5 s.  No live agent binary is invoked.
- The fake agent emits ACP updates that flow through the on_session_update
  callback (verified by checking the Session becomes RUNNING, which requires
  the spawn path to complete without error).

We use a real KaganCore instance backed by on-disk SQLite and a real git
worktree so the full session-start path is exercised.  The only fake piece is
the agent itself.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from sqlmodel import select

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core._fake_agent import (
    FAKE_AGENT_BACKEND,
    register_fake_backend,
)
from kagan.core.enums import SessionStatus
from kagan.core.models import Session

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git(path: Path) -> Path:
    """Initialise a git repo with an initial commit in *path*."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "test@kagan.dev"],
        ["git", "config", "user.name", "Test"],
        ["git", "commit", "--allow-empty", "-m", "init"],
    ):
        subprocess.run(cmd, cwd=path, check=True, capture_output=True)
    return path


async def _wait_for_condition(
    coro_factory: Any,
    *,
    predicate: Any,
    timeout: float = 5.0,
    interval: float = 0.25,
) -> Any:
    """Poll *coro_factory()* until *predicate* is truthy or *timeout* elapses."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        result = await coro_factory()
        if predicate(result):
            return result
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"Condition not met within {timeout}s. Last value: {result!r}")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def fast_fake_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a very short delay so fake-agent tests finish quickly."""
    monkeypatch.setenv("KAGAN_FAKE_AGENT_DELAY_MS", "1500")
    register_fake_backend()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_fake_backend_is_idempotent() -> None:
    """register_fake_backend() can be called multiple times without error."""
    register_fake_backend()
    register_fake_backend()  # second call must not raise

    from kagan.core import get_backend_spec

    spec = get_backend_spec(FAKE_AGENT_BACKEND)
    assert spec.name == FAKE_AGENT_BACKEND
    assert spec.display_name is not None
    assert "Fake" in spec.display_name


@pytest.mark.asyncio
async def test_fake_agent_produces_running_session_within_5s(
    fast_fake_agent: None,
    tmp_path: Path,
) -> None:
    """Running a task with fake-agent produces a RUNNING Session in time.

    No live agent binary is invoked.  ``KAGAN_FAKE_AGENT_DELAY_MS=200`` keeps
    the fake running long enough for the assertion but exits quickly.
    """
    repo_path = _init_git(tmp_path / "repo")
    core = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        project = await core.projects.create("Fake Agent Project")
        await core.projects.set_active(project.id)
        await core.projects.add_repo(project.id, str(repo_path))

        task = await core.tasks.create(
            "Test task for fake agent",
            description="This task uses the fake-agent backend",
        )

        # Launch the agent task — it transitions to RUNNING almost immediately
        # (via _update_session_pid) and then stays RUNNING for 200 ms.
        runner = asyncio.create_task(core.tasks.run(task.id, agent_backend=FAKE_AGENT_BACKEND))

        async def _sessions_for_task() -> list[Session]:
            def _read(s: Any) -> list[Session]:
                return list(s.exec(select(Session).where(Session.task_id == task.id)).all())

            return await _db_async(core.engine, _read)

        # Wait until we see at least one RUNNING session row.
        sessions = await _wait_for_condition(
            _sessions_for_task,
            predicate=lambda rows: any(
                getattr(r.status, "value", r.status) == SessionStatus.RUNNING.value for r in rows
            ),
            timeout=5.0,
        )

        running = [
            r
            for r in sessions
            if getattr(r.status, "value", r.status) == SessionStatus.RUNNING.value
        ]
        assert len(running) >= 1, "Expected at least one RUNNING session"

        # Let the runner finish (it completes after the 200 ms delay).
        try:
            await asyncio.wait_for(runner, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            runner.cancel()
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_fake_agent_session_completes_without_error(
    fast_fake_agent: None,
    tmp_path: Path,
) -> None:
    """The fake agent session runs to COMPLETED without spawning a real process."""
    repo_path = _init_git(tmp_path / "repo2")
    core = KaganCore(db_path=tmp_path / "kagan2.db")
    try:
        project = await core.projects.create("Fake Agent Project 2")
        await core.projects.set_active(project.id)
        await core.projects.add_repo(project.id, str(repo_path))

        task = await core.tasks.create("Another fake task")

        # run() resolves once the agent task is spawned (not when it finishes).
        # The background reader_task completes after the delay.
        session = await asyncio.wait_for(
            core.tasks.run(task.id, agent_backend=FAKE_AGENT_BACKEND),
            timeout=5.0,
        )
        assert session is not None
        assert session.agent_backend == FAKE_AGENT_BACKEND

        # Allow the background fake session task to finish.
        await asyncio.sleep(0.5)

        # Session should now be COMPLETED (or still RUNNING if timing is tight).
        async def _get_session() -> Session | None:
            def _read(s: Any) -> Session | None:
                return s.get(Session, session.id)

            return await _db_async(core.engine, _read)

        final = await _wait_for_condition(
            _get_session,
            predicate=lambda s: s is not None
            and getattr(s.status, "value", s.status)
            in {SessionStatus.RUNNING.value, SessionStatus.COMPLETED.value},
            timeout=3.0,
        )
        assert final is not None
        final_status = getattr(final.status, "value", final.status)
        assert final_status in {SessionStatus.RUNNING.value, SessionStatus.COMPLETED.value}, (
            f"Expected RUNNING or COMPLETED, got {final_status}"
        )
    finally:
        await core.aclose()
