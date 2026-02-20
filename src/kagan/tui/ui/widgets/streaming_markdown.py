"""Streaming markdown widget for agent content display."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.widgets import Markdown, Static
from textual.widgets.markdown import MarkdownStream  # noqa: TC002 (used at runtime)

from kagan.core.domain.enums import StreamRole  # noqa: TC001 (used at runtime for type)
from kagan.tui.ui.utils.helpers import copy_with_notification

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Click


class StreamingMarkdown(Markdown):
    """Markdown widget that supports streaming content updates."""

    _FLUSH_INTERVAL_SECONDS: ClassVar[float] = 0.03

    def __init__(
        self,
        role: StreamRole,
        **kwargs,
    ) -> None:
        """Initialize StreamingMarkdown widget.

        Args:
            role: The role type (RESPONSE or THOUGHT) for CSS classification
            **kwargs: Additional arguments passed to Markdown
        """
        super().__init__("", **kwargs)
        self._role = role
        self._accumulated_content = ""
        self._stream: MarkdownStream | None = None
        self._pending_fragments: list[str] = []
        self._flush_task: asyncio.Task[None] | None = None
        self.add_class(f"agent-{role}")

    @property
    def role(self) -> StreamRole:
        """Get the widget's role."""
        return self._role

    @property
    def content(self) -> str:
        return self._accumulated_content

    @property
    def stream(self) -> MarkdownStream:
        """Get the Markdown stream used for incremental updates."""
        if self._stream is None:
            self._stream = self.get_stream(self)
        return self._stream

    async def append_content(self, text: str) -> None:
        """Append text to the accumulated content and update the display.

        Args:
            text: Text fragment to append
        """
        if not text:
            return
        self._accumulated_content += text
        self._pending_fragments.append(text)
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_pending_fragments())

    async def _flush_pending_fragments(self) -> None:
        """Flush pending markdown fragments in small batches."""
        try:
            while self._pending_fragments:
                await asyncio.sleep(self._FLUSH_INTERVAL_SECONDS)
                if not self._pending_fragments:
                    break
                chunk = "".join(self._pending_fragments)
                self._pending_fragments.clear()
                await self.stream.write(chunk)
        except asyncio.CancelledError:
            raise
        finally:
            self._flush_task = None

    async def stop_stream(self) -> None:
        """Stop the active Markdown stream task if present."""
        flush_task = self._flush_task
        self._flush_task = None
        if flush_task is not None:
            flush_task.cancel()
            with suppress(asyncio.CancelledError):
                await flush_task
        self._pending_fragments.clear()
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        with suppress(asyncio.CancelledError):
            await stream.stop()

    async def on_unmount(self) -> None:
        """Ensure stream workers are cancelled before widget teardown."""
        await self.stop_stream()

    def clear(self) -> None:
        self._accumulated_content = ""
        flush_task = self._flush_task
        self._flush_task = None
        self._pending_fragments.clear()
        if flush_task is not None:
            with suppress(RuntimeError):
                asyncio.get_running_loop().create_task(self._stop_flush_task_background(flush_task))
        stream = self._stream
        self._stream = None
        if stream is not None:
            with suppress(RuntimeError):
                asyncio.get_running_loop().create_task(self._stop_stream_background(stream))
        self.update("")

    async def _stop_flush_task_background(self, task: asyncio.Task[None]) -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _stop_stream_background(self, stream: MarkdownStream) -> None:
        with suppress(asyncio.CancelledError):
            await stream.stop()


class UserInput(Horizontal):
    DEFAULT_CLASSES = "user-input"
    can_focus = True
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "copy", "Copy", key_display="Enter", show=False),
        Binding("y", "copy", "Copy", show=False),
    ]

    def __init__(self, content: str) -> None:
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        yield Static("❯", classes="user-input-prompt")  # noqa: RUF001
        yield Markdown(self._content, classes="user-input-content")

    def action_copy(self) -> None:
        """Copy user input content."""
        copy_with_notification(self.app, self._content, "Input")

    async def _on_click(self, event: Click) -> None:
        if event.chain == 1:
            self.focus()
        elif event.chain == 2:
            self.action_copy()


__all__ = ["StreamingMarkdown", "UserInput"]
