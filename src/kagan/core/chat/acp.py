"""ACP transport seam for ChatEngine.

Defines the ``ACPSessionFactory`` protocol — the boundary between
``ChatEngine`` and the orchestrator agent process. Two strategies exist
historically:

* spawn-per-turn (server): a fresh ACP session per HTTP turn — implemented
  here as :class:`SpawnPerTurnACPFactory`, wrapping
  ``kagan.cli.chat.acp.run_orchestrator_turn``.
* long-lived (CLI REPL): one orchestrator subprocess across many turns —
  will land when the CLI migrates onto the engine in a later phase.

The pure mapping function :func:`acp_update_to_chat_event` translates one ACP
``session_update`` payload into a :class:`ChatEvent`. It mirrors the body of
``server._chat_routes._bridge_acp_update`` minus the side effects.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from loguru import logger

from kagan.core.chat.events import (
    AssistantChunk,
    ChatEvent,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Mirror of the four fields on :class:`events.UsageUpdate`."""

    used: int | None = None
    size: int | None = None
    cost: float | None = None
    cost_currency: str | None = None


@dataclass(frozen=True, slots=True)
class ACPTurnResult:
    """Return value of :meth:`ACPSessionFactory.prompt`."""

    full_response: str
    cancelled: bool
    usage: UsageSnapshot | None = None


@runtime_checkable
class ACPSessionFactory(Protocol):
    """The seam between :class:`ChatEngine` and the underlying ACP transport.

    Implementations own the lifecycle of an ACP session for a single turn.
    They MUST surface every ACP ``session_update`` to ``on_update`` and MUST
    honour ``cancel_event`` (cancelling the in-flight prompt when set).
    """

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Callable[[Any], Awaitable[None]],
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
    ) -> ACPTurnResult: ...


# ---------------------------------------------------------------------------
# Pure ACP -> ChatEvent mapping
# ---------------------------------------------------------------------------


def acp_update_to_chat_event(update: Any) -> ChatEvent | None:
    """Translate one ACP ``session_update`` payload into a :class:`ChatEvent`.

    Pure / side-effect-free — safe to call from any context. Returns ``None``
    for ACP updates that don't have a chat-level analogue (e.g. keepalive).
    Lifted from ``server._chat_routes._bridge_acp_update``.
    """
    from acp.schema import (
        AgentMessageChunk,
        AgentThoughtChunk,
    )
    from acp.schema import ToolCallProgress as ACPToolCallProgress
    from acp.schema import ToolCallStart as ACPToolCallStart
    from acp.schema import UsageUpdate as ACPUsageUpdate

    if isinstance(update, AgentMessageChunk):
        content = getattr(update, "content", None)
        if content and getattr(content, "type", None) == "text":
            text = getattr(content, "text", "") or ""
            if text:
                return AssistantChunk(text=text, thought=False)
        return None

    if isinstance(update, AgentThoughtChunk):
        content = getattr(update, "content", None)
        if content and getattr(content, "type", None) == "text":
            text = getattr(content, "text", "") or ""
            if text:
                return AssistantChunk(text=text, thought=True)
        return None

    if isinstance(update, ACPToolCallStart):
        title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
        tool_id = _coerce_tool_id(update)
        args = _coerce_tool_args(update)
        return ToolCallStart(
            tool_id=tool_id,
            title=str(title),
            kind_hint=getattr(update, "kind", None),
            args=args,
        )

    if isinstance(update, ACPToolCallProgress):
        tool_id = _coerce_tool_id(update)
        status_raw = getattr(update, "status", None)
        status = _normalize_tool_status(status_raw)
        result = _coerce_tool_result(update)
        return ToolCallProgress(tool_id=tool_id, status=status, result=result)

    if isinstance(update, ACPUsageUpdate):
        return UsageUpdate(
            used=getattr(update, "used", None),
            size=getattr(update, "size", None),
            cost=getattr(update, "cost", None),
            cost_currency=getattr(update, "cost_currency", None),
        )

    return None


