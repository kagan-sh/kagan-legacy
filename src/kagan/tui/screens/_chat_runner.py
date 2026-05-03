"""Shared TUI chat-turn runner — single seam from screens onto ChatEngine.

The four screens that host a :class:`ChatPanel` (kanban, workspace,
task_screen, session_dashboard) all run an orchestrator chat turn the same
way: drive :class:`kagan.core.chat.ChatEngine`, translate the resulting
:class:`ChatEvent` stream onto :class:`ChatPanel` widget calls, and persist
the rendered history through ``app.orchestrator_sessions``.

This module owns that shared path. It also keeps the legacy
``apply_task_chat_event`` translator (task agent ``SessionEvent`` →
``ChatPanel``) and the small payload helpers (``tool_call_*``,
``stream_chunk_*``) used by the task event handler — they used to live in
``kanban_chat.py`` which is gone after R1 phase 4c.

Permission events (``PermissionRequest`` / ``PermissionResolved``) emitted
by the engine are intentionally still no-ops here — the bidirectional
permission flow remains on the legacy ACP path inside
``SpawnPerTurnACPFactory``. Wiring permissions through the engine is
tracked for a follow-up; see the module docstring of
``kagan.core.chat.acp``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, Literal, cast

import acp
from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallProgress, ToolCallStart
from loguru import logger

from kagan.cli.chat import (
    build_orchestrator_prompt,
    resolve_default_agent_backend,
    run_orchestrator_turn,
    warm_orchestrator_backend,
)
from kagan.core.chat import (
    AssistantChunk,
    AssistantMessagePersisted,
    ChatEvent,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnInProgressError,
    TurnStarted,
    UsageUpdate,
)
from kagan.core.chat import (
    ToolCallProgress as ChatToolCallProgress,
)
from kagan.core.chat import (
    ToolCallStart as ChatToolCallStart,
)
from kagan.core.enums import SessionEventType
from kagan.core.errors import KaganError

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx

    from kagan.core import KaganCore
    from kagan.tui.widgets.chat import ChatPanel


_WATCH_RETRY_DELAY = 5.0
_WATCH_EVENT_TAKEOVER = "CHAT_TURN_TERMINATED"

StreamChunkKind = Literal["assistant", "thought", "note", "user"]


# ---------------------------------------------------------------------------
# Tiny payload helpers (lifted from the deleted kanban_chat.py)
# ---------------------------------------------------------------------------


def acp_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("acp")
    return nested if isinstance(nested, dict) else {}


def _content_text(content: object) -> str:
    if isinstance(content, dict):
        if str(content.get("type") or "") != "text":
            return ""
        return str(content.get("text") or "")
    if content is None or getattr(content, "type", None) != "text":
        return ""
    return str(getattr(content, "text", "") or "")


def _serialize_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return str(value)


def stream_chunk_kind(payload: dict[str, Any]) -> StreamChunkKind:
    kind = str(payload.get("kind") or "").strip().lower()
    if kind in {"assistant", "thought", "note", "user"}:
        return cast("StreamChunkKind", kind)
    if payload.get("thought"):
        return "thought"
    session_update = str(acp_payload(payload).get("sessionUpdate") or "").strip().lower()
    if session_update == "agent_thought_chunk":
        return "thought"
    return "assistant"


def stream_chunk_text(payload: object) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for key in ("text", "chunk", "content"):
            text = payload.get(key)
            if isinstance(text, str) and text:
                return text
            if text is not None:
                nested_text = _content_text(text)
                if nested_text:
                    return nested_text
        text = _content_text(acp_payload(payload).get("content"))
        if text:
            return text
        for key in ("error", "details", "reason"):
            if key in payload:
                return str(payload[key])
        if "message" in payload:
            return str(payload["message"])
    return ""


def tool_call_id(payload: dict[str, Any]) -> str:
    nested = acp_payload(payload)
    return str(
        payload.get("id")
        or payload.get("tool_id")
        or nested.get("toolCallId")
        or nested.get("tool_call_id")
        or payload.get("name")
        or "tool"
    )


def _format_tool_name(raw: str) -> str:
    if raw.startswith("toolu_") or raw.startswith("call_"):
        return "tool call"
    if "__" in raw:
        parts = raw.split("__")
        if parts[0] in {"mcp", "functions"} and len(parts) >= 3:
            return " / ".join(parts[1:])
        return " / ".join(parts)
    return raw.replace("_", " ")


def tool_call_title(payload: dict[str, Any]) -> str:
    nested = acp_payload(payload)
    raw = str(
        nested.get("title") or payload.get("name") or payload.get("tool") or tool_call_id(payload)
    )
    return _format_tool_name(raw)


def tool_call_status(payload: dict[str, Any], *, default: str) -> str:
    nested = acp_payload(payload)
    return str(payload.get("status") or nested.get("status") or default)


def tool_call_kind(payload: dict[str, Any]) -> str | None:
    nested = acp_payload(payload)
    return str(nested.get("kind") or payload.get("kind") or "") or None


def tool_call_args(payload: dict[str, Any]) -> str | None:
    nested = acp_payload(payload)
    raw = payload.get("args") or payload.get("rawInput") or nested.get("rawInput")
    return _serialize_value(raw)


def tool_call_result(payload: dict[str, Any]) -> str | None:
    nested = acp_payload(payload)
    return _serialize_value(
        payload.get("result") or payload.get("rawOutput") or nested.get("rawOutput")
    )


# ---------------------------------------------------------------------------
# ChatEvent → ChatPanel translator (engine path)
# ---------------------------------------------------------------------------


def apply_chat_event_to_panel(panel: ChatPanel, event: ChatEvent) -> None:
    """Translate one :class:`ChatEvent` from the engine into ChatPanel calls.

    Mirrors the user-visible status indicators that the legacy ACP-on_update
    path emitted (``set_runtime_status`` / ``set_stream_action``) so screens
    behave identically to phases 1-3.

    ``UsageUpdate`` is rendered as a runtime-status nudge — full token / cost
    UI lands later. ``PermissionRequest`` / ``PermissionResolved`` are
    intentionally no-ops; permissions still flow through the legacy ACP path
    inside ``SpawnPerTurnACPFactory`` (see TODO in ``core/chat/acp.py``).
    """
    if isinstance(event, TurnStarted):
        panel.set_runtime_status("thinking")
        panel.set_stream_action("Initializing...", confidence="assumption")
        return
    if isinstance(event, AssistantChunk):
        panel.set_runtime_status("thinking")
        if event.thought:
            panel.set_stream_action("Reasoning through approach", confidence="assumption")
            panel.append_thought_fragment(event.text)
            return
        panel.set_stream_action("Streaming response", confidence="certain")
        panel.append_assistant_fragment(event.text)
        return
    if isinstance(event, ChatToolCallStart):
        panel.set_runtime_status("thinking")
        panel.upsert_tool_call(
            event.tool_id,
            event.title,
            status="running",
            args=event.args,
            kind=event.kind_hint,
        )
        panel.set_stream_action(f"Running tool: {event.title}", confidence="certain")
        return
    if isinstance(event, ChatToolCallProgress):
        panel.set_runtime_status("thinking")
        panel.update_tool_call(event.tool_id, event.status, result=event.result)
        return
    if isinstance(event, UsageUpdate):
        panel.set_runtime_status("thinking")
        return
    if isinstance(event, AssistantMessagePersisted):
        return
    if isinstance(event, TurnDone):
        panel.set_runtime_status("ready")
        panel.set_stream_action("Waiting for prompt", confidence="certain")
        panel.increment_turn_count()
        return
    if isinstance(event, TurnCancelled):
        panel.set_runtime_status("ready")
        panel.set_stream_action("Waiting for prompt", confidence="certain")
        return
    if isinstance(event, TurnError):
        panel.set_runtime_status("error")
        panel.set_stream_action("Orchestrator error", confidence="needs-validation")
        panel.add_system_message(f"Orchestrator error: {event.message}")
        return


# ---------------------------------------------------------------------------
# Engine-driven orchestrator turn
# ---------------------------------------------------------------------------


async def send_chat_message(
    *,
    core: KaganCore,
    panel: ChatPanel,
    text: str,
    history: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Drive a single orchestrator chat turn through :class:`ChatEngine`.

    Resolves the active chat session id from ``panel.app.orchestrator_sessions``
    (every screen that calls this helper sets the namespace up at startup),
    pushes the user message via ``core.chat.push_user``, then translates the
    streamed :class:`ChatEvent` events onto ``panel`` until the turn ends.

    Returns the updated ``history`` list with the new user/assistant pair
    appended so the caller can persist via ``orchestrator_sessions``.
    """
    settings = await core.settings.get()
    backend = panel.preferred_agent_backend() or resolve_default_agent_backend(settings)
    panel.set_agent_backend(backend)

    app = panel.app
    sessions_ns = getattr(app, "orchestrator_sessions", None)
    chat_session_id = sessions_ns.current_session_id() if sessions_ns is not None else None
    if not chat_session_id:
        panel.set_runtime_status("error")
        panel.set_stream_action("Orchestrator error", confidence="needs-validation")
        panel.add_system_message("No active chat session.")
        return list(history)

    panel.set_runtime_status("initializing")
    panel.set_stream_action("Initializing...", confidence="assumption")
    with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
        await warm_orchestrator_backend(core, agent_backend=backend)

    prompt_text = build_orchestrator_prompt(history, text)

    streamed_chunks: list[str] = []
    persisted_response: str | None = None

    try:
        await core.chat.push_user(chat_session_id, text)
        try:
            async for event in core.chat.stream_assistant(
                chat_session_id,
                prompt_blocks=[acp.text_block(prompt_text)],
                agent_backend=backend,
            ):
                if isinstance(event, AssistantChunk) and not event.thought:
                    streamed_chunks.append(event.text)
                if isinstance(event, AssistantMessagePersisted):
                    persisted_response = event.content
                if isinstance(event, TurnDone) and event.full_response:
                    persisted_response = event.full_response
                apply_chat_event_to_panel(panel, event)
        except TurnInProgressError:
            panel.add_system_message("A turn is already running for this session.")
            return list(history)
    except asyncio.CancelledError:
        raise

    response = persisted_response or "".join(streamed_chunks) or "No response from orchestrator"
    return [*history, ("user", text), ("assistant", response)]


