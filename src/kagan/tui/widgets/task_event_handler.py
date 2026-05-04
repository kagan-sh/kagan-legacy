from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from kagan.tui.screens._chat_runner import (
    apply_task_chat_event,
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
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

RefreshCallback = Callable[..., None]


class TaskEventHandler:
    def __init__(
        self,
        *,
        output: StreamingOutput,
        overlay_chat: ChatPanel,
        is_task_chat_mode: Callable[[], bool],
        active_session_id: Callable[[], str | None],
        payload_text: Callable[[Any], str],
        queue_refresh: RefreshCallback,
        set_running: Callable[[bool], None],
        set_status: Callable[[str], None],
        set_usage: Callable[[int | None, int | None, float | None, str | None], None],
    ) -> None:
        self._output = output
        self._overlay_chat = overlay_chat
        self._is_task_chat_mode = is_task_chat_mode
        self._active_session_id = active_session_id
        self._payload_text = payload_text
        self._queue_refresh = queue_refresh
        self._set_running = set_running
        self._set_status = set_status
        self._set_usage = set_usage
        self.event_handlers: dict[str, Callable[[dict[str, Any], str | None], None]] = {
            "output_chunk": self._handle_output_chunk,
            "tool_call_start": self._handle_tool_call_start,
            "tool_call_update": self._handle_tool_call_update,
            "agent_status": self._handle_agent_status,
            "criterion_verdict": self._handle_criterion_verdict,
            "task_status_changed": self._handle_task_status_changed,
            "agent_completed": self._handle_agent_completed,
            "agent_failed": self._handle_agent_failed,
            "merge_completed": self._handle_merge_completed,
            "merge_failed": self._handle_merge_failed,
            "auto_review_started": self._handle_auto_review_started,
        }

    def _matches_active_session(self, event_session_id: str | None) -> bool:
        active_session_id = self._active_session_id()
        if active_session_id is None or event_session_id is None:
            return True
        return active_session_id == event_session_id

    def _maybe_apply_chat_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_session_id: str | None,
    ) -> None:
        if not self._is_task_chat_mode() or not self._matches_active_session(event_session_id):
            return
        with self._overlay_chat.state_only_updates():
            apply_task_chat_event(self._overlay_chat, event_type, payload)

    def _render_stream_chunk(self, payload: dict[str, Any]) -> None:
        text = stream_chunk_text(payload)
        kind = stream_chunk_kind(payload)
        if not text:
            return
        if kind in {"assistant", "thought", "note", "user"}:
            self._output.append_chunk(text, kind=cast("Any", kind), merge=True)
            return
        self._output.append_text(text)

    def _handle_output_chunk(self, payload: dict[str, Any], event_session_id: str | None) -> None:
        self._set_running(True)
        self._render_stream_chunk(payload)
        self._maybe_apply_chat_event(
            "output_chunk",
            payload,
            event_session_id=event_session_id,
        )

    def _handle_tool_call_start(
        self, payload: dict[str, Any], event_session_id: str | None
    ) -> None:
        self._set_running(True)
        self._output.upsert_tool_call(
            tool_call_id(payload),
            tool_call_title(payload),
            status=tool_call_status(payload, default="running"),
            args=tool_call_args(payload),
            result=tool_call_result(payload),
            kind=tool_call_kind(payload),
        )
        self._maybe_apply_chat_event(
            "tool_call_start",
            payload,
            event_session_id=event_session_id,
        )

    def _handle_tool_call_update(
        self, payload: dict[str, Any], event_session_id: str | None
    ) -> None:
        self._output.update_tool_status(
            tool_call_id(payload),
            tool_call_status(payload, default="updated"),
            result=tool_call_result(payload),
        )
        self._maybe_apply_chat_event(
            "tool_call_update",
            payload,
            event_session_id=event_session_id,
        )

    def _handle_agent_status(self, payload: dict[str, Any], event_session_id: str | None) -> None:
        self._maybe_apply_chat_event(
            "agent_status",
            payload,
            event_session_id=event_session_id,
        )
        self._output.post_note(self._payload_text(payload) or "Agent status update")
        usage = payload.get("usage")
        if isinstance(usage, dict):
            self._set_usage(
                usage.get("used"),
                usage.get("size"),
                usage.get("cost"),
                usage.get("cost_currency"),
            )

    def _handle_criterion_verdict(
        self, payload: dict[str, Any], _event_session_id: str | None
    ) -> None:
        verdict = str(payload.get("verdict", "")).upper()
        criterion_index = payload.get("criterion_index")
        if isinstance(criterion_index, int):
            self._output.post_note(f"Criterion {criterion_index + 1}: AI {verdict}")
            return
        self._output.post_note(f"Criterion verdict: AI {verdict}")

    def _handle_task_status_changed(
        self, payload: dict[str, Any], _event_session_id: str | None
    ) -> None:
        self._output.post_note(self._payload_text(payload) or "Task status changed")
        self._queue_refresh(runtime=True)

    def _handle_agent_completed(
        self, payload: dict[str, Any], event_session_id: str | None
    ) -> None:
        self._set_running(False)
        self._set_status("Completed")
        self._maybe_apply_chat_event(
            "agent_completed",
            payload,
            event_session_id=event_session_id,
        )
        self._output.post_note("Agent completed")

    def _handle_agent_failed(self, payload: dict[str, Any], event_session_id: str | None) -> None:
        self._set_running(False)
        self._set_status("Failed")
        self._maybe_apply_chat_event(
            "agent_failed",
            payload,
            event_session_id=event_session_id,
        )
        self._output.post_note(self._payload_text(payload) or "Agent failed")

    def _handle_merge_completed(
        self, payload: dict[str, Any], _event_session_id: str | None
    ) -> None:
        self._output.post_note(self._payload_text(payload) or "Merge completed")

    def _handle_merge_failed(self, payload: dict[str, Any], _event_session_id: str | None) -> None:
        self._output.post_note(self._payload_text(payload) or "Merge failed")

    def _handle_auto_review_started(
        self, payload: dict[str, Any], _event_session_id: str | None
    ) -> None:
        self._set_running(True)
        self._set_status("AI Reviewing...")
        self._output.post_note("Auto-review started")
        self._queue_refresh(runtime=True, review=True)
