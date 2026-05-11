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
from typing import TYPE_CHECKING, Any

import acp
from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallProgress, ToolCallStart

from kagan.cli.chat import (
    build_orchestrator_prompt,
    resolve_default_agent_backend,
    run_orchestrator_turn,
    warm_orchestrator_backend,
)
from kagan.core.chat import TurnInProgressError
from kagan.core.chat._turn_display import TurnPhaseTracker
from kagan.core.errors import KaganError
from kagan.core.events import (
    AgentLifecycle,
    AssistantChunk,
    AssistantMessagePersisted,
    Error,
    Event,
    ThinkingChunk,
    ToolCall,
    ToolCallResult,
    ToolCallUpdate,
    TurnEnd,
    TurnStart,
    UsageUpdate,
)
from kagan.core.permission import PermissionRequest
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
    from kagan.core import KaganCore
    from kagan.tui._event_source import HttpEventSource, InProcEventSource
    from kagan.tui.widgets.chat import ChatPanel

# Session key constants shared across kanban, task_screen, and session_dashboard.
TASK_WORKER_SESSION_KEY = "task-worker"
TASK_REVIEWER_SESSION_KEY = "task-reviewer"

# ---------------------------------------------------------------------------
# ChatEvent → ChatPanel translator (engine path)
# ---------------------------------------------------------------------------


def apply_chat_event_to_panel(panel: ChatPanel, event: Event | PermissionRequest) -> None:
    """Translate one :class:`Event` from the engine into ChatPanel calls.

    Mirrors the user-visible status indicators that the legacy ACP-on_update
    path emitted (``set_runtime_status`` / ``set_stream_action``) so screens
    behave identically to phases 1-3.

    ``UsageUpdate`` is rendered as a runtime-status nudge — full token / cost
    UI lands later. ``PermissionRequest`` is consumed in
    :func:`send_chat_message` before this translator runs.
    """
    match event:
        case TurnStart():
            panel._turn_tracker = TurnPhaseTracker()
            panel.set_runtime_status("thinking")
            panel.set_stream_action("Initializing...", confidence="assumption")
        case AssistantChunk():
            panel.set_runtime_status("thinking")
            if panel._turn_tracker is None:
                panel._turn_tracker = TurnPhaseTracker()
            panel._turn_tracker.set_phase("composing")
            panel._turn_tracker.add_text(event.delta)
            panel.set_stream_action(panel._turn_tracker.composing_label(), confidence="certain")
            panel.append_assistant_fragment(event.delta)
        case ThinkingChunk():
            panel.set_runtime_status("thinking")
            if panel._turn_tracker is None:
                panel._turn_tracker = TurnPhaseTracker()
            panel._turn_tracker.set_phase("thinking")
            panel._turn_tracker.add_text(event.delta)
            panel.set_stream_action(panel._turn_tracker.thinking_label(), confidence="assumption")
            panel.append_thought_fragment(event.delta)
        case ToolCall():
            panel.set_runtime_status("thinking")
            panel.upsert_tool_call(
                event.tool_call_id,
                event.title,
                status="running",
                args=event.args,
                kind=event.kind,
            )
            panel.set_stream_action(f"Running tool: {event.title}", confidence="certain")
        case ToolCallUpdate():
            panel.set_runtime_status("thinking")
            panel.update_tool_call(
                event.tool_call_id,
                event.progress or "running",
                result=event.content,
            )
        case ToolCallResult():
            status = "failed" if event.is_error else "completed"
            panel.update_tool_call(event.tool_call_id, status, result=event.output)
        case UsageUpdate():
            panel.set_runtime_status("thinking")
        case AssistantMessagePersisted():
            pass
        case TurnEnd(reason="done"):
            panel._turn_tracker = None
            panel.finish_thought()
            panel.set_runtime_status("ready")
            panel.set_stream_action("Waiting for prompt", confidence="certain")
            panel.increment_turn_count()
        case TurnEnd():
            # cancelled or error
            panel._turn_tracker = None
            panel.finish_thought()
            panel.set_runtime_status("ready")
            panel.set_stream_action("Waiting for prompt", confidence="certain")
        case Error():
            panel.set_runtime_status("error")
            panel.set_stream_action("Orchestrator error", confidence="needs-validation")
            panel.add_system_message(f"Orchestrator error: {event.message}")
        case AgentLifecycle():
            _GLYPH = {"started": "▸", "finished": "✓", "stopped": "◯", "failed": "✗"}
            glyph = _GLYPH.get(event.kind, "·")
            task_ref = f"#{event.task_id[:8]}" if event.task_id else "task"
            if event.kind == "failed":
                detail_suffix = f": {event.detail}" if event.detail else ""
                label = f"failed{detail_suffix}"
            elif event.kind == "finished":
                label = "finished"
            elif event.kind == "stopped":
                label = "stopped"
            else:
                label = event.kind
            panel.add_system_message(f"{glyph} {task_ref} {label}")
        case _:
            pass


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
    # Propagate show_reasoning setting to the streaming panel
    _raw_reasoning = settings.get("chat.show_reasoning", "").strip().lower()
    panel.set_show_reasoning(_raw_reasoning not in {"", "0", "false", "no", "off"})

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
                elif isinstance(event, AssistantChunk):
                    streamed_chunks.append(event.delta)
                if isinstance(event, AssistantMessagePersisted):
                    persisted_response = event.content
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