# ---------------------------------------------------------------------------
# Task-bound chat: SessionEvent translator + stream watcher
# ---------------------------------------------------------------------------


def apply_task_chat_event(
    panel: ChatPanel,
    event_type: SessionEventType,
    payload: dict[str, Any],
) -> None:
    """Translate a task agent ``SessionEvent`` payload onto ``panel``.

    Used by the task chat mode (panel attached to a Session row, not a free
    chat session), which streams ``core.tasks.events`` directly. Distinct
    from :func:`apply_chat_event_to_panel`, which dispatches engine
    :class:`ChatEvent` values.
    """
    if event_type == SessionEventType.OUTPUT_CHUNK:
        text = stream_chunk_text(payload)
        if not text:
            return
        kind = stream_chunk_kind(payload)
        panel.set_runtime_status("thinking")
        if kind == "thought":
            panel.set_stream_action("Reasoning through approach", confidence="assumption")
            panel.append_thought_fragment(text)
            return
        panel.set_stream_action("Streaming response", confidence="certain")
        panel.append_assistant_fragment(text)
        return

    if event_type == SessionEventType.TOOL_CALL_START:
        title = tool_call_title(payload)
        panel.set_runtime_status("thinking")
        panel.upsert_tool_call(
            tool_call_id(payload),
            title,
            status=tool_call_status(payload, default="running"),
            args=tool_call_args(payload),
            result=tool_call_result(payload),
            kind=tool_call_kind(payload),
        )
        panel.set_stream_action(f"Running tool: {title}", confidence="certain")
        return

    if event_type == SessionEventType.TOOL_CALL_UPDATE:
        title = tool_call_title(payload)
        panel.set_runtime_status("thinking")
        panel.upsert_tool_call(
            tool_call_id(payload),
            title,
            status=tool_call_status(payload, default="updated"),
            args=tool_call_args(payload),
            result=tool_call_result(payload),
            kind=tool_call_kind(payload),
        )
        panel.set_stream_action(f"Running tool: {title}", confidence="certain")
        return

    if event_type == SessionEventType.AGENT_COMPLETED:
        panel.set_runtime_status("ready")
        panel.set_stream_action("Waiting for prompt", confidence="certain")
        return

    if event_type == SessionEventType.AGENT_FAILED:
        panel.set_runtime_status("error")
        panel.set_stream_action("Agent failed", confidence="needs-validation")
        detail = stream_chunk_text(payload) or "Agent failed"
        panel.add_system_message(detail)
        return

    if event_type == SessionEventType.AGENT_STATUS:
        status_text = str(payload.get("status") or acp_payload(payload).get("status") or "").lower()
        if status_text in {"running", "thinking", "initializing", "pending"}:
            panel.set_runtime_status("thinking")
            panel.set_stream_action("Waiting for task agent response", confidence="assumption")


