"""Response chunk processing and streaming output with markdown rendering."""

from __future__ import annotations

import time
from threading import RLock
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Group
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

from kagan.core.chat._turn_display import TurnPhaseTracker

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console, RenderableType

# 10MB safeguard to prevent OOM from unbounded chunk accumulation
_MAX_RESPONSE_CHUNKS_BYTES = 10 * 1024 * 1024

# Blocks that are self-closing (no paired close token in markdown-it).
_SELF_CLOSING_BLOCKS = frozenset(("fence", "code_block", "hr", "html_block"))


class ResponseChunkBuffer:
    """Accumulates response chunks with memory safeguards."""

    def __init__(self, max_bytes: int = _MAX_RESPONSE_CHUNKS_BYTES) -> None:
        self._chunks: list[str] = []
        self._max_bytes = max_bytes
        self._total_bytes = 0

    def append(self, chunk: str) -> None:
        chunk_bytes = len(chunk.encode("utf-8"))
        if self._total_bytes + chunk_bytes > self._max_bytes:
            logger.error(
                "Response chunks exceed {} MB limit",
                self._max_bytes // (1024 * 1024),
            )
            raise MemoryError(
                f"Response too large: {self._total_bytes + chunk_bytes} bytes "
                f"> {self._max_bytes} bytes"
            )
        self._chunks.append(chunk)
        self._total_bytes += chunk_bytes

    def get_all(self) -> str:
        result = "".join(self._chunks)
        self._chunks = []
        self._total_bytes = 0
        return result

    def clear(self) -> None:
        self._chunks = []
        self._total_bytes = 0

    @property
    def is_empty(self) -> bool:
        return len(self._chunks) == 0


def _find_committed_boundary(text: str) -> int | None:
    """Return the char offset up to which *text* can be safely rendered.

    Parses block-level tokens via markdown-it and finds the last complete
    top-level block. Returns None when fewer than 2 blocks exist (nothing
    confirmed yet). Adapted from kimi-cli's ``_find_committed_boundary``.
    """
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        return None

    md = MarkdownIt().enable("strikethrough").enable("table")
    tokens = md.parse(text)

    block_maps: list[list[int]] = []
    depth = 0
    for t in tokens:
        if t.nesting == 1:
            if depth == 0 and t.map is not None:
                block_maps.append(t.map)
            depth += 1
        elif t.nesting == -1:
            depth -= 1
        elif depth == 0 and t.type in _SELF_CLOSING_BLOCKS and t.map is not None:
            block_maps.append(t.map)

    if len(block_maps) < 2:
        return None

    # Convert end-line of the second-to-last block to a character offset.
    target_line = block_maps[-2][1]
    offset = 0
    try:
        for _ in range(target_line):
            offset = text.index("\n", offset) + 1
    except ValueError:
        return None
    return offset


class _TurnLiveState:
    """Rich-renderable consumed by Rich.Live — re-evaluated on every 10fps refresh.

    Renders a status spinner plus, when composing, the uncommitted tail buffer
    so the user sees words appear as they stream within a paragraph (committed
    blocks are flushed above the Live region as formatted Markdown).

    A small right-aligned single-line status Text (kimi-cli parity) may be
    appended after the spinner via ``inline_status``.  This replaces the old
    multi-line footer Group that caused the toolbar to jump mid-screen: Rich
    Live writes inline at the cursor, not at the viewport bottom, so only a
    compact single-line indicator belongs here.  The full 3-line toolbar lives
    in prompt_toolkit's ``bottom_toolbar`` callback which is viewport-pinned.
    """

    def __init__(self, inline_status: Callable[[], Text | None] | None = None) -> None:
        self._tracker = TurnPhaseTracker()
        self._spinner = Spinner("dots", "")
        self._tail = ""
        self._inline_status = inline_status

    def set_phase(self, phase: str) -> None:
        self._tracker.set_phase(phase)

    def add_text(self, text: str) -> None:
        self._tracker.add_text(text)

    def set_tail(self, tail: str) -> None:
        self._tail = tail

    def __rich__(self) -> RenderableType:
        if self._tracker._phase == "thinking":
            self._spinner.text = Text(self._tracker.thinking_label(), style="italic grey50")
            spinner_content: RenderableType = self._spinner
        else:
            self._spinner.text = Text(self._tracker.composing_label(), style="grey50")
            if not self._tail.strip():
                spinner_content = self._spinner
            else:
                spinner_content = Group(self._spinner, Text(self._tail, style="dim"))

        if self._inline_status is not None:
            status_text = self._inline_status()
            if status_text is not None:
                return Group(spinner_content, status_text)
        return spinner_content


