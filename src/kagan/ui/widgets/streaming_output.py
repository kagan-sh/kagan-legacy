"""Streaming output widget for smooth AI response rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import ScrollableContainer
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Markdown, RichLog

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.widgets.markdown import MarkdownStream


class StreamingOutput(Widget):
    """Reusable streaming output widget using Markdown for smooth text rendering.

    Uses Textual's MarkdownStream API for flicker-free streaming of AI responses.
    Optionally includes a RichLog for status messages (tool calls, thinking, etc.).
    """

    def __init__(
        self,
        *,
        show_status_log: bool = False,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize StreamingOutput widget.

        Args:
            show_status_log: Whether to show a separate RichLog for status messages.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(id=id, classes=classes)
        self._show_status_log = show_status_log
        self._markdown_stream: MarkdownStream | None = None

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        with ScrollableContainer(id="streaming-container"):
            yield Markdown("", id="streaming-content")
        if self._show_status_log:
            yield RichLog(
                id="streaming-status",
                wrap=True,
                highlight=True,
                markup=True,
            )

    async def on_mount(self) -> None:
        """Initialize markdown stream on mount."""
        markdown = self.query_one("#streaming-content", Markdown)
        self._markdown_stream = Markdown.get_stream(markdown)

    async def write(self, text: str) -> None:
        """Stream text to the markdown widget.

        This method streams text smoothly without adding newlines between chunks,
        making it ideal for AI response streaming.

        Args:
            text: Text to stream.
        """
        if self._markdown_stream:
            await self._markdown_stream.write(text)
            self._scroll_content_to_bottom()

    def write_status(self, text: str, style: str = "") -> None:
        """Write to the status log.

        Use this for metadata like tool calls, thinking indicators, etc.
        Only works if show_status_log=True was set.

        Args:
            text: Text to write.
            style: Rich markup style (e.g., "bold cyan", "dim italic").
        """
        if not self._show_status_log:
            return
        try:
            log = self.query_one("#streaming-status", RichLog)
            if style:
                log.write(f"[{style}]{text}[/{style}]")
            else:
                log.write(text)
            log.scroll_end(animate=False)
        except NoMatches:
            pass

    def _scroll_content_to_bottom(self) -> None:
        """Scroll the content container to bottom."""
        try:
            container = self.query_one("#streaming-container", ScrollableContainer)
            container.scroll_end(animate=False)
        except NoMatches:
            pass

    async def clear(self) -> None:
        """Clear all content and reset the stream."""
        try:
            # Reset markdown widget
            markdown = self.query_one("#streaming-content", Markdown)
            await markdown.update("")
            self._markdown_stream = Markdown.get_stream(markdown)

            # Clear status log if present
            if self._show_status_log:
                log = self.query_one("#streaming-status", RichLog)
                log.clear()
        except NoMatches:
            pass

    def get_content(self) -> str:
        """Get the current markdown content as text.

        Returns:
            The accumulated text content.
        """
        try:
            markdown = self.query_one("#streaming-content", Markdown)
            # The markdown widget stores its content
            return str(markdown._markdown) if hasattr(markdown, "_markdown") else ""
        except NoMatches:
            return ""

    def on_unmount(self) -> None:
        """Clean up resources on unmount."""
        # Clear the stream reference to break any reference cycles
        self._markdown_stream = None
