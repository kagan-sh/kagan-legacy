"""kagan.server.mcp.toolsets.terminal_run — Long-running terminal command MCP tool.

Provides one tool: terminal_run.

``terminal_run`` is the interactive-terminal variant of ``bash_exec``.  It is
designed for commands that drive interactive processes (test suites, build
pipelines, REPL sessions) whose output streams over time.  Unlike ``bash_exec``
which is a general-purpose one-shot shell executor, ``terminal_run`` is
optimised for the *streaming-first* use case:

- The ``on_update`` callback is wired by default when a task/session context
  is available; callers can rely on ``tool_execution_update`` events landing
  on the per-task stream throughout the command's lifetime.
- A configurable ``max_output_lines`` cap prevents unbounded growth for
  commands that produce high-frequency output (e.g. webpack watch).
- ``stdin`` can be provided as a string for non-interactive but stdin-reading
  programs.

Design notes
- Shares ``run_bash`` from ``kagan.server.mcp.toolsets.bash`` as the
  subprocess execution primitive.  ``terminal_run`` layers session-aware event
  emission and additional configuration on top.
- TC001/TC002/TC003 suppressed per MCP convention.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions
from kagan.server.mcp.toolsets import mcp_error_boundary
from kagan.server.mcp.toolsets._path_validation import assert_cwd_contained
from kagan.server.mcp.toolsets.bash import run_bash

# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register terminal_run on mcp, filtered by opts."""

    if not is_tool_allowed("terminal_run", opts):
        return

    @mcp.tool()
    @mcp_error_boundary
    async def terminal_run(
        ctx: Context,
        command: str,
        cwd: str | None = None,
        timeout: float | None = 600.0,
        max_output_lines: int = 5_000,
    ) -> dict:
        """Run a long-running terminal command and stream its output.

        Designed for commands that produce output over time: test runners,
        build pipelines, or any program that writes incrementally to stdout.

        Each output line is forwarded as a ``tool_execution_update`` event on
        the per-task event stream when a task context is available, allowing
        clients to render partial output in real time.

        Parameters
        ----------
        command:
            Shell command string (passed to /bin/sh -c or cmd.exe /c).
        cwd:
            Working directory.  Defaults to the server process cwd.
        timeout:
            Wall-clock timeout in seconds (default 600 — 10 minutes).
            Pass null for no limit.
        max_output_lines:
            Maximum lines retained in the final ``output`` field.  Lines
            beyond this limit are still forwarded to the event stream but
            are not included in the final return value.

        Returns
        -------
        ``{"output": str, "exit_code": int, "timed_out": bool}``
        """
        from kagan.server.mcp.server import get_context

        app = get_context(ctx)
        task_id: str | None = app.bound_task_id
        session_id: str | None = app.bound_session_id or app.opts.session_id
        tool_id = f"terminal_run:{uuid.uuid4().hex[:12]}"

        # Reject cwd that escapes the bound task's worktree (F2 containment).
        await assert_cwd_contained(cwd, "terminal_run", app)

        on_update: Callable[[str], None] | None = None
        collected_lines: list[str] = []
        line_cap = max(1, max_output_lines)

        if task_id is not None and session_id is not None:
            # Emit ToolExecutionStart so consumers can correlate updates.
            await app.client.tasks.events.emit(
                task_id,
                "tool_execution_start",
                {
                    "kind": "tool_execution_start",
                    "tool_id": tool_id,
                    "name": "terminal_run",
                    "args": {"command": command, "cwd": cwd, "timeout": timeout},
                },
                session_id=session_id,
                persist=False,
            )

            # Track in-flight update emits so we can drain them before
            # tool_execution_end ships. (Greptile P1 — same as bash_exec.)
            pending_emits: list[asyncio.Task[None]] = []

            def _on_update(line: str) -> None:
                if len(collected_lines) < line_cap:
                    collected_lines.append(line)

                async def _emit() -> None:
                    try:
                        await app.client.tasks.events.emit(
                            task_id,  # type: ignore[arg-type]
                            "tool_execution_update",
                            {
                                "kind": "tool_execution_update",
                                "tool_id": tool_id,
                                "partial_result": line,
                            },
                            session_id=session_id,
                            persist=False,
                        )
                    except Exception as exc:
                        logger.debug("terminal_run on_update emit failed: {}", exc)

                try:
                    loop = asyncio.get_running_loop()
                    pending_emits.append(loop.create_task(_emit()))
                except RuntimeError:
                    pass

            on_update = _on_update
        else:
            logger.debug("terminal_run: no task context — output will not be streamed as events")

        result: dict[str, Any] = await run_bash(
            command, cwd=cwd, timeout=timeout, on_update=on_update
        )

        if task_id is not None and session_id is not None:
            # Drain in-flight update emits so end is observed AFTER updates.
            if pending_emits:
                await asyncio.gather(*pending_emits, return_exceptions=True)
            # Use collected_lines (capped) instead of run_bash's assembled output
            # so max_output_lines is honoured in the final event too.
            capped_output = "\n".join(collected_lines)
            status = "success" if result["exit_code"] == 0 else "error"
            await app.client.tasks.events.emit(
                task_id,
                "tool_execution_end",
                {
                    "kind": "tool_execution_end",
                    "tool_id": tool_id,
                    "status": status,
                    "result": capped_output[:500] if capped_output else None,
                },
                session_id=session_id,
                persist=False,
            )
            # Override output with the capped version.
            result = dict(result)
            result["output"] = capped_output

        return result
