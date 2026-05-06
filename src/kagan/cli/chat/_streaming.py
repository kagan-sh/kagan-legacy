"""Response chunk processing and streaming output with markdown rendering."""

from __future__ import annotations

import time
from threading import RLock
from typing import TYPE_CHECKING

from loguru import logger
from rich.markdown import Markdown

if TYPE_CHECKING:
    from rich.console import Console

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        with self._lock:
            self._end_thought()
            tail = self._buffer[self._committed_len:]
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

    @property
    def is_active(self) -> bool:
        with self._lock:
            return bool(self._buffer[self._committed_len:])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append_thought(self, text: str) -> None:
        if not self._thought_announced:
            self._thought_start = time.monotonic()
            self._thought_announced = True
            self._in_thought = True
            self._console.print("[dim italic]Thinking…[/dim italic]", highlight=False)
            self._console.file.flush()
        if self._show_thoughts:
            self._thought_buffer += text

    def _end_thought(self) -> None:
        if not self._in_thought:
            return
        self._in_thought = False
        if self._show_thoughts and self._thought_buffer.strip():
            elapsed = time.monotonic() - self._thought_start
            self._console.print(
                f"[dim italic]— thought for {elapsed:.1f}s —[/dim italic]",
                highlight=False,
            )
            self._console.print(
                Markdown(self._thought_buffer.strip(), style="dim italic"),
                highlight=False,
            )
        self._thought_buffer = ""

    def _append_composing(self, text: str) -> None:
        self._buffer += text
        self._has_printed_anything = True
        # Only check for committed boundary when a newline is present
        # (block boundaries require at least one newline).
        if "\n" not in text:
            return
        pending = self._buffer[self._committed_len:]
        boundary = _find_committed_boundary(pending)
        if boundary is None:
            return
        committed = pending[:boundary]
        if committed.strip():
            self._console.print(Markdown(committed.strip()), highlight=False)
            self._console.file.flush()
        self._committed_len += boundary
