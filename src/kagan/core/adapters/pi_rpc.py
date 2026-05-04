"""Pi-coding-agent JSONL-framed RPC adapter.

Spawns ``npx @mariozechner/pi-coding-agent --mode rpc`` as a subprocess and
translates pi's RPC stdout events into :class:`kagan.core.agent_events.AgentEvent`
instances.

Pi RPC protocol summary:
- Commands to agent:   JSON objects as single lines on stdin, each followed by ``\\n``.
- Events from agent:   JSON objects as single lines on stdout (AgentSessionEvent shape).
- The subprocess does **not** auto-exit after completing a prompt; the caller must
  terminate it explicitly.

Translator mapping (pi event type → AgentEvent variant):
  agent_start           → AgentStart
  agent_end             → AgentEnd
  turn_start            → TurnStart
  turn_end              → TurnEnd
  message_start         → MessageStart  (assistant messages only)
  message_update        → MessageUpdate (text_delta or thinking_delta assistantMessageEvent)
  message_end           → MessageEnd    (assistant messages only)
  tool_execution_start  → ToolExecutionStart
  tool_execution_update → ToolExecutionUpdate
  tool_execution_end    → ToolExecutionEnd
  compaction_start      → CompactionOccurred
  compaction_end        → CompactionOccurred  (ignored — start is sufficient)
  response              → None  (RPC ack frames, not events)
  extension_ui_request  → None  (UI frames not applicable in headless mode)
  *                     → None  (unknown frames are silently discarded)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

from kagan.core._subprocess import resolve_spawn_command
from kagan.core.agent_events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    CompactionOccurred,
    TurnEnd,
    TurnStart,
)
from kagan.core.events_common import (
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
)

__all__ = ["PiRpcClient", "translate_pi_rpc_message"]

# ---------------------------------------------------------------------------
# Per-line byte guard (CWE-770) — same limit as ACP path
# ---------------------------------------------------------------------------
_PI_RPC_MAX_LINE_BYTES: int = 10 * 1024 * 1024  # 10 MB per JSONL line
_PI_RPC_MAX_CUMULATIVE_BYTES: int = 500 * 1024 * 1024  # 500 MB total per session

# Subprocess kill grace period in seconds
_KILL_GRACE_SECONDS: float = 2.0


# ---------------------------------------------------------------------------
# JSONL → AgentEvent translator (split into per-domain helpers for complexity)
# ---------------------------------------------------------------------------

# Dispatcher table: event_type → handler function (populated after helpers are defined).
_TRANSLATOR_DISPATCH: dict[str, Any] = {}


def translate_pi_rpc_message(
    msg: dict[str, Any],
    *,
    session_id: str,
    backend: str = "pi-coding-agent",
) -> AgentEvent | None:
    """Translate a single pi RPC message dict into an :class:`AgentEvent`.

    Returns ``None`` for:
    - RPC ack frames (``type == "response"``)
    - Extension UI frames (``type == "extension_ui_request"``)
    - Unknown or non-event frames
    - Events that cannot be meaningfully represented (e.g. user ``message_start``)

    Args:
        msg:        Parsed JSON dict from a single pi stdout line.
        session_id: Session identifier injected into AgentStart / AgentEnd.
        backend:    Backend name injected into AgentStart / CompactionOccurred.
    """
    event_type = msg.get("type")
    if not isinstance(event_type, str):
        return None
    handler = _TRANSLATOR_DISPATCH.get(event_type)
    if handler is None:
        return None
    return handler(msg, session_id=session_id, backend=backend)


# ---------------------------------------------------------------------------
# Per-domain helper translators
# ---------------------------------------------------------------------------


def _translate_agent_start(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    return AgentStart(session_id=session_id, agent_backend=backend)


def _translate_agent_end(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    return AgentEnd(session_id=session_id, stop_reason="completed")


def _translate_turn_start(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    return TurnStart(turn_index=0)


def _translate_turn_end(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    return TurnEnd(turn_index=0)


def _translate_message_start(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    """pi emits message_start for user, assistant, and toolResult messages.

    Only assistant messages are surfaced as AgentEvents.
    """
    message = msg.get("message")
    if not isinstance(message, dict):
        return None
    if message.get("role") != "assistant":
        return None
    message_id = str(message.get("id") or uuid.uuid4())
    return MessageStart(message_id=message_id)


def _translate_message_update(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    """pi emits message_update only for assistant messages (streaming).

    assistantMessageEvent carries the streaming delta.
    """
    message = msg.get("message")
    if not isinstance(message, dict):
        return None
    ame = msg.get("assistantMessageEvent")
    if not isinstance(ame, dict):
        return None
    delta_type = ame.get("type")
    if delta_type not in {"text_delta", "thinking_delta"}:
        return None
    delta = ame.get("delta", "")
    if not isinstance(delta, str) or not delta:
        return None
    message_id = str(message.get("id") or uuid.uuid4())
    return MessageUpdate(message_id=message_id, delta=delta)


def _translate_message_end(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    message = msg.get("message")
    if not isinstance(message, dict):
        return None
    if message.get("role") != "assistant":
        return None
    message_id = str(message.get("id") or uuid.uuid4())
    full_text = _extract_assistant_text(message)
    return MessageEnd(message_id=message_id, full_text=full_text)


def _translate_tool_start(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    tool_id = str(msg.get("toolCallId") or uuid.uuid4())
    name = str(msg.get("toolName") or "unknown")
    raw_args = msg.get("args")
    args = raw_args if isinstance(raw_args, dict) else None
    return ToolExecutionStart(tool_id=tool_id, name=name, args=args)


def _translate_tool_update(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    tool_id = str(msg.get("toolCallId") or uuid.uuid4())
    partial = msg.get("partialResult")
    partial_str = _result_to_str(partial)
    return ToolExecutionUpdate(tool_id=tool_id, partial_result=partial_str)


def _translate_tool_end(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    tool_id = str(msg.get("toolCallId") or uuid.uuid4())
    is_error = bool(msg.get("isError", False))
    status: str = "error" if is_error else "success"
    result = msg.get("result")
    result_str: str | None = _result_to_str(result) if result is not None else None
    return ToolExecutionEnd(tool_id=tool_id, status=status, result=result_str)  # type: ignore[arg-type]


def _translate_compaction_start(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    return CompactionOccurred(backend=backend)


def _translate_noop(
    msg: dict[str, Any], *, session_id: str, backend: str
) -> AgentEvent | None:
    """Return None for known non-event frames (compaction_end, RPC acks, UI requests)."""
    return None


# Build the dispatch table after all helpers are defined.
_TRANSLATOR_DISPATCH.update(
    {
        "agent_start": _translate_agent_start,
        "agent_end": _translate_agent_end,
        "turn_start": _translate_turn_start,
        "turn_end": _translate_turn_end,
        "message_start": _translate_message_start,
        "message_update": _translate_message_update,
        "message_end": _translate_message_end,
        "tool_execution_start": _translate_tool_start,
        "tool_execution_update": _translate_tool_update,
        "tool_execution_end": _translate_tool_end,
        "compaction_start": _translate_compaction_start,
        # compaction_end: CompactionOccurred was already emitted on start; drop end frame.
        "compaction_end": _translate_noop,
        # RPC ack frames (response to stdin commands) — not events.
        "response": _translate_noop,
        # Extension UI requests — not meaningful in headless mode.
        "extension_ui_request": _translate_noop,
        # Session state change frames — no AgentEvent equivalent.
        "queue_update": _translate_noop,
        "session_info_changed": _translate_noop,
        "thinking_level_changed": _translate_noop,
        "auto_retry_start": _translate_noop,
        "auto_retry_end": _translate_noop,
    }
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_assistant_text(message: dict[str, Any]) -> str:
    """Extract plain text from a pi assistant message content array."""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _result_to_str(result: Any) -> str:
    """Convert a pi tool result (any shape) to a string for ToolExecutionUpdate/End."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "".join(parts)
        # Fallback: JSON-encode the dict
        with contextlib.suppress(Exception):
            return json.dumps(result)
    return str(result)