class MarkdownStreamingRegion:
    """Progressive markdown rendering for streaming assistant responses.

    Buffers incoming text, flushes confirmed top-level markdown blocks as
    rendered ``Rich.Markdown`` immediately (so the user sees formatted output
    as soon as a paragraph/header/code-block is complete), and renders the
    remaining tail at ``finalize()``.

    For thinking tokens, the first chunk triggers a single ``Thinking…``
    line.  Subsequent thought chunks are suppressed unless ``show_thoughts``
    was set at construction.
    """

    def __init__(self, console: Console, *, show_thoughts: bool = False) -> None:
        self._console = console
        self._show_thoughts = show_thoughts
        self._lock = RLock()
        # Composing buffer state
        self._buffer: str = ""
        self._committed_len: int = 0
        self._has_printed_anything: bool = False
        # Thinking state
        self._in_thought: bool = False
        self._thought_announced: bool = False
        self._thought_start: float = 0.0
        self._thought_buffer: str = ""
        self._thought_chars: int = 0
        # Live turn indicator
        self._live_state: _TurnLiveState | None = None

    def set_show_thoughts(self, value: bool) -> None:
        """Toggle streaming-reasoning display at runtime."""
        self._show_thoughts = value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_live_state(self, ls: _TurnLiveState | None) -> None:
        self._live_state = ls

    def append(self, text: str, *, thought: bool = False) -> None:
        if not text:
            return
        with self._lock:
            if thought:
                self._append_thought(text)
            else:
                self._end_thought()
                self._append_composing(text)

    def finalize(self) -> None:
        """Flush remaining buffered text as markdown and reset state."""
        self._live_state = None
        with self._lock:
            self._end_thought()
            tail = self._buffer[self._committed_len :]
            self._buffer = ""
            self._committed_len = 0
            printed = self._has_printed_anything
            self._has_printed_anything = False

        if tail.strip():
            self._console.print(Markdown(tail.strip()), highlight=False)
        elif printed:
            self._console.print()
        self._console.file.flush()

    def discard(self) -> None:
        """Clear the buffer without printing (used on turn reset)."""
        with self._lock:
            self._buffer = ""
            self._committed_len = 0
            self._has_printed_anything = False
            self._in_thought = False
            self._thought_announced = False
            self._thought_buffer = ""
            self._thought_chars = 0

    @property
    def is_active(self) -> bool:
        with self._lock:
            return bool(self._buffer[self._committed_len :])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append_thought(self, text: str) -> None:
        if not self._thought_announced:
            self._thought_start = time.monotonic()
            self._thought_announced = True
            self._in_thought = True
        self._thought_chars += len(text)
        if self._live_state:
            self._live_state.set_phase("thinking")
            self._live_state.add_text(text)
        if self._show_thoughts:
            self._thought_buffer += text

    def _end_thought(self) -> None:
        if not self._in_thought:
            return
        self._in_thought = False
        elapsed = time.monotonic() - self._thought_start
        tok = max(1, self._thought_chars // 4)
        if self._live_state:
            self._live_state.set_phase("composing")
            self._live_state.set_tail("")
        if self._show_thoughts and self._thought_buffer.strip():
            self._console.print(
                f"[dim italic]— thought for {elapsed:.1f}s · {tok} tok —[/dim italic]",
                highlight=False,
            )
            self._console.print(
                Markdown(self._thought_buffer.strip(), style="dim italic"),
                highlight=False,
            )
        else:
            # Collapsed summary (always printed, regardless of show_thoughts)
            self._console.print(
                f"[dim italic]thinking… {elapsed:.1f}s · {tok} tok[/dim italic]",
                highlight=False,
            )
            self._console.file.flush()
        self._thought_buffer = ""
        self._thought_chars = 0

    def _append_composing(self, text: str) -> None:
        self._buffer += text
        self._has_printed_anything = True
        if self._live_state:
            self._live_state.add_text(text)
        # Only check for committed boundary when a newline is present
        # (block boundaries require at least one newline).
        if "\n" in text:
            pending = self._buffer[self._committed_len :]
            boundary = _find_committed_boundary(pending)
            if boundary is not None:
                committed = pending[:boundary]
                if committed.strip():
                    self._console.print(Markdown(committed.strip()), highlight=False)
                    self._console.file.flush()
                self._committed_len += boundary
        if self._live_state:
            self._live_state.set_tail(self._buffer[self._committed_len :])
