"""ACP transport seam for ChatEngine.

Defines the ``ACPSessionFactory`` protocol — the boundary between
``ChatEngine`` and the orchestrator agent process. Two strategies exist
historically:

* spawn-per-turn (server): a fresh ACP session per HTTP turn — implemented by
  :func:`make_spawn_per_turn_acp_factory`, wrapping
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

from kagan.core.events import (
    AssistantChunk,
    Event,
    ThinkingChunk,
    ToolCall,
    ToolCallResult,
    ToolCallUpdate,
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


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """Outcome of a consumer-driven permission resolution.

    Returned from :class:`ACPSessionFactory`'s ``permission_resolver`` callback
    back into the factory, which then translates it into an ACP
    ``RequestPermissionResponse``.
    """

    outcome: str  # one of: allow_once, allow_always, deny, deny_feedback
    feedback: str | None = None


@dataclass(frozen=True, slots=True)
class PermissionRequestPayload:
    """Permission request handed from the factory to the resolver.

    Shape-compatible with :class:`events.PermissionRequest` minus the
    ``future_id`` (the engine assigns that). Carries the ACP ``tool_call`` and
    ``options`` as plain dicts so the resolver doesn't depend on ACP schema.
    """

    tool_call: dict[str, Any]
    options: list[dict[str, Any]]


@runtime_checkable
class ACPSessionFactory(Protocol):
    """The seam between :class:`ChatEngine` and the underlying ACP transport.

    Implementations own the lifecycle of an ACP session for a single turn.
    They MUST surface every ACP ``session_update`` to ``on_update`` and MUST
    honour ``cancel_event`` (cancelling the in-flight prompt when set).

    ``permission_resolver`` (when provided) is invoked when the underlying ACP
    agent issues a ``request_permission`` JSON-RPC call. The factory hands the
    request — already shaped as a :class:`PermissionRequestPayload` — to the
    resolver, awaits a :class:`PermissionDecision`, and translates it back
    into the ACP outcome. When ``None``, factories MUST fall back to their
    historical behaviour (auto-deny for the server, prompt-toolkit modal for
    the legacy CLI).
    """

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Callable[[Any], Awaitable[None]],
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Callable[[PermissionRequestPayload], Awaitable[PermissionDecision]]
        | None = None,
    ) -> ACPTurnResult: ...


# ---------------------------------------------------------------------------
# Pure ACP -> ChatEvent mapping
# ---------------------------------------------------------------------------


def acp_update_to_chat_event(
    update: Any,
    *,
    turn_id: str = "",
    session_id: str = "",
) -> Event | None:
    """Translate one ACP ``session_update`` payload into an :class:`Event`.

    Pure / side-effect-free — safe to call from any context. Returns ``None``
    for ACP updates that don't have a chat-level analogue (e.g. keepalive).
    Lifted from ``server._chat_routes._bridge_acp_update``.

    ``turn_id`` and ``session_id`` are forwarded into the returned events;
    they default to empty strings when called from contexts (e.g. tests) that
    don't have turn-scoped IDs.

    Dispatches on the ``session_update`` literal that every ACP schema type
    carries as its discriminator field.
    """
    import uuid as _uuid

    match getattr(update, "session_update", None):
        case "agent_message_chunk":
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    return AssistantChunk(
                        turn_id=turn_id,
                        session_id=session_id,
                        message_id=_uuid.uuid4().hex,
                        delta=text,
                    )
            return None

        case "agent_thought_chunk":
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    return ThinkingChunk(
                        turn_id=turn_id,
                        session_id=session_id,
                        message_id=_uuid.uuid4().hex,
                        delta=text,
                    )
            return None

        case "tool_call":
            title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
            tool_call_id = _coerce_tool_id(update)
            args = _coerce_tool_args(update)
            return ToolCall(
                turn_id=turn_id,
                session_id=session_id,
                tool_call_id=tool_call_id,
                name=str(getattr(update, "name", None) or title),
                title=str(title),
                kind=getattr(update, "kind", None),
                args=args,
            )

        case "tool_call_update":
            tool_call_id = _coerce_tool_id(update)
            status_raw = getattr(update, "status", None)
            normalized = _normalize_tool_status(status_raw)
            result_text = _coerce_tool_result(update)
            if normalized in ("completed", "failed"):
                return ToolCallResult(
                    tool_call_id=tool_call_id,
                    output=result_text,
                    is_error=normalized == "failed",
                )
            return ToolCallUpdate(
                tool_call_id=tool_call_id,
                content=None,
                progress=normalized,
            )

        case "usage_update":
            return UsageUpdate(
                turn_id=turn_id,
                input=getattr(update, "used", None),
                output=None,
                cached=None,
                cost=getattr(update, "cost", None),
            )

        case _:
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
# Spawn-per-turn factory helper — wraps run_orchestrator_turn
# ---------------------------------------------------------------------------


def make_spawn_per_turn_acp_factory(
    *,
    client: Any,
    default_agent_backend: str | None = None,
    cwd: Path | None = None,
    attachments: list[dict[str, str]] | None = None,
    raw: bool = False,
) -> ACPSessionFactory:
    """Return an ``ACPSessionFactory`` backed by one fresh ACP process per turn.

    The private wrapper exists only because pyrefly cannot prove protocol
    compatibility for dynamic objects with a ``prompt`` attribute. The public
    API is the helper function, and all spawn state lives in this closure.

    When ``raw`` is True, the backend receives user blocks verbatim — no
    orchestrator system prompt and no MCP tools.
    """

    async def prompt(
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Callable[[Any], Awaitable[None]],
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Callable[[PermissionRequestPayload], Awaitable[PermissionDecision]]
        | None = None,
    ) -> ACPTurnResult:
        return await run_spawn_per_turn_acp_prompt(
            client=client,
            default_agent_backend=default_agent_backend,
            cwd=cwd,
            attachments=attachments,
            raw=raw,
            session_id=session_id,
            prompt_blocks=prompt_blocks,
            on_update=on_update,
            cancel_event=cancel_event,
            agent_backend=agent_backend,
            permission_resolver=permission_resolver,
        )

    return _PromptFactory(prompt)


class _PromptFactory:
    """Thin typed wrapper for a closure-backed ``prompt`` function."""

    __slots__ = ("_prompt",)

    def __init__(self, prompt: Callable[..., Awaitable[ACPTurnResult]]) -> None:
        self._prompt = prompt

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Callable[[Any], Awaitable[None]],
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Callable[[PermissionRequestPayload], Awaitable[PermissionDecision]]
        | None = None,
    ) -> ACPTurnResult:
        return await self._prompt(
            session_id=session_id,
            prompt_blocks=prompt_blocks,
            on_update=on_update,
            cancel_event=cancel_event,
            agent_backend=agent_backend,
            permission_resolver=permission_resolver,
        )


async def run_spawn_per_turn_acp_prompt(
    *,
    client: Any,
    default_agent_backend: str | None = None,
    cwd: Path | None = None,
    attachments: list[dict[str, str]] | None = None,
    raw: bool = False,
    session_id: str,
    prompt_blocks: list[Any],
    on_update: Callable[[Any], Awaitable[None]],
    cancel_event: asyncio.Event,
    agent_backend: str | None = None,
    permission_resolver: Callable[[PermissionRequestPayload], Awaitable[PermissionDecision]]
    | None = None,
) -> ACPTurnResult:
    """Run one spawn-per-turn ACP prompt and adapt it to ``ACPTurnResult``."""
    from kagan.cli.chat.acp import run_orchestrator_turn

    del session_id  # spawn-per-turn doesn't reuse a session id

    backend = agent_backend or default_agent_backend
    if not backend:
        raise ValueError("agent_backend is required (no default configured)")
    prompt_text = _flatten_prompt_blocks(prompt_blocks)

    run_task = asyncio.create_task(
        run_orchestrator_turn(
            client,
            prompt=prompt_text,
            agent_backend=backend,
            on_update=on_update,
            attachments=attachments,
            cwd=cwd,
            lightweight=raw,
            permission_resolver=permission_resolver,
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
    "PermissionDecision",
    "PermissionRequestPayload",
    "UsageSnapshot",
    "acp_update_to_chat_event",
    "make_spawn_per_turn_acp_factory",
    "run_spawn_per_turn_acp_prompt",
]