# ---------------------------------------------------------------------------
# PiRpcClient
# ---------------------------------------------------------------------------


class PiRpcClient:
    """Thin JSONL-framed RPC client for ``npx @mariozechner/pi-coding-agent --mode rpc``.

    Usage::

        async with PiRpcClient(cwd=Path("/my/project")) as client:
            result = await client.prompt(text="say hi", on_update=handler)

    The client spawns the subprocess on ``__aenter__`` and terminates it on
    ``__aexit__``.  Pi's RPC process does **not** auto-exit after completing a
    prompt, so the caller must either use the context manager or call
    :meth:`aclose` explicitly.
    """

    def __init__(
        self,
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        session_id: str | None = None,
    ) -> None:
        self._cwd = cwd
        self._env = env
        self._session_id = session_id or str(uuid.uuid4())
        self._proc: asyncio.subprocess.Process | None = None
        self._cumulative_bytes: int = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> PiRpcClient:
        await self._start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prompt(
        self,
        *,
        text: str,
        on_update: Callable[[AgentEvent], Awaitable[None]] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> str:
        """Send *text* as a prompt; stream JSONL events; return the final assistant text.

        Args:
            text:         The prompt string to send.
            on_update:    Optional async callback invoked for each translated
                          :class:`AgentEvent`.  Called in the order events arrive.
            cancel_event: When set, an abort RPC command is sent and the session
                          is considered aborted.

        Returns:
            The final assembled assistant text (concatenation of all
            ``message_update`` deltas since the last ``message_start``).

        Raises:
            RuntimeError: If the client has not been started or has already been
                          closed.
            AgentError:   On subprocess spawn failure (raised during start).
        """
        if self._proc is None:
            raise RuntimeError(
                "PiRpcClient has not been started — use 'async with' or call _start()"
            )

        final_text = await self._run_prompt(
            text=text,
            on_update=on_update,
            cancel_event=cancel_event,
        )
        return final_text

    async def aclose(self) -> None:
        """Terminate the subprocess gracefully, then forcefully if needed."""
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.returncode is not None:
            return

        with contextlib.suppress(ProcessLookupError, OSError):
            proc.terminate()

        try:
            await asyncio.wait_for(proc.wait(), timeout=_KILL_GRACE_SECONDS)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
            with contextlib.suppress(ProcessLookupError, OSError):
                await proc.wait()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _start(self) -> None:
        """Spawn the pi-coding-agent subprocess in RPC mode."""
        cmd = resolve_spawn_command("npx", "@mariozechner/pi-coding-agent", "--mode", "rpc")
        logger.debug("Spawning pi-coding-agent RPC subprocess: {}", cmd)

        import os

        base_env = dict(os.environ)
        if self._env:
            base_env.update(self._env)

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._cwd),
                env=base_env,
                limit=_PI_RPC_MAX_LINE_BYTES,
            )
        except (FileNotFoundError, PermissionError) as exc:
            raise RuntimeError(
                f"Failed to spawn pi-coding-agent (npx not found or not executable): {exc}"
            ) from exc

        logger.debug("Pi-coding-agent RPC subprocess started, pid={}", self._proc.pid)

    def _send_command(self, cmd: dict[str, Any]) -> None:
        """Write a single JSONL command to the subprocess stdin."""
        if self._proc is None or self._proc.stdin is None:
            return
        line = json.dumps(cmd, ensure_ascii=False) + "\n"
        encoded = line.encode("utf-8")
        self._proc.stdin.write(encoded)

    async def _run_prompt(
        self,
        *,
        text: str,
        on_update: Callable[[AgentEvent], Awaitable[None]] | None,
        cancel_event: asyncio.Event | None,
    ) -> str:
        """Core prompt loop: send command, read events, return final text."""
        assert self._proc is not None

        # Send the prompt command.
        self._send_command({"type": "prompt", "message": text})
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
            await self._proc.stdin.drain()  # type: ignore[union-attr]

        # Accumulate the final assistant response text across messages.
        assembled_text = ""
        # Track current message_id for delta assembly
        current_message_id: str | None = None
        current_message_parts: list[str] = []
        done = False

        async def _poll_cancel() -> None:
            """Monitor cancel_event and send abort if triggered."""
            nonlocal done
            if cancel_event is None:
                return
            await cancel_event.wait()
            if not done:
                with contextlib.suppress(Exception):
                    self._send_command({"type": "abort"})
                    await self._proc.stdin.drain()  # type: ignore[union-attr]

        cancel_task: asyncio.Task[None] | None = None
        if cancel_event is not None:
            cancel_task = asyncio.create_task(_poll_cancel(), name="pi-rpc-cancel-monitor")

        try:
            stdout = self._proc.stdout
            assert stdout is not None

            while not done:
                try:
                    raw_line = await asyncio.wait_for(
                        stdout.readline(),
                        timeout=300.0,  # 5-minute per-line timeout
                    )
                except TimeoutError:
                    logger.warning(
                        "Pi RPC session={} timed out waiting for next event",
                        self._session_id,
                    )
                    break

                if not raw_line:
                    # EOF — subprocess exited
                    logger.debug("Pi RPC session={} stdout EOF", self._session_id)
                    break

                # Byte-counting guard
                self._cumulative_bytes += len(raw_line)
                if self._cumulative_bytes > _PI_RPC_MAX_CUMULATIVE_BYTES:
                    logger.warning(
                        "Pi RPC session={} exceeded cumulative byte limit ({} bytes), aborting",
                        self._session_id,
                        self._cumulative_bytes,
                    )
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    msg: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(
                        "Pi RPC session={} unparseable line (ignored): {!r}",
                        self._session_id,
                        line[:200],
                    )
                    continue

                # Detect done: agent_end signals completion.
                if msg.get("type") == "agent_end":
                    done = True

                # Delta assembly for final text collection
                assembled_text = _update_assembled_text(
                    msg,
                    assembled_text=assembled_text,
                    current_message_id=current_message_id,
                    current_message_parts=current_message_parts,
                )
                # Sync tracking state
                current_message_id, current_message_parts = _track_message_state(
                    msg,
                    current_message_id=current_message_id,
                    current_message_parts=current_message_parts,
                )

                event = translate_pi_rpc_message(
                    msg,
                    session_id=self._session_id,
                    backend="pi-coding-agent",
                )
                if event is not None and on_update is not None:
                    try:
                        await on_update(event)
                    except Exception:
                        logger.opt(exception=True).debug(
                            "Pi RPC on_update callback raised for session={}", self._session_id
                        )
        finally:
            if cancel_task is not None and not cancel_task.done():
                cancel_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_task

        return assembled_text


