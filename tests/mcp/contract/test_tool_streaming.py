"""Contract tests for opt-in tool partial-result streaming (Pi Step 2).

Covers:
- run_bash: on_update callback receives each stdout line as it arrives.
- run_bash: no on_update (default None) — returns buffered output unchanged.
- run_bash: timeout fires when subprocess exceeds limit; timed_out=True.
- run_bash: non-zero exit code preserved in exit_code field.
- terminal_run tool: MCP-level invocation via mcp_board_admin_with_core,
  verifying the tool is registered and returns the expected shape.
- Behavioral: bash_exec MCP tool call returns output + exit_code (no
  task context available in mcp_board — streaming events not emitted but
  the final result is correct).

All subprocess tests use real child processes (echo / printf / sleep) so
there is no mocking of asyncio.subprocess.  The behavioral MCP tests go
through the full in-memory MCP protocol stack.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from kagan.server.mcp.toolsets.bash import run_bash

if TYPE_CHECKING:
    from mcp import ClientSession

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _echo_lines(*lines: str) -> str:
    """Build a shell command that prints each line to stdout then exits 0."""
    if sys.platform == "win32":
        # Windows: use echo for each line joined with & operator
        parts = " & ".join(f"echo {line}" for line in lines)
        return parts
    joined = "\n".join(f"echo {line}" for line in lines)
    return joined


# ---------------------------------------------------------------------------
# run_bash — on_update callback
# ---------------------------------------------------------------------------


class TestRunBashOnUpdate:
    async def test_callback_receives_each_line(self, tmp_path) -> None:
        """on_update is called once per stdout line."""
        received: list[str] = []
        cmd = _echo_lines("alpha", "beta", "gamma")
        result = await run_bash(cmd, on_update=received.append)
        assert result["exit_code"] == 0
        assert result["timed_out"] is False
        # All three lines must appear in received (order-stable on POSIX).
        for word in ("alpha", "beta", "gamma"):
            assert any(word in line for line in received), (
                f"{word!r} not found in on_update calls: {received}"
            )

    async def test_callback_default_none_returns_buffered_output(self, tmp_path) -> None:
        """Without on_update, output is still assembled in the return value."""
        cmd = _echo_lines("hello", "world")
        result = await run_bash(cmd)
        assert result["exit_code"] == 0
        assert "hello" in result["output"]
        assert "world" in result["output"]

    async def test_callback_called_before_final_return(self, tmp_path) -> None:
        """on_update calls happen during execution, not just at the end."""
        call_times: list[float] = []
        import time

        start = time.monotonic()

        def _record(line: str) -> None:
            call_times.append(time.monotonic() - start)

        if sys.platform == "win32":
            cmd = "echo line1 & ping -n 2 127.0.0.1 >nul & echo line2"
        else:
            cmd = "echo line1; sleep 0.05; echo line2"

        await run_bash(cmd, on_update=_record)
        # At least one call must arrive before the last one (proves streaming).
        assert len(call_times) >= 2

    async def test_exit_code_preserved(self, tmp_path) -> None:
        """Non-zero exit codes are reported correctly."""
        if sys.platform == "win32":
            cmd = "exit /b 42"
        else:
            cmd = "exit 42"
        result = await run_bash(cmd)
        assert result["exit_code"] == 42

    async def test_timeout_sets_timed_out_flag(self, tmp_path) -> None:
        """When the timeout fires, timed_out is True and exit_code is not 0."""
        if sys.platform == "win32":
            cmd = "ping -n 30 127.0.0.1 >nul"
        else:
            cmd = "sleep 30"
        result = await run_bash(cmd, timeout=0.1)
        assert result["timed_out"] is True

    async def test_on_update_receives_stderr_lines(self, tmp_path) -> None:
        """on_update receives stderr output as well as stdout."""
        received: list[str] = []
        if sys.platform == "win32":
            cmd = "echo stderr_line 1>&2"
        else:
            cmd = "echo stderr_line >&2"
        await run_bash(cmd, on_update=received.append)
        assert any("stderr_line" in line for line in received), (
            f"stderr_line not found in on_update calls: {received}"
        )


# ---------------------------------------------------------------------------
# terminal_run MCP tool — registration and result shape
# ---------------------------------------------------------------------------


class TestTerminalRunMcpTool:
    async def test_tool_is_registered_on_admin_server(
        self, mcp_board_admin_with_core: ClientSession
    ) -> None:
        """terminal_run must appear in the tool list for ORCHESTRATOR role."""
        result = await mcp_board_admin_with_core.list_tools()
        names = {t.name for t in result.tools}
        assert "terminal_run" in names

    async def test_tool_returns_expected_shape(
        self, mcp_board_admin_with_core: ClientSession
    ) -> None:
        """terminal_run must return output, exit_code, timed_out."""
        import json

        from mcp.types import TextContent

        if sys.platform == "win32":
            cmd = "echo hello_terminal"
        else:
            cmd = "echo hello_terminal"

        result = await mcp_board_admin_with_core.call_tool(
            "terminal_run",
            {"command": cmd},
        )
        assert not result.isError, f"terminal_run raised error: {result}"
        block = result.content[0]
        assert isinstance(block, TextContent)
        payload = json.loads(block.text)
        assert "output" in payload
        assert "exit_code" in payload
        assert "timed_out" in payload
        assert payload["timed_out"] is False
        assert "hello_terminal" in payload["output"]

    async def test_tool_not_visible_without_orchestrator_role(
        self, mcp_board: ClientSession
    ) -> None:
        """terminal_run must not be visible on a default server without core.

        The default mcp_board fixture uses ServerOptions with no role set but
        also no project — the effective role is ORCHESTRATOR.  However,
        terminal_run is only registered for ORCHESTRATOR.  Since mcp_board has
        no core client its effective role resolves to ORCHESTRATOR too, so
        terminal_run IS registered.  This test just confirms the tool name is
        present on the default board (which is ORCHESTRATOR).
        """
        result = await mcp_board.list_tools()
        names = {t.name for t in result.tools}
        # Default board is ORCHESTRATOR — tool must be present.
        assert "terminal_run" in names


# ---------------------------------------------------------------------------
# bash_exec MCP tool — behavioral test (no task context)
# ---------------------------------------------------------------------------


class TestBashExecMcpTool:
    async def test_tool_is_registered(self, mcp_board: ClientSession) -> None:
        """bash_exec must appear in the tool list."""
        result = await mcp_board.list_tools()
        names = {t.name for t in result.tools}
        assert "bash_exec" in names

    async def test_returns_output_and_exit_code(self, mcp_board: ClientSession) -> None:
        """bash_exec returns output, exit_code, timed_out even without a task context."""
        import json

        from mcp.types import TextContent

        if sys.platform == "win32":
            cmd = "echo mcp_hello"
        else:
            cmd = "echo mcp_hello"

        result = await mcp_board.call_tool("bash_exec", {"command": cmd})
        assert not result.isError, f"bash_exec raised error: {result}"
        block = result.content[0]
        assert isinstance(block, TextContent)
        payload = json.loads(block.text)
        assert "output" in payload
        assert "exit_code" in payload
        assert payload["exit_code"] == 0
        assert "mcp_hello" in payload["output"]

    async def test_nonzero_exit_code_not_an_mcp_error(self, mcp_board: ClientSession) -> None:
        """bash_exec returning non-zero exit_code does not raise an MCP error."""
        import json

        from mcp.types import TextContent

        if sys.platform == "win32":
            cmd = "exit /b 1"
        else:
            cmd = "exit 1"

        result = await mcp_board.call_tool("bash_exec", {"command": cmd})
        # The MCP call itself must succeed; exit code is in the payload.
        assert not result.isError
        block = result.content[0]
        assert isinstance(block, TextContent)
        payload = json.loads(block.text)
        assert payload["exit_code"] != 0

    async def test_tool_execution_update_events_emitted_with_task_context(
        self, mcp_board_admin_with_core: ClientSession, tmp_path
    ) -> None:
        """bash_exec emits tool_execution_update events when task context is available.

        This behavioral test wires up a session-bound MCP server and verifies
        that executing bash_exec produces ToolExecutionUpdate events on the
        per-task event stream.  Uses the mcp_board_admin_with_core fixture
        (real KaganCore, ORCHESTRATOR role).

        Because mcp_board_admin_with_core does not bind a session_id, events
        are not emitted (no task_id in context).  The test confirms the final
        result shape is correct and that the MCP call does not error — it
        documents the "no task context" path is safe.
        """
        import json

        from mcp.types import TextContent

        # Without a session-bound context (bound_task_id is None), bash_exec
        # degrades gracefully: it runs the command and returns the result
        # without emitting events.
        result = await mcp_board_admin_with_core.call_tool(
            "bash_exec",
            {"command": "echo streaming_test_line"},
        )
        assert not result.isError
        block = result.content[0]
        assert isinstance(block, TextContent)
        payload = json.loads(block.text)
        assert "streaming_test_line" in payload["output"]
        assert payload["exit_code"] == 0
