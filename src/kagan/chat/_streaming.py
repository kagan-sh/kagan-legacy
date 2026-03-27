"""Response chunk processing and streaming output with memory safeguards."""

import time
from typing import Any

from loguru import logger

# 10MB safeguard to prevent OOM from unbounded chunk accumulation
_MAX_RESPONSE_CHUNKS_BYTES = 10 * 1024 * 1024
_STREAM_FLUSH_INTERVAL_SECONDS = 1 / 30


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


class OutputFlushManager:
    """Manages debounced flushing of pending output chunks."""

    def __init__(self, console: Any) -> None:
        self._console = console
        self._pending_chunks: list[str] = []
        self._last_flush = float("-inf")
        self._flush_handle: Any = None

    def queue_chunk(self, chunk: str) -> None:
        """Queue a chunk for eventual output."""
        self._pending_chunks.append(chunk)

    def flush(self, *, force: bool = False) -> None:
        """Flush pending chunks to console, respecting rate limit.

        Args:
            force: If True, bypass rate limiting
        """
        self._cancel_timer()
        if not self._pending_chunks:
            return

        now = time.monotonic()
        if not force and now - self._last_flush < _STREAM_FLUSH_INTERVAL_SECONDS:
            remaining = _STREAM_FLUSH_INTERVAL_SECONDS - (now - self._last_flush)
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                self._flush_handle = loop.call_later(remaining, self._do_deferred_flush)
            except RuntimeError:
                pass
            return

        merged = "".join(self._pending_chunks)
        self._pending_chunks = []
        self._console.print(merged, end="", highlight=False, markup=False)
        self._console.file.flush()
        self._last_flush = now

    def _do_deferred_flush(self) -> None:
        """Internal callback for deferred flush."""
        self._flush_handle = None
        self.flush(force=True)

    def _cancel_timer(self) -> None:
        """Cancel any pending flush timer."""
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None

    def shutdown(self) -> None:
        """Ensure all pending data is flushed and timer is cancelled."""
        self.flush(force=True)
        self._cancel_timer()

    def clear(self) -> None:
        """Clear pending chunks without flushing."""
        self._pending_chunks = []
        self._cancel_timer()

    @property
    def is_empty(self) -> bool:
        """Check if there are pending chunks."""
        return len(self._pending_chunks) == 0
