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

Permission requests are surfaced in :func:`send_chat_message`: ``PermissionRequest``
events wait on :meth:`~kagan.tui.widgets.chat.ChatPanel.await_permission_resolution`
(auto-approving ``mcp__kagan*`` tools like the CLI). ``apply_chat_event_to_panel``
does not render permission prompts — only stream/tool/turn events.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

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
from kagan.core.chat._turn_display import TurnPhaseTracker
from kagan.core.chat.events import PermissionRequest
from kagan.core.errors import KaganError
from kagan.tui.screens._agent_event_presenter import (
    acp_payload,
    present_agent_event,
    render_agent_event_to_chat,
    render_agent_event_to_output,
    stream_chunk_kind,
    stream_chunk_text,
    tool_call_args,
    tool_call_id,
    tool_call_kind,
    tool_call_result,
    tool_call_status,
    tool_call_title,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx

    from kagan.core import KaganCore
    from kagan.tui.widgets.chat import ChatPanel


_WATCH_RETRY_DELAY = 5.0
_WATCH_EVENT_TAKEOVER = "CHAT_TURN_TERMINATED"

# Session key constants shared across kanban, task_screen, and session_dashboard.
TASK_WORKER_SESSION_KEY = "task-worker"
TASK_REVIEWER_SESSION_KEY = "task-reviewer"

# ---------------------------------------------------------------------------
# ChatEvent → ChatPanel translator (engine path)
# ---------------------------------------------------------------------------


def apply_chat_event_to_panel(panel: ChatPanel, event: ChatEvent) -> None:
    """Translate one :class:`ChatEvent` from the engine into ChatPanel calls.

    Mirrors the user-visible status indicators that the legacy ACP-on_update
    path emitted (``set_runtime_status`` / ``set_stream_action``) so screens
    behave identically to phases 1-3.

    ``UsageUpdate`` is rendered as a runtime-status nudge — full token / cost
    UI lands later. ``PermissionRequest`` is consumed in
    :func:`send_chat_message` before this translator runs.
    """
    if isinstance(event, TurnStarted):
        panel._turn_tracker = TurnPhaseTracker()
        panel.set_runtime_status("thinking")
        panel.set_stream_action("Initializing...", confidence="assumption")
        return
    if isinstance(event, AssistantChunk):
        panel.set_runtime_status("thinking")
        if panel._turn_tracker is None:
            panel._turn_tracker = TurnPhaseTracker()
        if event.thought:
            panel._turn_tracker.set_phase("thinking")
            panel._turn_tracker.add_text(event.text)
            panel.set_stream_action(panel._turn_tracker.thinking_label(), confidence="assumption")
            panel.append_thought_fragment(event.text)
            return
        panel._turn_tracker.set_phase("composing")
        panel._turn_tracker.add_text(event.text)
        panel.set_stream_action(panel._turn_tracker.composing_label(), confidence="certain")
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
        panel._turn_tracker = None
        panel.set_runtime_status("ready")
        panel.set_stream_action("Waiting for prompt", confidence="certain")
        panel.increment_turn_count()
        return
    if isinstance(event, TurnCancelled):
        panel._turn_tracker = None
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
                if isinstance(event, PermissionRequest):
                    from kagan.cli.chat._permission_ui import _tool_action_key

                    if _tool_action_key(event.tool_call).startswith("mcp__kagan"):
                        await core.chat.resolve_permission(
                            chat_session_id, event.future_id, outcome="allow_once"
                        )
                    else:
                        await panel.await_permission_resolution(core, chat_session_id, event)
                elif isinstance(event, AssistantChunk) and not event.thought:
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
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Translate a task agent ``SessionEvent`` payload onto ``panel``.

    Used by the task chat mode (panel attached to a Session row, not a free
    chat session), which streams ``core.tasks.events`` directly. Distinct
    from :func:`apply_chat_event_to_panel`, which dispatches engine
    :class:`ChatEvent` values.
    """
    render_agent_event_to_chat(panel, present_agent_event(event_type, payload))


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
    "present_agent_event",
    "render_agent_event_to_output",
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
