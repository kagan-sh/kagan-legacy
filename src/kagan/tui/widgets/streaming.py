import contextlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.events import Click, MouseScrollDown, MouseScrollUp, MouseUp
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import Markdown, Static
from textual.widgets.markdown import MarkdownStream

ChunkKind = Literal["assistant", "thought", "note", "user"]
AgentChunkKind = Literal["assistant", "thought", "note"]
ConfidenceLevel = Literal["certain", "assumption", "needs-validation"]


class UserInputWidget(Horizontal):
    def __init__(self, text: str) -> None:
        super().__init__(classes="user-input")
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static(">", classes="user-input-prompt")
        yield Static(self._text, classes="user-input-content")

    def rendered_text(self) -> str:
        return f"> {self._text}"


class OutputChunk(Markdown):
    def __init__(
        self,
        text: str,
        *,
        kind: AgentChunkKind = "assistant",
        chunk_id: str | None = None,
    ) -> None:
        classes = {
            "assistant": "agent-chunk agent-response",
            "thought": "agent-chunk agent-thought",
            "note": "agent-chunk streaming-note stream-note info",
        }[kind]
        super().__init__(text or None, id=chunk_id, classes=classes)
        self.kind: AgentChunkKind = kind
        self._accumulated_text = text or ""
        self._stream: MarkdownStream | None = None

    @property
    def stream(self) -> MarkdownStream:
        if self._stream is None:
            self._stream = self.get_stream(self)
        return self._stream

    async def append_fragment(self, fragment: str) -> None:
        if not fragment:
            return
        self._accumulated_text = f"{self._accumulated_text}{fragment}"
        await self.stream.write(fragment)

    async def write_fragment(self, fragment: str) -> None:
        if not fragment:
            return
        await self.stream.write(fragment)

    def rendered_text(self) -> str:
        prefix = {
            "assistant": "",
            "thought": "Thinking:",
            "note": "Note:",
        }[self.kind]
        if not self._accumulated_text:
            return prefix
        return f"{prefix} {self._accumulated_text}".strip()


