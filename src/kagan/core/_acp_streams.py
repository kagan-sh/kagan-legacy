"""ACP stdio stream guards."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    import asyncio


class JsonRpcObjectStreamReader:
    """Drop non-JSON-RPC stdout lines before the ACP SDK parses them.

    ACP transports are line-delimited JSON-RPC. Some Windows agent launchers can
    emit terminal/control output on stdout before or between JSON-RPC frames.
    The upstream ACP SDK logs a full traceback for every such line, so we filter
    non-object JSON here and leave valid frames untouched.
    """

    def __init__(self, reader: asyncio.StreamReader, *, backend_name: str) -> None:
        self._reader = reader
        self._backend_name = backend_name
        self._dropped = 0

    async def readline(self) -> bytes:
        while True:
            line = await self._reader.readline()
            if not line:
                return line

            stripped = line.strip()
            if not stripped:
                continue

            try:
                message: Any = json.loads(line)
            except Exception:
                self._record_drop(line, reason="non-JSON")
                continue

            if not isinstance(message, dict):
                self._record_drop(line, reason=f"JSON {type(message).__name__}")
                continue

            return line

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        return await self._reader.readuntil(separator)

    async def read(self, n: int = -1) -> bytes:
        return await self._reader.read(n)

    async def readexactly(self, n: int) -> bytes:
        return await self._reader.readexactly(n)

    def at_eof(self) -> bool:
        return self._reader.at_eof()

    def _record_drop(self, line: bytes, *, reason: str) -> None:
        self._dropped += 1
        if self._dropped > 1:
            logger.debug(
                "Discarding ACP stdout noise from backend={} reason={} count={}",
                self._backend_name,
                reason,
                self._dropped,
            )
            return

        preview = line.decode("utf-8", errors="replace").strip().replace("\x1b", "\\x1b")
        logger.warning(
            "Discarding ACP stdout noise from backend={} reason={} preview={!r}",
            self._backend_name,
            reason,
            preview[:200],
        )
