"""Response chunk processing and streaming output with memory safeguards."""

from typing import Any

from loguru import logger
from rich.markdown import Markdown

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


class StreamingMarkdownRegion:
    """Accumulates streaming Markdown chunks and commits them on finalize.

    Chunks accumulate in a buffer.  ``finalize()`` commits the final
    Markdown render to the console via ``_console.print(Markdown(text))``.
    ``patch_stdout(raw=True)`` in the outer REPL loop routes this output
    above the prompt-toolkit toolbar so the footer stays pinned.

    The previous ``attach()`` / parent-tail mechanism (``TurnLiveRegion``)
    has been removed.  Streaming updates are now purely accumulative;
    the prompt-toolkit toolbar provides the only live footer.
    """

    def __init__(self, console: Any) -> None:
        self._console = console
        self._buffer: list[str] = []

    def append(self, text: str) -> None:
        if not text:
            return
        self._buffer.append(text)

    def finalize(self) -> None:
        """Commit the accumulated Markdown to the console and clear the buffer."""
        text = self._joined().strip()
        self._buffer = []
        if text:
            self._console.print(Markdown(text))

    def discard(self) -> None:
        """Clear the buffer without printing (used on turn reset)."""
        self._buffer = []

    @property
    def is_active(self) -> bool:
        return bool(self._buffer)

    def _joined(self) -> str:
        return "".join(self._buffer)