async def subscribe_session(
    *,
    panel: ChatPanel,
    session_id: str,
    kind: str,
    event_source: HttpEventSource | InProcEventSource,
    from_seq: int = 0,
    stop_after_snapshot: bool = False,
) -> None:
    """Subscribe to session events via ``event_source`` and paint frames onto ``panel``.

    Delegates to ``event_source.subscribe`` — the retry-loop for remote
    connections is handled inside ``HttpEventSource.subscribe``.

    Parameters
    ----------
    panel:
        Target ``ChatPanel`` to receive frame renders.
    session_id:
        Session / task id to subscribe to.
    kind:
        ``"chat"`` or ``"task"``.
    event_source:
        ``InProcEventSource`` or ``HttpEventSource`` obtained from
        ``KaganApp.event_source``.
    from_seq:
        Resume from this sequence number (default 0 = full replay).
    stop_after_snapshot:
        When ``True``, return after the first ``FrameReady`` frame is
        received (useful for tests that want a one-shot replay without
        blocking on the live-tail subscription forever).
    """
    from kagan.tui._frame_reducer import apply_frame

    state: dict = {}
    async for frame in event_source.subscribe(session_id, kind, from_seq):
        frame_type: str = getattr(frame, "type", "")

        if frame_type == "patch":
            op: str = getattr(frame, "op", "")
            value = getattr(frame, "value", None)

            if op == "create":
                text = value.get("text", "") if isinstance(value, dict) else ""
                if text:
                    panel.append_assistant_fragment(text)
            elif op == "append":
                delta = value if isinstance(value, str) else ""
                if delta:
                    panel.append_assistant_fragment(delta)
            elif op == "finalize":
                with contextlib.suppress(Exception):
                    panel.finish_thought()

            state = apply_frame(state, frame)

        elif frame_type == "snapshot":
            state = apply_frame(state, frame)
            # Render snapshot entries to panel
            for entry in sorted(state.values(), key=lambda e: e.idx):
                if entry.text:
                    panel.append_assistant_fragment(entry.text)

        elif frame_type == "ready":
            if stop_after_snapshot:
                return

        elif frame_type == "resume":
            pass  # meta-frame, no entry mutations


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
    "subscribe_session",
    "tool_call_args",
    "tool_call_id",
    "tool_call_kind",
    "tool_call_result",
    "tool_call_status",
    "tool_call_title",
]