async def stream_task_chat(
    *,
    core: KaganCore,
    panel: ChatPanel,
    task_id: str,
    is_active: Callable[[], bool],
) -> None:
    async for event in core.tasks.events.stream(task_id):
        if not is_active():
            continue

        payload = event.payload or {}
        apply_task_chat_event(panel, event.event_type, payload)


async def watch_chat_session(
    *,
    session_id: str,
    panel: ChatPanel,
    http_client: httpx.AsyncClient | None,
) -> None:
    """Subscribe to the /watch SSE endpoint for a chat session.

    Delivers a Textual notification when another client takes over the session
    (``CHAT_TURN_TERMINATED`` with ``reason=="takeover"``).

    If ``http_client`` is ``None`` the function returns immediately — the TUI
    runs against a local ``KaganCore`` and has no HTTP connection to the server.
    Retry after ``_WATCH_RETRY_DELAY`` seconds on any connection error.
    """
    if http_client is None:
        return

    watch_url = f"/api/chat/sessions/{session_id}/watch"

    while True:
        try:
            async with http_client.stream("GET", watch_url) as response:
                if response.status_code == 404:
                    logger.debug(
                        "Chat watch endpoint not available for session {}; skipping", session_id
                    )
                    return
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if (
                        event.get("t") == _WATCH_EVENT_TAKEOVER
                        and str(event.get("reason") or "") == "takeover"
                        and panel.is_mounted
                    ):
                        panel.app.notify(
                            "Session taken over by another client. Your turn was interrupted.",
                            severity="warning",
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Chat watch connection lost for session {}: {}", session_id, exc)

        try:
            await asyncio.sleep(_WATCH_RETRY_DELAY)
        except asyncio.CancelledError:
            raise


# Re-export the ACP schema names that older imports referenced via kanban_chat.
__all__ = [
    "AgentMessageChunk",
    "AgentThoughtChunk",
    "ToolCallProgress",
    "ToolCallStart",
    "acp_payload",
    "apply_chat_event_to_panel",
    "apply_task_chat_event",
    "run_orchestrator_turn",
    "send_chat_message",
    "stream_chunk_kind",
    "stream_chunk_text",
    "stream_task_chat",
    "tool_call_args",
    "tool_call_id",
    "tool_call_kind",
    "tool_call_result",
    "tool_call_status",
    "tool_call_title",
    "watch_chat_session",
]
