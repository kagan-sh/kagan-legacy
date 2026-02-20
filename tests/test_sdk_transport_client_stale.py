from __future__ import annotations

import pytest

from kagan.core.ipc.contracts import CoreResponse
from kagan.sdk._errors import CoreFailureError
from kagan.sdk._transport import SDKTransport


class _FakeIPCClient:
    def __init__(self, response: CoreResponse) -> None:
        self.is_connected = True
        self._response = response

    async def connect(self) -> None:
        self.is_connected = True

    async def close(self) -> None:
        self.is_connected = False

    async def request(self, **_kwargs):  # type: ignore[no-untyped-def]
        return self._response


@pytest.mark.asyncio
async def test_stale_client_error_adds_tui_restart_hint() -> None:
    response = CoreResponse.failure(
        request_id="req-1",
        code="CLIENT_OUTDATED",
        message="Client build hash mismatch.",
    )
    transport = SDKTransport(
        client=_FakeIPCClient(response),
        session_origin="tui",
        session_id="tui:test",
        client_version="dev",
        client_build_hash="hash",
        capability_profile="maintainer",
    )

    with pytest.raises(CoreFailureError) as exc_info:
        await transport.request("tasks", "list", {})

    assert "Restart the TUI session to reload the latest runtime." in str(exc_info.value)


@pytest.mark.asyncio
async def test_stale_client_error_adds_mcp_restart_hint() -> None:
    response = CoreResponse.failure(
        request_id="req-2",
        code="CLIENT_BUILD_HASH_REQUIRED",
        message="Client did not report a runtime build hash.",
    )
    transport = SDKTransport(
        client=_FakeIPCClient(response),
        session_origin="kagan_admin",
        session_id="ext:test",
        client_version="dev",
        client_build_hash="hash",
        capability_profile="maintainer",
    )

    with pytest.raises(CoreFailureError) as exc_info:
        await transport.request("tasks", "list", {})

    assert "Restart the MCP session to reload the latest runtime." in str(exc_info.value)

