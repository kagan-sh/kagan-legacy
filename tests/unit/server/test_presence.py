from __future__ import annotations

from types import SimpleNamespace

import pytest

import kagan.server._helpers as server_helpers
from kagan.server._presence import MAX_PRESENCE_CLIENT_ID, MAX_PRESENCE_USER_LABEL, PresenceTracker
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server

pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_presence_heartbeat_truncates_client_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    tracker = PresenceTracker()
    monkeypatch.setattr(
        server_helpers,
        "get_server_context",
        lambda _mcp: SimpleNamespace(
            client=SimpleNamespace(),
            opts=ServerOptions(),
            presence=tracker,
        ),
    )

    heartbeat = get_http_endpoint(mcp, "/api/presence/heartbeat", "POST")
    response = await heartbeat(
        make_request(
            "POST",
            "/api/presence/heartbeat",
            body={
                "client_id": "x" * (MAX_PRESENCE_CLIENT_ID + 20),
                "client_type": "web",
                "user_label": "y" * (MAX_PRESENCE_USER_LABEL + 20),
                "active_task_id": "task-123",
            },
        )
    )

    assert json_body(response)["ok"] is True
    presence = tracker.to_wire()
    assert len(presence) == 1
    assert presence[0]["client_id"] == "x" * MAX_PRESENCE_CLIENT_ID
    assert presence[0]["user_label"] == "y" * MAX_PRESENCE_USER_LABEL
    assert presence[0]["active_task_id"] == "task-123"


def test_presence_unregister_ignores_stale_connection_token() -> None:
    tracker = PresenceTracker()

    tracker.register("client-1", "web", connection_token="token-old")
    tracker.register("client-1", "web", connection_token="token-new")
    tracker.unregister("client-1", connection_token="token-old")

    presence = tracker.to_wire()
    assert len(presence) == 1
    assert presence[0]["client_id"] == "client-1"
