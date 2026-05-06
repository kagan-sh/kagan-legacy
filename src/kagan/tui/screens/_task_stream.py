from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from textual import on
from textual.css.query import NoMatches
from textual.widgets import TabbedContent

from kagan.core.enums import TaskStatus
from kagan.core.errors import KaganError
from kagan.tui.screens._chat_runner import (
    acp_payload,
    stream_chunk_kind,
    stream_chunk_text,
    tool_call_args,
    tool_call_id,
    tool_call_kind,
    tool_call_result,
    tool_call_status,
    tool_call_title,
)
from kagan.tui.widgets.streaming import OutputChunk, StreamingOutput, ToolCallView, UserInputWidget
from kagan.tui.widgets.task_detail_pane import TaskDetailPane
from kagan.tui.widgets.task_event_handler import TaskEventHandler

if TYPE_CHECKING:
    from textual.widget import Widget


TASK_SCREEN_REPLAY_EVENT_LIMIT = 400


class _TaskStreamMixin:
    def _ensure_stream_worker(self) -> None:
        if self._stream_task is not None and not self._stream_task.done():
            return
        if self._task_id is None:
            return
        self._stream_task = asyncio.create_task(self._stream_events(self._task_id))

    def _maybe_apply_chat_event(
        self, overlay_chat: Any, event_type: str, payload: dict[str, Any]
    ) -> None:
        """Apply chat event if in task chat mode."""
        from kagan.core.enums import ChatMode
        from kagan.tui.screens._chat_runner import apply_task_chat_event

        if self._chat_mode == ChatMode.TASK:
            apply_task_chat_event(overlay_chat, event_type, payload)

    async def _stream_events(self, task_id: str) -> None:
        output = self._output_stream()
        overlay_chat = self._overlay_panel()
        from kagan.core.enums import ChatMode

        detail_pane = self.query_one(TaskDetailPane)
        event_handler = TaskEventHandler(
            output=output,
            overlay_chat=overlay_chat,
            is_task_chat_mode=lambda: self._chat_mode == ChatMode.TASK,
            active_session_id=self._active_stream_session_id,
            payload_text=self._payload_text,
            queue_refresh=self._queue_stream_refresh,
            set_running=self._set_running,
            set_status=self._set_status,
            set_usage=lambda context_used, context_size, cost_amount, cost_currency: (
                detail_pane.agent_status_panel.set_usage_info(
                    context_used, context_size, cost_amount, cost_currency
                )
            ),
        )
        self._replay_count = 0
        self._oldest_event_ts = None
        try:
            async for event in self.kagan_app.core.tasks.events.stream(
                task_id,
                replay_limit=TASK_SCREEN_REPLAY_EVENT_LIMIT,
            ):
                self._replay_count += 1
                if self._oldest_event_ts is None and event.created_at:
                    from kagan.core import utc_iso

                    self._oldest_event_ts = utc_iso(event.created_at)
                if self._replay_count == TASK_SCREEN_REPLAY_EVENT_LIMIT:
                    output.show_load_more_bar()
                self._track_session_event(event.event_type, event.session_id)
                active_session_id = self._active_stream_session_id()
                if event.session_id and active_session_id and event.session_id != active_session_id:
                    continue
                payload = event.payload or {}
                handler = event_handler.event_handlers.get(event.event_type)
                if handler is not None:
                    handler(payload, event.session_id)
                if self._should_refresh_after_event(event.event_type):
                    self._queue_stream_refresh(workspace=True, review=True)
        except asyncio.CancelledError:
            raise
        except (KaganError, NoMatches, AttributeError, OSError, RuntimeError) as exc:
            self._running = False
            self._set_status("Failed")
            output.post_note(f"Stream ended unexpectedly: {exc}")

    def _set_running(self, running: bool) -> None:
        self._running = running

    @staticmethod
    def _should_refresh_after_event(event_type: str) -> bool:
        return event_type in {
            "output_chunk",
            "tool_call_start",
            "tool_call_update",
            "criterion_verdict",
            "agent_completed",
            "agent_failed",
            "task_status_changed",
            "auto_review_started",
        }

    def _output_stream(self) -> StreamingOutput:
        return self._overlay_panel().stream_output()

    def _active_stream_session_id(self) -> str | None:
        source = self._effective_stream_source()
        if source == "reviewer":
            return self._reviewer_session_id
        return self._worker_session_id

    def _track_session_event(self, event_type: str, event_session_id: str | None) -> None:
        if event_type == "auto_review_started":
            self._pending_reviewer_session_id = True
            return
        if event_session_id is None:
            return
        if self._pending_reviewer_session_id:
            self._reviewer_session_id = event_session_id
            self._pending_reviewer_session_id = False
            return
        if self._effective_stream_source() == "reviewer" and self._reviewer_session_id is None:
            self._reviewer_session_id = event_session_id
            return
        if self._worker_session_id is None:
            self._worker_session_id = event_session_id
            return
        if self._worker_session_id != event_session_id and self._reviewer_session_id is None:
            self._reviewer_session_id = event_session_id

    @on(StreamingOutput.LoadMore)
    async def _on_load_more(self) -> None:
        if self._task_id is None or self._oldest_event_ts is None:
            return
        output = self._output_stream()
        output.hide_load_more_bar()

        older_events = await self.kagan_app.core.tasks.events.list_before(
            self._task_id,
            before=self._oldest_event_ts,
            limit=200,
        )
        if not older_events:
            return

        if older_events[0].created_at:
            from kagan.core import utc_iso

            self._oldest_event_ts = utc_iso(older_events[0].created_at) or self._oldest_event_ts

        active_session_id = self._active_stream_session_id()
        widgets: list[Widget] = []
        filtered_events = [
            event
            for event in older_events
            if not (
                event.session_id and active_session_id and event.session_id != active_session_id
            )
        ]
        for event in filtered_events:
            payload = event.payload or {}
            match event.event_type:
                case "output_chunk":
                    text = stream_chunk_text(payload)
                    kind = stream_chunk_kind(payload)
                    if text and kind in {"assistant", "thought", "note", "user"}:
                        if kind == "user":
                            widgets.append(UserInputWidget(text))
                        else:
                            widgets.append(OutputChunk(text, kind=kind))
                case "tool_call_start":
                    widgets.append(
                        ToolCallView(
                            tool_call_title(payload),
                            status=tool_call_status(payload, default="running"),
                            args=tool_call_args(payload),
                            result=tool_call_result(payload),
                            tool_id=tool_call_id(payload),
                            kind=tool_call_kind(payload),
                        )
                    )
                case "agent_completed":
                    widgets.append(OutputChunk("Agent completed", kind="note"))
                case "agent_failed":
                    widgets.append(
                        OutputChunk(stream_chunk_text(payload) or "Agent failed", kind="note")
                    )
                case "task_status_changed":
                    widgets.append(
                        OutputChunk(
                            stream_chunk_text(payload) or "Task status changed", kind="note"
                        )
                    )
                case _:
                    continue

        if widgets:
            output.prepend_widgets(widgets)

        if len(filtered_events) >= 200:
            output.show_load_more_bar()

    def _payload_text(self, payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            text = stream_chunk_text(payload)
            if text:
                return text
            nested = acp_payload(payload)
            if nested:
                if "title" in nested:
                    return str(nested["title"])
                if "status" in nested and "sessionUpdate" in nested:
                    return str(nested["status"])
            if "message" in payload:
                return str(payload["message"])
            pieces = [f"{key}={value}" for key, value in payload.items()]
            return " ".join(pieces)
        return str(payload)

    def _schedule_runtime_refresh(self) -> None:
        if not self.is_mounted:
            return
        self._queue_stream_refresh(runtime=True)

    def _queue_stream_refresh(
        self,
        *,
        runtime: bool = False,
        workspace: bool = False,
        review: bool = False,
    ) -> None:
        if not self.is_mounted:
            return
        self._pending_runtime_refresh = self._pending_runtime_refresh or runtime
        self._pending_workspace_refresh = self._pending_workspace_refresh or workspace
        self._pending_review_refresh = self._pending_review_refresh or review
        if self._stream_refresh_timer is not None:
            return
        self._stream_refresh_timer = self.set_timer(0.12, self._flush_stream_refresh)

    def _flush_stream_refresh(self) -> None:
        self._stream_refresh_timer = None
        runtime = self._pending_runtime_refresh
        workspace = self._pending_workspace_refresh
        review = self._pending_review_refresh
        self._pending_runtime_refresh = False
        self._pending_workspace_refresh = False
        self._pending_review_refresh = False
        if not self.is_mounted:
            return
        if runtime:
            self.run_worker(
                self._refresh_runtime_state,
                group="task-screen-runtime-refresh",
                exclusive=True,
                exit_on_error=False,
            )
        if workspace:
            self.run_worker(
                self._hydrate_workspace_panels,
                group="task-screen-hydrate-stream",
                exclusive=True,
                exit_on_error=False,
            )
        if review:
            self.run_worker(
                self._load_review_context,
                group="task-screen-review-hydrate-stream",
                exclusive=True,
                exit_on_error=False,
            )

    def _maybe_auto_switch_to_review(self) -> None:
        if self._user_switched_tab:
            return
        if self._task_model is not None and self._task_model.status is TaskStatus.REVIEW:
            with contextlib.suppress(NoMatches):
                tabs = self.query_one("#ts-tabs", TabbedContent)
                if getattr(tabs, "active", "") != "review":
                    tabs.active = "review"

    async def _refresh_runtime_state(self) -> None:
        if self._task_id is None:
            return
        with contextlib.suppress(KaganError):
            latest = await self.kagan_app.core.tasks.get(self._task_id)
            self._task_model = latest
            self._refresh_header()
            self._refresh_header_labels()
            self._sync_action_bar()
            self._maybe_auto_switch_to_review()
            await self._load_review_context()
            await self._hydrate_workspace_panels()
