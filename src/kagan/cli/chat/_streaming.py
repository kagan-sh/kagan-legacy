"""Response chunk processing and streaming output with memory safeguards."""

import re
from threading import RLock
from typing import Any

from loguru import logger
from rich.text import Text

# 10MB safeguard to prevent OOM from unbounded chunk accumulation
_MAX_RESPONSE_CHUNKS_BYTES = 10 * 1024 * 1024


class ResponseChunkBuffer:
    """Accumulates response chunks with memory safeguards."""

    def __init__(self, max_bytes: int = _MAX_RESPONSE_CHUNKS_BYTES) -> None:
        self._chunks: list[str] = []
        self._max_bytes = max_bytes
        self._total_bytes = 0

    def append(self, chunk: str) -> None:
        """Add a chunk, raising if exceeds memory limit.

        Args:
            chunk: Text chunk to append

        Raises:
            MemoryError: If total size exceeds max_bytes
        """
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
        """Return concatenated chunks and reset buffer."""
        result = "".join(self._chunks)
        self._chunks = []
        self._total_bytes = 0
        return result

    def clear(self) -> None:
        """Reset the buffer."""
        self._chunks = []
        self._total_bytes = 0

    @property
    def is_empty(self) -> bool:
        """Check if buffer has no chunks."""
        return len(self._chunks) == 0


_WORD_RE = re.compile(r"\S+\s*|\s+")


class StreamingMarkdownRegion:
    """Streams incoming chunks immediately and keeps the final response buffer."""

    def __init__(self, console: Any) -> None:
        self._console = console
        self._buffer: list[str] = []
        self._printed = False
        self._lock = RLock()

    def append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._buffer.append(text)
            self._print_words(text)

    def finalize(self) -> None:
        """Finish the live line after a streamed response."""
        with self._lock:
            text = self._joined().strip()
            printed = self._printed
            self._buffer = []
            self._printed = False
        if text:
            if printed:
                self._console.print()
                self._console.file.flush()

    def discard(self) -> None:
        """Clear the buffer without printing (used on turn reset)."""
        with self._lock:
            self._buffer = []
            self._printed = False

    @property
    def is_active(self) -> bool:
        return bool(self._buffer)

    def _joined(self) -> str:
        return "".join(self._buffer)

    def _print_words(self, text: str) -> None:
        for token in _WORD_RE.findall(text):
            if not token:
                continue
            self._console.print(Text(token, style="bright_white"), end="", highlight=False)
            self._console.file.flush()
            self._printed = True
