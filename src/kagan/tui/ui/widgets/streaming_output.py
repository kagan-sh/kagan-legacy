"""Streaming output container for agent conversation display."""

from __future__ import annotations

import contextlib
import re
from collections import OrderedDict
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from acp.schema import PlanEntry
from acp.schema import ToolCall as AcpToolCall
from acp.schema import ToolCallUpdate as AcpToolCallUpdate
from pydantic import ValidationError
from textual import events, on
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Rule, Static

from kagan.core.domain.enums import StreamPhase, StreamRole
from kagan.core.limits import MAX_TOOL_CALLS
from kagan.core.ux_text import normalize_interaction_verbosity, preview_text_for_interaction
from kagan.core.wire.events import (
    AgentCompleted,
    AgentFailed,
    AgentStatus,
    FollowUpDelivered,
    FollowUpQueued,
    JobStarted,
    ReviewRequested,
    StreamChunk,
    ToolExecution,
    WireEvent,
)
from kagan.tui.ui.utils.helpers import WAVE_FRAMES, WAVE_INTERVAL_MS
from kagan.tui.ui.widgets.permission_prompt import PermissionPrompt
from kagan.tui.ui.widgets.plan_approval import PlanApprovalWidget
from kagan.tui.ui.widgets.plan_display import PlanDisplay
from kagan.tui.ui.widgets.streaming_markdown import StreamingMarkdown, UserInput
from kagan.tui.ui.widgets.tool_call import ToolCall

if TYPE_CHECKING:
    import asyncio

    from acp.schema import PermissionOption
    from textual.app import ComposeResult
    from textual.widget import Widget

    from kagan.core.acp.messages import Answer
    from kagan.tui.ui.widgets.plan_approval import PlanTaskLike


# Regex to strip plan/todos XML blocks from response text
XML_BLOCK_PATTERN = re.compile(r"<(todos|plan)>.*?</\1>", re.DOTALL | re.IGNORECASE)

XML_PARTIAL_START = re.compile(r"<(todos|plan)", re.IGNORECASE)
_SCROLL_LIVE_MARGIN = 2
ToolCallKind = Literal[
    "read",
    "edit",
    "delete",
    "move",
    "search",
    "execute",
    "think",
    "fetch",
    "switch_mode",
    "other",
]


class ThinkingIndicator(Static):
    """Animated thinking indicator with wave animation."""

    def __init__(self, label: str = "Thinking...", **kwargs) -> None:
        self._label = label
        super().__init__(f"{WAVE_FRAMES[0]} {label}", **kwargs)
        self._frame_index = 0
        self._timer = None

    def on_mount(self) -> None:
        """Start animation when mounted."""
        self._timer = self.set_interval(WAVE_INTERVAL_MS / 1000, self._next_frame, pause=False)

    def on_unmount(self) -> None:
        """Stop animation when unmounted."""
        if self._timer:
            self._timer.stop()

    def _next_frame(self) -> None:
        """Advance to the next animation frame."""
        self._frame_index = (self._frame_index + 1) % len(WAVE_FRAMES)
        self.update(f"{WAVE_FRAMES[self._frame_index]} {self._label}")