def _coerce_tool_id(update: Any) -> str:
    raw = (
        getattr(update, "tool_call_id", None)
        or getattr(update, "tool_id", None)
        or getattr(update, "id", None)
    )
    if raw:
        return str(raw)
    title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
    return str(title)


def _coerce_tool_args(update: Any) -> str | None:
    for attr in ("raw_input", "rawInput", "arguments", "args"):
        value = getattr(update, attr, None)
        if value not in (None, ""):
            try:
                return value if isinstance(value, str) else repr(value)
            except (TypeError, ValueError):
                return None
    return None


def _coerce_tool_result(update: Any) -> str | None:
    for attr in ("raw_output", "rawOutput", "result", "output"):
        value = getattr(update, attr, None)
        if value not in (None, ""):
            try:
                return value if isinstance(value, str) else repr(value)
            except (TypeError, ValueError):
                return None
    return None


def _normalize_tool_status(raw: Any) -> str:
    text = str(getattr(raw, "value", raw) or "running").lower()
    if text in {"completed", "done", "success", "succeeded"}:
        return "completed"
    if text in {"failed", "error", "errored"}:
        return "failed"
    return "running"


# ---------------------------------------------------------------------------
# SpawnPerTurnACPFactory — wraps run_orchestrator_turn
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SpawnPerTurnACPFactory:
    """Spawn-per-turn factory: one fresh orchestrator process per ``prompt`` call.

    Mirrors how the server currently runs each HTTP turn. Cancellation is
    honoured by cancelling the underlying ``run_orchestrator_turn`` task when
    ``cancel_event`` fires.

    ``client`` is the :class:`KaganCore` instance — needed by
    ``run_orchestrator_turn`` for settings + project resolution.
    ``default_agent_backend`` is used when callers don't pass one through
    :meth:`prompt`.
    """

    client: Any
    default_agent_backend: str | None = None
    cwd: Path | None = None
    attachments: list[dict[str, str]] | None = None

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Callable[[Any], Awaitable[None]],
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
    ) -> ACPTurnResult:
        from kagan.cli.chat.acp import run_orchestrator_turn

        del session_id  # spawn-per-turn doesn't reuse a session id

        backend = agent_backend or self.default_agent_backend
        if not backend:
            raise ValueError("agent_backend is required (no default configured)")
        prompt_text = _flatten_prompt_blocks(prompt_blocks)

        run_task = asyncio.create_task(
            run_orchestrator_turn(
                self.client,
                prompt=prompt_text,
                agent_backend=backend,
                on_update=on_update,
                attachments=self.attachments,
                cwd=self.cwd,
            )
        )
        cancel_task = asyncio.create_task(cancel_event.wait())

        try:
            done, _pending = await asyncio.wait(
                {run_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            cancel_task.cancel()

        if cancel_task in done and not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("run_orchestrator_turn raised after cancel")
            return ACPTurnResult(full_response="", cancelled=True, usage=None)

        try:
            full_response = run_task.result()
        except asyncio.CancelledError:
            return ACPTurnResult(full_response="", cancelled=True, usage=None)
        return ACPTurnResult(full_response=full_response or "", cancelled=False, usage=None)


def _flatten_prompt_blocks(prompt_blocks: list[Any]) -> str:
    """Render ACP prompt blocks back to text for ``run_orchestrator_turn``.

    ``run_orchestrator_turn`` internally reconstructs system + user blocks; the
    spawn-per-turn shim only needs to forward the user prompt text. Engine
    callers pass plain text in a single block today.
    """
    parts: list[str] = []
    for block in prompt_blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n\n".join(parts)


__all__ = [
    "ACPSessionFactory",
    "ACPTurnResult",
    "SpawnPerTurnACPFactory",
    "UsageSnapshot",
    "acp_update_to_chat_event",
]
