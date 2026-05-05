import asyncio
import contextlib
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.events import Click, MouseScrollDown, MouseScrollUp, MouseUp, Resize
from textual.message import Message
from textual.reactive import var
from textual.widget import Widget
from textual.widgets import Markdown, Static
from textual.widgets.markdown import MarkdownStream

from kagan.tui._osc8 import file_link
from kagan.tui.keybindings import (
    STREAMING_TIMELINE_BINDINGS,
    TOOL_CALL_VIEW_BINDINGS,
    USER_INPUT_BINDINGS,
)
from kagan.tui.widgets._mention_links import linkify_mentions

ChunkKind = Literal["assistant", "thought", "note", "user"]
AgentChunkKind = Literal["assistant", "thought", "note"]
ConfidenceLevel = Literal["certain", "assumption", "needs-validation"]

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_STREAM_WORD_RE = re.compile(r"\S+\s*|\s+")
_DEFAULT_WORD_DELAY_SECONDS = 0.012


def _sanitize_stream_text(text: str) -> str:
    normalized_newlines = text.replace("\r\n", "\n").replace("\r", "\n")
    without_ansi = _ANSI_ESCAPE_RE.sub("", normalized_newlines)
    return _CONTROL_CHARS_RE.sub("", without_ansi)


class UserInputWidget(Horizontal):
    BINDINGS = [*USER_INPUT_BINDINGS]
    can_focus = True

    def __init__(self, text: str) -> None:
        super().__init__(classes="user-input")
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static(">", classes="user-input-prompt")
        yield Static(self._text, classes="user-input-content")

    def rendered_text(self) -> str:
        return f"> {self._text}"

    def action_open_actions(self) -> None:
        from kagan.tui.screens.message_actions_modal import MessageActionsModal
        from kagan.tui.widgets.chat import ChatPanel

        def _handle_result(result: str | None) -> None:
            if result == "edit_resend":
                self.post_message(ChatPanel.EditResendRequested(text=self._text))

        self.app.push_screen(MessageActionsModal(self._text), _handle_result)


