"""Shared fixtures for kagan.server.mcp tests.

Provides the mcp_board fixture: an in-memory MCP server connected via
create_client_server_memory_streams, yielding a ClientSession for tool calls.
Also provides mcp_driver fixture: an McpDriver backed by mcp_board.
"""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession
from tests.helpers.mcp_driver import McpDriver

_SESSION_STARTUP_TIMEOUT_SECONDS = 10.0


async def _wait_for_session_startup(
    *,
    session_q: asyncio.Queue[ClientSession],
    error_q: asyncio.Queue[BaseException],
    lifecycle_task: asyncio.Task,
    timeout_seconds: float = _SESSION_STARTUP_TIMEOUT_SECONDS,
) -> ClientSession:
    session_get_task = asyncio.create_task(session_q.get())
    error_get_task = asyncio.create_task(error_q.get())
    done, pending = await asyncio.wait(
        {session_get_task, error_get_task, lifecycle_task},
        return_when=asyncio.FIRST_COMPLETED,
        timeout=timeout_seconds,
    )

    for task in pending:
        if task is lifecycle_task:
            continue
        task.cancel()
    for task in pending:
        if task is lifecycle_task:
            continue
        with contextlib.suppress(asyncio.CancelledError):
            await task

    if not done:
        raise TimeoutError(
            f"Timed out waiting for MCP session startup after {timeout_seconds:.1f}s"
        )

    if lifecycle_task in done:
        exc = lifecycle_task.exception()
        if exc is not None:
            raise RuntimeError("MCP lifecycle failed before session initialization") from exc
        raise RuntimeError("MCP lifecycle ended before session initialization")

    if error_get_task in done:
        exc = error_get_task.result()
        raise RuntimeError("MCP lifecycle failed before session initialization") from exc

    return session_get_task.result()


@pytest.fixture
async def mcp_board(tmp_path):
    """Yield a connected ClientSession backed by an in-memory kagan MCP server.

    Uses create_client_server_memory_streams (InMemoryTransport) — no subprocess,
    no STDIO.

    The server and ClientSession lifecycle are managed inside a single asyncio
    task (_lifecycle) to avoid anyio cancel scope cross-task issues with
    pytest-asyncio's teardown mechanism. Communication uses asyncio.Queue and
    asyncio.Event — no anyio primitives cross the task boundary.
    """
    opts = ServerOptions(db_path=str(tmp_path / "kagan_mcp_default_test.db"))
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
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )

                try:
                    async with ClientSession(client_read, client_write) as session:
                        await session.initialize()
                        await session_q.put(session)
                        await teardown_event.wait()
                finally:
                    server_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await server_task
        except Exception as exc:
            await error_q.put(exc)

    lifecycle_task = asyncio.create_task(_lifecycle())

    session = await _wait_for_session_startup(
        session_q=session_q,
        error_q=error_q,
        lifecycle_task=lifecycle_task,
    )
    yield session

    teardown_event.set()
    await lifecycle_task

    if not error_q.empty():
        raise error_q.get_nowait()


@pytest.fixture
async def mcp_driver(mcp_board: ClientSession) -> McpDriver:
    """Yield an McpDriver backed by the in-memory mcp_board session."""
    return McpDriver(mcp_board)


async def _make_session(opts: ServerOptions) -> tuple[ClientSession, asyncio.Task, asyncio.Event]:
    """Spin up an in-memory MCP server with given opts, return (session, task, teardown_event)."""
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
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(client_read, client_write) as session:
                        await session.initialize()
                        await session_q.put(session)
                        await teardown_event.wait()
                finally:
                    server_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await server_task
        except Exception as exc:
            await error_q.put(exc)

    lifecycle_task = asyncio.create_task(_lifecycle())
    session = await _wait_for_session_startup(
        session_q=session_q,
        error_q=error_q,
        lifecycle_task=lifecycle_task,
    )
    return session, lifecycle_task, teardown_event


@pytest.fixture
async def mcp_board_with_session(tmp_path):
    """Yield a ClientSession backed by a server with session_id='test-session'."""
    session, lifecycle_task, teardown_event = await _make_session(
        ServerOptions(
            session_id="test-session",
            db_path=str(tmp_path / "kagan_mcp_session_bound.db"),
        )
    )
    yield session
    teardown_event.set()
    await lifecycle_task


@pytest.fixture
async def mcp_board_with_core(tmp_path):
    """Yield a ClientSession backed by a server with a real KaganCore.

    Uses a tmp_path database so the core client branches are exercised.
    Pre-creates a project so task operations work without 'no active project' errors.
    """
    from kagan.core import KaganCore

    db_path = str(tmp_path / "kagan_mcp_test.db")
    # Pre-create a project so the server's client can activate it at startup
    bootstrap = KaganCore(db_path=db_path)
    project = await bootstrap.projects.create("MCP Test Project")

    session, lifecycle_task, teardown_event = await _make_session(
        ServerOptions(db_path=db_path, project_id=project.id)
    )
    yield session
    teardown_event.set()
    await lifecycle_task


@pytest.fixture
async def mcp_board_admin_with_core(tmp_path):
    """Yield an admin ClientSession backed by a server with a real KaganCore."""
    from kagan.core import KaganCore

    db_path = str(tmp_path / "kagan_mcp_admin_test.db")
    bootstrap = KaganCore(db_path=db_path)
    project = await bootstrap.projects.create("MCP Admin Test Project")

    session, lifecycle_task, teardown_event = await _make_session(
        ServerOptions(admin=True, db_path=db_path, project_id=project.id)
    )
    yield session
    teardown_event.set()
    await lifecycle_task


@pytest.fixture
async def mcp_board_core_with_session(tmp_path):
    """Yield a ClientSession backed by a real KaganCore with session_id set."""
    from kagan.core import KaganCore

    db_path = str(tmp_path / "kagan_mcp_session_test.db")
    bootstrap = KaganCore(db_path=db_path)
    project = await bootstrap.projects.create("MCP Session Test Project")

    session, lifecycle_task, teardown_event = await _make_session(
        ServerOptions(db_path=db_path, project_id=project.id, session_id="core-test-session")
    )
    yield session
    teardown_event.set()
    await lifecycle_task


@pytest.fixture
async def mcp_board_core_instrumented(tmp_path):
    from kagan.core import KaganCore

    db_path = str(tmp_path / "kagan_mcp_instrumented_test.db")
    bootstrap = KaganCore(db_path=db_path)
    project = await bootstrap.projects.create("MCP Instrumented Test Project")

    session, lifecycle_task, teardown_event = await _make_session(
        ServerOptions(db_path=db_path, project_id=project.id, enable_instrumentation=True)
    )
    yield session
    teardown_event.set()
    await lifecycle_task


@pytest.fixture
async def mcp_board_with_core_client(tmp_path):
    """Yield (ClientSession, KaganCore) sharing the same DB.

    The core client allows direct DB manipulation for tests that need to set up
    specific states (e.g. tasks with sessions that reference dead PIDs).
    """
    from kagan.core import KaganCore

    db_path = str(tmp_path / "kagan_mcp_core_client_test.db")
    bootstrap = KaganCore(db_path=db_path)
    project = await bootstrap.projects.create("MCP Core Client Test Project")
    await bootstrap.projects.set_active(project.id)

    session, lifecycle_task, teardown_event = await _make_session(
        ServerOptions(db_path=db_path, project_id=project.id)
    )
    yield session, bootstrap
    teardown_event.set()
    await lifecycle_task
