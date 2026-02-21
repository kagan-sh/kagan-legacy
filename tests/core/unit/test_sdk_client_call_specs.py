from __future__ import annotations

from typing import Any

import pytest

from kagan.core.domain.enums import QueueLane
from kagan.sdk._client import KaganSDK


class _StubTransport:
    def __init__(
        self,
        *,
        query_responses: dict[tuple[str, str], dict[str, Any]] | None = None,
        request_responses: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.is_connected = False
        self.query_responses = query_responses or {}
        self.request_responses = request_responses or {}
        self.query_calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.request_calls: list[tuple[str, str, dict[str, Any] | None]] = []

    async def connect(self) -> None:
        self.is_connected = True

    async def close(self) -> None:
        self.is_connected = False

    async def query(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.query_calls.append(
            (capability, method, dict(params) if isinstance(params, dict) else params)
        )
        return dict(self.query_responses.get((capability, method), {}))

    async def request(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.request_calls.append(
            (capability, method, dict(params) if isinstance(params, dict) else params)
        )
        return dict(self.request_responses.get((capability, method), {}))


@pytest.mark.asyncio
async def test_tasks_get_uses_query_call_spec() -> None:
    transport = _StubTransport(query_responses={("tasks", "get"): {"found": False}})
    sdk = KaganSDK(transport=transport, client_version="test")

    response = await sdk.tasks_get("task-123")

    assert response.found is False
    assert transport.query_calls == [("tasks", "get", {"task_id": "task-123"})]
    assert transport.request_calls == []


@pytest.mark.asyncio
async def test_tasks_delete_uses_request_call_spec() -> None:
    transport = _StubTransport(
        request_responses={
            ("tasks", "delete"): {"success": True, "task_id": "task-123", "message": "deleted"}
        }
    )
    sdk = KaganSDK(transport=transport, client_version="test")

    response = await sdk.tasks_delete("task-123")

    assert response.success is True
    assert response.task_id == "task-123"
    assert transport.request_calls == [("tasks", "delete", {"task_id": "task-123"})]
    assert transport.query_calls == []


@pytest.mark.asyncio
async def test_settings_get_applies_success_override_in_call_helper() -> None:
    transport = _StubTransport(
        query_responses={("settings", "get"): {"settings": {"theme": "light"}}}
    )
    sdk = KaganSDK(transport=transport, client_version="test")

    response = await sdk.settings_get()

    assert response.success is True
    assert response.settings == {"theme": "light"}
    assert transport.query_calls == [("settings", "get", {})]


@pytest.mark.asyncio
async def test_get_queue_status_uses_spec_and_lane_override() -> None:
    transport = _StubTransport(
        query_responses={("automation", "get_queue_status"): {"has_queued": True}}
    )
    sdk = KaganSDK(transport=transport, client_version="test")

    response = await sdk.get_queue_status("session-1", lane=QueueLane.REVIEW)

    assert response.has_queued is True
    assert response.lane == QueueLane.REVIEW
    assert transport.query_calls == [
        ("automation", "get_queue_status", {"session_id": "session-1", "lane": QueueLane.REVIEW})
    ]