class OutputChunk(Markdown):
    can_focus = True

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
        self._pending_fragments: asyncio.Queue[str] = asyncio.Queue()
        self._drain_task: asyncio.Task[None] | None = None
        self.word_delay_seconds = _DEFAULT_WORD_DELAY_SECONDS

    @property
    def stream(self) -> MarkdownStream:
        if self._stream is None:
            self._stream = self.get_stream(self)
        return self._stream

    async def append_fragment(self, fragment: str) -> None:
        if not fragment:
            return
        self._accumulated_text = f"{self._accumulated_text}{fragment}"
        await self._write_animated(fragment)

    async def write_fragment(self, fragment: str) -> None:
        if not fragment:
            return
        await self._write_animated(fragment)

    def stream_fragment(self, fragment: str, *, delay: float | None = None) -> None:
        if not fragment:
            return
        self._accumulated_text = f"{self._accumulated_text}{fragment}"
        if delay is not None:
            self.word_delay_seconds = max(0.0, delay)
        if self.is_mounted or self.parent is not None:
            self._pending_fragments.put_nowait(fragment)
            self._ensure_drain_task()
        else:
            self.update(self._accumulated_text)

    def on_mount(self) -> None:
        if not self._pending_fragments.empty():
            self._ensure_drain_task()

    def _ensure_drain_task(self) -> None:
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain_fragments())

    async def _drain_fragments(self) -> None:
        while not self._pending_fragments.empty():
            fragment = await self._pending_fragments.get()
            await self._write_animated(fragment)

    async def _write_animated(self, fragment: str) -> None:
        for token in _STREAM_WORD_RE.findall(fragment):
            if not token:
                continue
            await self.stream.write(token)
            if self.word_delay_seconds > 0:
                await asyncio.sleep(self.word_delay_seconds)

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
    BINDINGS = [*TOOL_CALL_VIEW_BINDINGS]
    can_focus = True
    has_content: var[bool] = var(False, toggle_class="-has-content")
    expanded: var[bool] = var(False, toggle_class="-expanded")
    _MAX_DETAILS_HEIGHT = 15

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
            markup=False,
        )
        with ScrollableContainer(id="tool-content"):
            yield Static(
                self._details_line(),
                classes="tool-call-body",
                id="tool-call-body",
                markup=False,
            )

    @on(Click, "#tool-call-header")
    def _on_header_click(self) -> None:
        self.action_toggle_expand()

    def action_toggle_expand(self) -> None:
        if not self.has_content:
            return
        self.expanded = not self.expanded

    def watch_expanded(self, expanded: bool) -> None:
        with contextlib.suppress(NoMatches):
            body = self.query_one("#tool-content", ScrollableContainer)
            body.display = expanded
        if expanded:
            self.call_after_refresh(self._scroll_into_view_then_sync)
        self._sync_content_bounds()
        self.call_after_refresh(self._sync_content_bounds)

    def on_mount(self) -> None:
        self.watch_expanded(self.expanded)
        self._refresh()
        self._sync_content_bounds()
        self.call_after_refresh(self._sync_content_bounds)

    def on_resize(self, _: Resize) -> None:
        self._sync_content_bounds()
        self.call_after_refresh(self._sync_content_bounds)

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
        self._sync_content_bounds()

    def _sync_content_bounds(self) -> None:
        with contextlib.suppress(NoMatches):
            body = self.query_one("#tool-content", ScrollableContainer)
            bounded_height = self._bounded_details_height()
            body.styles.max_height = str(bounded_height)
            if self.expanded and self.has_content:
                body.styles.height = str(bounded_height)
            else:
                body.styles.height = "auto"
            body.refresh(layout=True)
        if self.parent is not None:
            self.parent.refresh(layout=True)

    def _scroll_into_view_then_sync(self) -> None:
        self.scroll_visible(animate=False)
        self._sync_content_bounds()

    def _bounded_details_height(self) -> int:
        viewport = self._streaming_viewport_region()
        header_bottom = self._header_bottom_y()
        if viewport is None or header_bottom is None:
            return 1
        viewport_bottom = int(viewport.y + viewport.height)
        allowed = max(1, viewport_bottom - header_bottom)
        return min(self._MAX_DETAILS_HEIGHT, allowed)

    def _streaming_viewport_region(self):
        parent = self.parent
        while parent is not None:
            if isinstance(parent, ScrollableContainer):
                return parent.region if int(parent.region.height) > 0 else None
            parent = parent.parent
        return None

    def _header_bottom_y(self) -> int | None:
        with contextlib.suppress(NoMatches):
            header = self.query_one("#tool-call-header", Static)
            return int(header.region.y + header.region.height)
        return None

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

    def _extract_key_arg(self) -> tuple[str, str] | None:
        """Return the (key, raw_value) of the most significant tool argument.

        Returns None when args are absent or unparseable.
        """
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
                return key, str(value)
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
            key, value = key_arg
            # Render file paths as clickable OSC 8 hyperlinks when supported.
            label = value[:50]
            display_value = file_link(value, label) if key == "path" else label
            return f"{expand} {title} ({key}: {display_value}) · {status_label}{hint}"
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
    BINDINGS = [*STREAMING_TIMELINE_BINDINGS]

    class LoadMore(Message):
        pass

    live_follow: var[bool] = var(True)
    unread_count: var[int] = var(0)
    _SCROLL_END_TOLERANCE: float = 1.0
    _PRUNE_HIGH_MARK: int = 150
    _PRUNE_LOW_MARK: int = 100
    _MAX_LINE_HISTORY: int = 150

    def __init__(
        self,
        *,
        id: str | None = None,
        classes: str | None = None,
        github_repo_slug: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._github_repo_slug: str | None = github_repo_slug
        self._lines: OrderedDict[int, _Line] = OrderedDict()
        self._line_order_by_key: dict[str, int] = {}
        self._line_key_by_widget_id: dict[int, str] = {}
        self._tool_calls: OrderedDict[str, ToolCallView] = OrderedDict()
        self._counter = 0
        self._last_chunk: OutputChunk | None = None
        self._last_chunk_kind: AgentChunkKind | None = None
        self._last_chunk_line_key: str | None = None
        self._scroll_scheduled = False
        self.word_delay_seconds = _DEFAULT_WORD_DELAY_SECONDS

    def compose(self) -> ComposeResult:
        yield Static(
            "Waiting for prompt",
            id="stream-current-action",
            classes="stream-current-action chat-stream-current-action confidence-certain",
        )
        with ScrollableContainer(id="streaming-body"):
            with Vertical(id="streaming-body-content"):
                yield Static(
                    "Load earlier events",
                    id="load-more-bar",
                    classes="load-more-bar",
                )

    def on_mount(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#load-more-bar").display = False
        self.call_after_refresh(self._scroll_latest)

    def on_resize(self, _: Resize) -> None:
        self._resync_expanded_tool_bounds()
        self.call_after_refresh(self._resync_expanded_tool_bounds)

    @on(Click, "#load-more-bar")
    def _on_load_more_click(self) -> None:
        self.post_message(self.LoadMore())

    def show_load_more_bar(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#load-more-bar").display = True

    def hide_load_more_bar(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#load-more-bar").display = False

    def prepend_widgets(self, widgets: list[Widget]) -> None:
        if not widgets:
            return
        content = self.query_one("#streaming-body-content", Vertical)
        anchor: Widget | None = None
        for child in content.children:
            if child.id != "load-more-bar":
                anchor = child
                break
        if anchor is not None:
            content.mount(*widgets, before=anchor)
        else:
            content.mount(*widgets)

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
        text = _sanitize_stream_text(text)
        if not text:
            return self

        if merge and self._last_chunk is not None and self._last_chunk_kind == kind:
            linked_text = (
                linkify_mentions(text, github_repo_slug=self._github_repo_slug)
                if kind != "user"
                else text
            )
            self._last_chunk.stream_fragment(linked_text, delay=self.word_delay_seconds)
            if self.is_mounted:
                self._schedule_follow_scroll()
            if self._last_chunk_line_key is not None:
                self._push_line(
                    self._last_chunk.rendered_text(),
                    key=self._last_chunk_line_key,
                )
            return self._last_chunk

        linked_text = (
            linkify_mentions(text, github_repo_slug=self._github_repo_slug)
            if kind != "user"
            else text
        )
        chunk = UserInputWidget(text) if kind == "user" else OutputChunk("", kind=kind)
        line_key = f"chunk:{self._counter + 1}"
        if isinstance(chunk, OutputChunk):
            self._append_widget(chunk, line_key=line_key)
            chunk.stream_fragment(linked_text, delay=self.word_delay_seconds)
            self._push_line(chunk.rendered_text(), key=line_key)
        else:
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
        try:
            current = self.query_one("#stream-current-action", Static)
        except NoMatches:
            return
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
        try:
            content = self.query_one("#streaming-body-content", Vertical)
        except NoMatches:
            return
        for child in list(content.children):
            if child.id != "load-more-bar":
                child.remove()
        self._tool_calls.clear()
        self._counter = 0
        self._reset_chunk_tracking()
        self.live_follow = True
        self.unread_count = 0
        self.hide_load_more_bar()
        self.set_current_action("Waiting for prompt", confidence="certain")
        self.call_after_refresh(self._scroll_latest)

    def get_text_content(self) -> str:
        return "\n".join(line.content for line in self._lines.values())

    def action_jump_to_latest(self) -> None:
        self._scroll_latest()
        entries = self._focusable_entries()
        if entries:
            self._focus_entry(entries[-1])

    def action_focus_next_entry(self) -> None:
        entries = self._focusable_entries()
        if not entries:
            return
        focused = self.screen.focused
        if focused in entries:
            index = min(len(entries) - 1, entries.index(cast("Widget", focused)) + 1)
        else:
            index = 0
        self._focus_entry(entries[index])

    def action_focus_prev_entry(self) -> None:
        entries = self._focusable_entries()
        if not entries:
            return
        focused = self.screen.focused
        if focused in entries:
            index = max(0, entries.index(cast("Widget", focused)) - 1)
        else:
            index = len(entries) - 1
        self._focus_entry(entries[index])

    def action_focus_first_entry(self) -> None:
        entries = self._focusable_entries()
        if not entries:
            return
        self._focus_entry(entries[0])

    def action_expand_entry(self) -> None:
        focused = self.screen.focused
        if isinstance(focused, ToolCallView) and focused.has_content:
            focused.expanded = True

    def action_collapse_entry(self) -> None:
        focused = self.screen.focused
        if isinstance(focused, ToolCallView) and focused.has_content:
            focused.expanded = False

    @on(MouseScrollUp, "#streaming-body")
    def _on_stream_scroll_up(self) -> None:
        self.live_follow = False
        self.call_after_refresh(self._maybe_auto_load_earlier)

    @on(MouseScrollDown, "#streaming-body")
    def _on_stream_scroll_down(self) -> None:
        self.call_after_refresh(self._sync_live_follow_from_position)

    @on(MouseUp, "#streaming-body")
    def _on_stream_mouse_up(self) -> None:
        self.call_after_refresh(self._sync_live_follow_from_position)

    def _maybe_auto_load_earlier(self) -> None:
        try:
            body = self.query_one("#streaming-body", ScrollableContainer)
        except NoMatches:
            return
        if float(body.scroll_y) > 0:
            return
        try:
            load_more = self.query_one("#load-more-bar", Static)
        except NoMatches:
            return
        if not load_more.display:
            return
        self.post_message(self.LoadMore())

    def _push_line(self, content: str, *, key: str | None = None) -> None:
        if key is not None:
            existing_order = self._line_order_by_key.get(key)
            if existing_order is not None:
                line = self._lines.get(existing_order)
                if line is not None:
                    line.content = content
                    return
                self._line_order_by_key.pop(key, None)

        self._counter += 1
        self._lines[self._counter] = _Line(order=self._counter, content=content, key=key)
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

    def _focusable_entries(self) -> list[Widget]:
        content = self.query_one("#streaming-body-content", Vertical)
        return [
            child for child in content.children if child.can_focus and child.id != "load-more-bar"
        ]

    def _focus_entry(self, entry: Widget) -> None:
        entry.focus()
        entry.scroll_visible(animate=False)
        self.call_after_refresh(self._sync_live_follow_from_position)

    def _maybe_prune(self) -> None:
        try:
            content = self.query_one("#streaming-body-content", Vertical)
        except NoMatches:
            return
        prunable = [c for c in content.children if c.id != "load-more-bar"]
        if len(prunable) <= self._PRUNE_HIGH_MARK:
            self._trim_line_history()
            return
        excess = len(prunable) - self._PRUNE_LOW_MARK
        to_remove = prunable[:excess]
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
        try:
            body = self.query_one("#streaming-body", ScrollableContainer)
        except NoMatches:
            return
        body.scroll_end(animate=False)
        self._sync_live_follow_from_position()
        self._resync_expanded_tool_bounds()

    def _schedule_follow_scroll(self) -> None:
        """Coalesce auto-scroll requests during merge streaming."""
        if not self.live_follow:
            return
        if self._scroll_scheduled:
            return
        self._scroll_scheduled = True
        self.call_after_refresh(self._do_follow_scroll)

    def _do_follow_scroll(self) -> None:
        self._scroll_scheduled = False
        self._scroll_latest()

    def _resync_expanded_tool_bounds(self) -> None:
        for tool_call in self._tool_calls.values():
            if tool_call.expanded:
                tool_call._sync_content_bounds()

    def _sync_live_follow_from_position(self) -> None:
        try:
            body = self.query_one("#streaming-body", ScrollableContainer)
        except NoMatches:
            return
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