class StreamingOutput(VerticalScroll):
    """Container for streaming agent conversation content."""

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._agent_response: StreamingMarkdown | None = None
        self._agent_thought: StreamingMarkdown | None = None
        self._tool_calls: OrderedDict[str, ToolCall] = OrderedDict()
        self._plan_display: PlanDisplay | None = None
        self._thinking_indicator: ThinkingIndicator | None = None
        self._phase: StreamPhase = StreamPhase.IDLE
        self._xml_buffer: str = ""
        self._last_agent_status: str | None = None
        self._scroll_scheduled: bool = False
        self._unread_events: int = 0
        self._follow_live_stream: bool = True

    @property
    def phase(self) -> StreamPhase:
        return self._phase

    def set_phase(self, phase: StreamPhase) -> None:
        """Set phase."""
        self._phase = phase

    def compose(self) -> ComposeResult:
        yield Static(
            "Waiting for prompt",
            id="stream-current-action",
            classes="stream-current-action confidence-certain",
        )
        with Horizontal(id="stream-live-jump-row", classes="stream-live-jump-row"):
            yield Button("Jump to latest", id="stream-jump-live-btn")

    def on_mount(self) -> None:
        self._sync_live_jump()

    @on(Button.Pressed, "#stream-jump-live-btn")
    def _on_jump_to_live_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_jump_to_live()

    def action_jump_to_live(self) -> None:
        self._follow_live_stream = True
        self._clear_unread()
        self._scroll_to_end(force=True)

    def on_scroll(self, _event: events.Scroll) -> None:
        if self._is_at_live_edge():
            self._follow_live_stream = True
            self._clear_unread()
            return
        self._follow_live_stream = False
        self._sync_live_jump()

    def _interaction_verbosity(self) -> str:
        config = getattr(self.app, "config", None)
        general = getattr(config, "general", None)
        configured = getattr(general, "interaction_verbosity", None)
        return normalize_interaction_verbosity(configured)

    async def post_user_input(self, text: str) -> UserInput:
        """Post user input as a separate widget."""
        widget = UserInput(text)
        self._set_current_action("Queued user request", confidence="certain")
        await self._mount_content(widget)
        return widget

    async def post_thinking_indicator(self, *, label: str = "Thinking...") -> ThinkingIndicator:
        """Mount a thinking indicator, removed when streaming starts."""
        await self._remove_thinking_indicator()
        self._thinking_indicator = ThinkingIndicator(label=label, classes="thinking-indicator")
        self._set_current_action(label, confidence="assumption")
        await self._mount_content(self._thinking_indicator)
        self._phase = StreamPhase.THINKING
        return self._thinking_indicator

    async def clear_thinking_indicator(self, *, phase: StreamPhase | None = None) -> None:
        """Clear thinking indicator and optionally update phase."""
        await self._remove_thinking_indicator()
        if phase is not None:
            self._phase = phase
        elif self._phase == StreamPhase.THINKING:
            self._phase = StreamPhase.IDLE

    async def _remove_thinking_indicator(self) -> None:
        """Remove thinking indicator if present."""
        if self._thinking_indicator is not None:
            await self._thinking_indicator.remove()
            self._thinking_indicator = None

    async def post_response(self, fragment: str = "") -> StreamingMarkdown:
        """Get or create agent response widget.

        Uses a local reference to guard against concurrent nullification of
        ``_agent_response`` by ``post_tool_call`` during the
        ``await self.mount(...)`` yield point.
        """
        await self._remove_thinking_indicator()
        self._agent_thought = None
        self._phase = StreamPhase.STREAMING
        follow_live = self._should_follow_live_stream()
        self._set_current_action("Drafting response", confidence="certain")

        if fragment:
            fragment = self._filter_xml_content(fragment)

        if self._agent_response is None:
            response = StreamingMarkdown(role=StreamRole.RESPONSE)
            self._agent_response = response
            await self.mount(response)
        else:
            response = self._agent_response
        if fragment:
            await response.append_content(fragment)
        self._scroll_to_end(force=follow_live)
        return response

    def _filter_xml_content(self, fragment: str) -> str:
        """Filter XML blocks from fragment, buffering partial tags."""
        combined = self._xml_buffer + fragment
        self._xml_buffer = ""

        combined = XML_BLOCK_PATTERN.sub("", combined)

        match = XML_PARTIAL_START.search(combined)
        if match:
            tag_name = match.group(1).lower()
            close_tag = f"</{tag_name}>"

            close_pos = combined.lower().find(close_tag, match.start())
            if close_pos == -1:
                safe_content = combined[: match.start()]
                self._xml_buffer = combined[match.start() :]
                return safe_content

        return combined

    def flush_xml_buffer(self) -> str:
        """Flush any remaining XML buffer content (call at end of stream).

        Returns any non-XML content that was buffered.
        """
        if not self._xml_buffer:
            return ""

        content = XML_BLOCK_PATTERN.sub("", self._xml_buffer)
        self._xml_buffer = ""

        if XML_PARTIAL_START.match(content):
            return ""

        return content

    async def post_thought(self, fragment: str) -> StreamingMarkdown:
        """Get or create agent thought widget.

        Uses a local reference to guard against concurrent nullification of
        ``_agent_thought`` by ``post_response`` / ``post_tool_call`` during
        the ``await self.mount(...)`` yield point.
        """
        await self._remove_thinking_indicator()
        follow_live = self._should_follow_live_stream()
        self._set_current_action("Reasoning through approach", confidence="assumption")
        if self._agent_thought is None:
            thought = StreamingMarkdown(role=StreamRole.THOUGHT)
            self._agent_thought = thought
            await self.mount(thought)
        else:
            thought = self._agent_thought
        await thought.append_content(fragment)
        self._scroll_to_end(force=follow_live)
        return thought

    async def post_tool_call(
        self,
        tool_id: str,
        title: str,
        kind: ToolCallKind | None = None,
    ) -> ToolCall:
        """Post a tool call notification.

        Idempotent: returns existing widget if tool_id already exists.
        """
        await self._remove_thinking_indicator()
        self._agent_response = None
        self._agent_thought = None
        follow_live = self._should_follow_live_stream()
        action_label = kind or "tool"
        self._set_current_action(f"Running {action_label}: {title}", confidence="certain")

        if not tool_id or tool_id == "unknown":
            tool_id = f"auto-{uuid4().hex[:8]}"
        elif tool_id in self._tool_calls:
            return self._tool_calls[tool_id]

        # Sanitize tool_id for use as widget ID (only letters, numbers, underscores, hyphens)
        sanitized_id = tool_id.replace("/", "-")
        widget_id = f"tool-{sanitized_id}"
        try:
            existing = self.query_one(f"#{widget_id}", ToolCall)
            # Widget exists in DOM but not in our tracking dict - add it back
            self._tool_calls[tool_id] = existing
            return existing
        except NoMatches:
            pass

        tool_data = AcpToolCall(
            toolCallId=tool_id,
            title=title,
            kind=kind,
            status="pending",
        )
        widget = ToolCall(tool_data, id=widget_id)
        self._tool_calls[tool_id] = widget

        while len(self._tool_calls) > MAX_TOOL_CALLS:
            _old_id, old_widget = self._tool_calls.popitem(last=False)
            await old_widget.remove()

        await self.mount(widget)
        self._scroll_to_end(force=follow_live)
        return widget

    async def upsert_tool_call(self, tool_call: AcpToolCall) -> ToolCall:
        """Create or update a tool call widget from full ACP payload."""
        widget = await self.post_tool_call(
            tool_call.tool_call_id,
            tool_call.title or "Tool call",
            tool_call.kind,
        )
        widget.update_tool_call(tool_call)
        self._scroll_to_end()
        return widget

    async def apply_tool_call_update(
        self, update: AcpToolCallUpdate, tool_call: AcpToolCall
    ) -> ToolCall:
        """Apply incremental tool call update while preserving full content."""
        widget = await self.upsert_tool_call(tool_call)
        if update.status:
            widget.update_status(update.status)
        return widget

    def update_tool_status(self, tool_id: str, status: str) -> None:
        """Update a tool call's status."""
        if tool_id in self._tool_calls:
            self._tool_calls[tool_id].update_status(status)

    async def post_note(self, text: str, classes: str = "") -> Widget:
        """Post a simple text note."""
        follow_live = self._should_follow_live_stream()
        widget = Static(text, classes=f"streaming-note {classes}".strip())
        await self.mount(widget)
        self._scroll_to_end(force=follow_live)
        return widget

    async def post_plan(self, entries: list[PlanEntry] | list[dict[str, object]]) -> PlanDisplay:
        """Display agent plan entries."""
        self._agent_thought = None

        normalized = _coerce_plan_entries(entries)

        if self._plan_display is not None:
            self._plan_display.update_entries(normalized)
        else:
            self._plan_display = PlanDisplay(normalized, classes="plan-display")
            await self.mount(self._plan_display)

        self._set_current_action("Reviewing generated plan", confidence="assumption")
        self._scroll_to_end(force=self._should_follow_live_stream())
        return self._plan_display

    async def post_permission_request(
        self,
        options: list[PermissionOption],
        tool_call: AcpToolCall | AcpToolCallUpdate,
        result_future: asyncio.Future[Answer],
        timeout: float = 300.0,
    ) -> PermissionPrompt:
        """Display inline permission prompt widget.

        Args:
            options: Available permission options from agent.
            tool_call: The tool call requesting permission.
            result_future: Future to resolve with user's answer.
            timeout: Timeout in seconds before auto-reject.

        Returns:
            The mounted PermissionPrompt widget.
        """
        await self._remove_thinking_indicator()
        widget = PermissionPrompt(options, tool_call, result_future, timeout)
        self._set_current_action("Waiting for permission response", confidence="needs-validation")
        await self._mount_content(widget)
        widget.focus()
        return widget

    async def post_plan_approval(self, tasks: list[PlanTaskLike]) -> PlanApprovalWidget:
        """Display inline plan approval widget.

        Args:
            tasks: The generated tasks to approve or dismiss.

        Returns:
            The mounted PlanApprovalWidget.
        """
        await self._remove_thinking_indicator()
        widget = PlanApprovalWidget(tasks)
        self._set_current_action("Waiting for plan approval", confidence="needs-validation")
        await self._mount_content(widget)
        widget.focus()
        return widget

    async def post_turn_separator(self) -> Rule:
        """Mount a horizontal divider between conversation turns."""
        rule = Rule(classes="turn-separator")
        await self._mount_content(rule)
        return rule

    async def dispatch_wire_event(self, event: WireEvent) -> bool:
        """Dispatch a Wire event to the appropriate output method.

        Returns True if the event was handled.
        """
        if isinstance(event, StreamChunk):
            if event.text.strip():
                await self.post_response(event.text)
            return True
        if isinstance(event, AgentStatus):
            status = (event.status or "running").strip().lower()
            if status in {"initializing", "running", "thinking"}:
                # Clear loading signal until the first response chunk arrives.
                indicator_label = "Initializing..." if status == "initializing" else "Thinking..."
                await self.post_thinking_indicator(label=indicator_label)
                self._phase = StreamPhase.THINKING
                if status != self._last_agent_status:
                    await self.post_note(event.message or "Agent is thinking…", classes="info")
            elif status == "ready":
                await self.clear_thinking_indicator(phase=StreamPhase.IDLE)
                self._set_current_action("Ready for the next request", confidence="certain")
                if status != self._last_agent_status:
                    await self.post_note(event.message or "Agent ready", classes="success")
            else:
                await self.clear_thinking_indicator(phase=StreamPhase.IDLE)
                self._set_current_action(f"Status update: {status}", confidence="assumption")
                if status != self._last_agent_status:
                    await self.post_note(
                        event.message or f"Agent status: {status}",
                        classes="info",
                    )
            self._last_agent_status = status
            return True
        if isinstance(event, ToolExecution):
            self._set_current_action(f"Tool execution: {event.tool_name}", confidence="certain")
            msg = f"Tool: {event.tool_name}"
            if event.result:
                result_str = str(event.result)[:300]
                msg += f" → {result_str}"
            await self.post_note(msg, classes="info")
            return True
        if isinstance(event, AgentCompleted):
            await self.clear_thinking_indicator(phase=StreamPhase.IDLE)
            self._set_current_action("Run completed", confidence="certain")
            await self.post_note(f"Agent completed: {event.outcome or 'done'}", classes="success")
            return True
        if isinstance(event, AgentFailed):
            await self.clear_thinking_indicator(phase=StreamPhase.IDLE)
            self._set_current_action("Run failed", confidence="needs-validation")
            await self.post_note(f"Agent failed: {event.error}", classes="error")
            return True
        if isinstance(event, JobStarted):
            self._set_current_action("Dispatching background job", confidence="certain")
            await self.post_note(f"Job started: {event.job_id}", classes="info")
            return True
        if isinstance(event, ReviewRequested):
            self._set_current_action("Preparing review request", confidence="certain")
            await self.post_note("Review requested", classes="info")
            return True
        if isinstance(event, FollowUpQueued):
            self._set_current_action("Queued follow-up context", confidence="certain")
            preview = preview_text_for_interaction(
                event.message,
                verbosity=self._interaction_verbosity(),
            )
            await self.post_note(f"Follow-up queued: {preview}", classes="dim")
            return True
        if isinstance(event, FollowUpDelivered):
            self._set_current_action("Delivered follow-up to worker", confidence="certain")
            preview = preview_text_for_interaction(
                event.message,
                verbosity=self._interaction_verbosity(),
            )
            await self.post_note(f"Follow-up delivered: {preview}", classes="success")
            return True
        return False

    def reset_turn(self) -> None:
        """Reset state for a new conversation turn.

        Note: Does NOT clear tool_calls - use clear() for full reset.
        Tool calls from previous turns remain visible in the conversation.
        """
        self._agent_response = None
        self._agent_thought = None
        self._plan_display = None
        self._xml_buffer = ""
        self._phase = StreamPhase.IDLE
        self._set_current_action("Waiting for prompt", confidence="certain")

    async def clear(self) -> None:
        """Clear all content from the container."""
        for widget in self.query(StreamingMarkdown):
            await widget.stop_stream()
        for child in list(self.children):
            if child.id in {"stream-current-action", "stream-live-jump-row"}:
                continue
            await child.remove()
        self._agent_response = None
        self._agent_thought = None
        self._tool_calls.clear()
        self._plan_display = None
        self._thinking_indicator = None
        self._xml_buffer = ""
        self._phase = StreamPhase.IDLE
        self._last_agent_status = None
        self._scroll_scheduled = False
        self._unread_events = 0
        self._follow_live_stream = True
        self._set_current_action("Waiting for prompt", confidence="certain")
        self._sync_live_jump()

    def _is_at_live_edge(self) -> bool:
        try:
            return self.max_scroll_y - self.scroll_y <= _SCROLL_LIVE_MARGIN
        except Exception:
            return True

    def _should_follow_live_stream(self) -> bool:
        if self._scroll_scheduled and self._follow_live_stream:
            return True
        return self._follow_live_stream and self._is_at_live_edge()

    async def _mount_content(self, widget: Widget) -> Widget:
        follow_live = self._should_follow_live_stream()
        await self.mount(widget)
        self._scroll_to_end(force=follow_live)
        return widget

    def _set_current_action(self, action: str, *, confidence: str) -> None:
        normalized_confidence = {
            "certain": "certain",
            "assumption": "assumption",
            "needs-validation": "needs-validation",
        }.get(confidence, "certain")
        text = action
        with contextlib.suppress(NoMatches):
            widget = self.query_one("#stream-current-action", Static)
            widget.update(text)
            widget.set_class(normalized_confidence == "certain", "confidence-certain")
            widget.set_class(normalized_confidence == "assumption", "confidence-assumption")
            widget.set_class(
                normalized_confidence == "needs-validation",
                "confidence-needs-validation",
            )

    def _mark_unread(self) -> None:
        self._unread_events += 1
        self._sync_live_jump()

    def _clear_unread(self) -> None:
        if self._unread_events == 0:
            self._sync_live_jump()
            return
        self._unread_events = 0
        self._sync_live_jump()

    def _sync_live_jump(self) -> None:
        with contextlib.suppress(NoMatches):
            row = self.query_one("#stream-live-jump-row", Horizontal)
            button = self.query_one("#stream-jump-live-btn", Button)
            visible = self._unread_events > 0 and not self._is_at_live_edge()
            row.display = visible
            button.label = (
                f"Jump to latest ({self._unread_events})" if visible else "Jump to latest"
            )

    def _scroll_to_end(self, *, force: bool = False) -> None:
        """Scroll to the bottom of the container."""
        if force:
            self._follow_live_stream = True
        if not force and not self._should_follow_live_stream():
            self._mark_unread()
            return
        if self._scroll_scheduled:
            return
        self._scroll_scheduled = True

        def _do_scroll() -> None:
            self._scroll_scheduled = False
            if self.is_mounted and self._follow_live_stream:
                self.scroll_end(animate=False)
                self._clear_unread()
                return
            self._sync_live_jump()

        self.call_after_refresh(_do_scroll)

    def get_text_content(self) -> str:
        """Extract all text content from the streaming output.

        Returns:
            Combined text content from all child widgets.
        """
        parts: list[str] = []

        for child in self.children:
            if isinstance(child, StreamingMarkdown):
                parts.append(child.content)
            elif isinstance(child, UserInput):
                parts.append(f"> {child._content}")
            elif isinstance(child, ToolCall):
                title = child._tool_call.title
                parts.append(f"[Tool: {title}]")
            elif isinstance(child, PlanDisplay):
                entries = [f"- {e.content}" for e in child._entries]
                if entries:
                    parts.append("Plan:\n" + "\n".join(entries))
            elif isinstance(child, Static) and not isinstance(child, ThinkingIndicator):
                if child.id == "stream-current-action":
                    continue
                # Static notes - get rendered text content
                text = str(child.render())
                if text:
                    parts.append(text)

        return "\n\n".join(parts)


def _coerce_plan_entries(entries: list[PlanEntry] | list[dict[str, object]]) -> list[PlanEntry]:
    normalized: list[PlanEntry] = []
    for entry in entries:
        if isinstance(entry, PlanEntry):
            normalized.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        data = dict(entry)
        data.setdefault("priority", "medium")
        status = data.get("status")
        if status == "failed":
            data["status"] = "completed"
        elif status is None or status not in ("pending", "in_progress", "completed"):
            data["status"] = "pending"
        try:
            normalized.append(PlanEntry.model_validate(data))
        except ValidationError:
            continue
    return normalized
