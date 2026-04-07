"""Behavioral tests for kagan MCP prompts.

Tests exercise prompt behavior through MCP protocol (ClientSession.list_prompts
and get_prompt), not by importing production internals.
All assertions are on observable protocol-level outcomes.
"""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


# ---------------------------------------------------------------------------
# Prompt visibility
# ---------------------------------------------------------------------------


async def test_review_a_task_prompt_is_listed(mcp_board: ClientSession) -> None:
    """review_task must appear in list_prompts."""
    result = await mcp_board.list_prompts()
    names = {p.name for p in result.prompts}
    assert "review_task" in names


async def test_plan_tasks_from_description_prompt_is_listed(mcp_board: ClientSession) -> None:
    """plan_tasks_from_description must appear in list_prompts."""
    result = await mcp_board.list_prompts()
    names = {p.name for p in result.prompts}
    assert "plan_tasks_from_description" in names


async def test_diagnose_failure_prompt_is_listed(mcp_board: ClientSession) -> None:
    """diagnose_failure must appear in list_prompts."""
    result = await mcp_board.list_prompts()
    names = {p.name for p in result.prompts}
    assert "diagnose_failure" in names


async def test_all_three_prompts_listed(mcp_board: ClientSession) -> None:
    """All 3 prompts must be registered."""
    result = await mcp_board.list_prompts()
    names = {p.name for p in result.prompts}
    assert {"review_task", "plan_tasks_from_description", "diagnose_failure"}.issubset(names)


# ---------------------------------------------------------------------------
# review_a_task — structured review prompt with diff context
# ---------------------------------------------------------------------------


async def test_review_a_task_returns_messages(mcp_board: ClientSession) -> None:
    """review_task must return at least one message."""
    result = await mcp_board.get_prompt("review_task", {"task_id": "task-123"})
    assert len(result.messages) >= 1


async def test_review_a_task_message_contains_task_id(mcp_board: ClientSession) -> None:
    """review_task message must reference the provided task_id."""
    result = await mcp_board.get_prompt("review_task", {"task_id": "task-abc"})
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "task-abc" in text


async def test_review_a_task_has_task_id_argument(mcp_board: ClientSession) -> None:
    """review_task must declare task_id as a required argument."""
    result = await mcp_board.list_prompts()
    prompt = next(p for p in result.prompts if p.name == "review_task")
    arg_names = {a.name for a in (prompt.arguments or [])}
    assert "task_id" in arg_names


# ---------------------------------------------------------------------------
# plan_tasks_from_description — task breakdown prompt
# ---------------------------------------------------------------------------


async def test_plan_tasks_from_description_returns_messages(mcp_board: ClientSession) -> None:
    """plan_tasks_from_description must return at least one message."""
    result = await mcp_board.get_prompt(
        "plan_tasks_from_description", {"description": "Build a login page"}
    )
    assert len(result.messages) >= 1


async def test_plan_tasks_from_description_message_contains_description(
    mcp_board: ClientSession,
) -> None:
    """plan_tasks_from_description message must reference the provided description."""
    result = await mcp_board.get_prompt(
        "plan_tasks_from_description", {"description": "Implement OAuth2"}
    )
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "Implement OAuth2" in text


async def test_plan_tasks_from_description_includes_concurrency_and_dependency_guidance(
    mcp_board: ClientSession,
) -> None:
    result = await mcp_board.get_prompt(
        "plan_tasks_from_description", {"description": "Ship notifications"}
    )
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "Acceptance criteria (2-6 bullets" in text
    assert "Dependency notes" in text
    assert "Parallelization notes" in text
    assert "concurrent waves" in text


async def test_plan_tasks_from_description_has_description_argument(
    mcp_board: ClientSession,
) -> None:
    """plan_tasks_from_description must declare description as a required argument."""
    result = await mcp_board.list_prompts()
    prompt = next(p for p in result.prompts if p.name == "plan_tasks_from_description")
    arg_names = {a.name for a in (prompt.arguments or [])}
    assert "description" in arg_names


# ---------------------------------------------------------------------------
# diagnose_failure — diagnostic prompt
# ---------------------------------------------------------------------------


async def test_diagnose_failure_returns_messages(mcp_board: ClientSession) -> None:
    """diagnose_failure must return at least one message."""
    result = await mcp_board.get_prompt(
        "diagnose_failure",
        {"task_id": "task-xyz", "failure_summary": "Agent timed out"},
    )
    assert len(result.messages) >= 1


async def test_diagnose_failure_message_contains_task_id(mcp_board: ClientSession) -> None:
    """diagnose_failure message must reference the provided task_id."""
    result = await mcp_board.get_prompt(
        "diagnose_failure",
        {"task_id": "task-999", "failure_summary": "OOM error"},
    )
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "task-999" in text


async def test_diagnose_failure_message_contains_failure_summary(
    mcp_board: ClientSession,
) -> None:
    """diagnose_failure message must reference the provided failure_summary."""
    result = await mcp_board.get_prompt(
        "diagnose_failure",
        {"task_id": "task-001", "failure_summary": "Segmentation fault"},
    )
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "Segmentation fault" in text


async def test_diagnose_failure_has_required_arguments(mcp_board: ClientSession) -> None:
    """diagnose_failure must declare task_id and failure_summary as arguments."""
    result = await mcp_board.list_prompts()
    prompt = next(p for p in result.prompts if p.name == "diagnose_failure")
    arg_names = {a.name for a in (prompt.arguments or [])}
    assert "task_id" in arg_names
    assert "failure_summary" in arg_names


# ---------------------------------------------------------------------------
# Prompts available on all tiers (readonly, default, admin)
# ---------------------------------------------------------------------------


async def test_prompts_available_on_readonly_server() -> None:
    """Prompts must be listed on a readonly server."""
    mcp = create_server(ServerOptions(readonly=True))
    session_q: asyncio.Queue = asyncio.Queue()
    teardown_event = asyncio.Event()

    async def _lifecycle() -> None:
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

    task = asyncio.create_task(_lifecycle())
    session = await session_q.get()
    result = await session.list_prompts()
    names = {p.name for p in result.prompts}
    teardown_event.set()
    await task
    assert {"review_task", "plan_tasks_from_description", "diagnose_failure"}.issubset(names)
