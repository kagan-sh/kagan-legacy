"""Shared ACP client stub for integration tests."""

from __future__ import annotations

from typing import Any


class StubAcpClient:
    """Minimal ACP client stub used by handshake and roundtrip integration tests."""

    async def session_update(self, *_: Any, **__: Any) -> None:
        pass

    async def request_permission(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def read_text_file(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def write_text_file(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def create_terminal(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def terminal_output(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def kill_terminal(self, *_: Any, **__: Any) -> None:
        pass

    async def release_terminal(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def wait_for_terminal_exit(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]