# ---------------------------------------------------------------------------
# Internal text-assembly helpers (module-level to avoid closure mutation)
# ---------------------------------------------------------------------------


def _update_assembled_text(
    msg: dict[str, Any],
    *,
    assembled_text: str,
    current_message_id: str | None,
    current_message_parts: list[str],
) -> str:
    """Update the assembled assistant text based on the current message."""
    event_type = msg.get("type")
    if event_type == "message_end":
        message = msg.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            if current_message_parts:
                return "".join(current_message_parts)
            return _extract_assistant_text(message)
    return assembled_text


def _track_message_state(
    msg: dict[str, Any],
    *,
    current_message_id: str | None,
    current_message_parts: list[str],
) -> tuple[str | None, list[str]]:
    """Return updated (current_message_id, current_message_parts) after processing msg."""
    event_type = msg.get("type")

    if event_type == "message_start":
        message = msg.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            mid = str(message.get("id") or uuid.uuid4())
            return mid, []

    if event_type == "message_update":
        ame = msg.get("assistantMessageEvent")
        if isinstance(ame, dict) and ame.get("type") in {"text_delta", "thinking_delta"}:
            delta = ame.get("delta", "")
            if isinstance(delta, str) and delta:
                new_parts = list(current_message_parts)
                new_parts.append(delta)
                return current_message_id, new_parts

    if event_type == "message_end":
        message = msg.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            return None, []

    return current_message_id, current_message_parts
