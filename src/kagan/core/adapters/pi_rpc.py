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
from kagan.core.adapters.pi_rpc_messages import (
    PiAgentEnd,
    PiAgentStart,
    PiCompactionStart,
    PiMessageEnd,
    PiMessageStart,
    PiMessageUpdate,
    PiToolCallEnd,
    PiToolCallStart,
    PiToolCallUpdate,
    PiTurnEnd,
    PiTurnStart,
    parse_pi_rpc_message,
)
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
# JSONL → AgentEvent translator
# ---------------------------------------------------------------------------


def translate_pi_rpc_message(
    raw: dict[str, Any],
    *,
    session_id: str,
    backend: str = "pi-coding-agent",
    turn_index: int = 0,
) -> AgentEvent | None:
    """Translate a single pi RPC message dict into an :class:`AgentEvent`.

    Returns ``None`` for:
    - RPC ack frames (``type == "response"``)
    - Extension UI frames (``type == "extension_ui_request"``)
    - Unknown or non-event frames
    - Events that cannot be meaningfully represented (e.g. user ``message_start``)

    Args:
        raw:        Parsed JSON dict from a single pi stdout line.
        session_id: Session identifier injected into AgentStart / AgentEnd.
        backend:    Backend name injected into AgentStart / CompactionOccurred.
        turn_index: Caller's per-prompt turn counter; used as the TurnStart /
                    TurnEnd index (pi's real protocol carries no turn_index field).
    """
    msg = parse_pi_rpc_message(raw)
    if msg is None:
        return None

    match msg:
        case PiAgentStart():
            return AgentStart(session_id=session_id, agent_backend=backend)

        case PiAgentEnd():
            return AgentEnd(session_id=session_id, stop_reason="completed")

        case PiTurnStart():
            # Pi's real protocol has no turn_index on these frames; use caller counter.
            return TurnStart(turn_index=turn_index)

        case PiTurnEnd():
            return TurnEnd(turn_index=turn_index)

        case PiMessageStart(message=m) if m.role == "assistant":
            return MessageStart(message_id=m.id or str(uuid.uuid4()))

        case PiMessageStart():
            return None  # user / toolResult messages — not surfaced

        case PiMessageUpdate(message=m, assistantMessageEvent=ame):
            if ame is None:
                return None
            if ame.type not in {"text_delta", "thinking_delta"}:
                return None
            if not ame.delta:
                return None
            return MessageUpdate(message_id=m.id or str(uuid.uuid4()), delta=ame.delta)

        case PiMessageEnd(message=m) if m.role == "assistant":
            return MessageEnd(
                message_id=m.id or str(uuid.uuid4()),
                full_text=_extract_assistant_text(m.content),
            )

        case PiMessageEnd():
            return None  # user / toolResult messages — not surfaced

        case PiToolCallStart(toolCallId=tid, toolName=tn, args=a):
            tool_id = str(tid or uuid.uuid4())
            name = str(tn or "unknown")
            args = a if isinstance(a, dict) else None
            return ToolExecutionStart(tool_id=tool_id, name=name, args=args)

        case PiToolCallUpdate(toolCallId=tid, partialResult=partial):
            tool_id = str(tid or uuid.uuid4())
            partial_str = _result_to_str(partial)
            return ToolExecutionUpdate(tool_id=tool_id, partial_result=partial_str)

        case PiToolCallEnd(toolCallId=tid, isError=is_error, result=r):
            tool_id = str(tid or uuid.uuid4())
            status: str = "error" if is_error else "success"
            result_str: str | None = _result_to_str(r) if r is not None else None
            return ToolExecutionEnd(tool_id=tool_id, status=status, result=result_str)  # type: ignore[arg-type]

        case PiCompactionStart():
            return CompactionOccurred(backend=backend)

        case _:
            # Covers: PiCompactionEnd, PiResponseAck, PiExtensionUiRequest,
            # PiQueueUpdate, PiSessionInfoChanged, PiThinkingLevelChanged,
            # PiAutoRetryStart, PiAutoRetryEnd — all known non-event frames.
            return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_assistant_text(content: list[Any]) -> str:
    """Extract plain text from a pi assistant message content array."""
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
        # Per-prompt counters; reset at the start of each _run_prompt so a
        # long-lived client across many prompts doesn't accumulate state.
        self._cumulative_bytes: int = 0
        self._turn_counter: int = 0

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

        # Reset the per-prompt cumulative-bytes counter. Greptile P2: the
        # original counter was initialised once in __init__ and never reset
        # across multiple prompt() calls on a long-lived client, so it would
        # eventually trip the 500 MB ceiling and silently abort processing.
        # The cap is a per-prompt safety bound, not a session-lifetime budget.
        self._cumulative_bytes = 0

        # Increment per-prompt turn counter so TurnStart/TurnEnd events
        # carry meaningful turn_index instead of always 0.
        self._turn_counter += 1

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
                assembled_text, current_message_id, current_message_parts = (
                    _update_assembled_text_state(
                        msg,
                        assembled_text=assembled_text,
                        current_message_id=current_message_id,
                        current_message_parts=current_message_parts,
                    )
                )

                event = translate_pi_rpc_message(
                    msg,
                    session_id=self._session_id,
                    backend="pi-coding-agent",
                    turn_index=self._turn_counter,
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


def _update_assembled_text_state(
    msg: dict[str, Any],
    *,
    assembled_text: str,
    current_message_id: str | None,
    current_message_parts: list[str],
) -> tuple[str, str | None, list[str]]:
    """Return updated ``(assembled_text, message_id, parts)`` after processing *msg*.

    Merges the two separate helpers that existed before the boundary-typing
    sweep so the caller only makes one pass per message.
    """
    event_type = msg.get("type")

    if event_type == "message_start":
        message = msg.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            mid = str(message.get("id") or uuid.uuid4())
            return assembled_text, mid, []

    if event_type == "message_update":
        ame = msg.get("assistantMessageEvent")
        if isinstance(ame, dict) and ame.get("type") in {"text_delta", "thinking_delta"}:
            delta = ame.get("delta", "")
            if isinstance(delta, str) and delta:
                new_parts = list(current_message_parts)
                new_parts.append(delta)
                return assembled_text, current_message_id, new_parts

    if event_type == "message_end":
        message = msg.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            if current_message_parts:
                new_text = "".join(current_message_parts)
            else:
                new_text = _extract_assistant_text(
                    message.get("content") if isinstance(message.get("content"), list) else []
                )
            return new_text, None, []

    return assembled_text, current_message_id, current_message_parts
