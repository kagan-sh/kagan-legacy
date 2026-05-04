"""kagan.server.mcp.toolsets.bash — Shell command execution MCP tool.

Provides one tool: bash_exec.

bash_exec runs a subprocess command and returns its combined stdout/stderr.
It accepts an optional ``on_update`` keyword-only callback that receives each
stdout line as it is emitted by the subprocess.  When the MCP tool is invoked
from a session-bound context (task_id + session_id available), the tool
automatically wires the callback to emit ``ToolExecutionUpdate`` events on the
per-task event stream so clients can render partial output in real time.

The callback is **opt-in only** — if no task context is available the output
is buffered until the subprocess exits and returned as the final result.

Design notes
- Uses ``asyncio.create_subprocess_exec`` so the event loop is not blocked.
- Stdout and stderr are merged in real time via a ``_merge_streams`` helper.
- Lines are emitted to ``on_update`` as they arrive; the full output is
  assembled and returned unchanged as the final tool result.
- TC001/TC002/TC003 are suppressed per MCP convention (annotations evaluated
  at runtime by the MCP framework).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions
from kagan.server.mcp.toolsets import mcp_error_boundary

# Maximum bytes per stdout/stderr read chunk — prevents runaway buffering on
# pathological subprocess output (e.g. binary data without newlines).
_READ_CHUNK = 4096

# Maximum number of output lines retained for the final result when the
# subprocess produces enormous output.  Lines beyond this limit are still
# forwarded to on_update but are dropped from the assembled return value to
# avoid sending multi-MB strings back through the MCP wire protocol.
_MAX_LINES = 10_000


async def _merge_streams(
    stdout: asyncio.StreamReader,
    stderr: asyncio.StreamReader,
    on_line: Callable[[str], None],
) -> list[str]:
    """Read stdout and stderr concurrently, calling on_line for each line.

    Returns all lines (stdout + stderr interleaved in arrival order) so the
    caller can assemble the final output string.
    """
    lines: list[str] = []
    buf_stdout = b""
    buf_stderr = b""
    overflow = False

    async def _drain(reader: asyncio.StreamReader, buf: bytearray) -> None:
        """Read until EOF, emitting complete lines via on_line."""
        nonlocal overflow
        buffer = bytearray(buf)
        while True:
            try:
                chunk = await reader.read(_READ_CHUNK)
            except Exception:
                break
            if not chunk:
                # Flush remaining bytes as a final line (no trailing newline).
                if buffer:
                    line = buffer.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line:
                        if not overflow:
                            lines.append(line)
                            if len(lines) >= _MAX_LINES:
                                overflow = True
                        on_line(line)
                break
            buffer.extend(chunk)
            while b"\n" in buffer:
                idx = buffer.index(b"\n")
                raw_line = buffer[:idx]
                buffer = buffer[idx + 1 :]
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                if not overflow:
                    lines.append(line)
                    if len(lines) >= _MAX_LINES:
                        overflow = True
                on_line(line)

    await asyncio.gather(
        _drain(stdout, bytearray(buf_stdout)),
        _drain(stderr, bytearray(buf_stderr)),
    )
    return lines


async def run_bash(
    command: str,
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    on_update: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute *command* in a shell, streaming output lines via *on_update*.

    Parameters
    ----------
    command:
        Shell command string passed to ``/bin/sh -c`` (POSIX) or
        ``cmd.exe /c`` (Windows).
    cwd:
        Working directory for the subprocess.  Defaults to the current
        working directory when ``None``.
    timeout:
        Optional wall-clock timeout in seconds.  When exceeded the
        subprocess is killed and the result includes ``timed_out=True``.
    on_update:
        Optional keyword-only callback invoked with each stdout/stderr line
        as it arrives.  Suitable for streaming partial results to callers.

    Returns
    -------
    dict
        ``{"output": str, "exit_code": int, "timed_out": bool}``
    """
    import sys

    if on_update is None:
        on_update = lambda _line: None  # noqa: E731

    if sys.platform == "win32":
        args = ["cmd.exe", "/c", command]
    else:
        args = ["/bin/sh", "-c", command]

    cwd_path = Path(cwd) if cwd else None

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd_path,
    )

    assert proc.stdout is not None
    assert proc.stderr is not None

    timed_out = False
    try:
        lines = await asyncio.wait_for(
            _merge_streams(proc.stdout, proc.stderr, on_update),
            timeout=timeout,
        )
    except TimeoutError:
        timed_out = True
        lines = []
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
    finally:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=5.0)

    exit_code = proc.returncode if proc.returncode is not None else -1
    output = "\n".join(lines)
    return {"output": output, "exit_code": exit_code, "timed_out": timed_out}


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register bash_exec on mcp, filtered by opts."""

    if not is_tool_allowed("bash_exec", opts):
        return

    @mcp.tool()
    @mcp_error_boundary
    async def bash_exec(
        ctx: Context,
        command: str,
        cwd: str | None = None,
        timeout: float | None = 300.0,
    ) -> dict:
        """Execute a shell command and return its combined output.

        Streams each stdout/stderr line as a ``tool_execution_update`` event on
        the per-task event stream when a task context is available (i.e. the
        server was started with a bound session_id linked to a task).

        Parameters
        ----------
        command:
            Shell command string (passed to /bin/sh -c or cmd.exe /c).
        cwd:
            Working directory.  Defaults to the server process cwd.
        timeout:
            Wall-clock timeout in seconds (default 300).  Pass null for no
            limit (use with care on long-running commands).

        Returns
        -------
        ``{"output": str, "exit_code": int, "timed_out": bool}``
        """
        from kagan.server.mcp.server import get_context

        app = get_context(ctx)
        task_id: str | None = app.bound_task_id
        session_id: str | None = app.bound_session_id or app.opts.session_id
        tool_id = f"bash_exec:{uuid.uuid4().hex[:12]}"

        on_update: Callable[[str], None] | None = None

        if task_id is not None and session_id is not None:
            # Emit ToolExecutionStart so consumers can correlate updates.
            await app.client.tasks.events.emit(
                task_id,
                "tool_execution_start",
                {
                    "kind": "tool_execution_start",
                    "tool_id": tool_id,
                    "name": "bash_exec",
                    "args": {"command": command, "cwd": cwd, "timeout": timeout},
                },
                session_id=session_id,
                persist=False,
            )

            # Track in-flight update emits so we can drain them before
            # tool_execution_end ships. Without this, the end event races
            # ahead of late update events, breaking the start→updates→end
            # ordering contract clients depend on. (Greptile P1.)
            pending_emits: list[asyncio.Task[None]] = []

            def _on_update(line: str) -> None:
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
                        logger.debug("bash_exec on_update emit failed: {}", exc)

                try:
                    loop = asyncio.get_running_loop()
                    pending_emits.append(loop.create_task(_emit()))
                except RuntimeError:
                    pass

            on_update = _on_update
        else:
            logger.debug(
                "bash_exec: no task context — output will not be streamed as events"
            )

        result = await run_bash(command, cwd=cwd, timeout=timeout, on_update=on_update)

        if task_id is not None and session_id is not None:
            # Drain in-flight update emits so end is observed AFTER updates.
            if pending_emits:
                await asyncio.gather(*pending_emits, return_exceptions=True)
            status = "success" if result["exit_code"] == 0 else "error"
            await app.client.tasks.events.emit(
                task_id,
                "tool_execution_end",
                {
                    "kind": "tool_execution_end",
                    "tool_id": tool_id,
                    "status": status,
                    "result": result["output"][:500] if result["output"] else None,
                },
                session_id=session_id,
                persist=False,
            )

        return result