class ToolCallView(Vertical):
    BINDINGS = [
        Binding("enter", "toggle_expand", "Toggle Details", show=False),
        Binding("space", "toggle_expand", "Toggle Details", show=False),
    ]
    can_focus = True
    has_content: var[bool] = var(False, toggle_class="-has-content")
    expanded: var[bool] = var(False, toggle_class="-expanded")

    def __init__(
        self,
        title: str,
        *,
        status: str = "running",
        args: str | None = None,
        result: str | None = None,
        tool_id: str | None = None,
        kind: str | None = None,
    ) -> None:
        super().__init__(classes="tool-call chat-tool-call")
        self.tool_id = tool_id
        self.title = title
        self.status = status
        self.args = args
        self.result = result
        self.kind = kind
        self.has_content = bool((args or "").strip() or (result or "").strip())

    def set_status(self, status: str) -> None:
        self.status = status
        self._refresh()

    def set_result(self, result: str | None) -> None:
        self.result = result
        self.has_content = bool((self.args or "").strip() or (self.result or "").strip())
        self._refresh()

    def compose(self) -> ComposeResult:
        yield Static(
            self._header_line(),
            classes="tool-call-header chat-tool-call-header",
            id="tool-call-header",
        )
        with Vertical(id="tool-content"):
            yield Static(self._details_line(), classes="tool-call-body", id="tool-call-body")

    @on(Click, "#tool-call-header")
    def _on_header_click(self) -> None:
        self.action_toggle_expand()

    def action_toggle_expand(self) -> None:
        if not self.has_content:
            return
        self.expanded = not self.expanded

    def watch_expanded(self, expanded: bool) -> None:
        with contextlib.suppress(NoMatches):
            body = self.query_one("#tool-content", Vertical)
            body.display = expanded

    def on_mount(self) -> None:
        self.watch_expanded(self.expanded)
        self._refresh()

    def _refresh(self) -> None:
        self._apply_status_classes()
        with contextlib.suppress(NoMatches):
            header = self.query_one("#tool-call-header", Static)
            header.update(self._header_line())
            header.set_class(True, "chat-tool-call-header")
            status = self._normalized_status()
            header.set_class(status == "running", "status-running")
            header.set_class(status == "completed", "status-completed")
            header.set_class(status == "failed", "status-failed")
        with contextlib.suppress(NoMatches):
            self.query_one("#tool-call-body", Static).update(self._details_line())

    _STATUS_ALIASES: dict[str, str] = {
        "pending": "running",
        "in_progress": "running",
        "updated": "completed",
        "error": "failed",
    }

    _STATUS_LABELS: dict[str, str] = {
        "running": "running",
        "completed": "done",
        "failed": "failed",
    }

    _KEY_ARG_PRIORITY = (
        "title",
        "name",
        "query",
        "path",
        "command",
        "task_id",
        "pattern",
        "content",
    )

    def _extract_key_arg(self) -> str | None:
        """Extract the first meaningful key argument from args for display."""
        if not self.args:
            return None
        parsed: dict[str, object] | None = None
        with contextlib.suppress(json.JSONDecodeError, ValueError, TypeError):
            obj = json.loads(self.args)
            if isinstance(obj, dict):
                parsed = obj
        if parsed is None:
            return None
        for key in self._KEY_ARG_PRIORITY:
            value = parsed.get(key)
            if value is not None:
                preview = str(value)[:50]
                return f"{key}: {preview}"
        return None

    def _header_line(self) -> str:
        expand = "▼" if self.expanded and self.has_content else ("▶" if self.has_content else "•")
        status = self._normalized_status()
        status_label = self._STATUS_LABELS.get(status, status)
        title = self.title.strip() or (self.tool_id or "tool")
        hint = ""
        if self.has_content:
            hint = " · Enter to collapse" if self.expanded else " · Enter to expand"
        key_arg = self._extract_key_arg()
        if key_arg:
            return f"{expand} {title} ({key_arg}) · {status_label}{hint}"
        return f"{expand} {title} · {status_label}{hint}"

    def _normalized_status(self) -> str:
        raw = self.status.strip().lower() or "running"
        return self._STATUS_ALIASES.get(raw, raw)

    def _apply_status_classes(self) -> None:
        status = self._normalized_status()
        self.set_class(status == "running", "status-running")
        self.set_class(status == "completed", "status-completed")
        self.set_class(status == "failed", "status-failed")

    @staticmethod
    def _truncate(text: str, max_lines: int = 12, max_chars: int = 600) -> str:
        """Truncate long text for display, preserving structure."""
        if len(text) > max_chars:
            text = text[:max_chars] + "\n… (truncated)"
        lines = text.splitlines()
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines]) + "\n… (truncated)"
        return text

    def _details_line(self) -> str:
        details: list[str] = []
        if self.args:
            details.append(f"input\n{self._truncate(self.args)}")
        if self.result:
            details.append(f"output\n{self._truncate(self.result)}")
        return "\n\n".join(details) if details else "No details"


@dataclass
class _Line:
    order: int
    content: str
    key: str | None = None


