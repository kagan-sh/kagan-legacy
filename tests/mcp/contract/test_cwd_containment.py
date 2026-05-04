"""Contract tests for cwd containment in bash_exec and terminal_run (F2).

Both tools must reject a cwd that escapes the bound task's worktree when a
task_id is present in the MCP context.  Without a bound task the cwd is
unconstrained (legitimate orchestrator-shell usage) — only a warning is emitted.

Six tests cover three branches for each tool:
- cwd outside worktree → ValidationError (MCP error)
- cwd inside worktree → success
- no bound task, arbitrary cwd → success
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.core import KaganCore, Session, TaskStatus, db_async, transition_task
from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession
from tests.helpers.helpers import make_git_repo
from tests.helpers.mcp_helpers import extract_text as _text

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]

_SESSION_STARTUP_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


async def _start_server(opts: ServerOptions) -> tuple[ClientSession, asyncio.Task, asyncio.Event]:
    """Spin up an in-memory MCP server, return (session, lifecycle_task, teardown_event)."""
    mcp = create_server(opts)
    session_q: asyncio.Queue[ClientSession] = asyncio.Queue()
    teardown_event = asyncio.Event()
    error_q: asyncio.Queue[BaseException] = asyncio.Queue()

    async def _lifecycle() -> None:
        try:
            async with create_client_server_memory_streams() as (client_streams, server_streams):
                client_read, client_write = client_streams
                server_read, server_write = server_streams
                server_task = asyncio.create_task(
                    mcp._mcp_server.run(
                        server_read, server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(client_read, client_write) as sess:
                        await sess.initialize()
                        await session_q.put(sess)
                        await teardown_event.wait()
                finally:
                    server_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await server_task
        except Exception as exc:
            await error_q.put(exc)

    lifecycle_task = asyncio.create_task(_lifecycle())

    session_get = asyncio.create_task(session_q.get())
    error_get = asyncio.create_task(error_q.get())
    done, pending = await asyncio.wait(
        {session_get, error_get, lifecycle_task},
        return_when=asyncio.FIRST_COMPLETED,
        timeout=_SESSION_STARTUP_TIMEOUT,
    )
    for t in pending:
        if t is lifecycle_task:
            continue
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t

    if lifecycle_task in done:
        exc = lifecycle_task.exception()
        raise RuntimeError("MCP lifecycle failed before session init") from exc
    if error_get in done:
        raise RuntimeError("MCP lifecycle error before session init") from error_get.result()

    return session_get.result(), lifecycle_task, teardown_event


async def _make_bound_session(tmp_path: Path) -> tuple[str, str, str, Path]:
    """Create a project, git repo, task, worktree, and session in DB.

    Returns (db_path, session_id, task_id, worktree_path).
    """
    db_path = str(tmp_path / "kagan_cwd_test.db")
    bootstrap = KaganCore(db_path=db_path)

    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    project = await bootstrap.projects.create("CWD Test Project")
    await bootstrap.projects.set_active(project.id)
    await bootstrap.projects.add_repo(project.id, str(repo_path))

    task_result = await bootstrap.tasks.create("cwd-containment-task")
    task_id = task_result.id

    # Transition to IN_PROGRESS so worktree creation is allowed.
    await transition_task(bootstrap, task_id, TaskStatus.IN_PROGRESS)

    worktree = await bootstrap.worktrees.create(task_id)
    worktree_path = Path(worktree.worktree_path)

    # Insert a Session row so the MCP server can resolve the binding.
    session_obj = Session(task_id=task_id, agent_backend="claude-code")
    session_obj = await db_async(
        bootstrap.engine,
        lambda s: (s.add(session_obj) or s.commit() or s.refresh(session_obj)) or session_obj,
    )

    bootstrap.close()
    return db_path, session_obj.id, task_id, worktree_path


# ---------------------------------------------------------------------------
# bash_exec — cwd containment
# ---------------------------------------------------------------------------


class TestBashExecCwdContainment:
    async def test_rejects_cwd_outside_worktree(self, tmp_path: Path) -> None:
        """bash_exec must return an error when cwd escapes the bound worktree."""
        db_path, session_id, _, _ = await _make_bound_session(tmp_path)
        sess, task, done = await _start_server(
            ServerOptions(db_path=db_path, session_id=session_id)
        )
        try:
            result = await sess.call_tool(
                "bash_exec", {"command": "echo hi", "cwd": str(tmp_path / ".." / "..")}
            )
            assert result.isError
        finally:
            done.set()
            await task

    async def test_accepts_cwd_inside_worktree(self, tmp_path: Path) -> None:
        """bash_exec must succeed when cwd is inside the bound worktree."""
        db_path, session_id, _, worktree_path = await _make_bound_session(tmp_path)
        sess, task, done = await _start_server(
            ServerOptions(db_path=db_path, session_id=session_id)
        )
        try:
            result = await sess.call_tool(
                "bash_exec", {"command": "echo inside", "cwd": str(worktree_path)}
            )
            assert not result.isError
            payload = _text(result)
            assert "inside" in payload["output"]
        finally:
            done.set()
            await task

    async def test_unbound_allows_any_cwd(self, tmp_path: Path) -> None:
        """bash_exec must succeed when no task is bound, even for an arbitrary cwd."""
        db_path = str(tmp_path / "unbound.db")
        bootstrap = KaganCore(db_path=db_path)
        await bootstrap.projects.create("Unbound Project")
        bootstrap.close()

        sess, task, done = await _start_server(ServerOptions(db_path=db_path))
        try:
            result = await sess.call_tool(
                "bash_exec",
                {"command": "echo unbound", "cwd": str(tmp_path)},
            )
            assert not result.isError
            payload = _text(result)
            assert "unbound" in payload["output"]
        finally:
            done.set()
            await task


# ---------------------------------------------------------------------------
# terminal_run — cwd containment
# ---------------------------------------------------------------------------


class TestTerminalRunCwdContainment:
    async def test_rejects_cwd_outside_worktree(self, tmp_path: Path) -> None:
        """terminal_run must return an error when cwd escapes the bound worktree."""
        db_path, session_id, _, _ = await _make_bound_session(tmp_path)
        sess, task, done = await _start_server(
            ServerOptions(db_path=db_path, session_id=session_id)
        )
        try:
            result = await sess.call_tool(
                "terminal_run", {"command": "echo hi", "cwd": str(tmp_path / ".." / "..")}
            )
            assert result.isError
        finally:
            done.set()
            await task

    async def test_accepts_cwd_inside_worktree(self, tmp_path: Path) -> None:
        """terminal_run must succeed when cwd is inside the bound worktree."""
        db_path, session_id, _, worktree_path = await _make_bound_session(tmp_path)
        sess, task, done = await _start_server(
            ServerOptions(db_path=db_path, session_id=session_id)
        )
        try:
            result = await sess.call_tool(
                "terminal_run", {"command": "echo inside", "cwd": str(worktree_path)}
            )
            assert not result.isError
            payload = _text(result)
            assert "inside" in payload["output"]
        finally:
            done.set()
            await task

    async def test_unbound_allows_any_cwd(self, tmp_path: Path) -> None:
        """terminal_run must succeed when no task is bound, even for an arbitrary cwd."""
        db_path = str(tmp_path / "unbound_tr.db")
        bootstrap = KaganCore(db_path=db_path)
        await bootstrap.projects.create("Unbound TR Project")
        bootstrap.close()

        sess, task, done = await _start_server(ServerOptions(db_path=db_path))
        try:
            result = await sess.call_tool(
                "terminal_run",
                {"command": "echo unbound", "cwd": str(tmp_path)},
            )
            assert not result.isError
            payload = _text(result)
            assert "unbound" in payload["output"]
        finally:
            done.set()
            await task