class StreamingOutput(Vertical):
    BINDINGS = [Binding("G", "jump_to_latest", "Jump to Latest", key_display="Shift+G", show=False)]

    live_follow: var[bool] = var(True)
    unread_count: var[int] = var(0)
    _SCROLL_END_TOLERANCE: float = 1.0
    _PRUNE_HIGH_MARK: int = 150
    _PRUNE_LOW_MARK: int = 100
    _MAX_LINE_HISTORY: int = 150

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._lines: OrderedDict[int, _Line] = OrderedDict()
        self._line_order_by_key: dict[str, int] = {}
        self._line_key_by_widget_id: dict[int, str] = {}
        self._tool_calls: OrderedDict[str, ToolCallView] = OrderedDict()
        self._counter = 0
        self._last_chunk: OutputChunk | None = None
        self._last_chunk_kind: AgentChunkKind | None = None
        self._last_chunk_line_key: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(
            "Waiting for prompt",
            id="stream-current-action",
            classes="stream-current-action chat-stream-current-action confidence-certain",
        )
        with ScrollableContainer(id="streaming-body"):
            yield Vertical(id="streaming-body-content")

    def on_mount(self) -> None:
        self.call_after_refresh(self._scroll_latest)

    def append_text(self, text: str) -> None:
        if not text:
            return
        self.append_chunk(text.rstrip("\n"), kind="assistant", merge=True)

    def append_chunk(
        self,
        text: str,
        *,
        kind: ChunkKind = "assistant",
        merge: bool = False,
    ) -> Widget:
        if merge and self._last_chunk is not None and self._last_chunk_kind == kind:
            if text:
                self._last_chunk._accumulated_text = f"{self._last_chunk._accumulated_text}{text}"
            if self.is_mounted:
                self.call_later(self._last_chunk.write_fragment, text)
            if self._last_chunk_line_key is not None:
                self._push_line(
                    self._last_chunk.rendered_text(),
                    key=self._last_chunk_line_key,
                )
            return self._last_chunk

        chunk = UserInputWidget(text) if kind == "user" else OutputChunk(text, kind=kind)
        line_key = f"chunk:{self._counter + 1}"
        self._push_line(chunk.rendered_text(), key=line_key)
        self._append_widget(chunk, line_key=line_key)
        if isinstance(chunk, OutputChunk):
            self._last_chunk = chunk
            self._last_chunk_kind = cast("AgentChunkKind", kind)
            self._last_chunk_line_key = line_key
        else:
            self._reset_chunk_tracking()
        return chunk

    def post_note(self, text: str) -> Widget:
        return self.append_chunk(text, kind="note")

    def post_user_input(self, text: str) -> Widget:
        return self.append_chunk(text, kind="user")

    def post_thought(self, text: str) -> Widget:
        return self.append_chunk(text, kind="thought")

    def upsert_tool_call(
        self,
        tool_id: str,
        title: str,
        *,
        status: str = "running",
        args: str | None = None,
        result: str | None = None,
        kind: str | None = None,
    ) -> ToolCallView:
        self._reset_chunk_tracking()
        existing = self._tool_calls.get(tool_id)
        if existing is None:
            existing = ToolCallView(
                title,
                status=status,
                args=args,
                result=result,
                tool_id=tool_id,
                kind=kind,
            )
            self._tool_calls[tool_id] = existing
            self._append_widget(existing, line_key=f"tool:{tool_id}")
        else:
            existing.title = title
            existing.status = status
            existing.args = args
            existing.result = result
            if kind is not None:
                existing.kind = kind
            existing.has_content = bool((args or "").strip() or (result or "").strip())
            existing._refresh()

        self._push_line(existing._header_line(), key=f"tool:{tool_id}")
        return existing

    def update_tool_status(self, tool_id: str, status: str, *, result: str | None = None) -> None:
        widget = self._tool_calls.get(tool_id)
        if widget is None:
            return
        widget.set_status(status)
        if result is not None:
            widget.set_result(result)
        self._push_line(widget._header_line(), key=f"tool:{tool_id}")

    def set_current_action(
        self,
        action: str,
        *,
        confidence: ConfidenceLevel = "certain",
    ) -> None:
        current = self.query_one("#stream-current-action", Static)
        current.update(action)
        current.set_class(confidence == "certain", "confidence-certain")
        current.set_class(confidence == "assumption", "confidence-assumption")
        current.set_class(confidence == "needs-validation", "confidence-needs-validation")

    def post_thinking_indicator(self, *, label: str = "Thinking...") -> None:
        self.set_current_action(label, confidence="assumption")

    def clear(self) -> None:
        self._lines.clear()
        self._line_order_by_key.clear()
        self._line_key_by_widget_id.clear()
        content = self.query_one("#streaming-body-content", Vertical)
        for child in list(content.children):
            child.remove()
        self._tool_calls.clear()
        self._counter = 0
        self._reset_chunk_tracking()
        self.live_follow = True
        self.unread_count = 0
        self.set_current_action("Waiting for prompt", confidence="certain")
        self.call_after_refresh(self._scroll_latest)

    def get_text_content(self) -> str:
        return "\n".join(line.content for line in self._lines.values())

    def action_jump_to_latest(self) -> None:
        self._scroll_latest()

    @on(MouseScrollUp, "#streaming-body")
    def _on_stream_scroll_up(self) -> None:
        self.live_follow = False

    @on(MouseScrollDown, "#streaming-body")
    def _on_stream_scroll_down(self) -> None:
        self.call_after_refresh(self._sync_live_follow_from_position)

    @on(MouseUp, "#streaming-body")
    def _on_stream_mouse_up(self) -> None:
        self.call_after_refresh(self._sync_live_follow_from_position)

    def _push_line(self, content: str, *, key: str | None = None) -> None:
        if key is not None:
            existing_order = self._line_order_by_key.get(key)
            if existing_order is not None:
                line = self._lines.get(existing_order)
                if line is not None:
                    line.content = f"{key}::{content}"
                    return
                self._line_order_by_key.pop(key, None)

        self._counter += 1
        line_content = content if key is None else f"{key}::{content}"
        self._lines[self._counter] = _Line(order=self._counter, content=line_content, key=key)
        if key is not None:
            self._line_order_by_key[key] = self._counter

    def _append_widget(self, widget: Widget, *, line_key: str | None = None) -> None:
        body = self.query_one("#streaming-body", ScrollableContainer)
        content = self.query_one("#streaming-body-content", Vertical)
        should_follow = self.live_follow or self._is_near_vertical_end(body)
        if widget.parent is None:
            content.mount(widget)
            if line_key is not None:
                self._line_key_by_widget_id[id(widget)] = line_key
        if should_follow:
            self.call_after_refresh(self._scroll_latest)
            self.call_after_refresh(self._maybe_prune)
            return
        self.live_follow = False
        self.unread_count += 1
        self.call_after_refresh(self._maybe_prune)

    def _maybe_prune(self) -> None:
        content = self.query_one("#streaming-body-content", Vertical)
        child_count = len(content.children)
        if child_count <= self._PRUNE_HIGH_MARK:
            self._trim_line_history()
            return
        excess = child_count - self._PRUNE_LOW_MARK
        to_remove = list(content.children[:excess])
        for child in to_remove:
            line_key = self._line_key_by_widget_id.pop(id(child), None)
            if line_key is not None:
                self._remove_line_by_key(line_key)
            if isinstance(child, ToolCallView) and child.tool_id is not None:
                self._tool_calls.pop(child.tool_id, None)
            if child is self._last_chunk:
                self._reset_chunk_tracking()
            child.remove()
        self._trim_line_history()

    def _remove_line_by_key(self, key: str) -> None:
        order = self._line_order_by_key.pop(key, None)
        if order is None:
            return
        line = self._lines.pop(order, None)
        if line is None:
            return
        if key.startswith("tool:"):
            self._tool_calls.pop(key.removeprefix("tool:"), None)
        if key == self._last_chunk_line_key:
            self._reset_chunk_tracking()

    def _trim_line_history(self) -> None:
        while len(self._lines) > self._MAX_LINE_HISTORY:
            _, line = self._lines.popitem(last=False)
            if line.key is None:
                continue
            self._line_order_by_key.pop(line.key, None)
            if line.key.startswith("tool:"):
                self._tool_calls.pop(line.key.removeprefix("tool:"), None)
            if line.key == self._last_chunk_line_key:
                self._reset_chunk_tracking()

    def _scroll_latest(self) -> None:
        body = self.query_one("#streaming-body", ScrollableContainer)
        body.scroll_end(animate=False)
        self._sync_live_follow_from_position()

    def _sync_live_follow_from_position(self) -> None:
        body = self.query_one("#streaming-body", ScrollableContainer)
        at_end = self._is_near_vertical_end(body)
        self.live_follow = at_end
        if at_end:
            self.unread_count = 0

    def _is_near_vertical_end(self, body: ScrollableContainer) -> bool:
        distance = max(0.0, float(body.max_scroll_y) - float(body.scroll_y))
        return distance <= self._SCROLL_END_TOLERANCE

    def _reset_chunk_tracking(self) -> None:
        self._last_chunk = None
        self._last_chunk_kind = None
        self._last_chunk_line_key = None
