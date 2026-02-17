from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

from kagan.core.api import KaganAPI
from kagan.core.commands.automation import (
    _DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
    handle_audit_list,
)
from kagan.core.host import CoreHost
from kagan.core.ipc.contracts import CoreRequest, CoreResponse
from kagan.version import get_kagan_version

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


def _audit_ctx(*, events: list[object]) -> Any:
    audit_repository = SimpleNamespace(list_events=AsyncMock(return_value=events))
    ctx = SimpleNamespace(audit_repository=audit_repository)
    ctx.api = KaganAPI(cast("Any", ctx))
    return ctx


async def test_record_audit_event_uses_nested_result_success_when_present() -> None:
    host = CoreHost()
    audit_repository = SimpleNamespace(record=AsyncMock())
    host._ctx = cast("AppContext", SimpleNamespace(audit_repository=audit_repository))

    request = CoreRequest(
        session_id="session-1",
        session_origin="tui",
        client_version=get_kagan_version(),
        capability="jobs",
        method="submit",
        params={"task_id": "T1"},
    )
    response = CoreResponse.success(
        request.request_id,
        result={"success": False, "code": "UNSUPPORTED_ACTION"},
    )

    await host._record_audit_event(request, response)

    kwargs = audit_repository.record.await_args.kwargs
    assert kwargs["success"] is False


async def test_record_audit_event_defaults_to_transport_success_without_nested_flag() -> None:
    host = CoreHost()
    audit_repository = SimpleNamespace(record=AsyncMock())
    host._ctx = cast("AppContext", SimpleNamespace(audit_repository=audit_repository))

    request = CoreRequest(
        session_id="session-1",
        session_origin="tui",
        client_version=get_kagan_version(),
        capability="tasks",
        method="list",
        params={},
    )
    response = CoreResponse.success(request.request_id, result={"count": 1})

    await host._record_audit_event(request, response)

    kwargs = audit_repository.record.await_args.kwargs
    assert kwargs["success"] is True


def _make_audit_event(*, payload_json: str = "{}", result_json: str = "{}") -> SimpleNamespace:
    return SimpleNamespace(
        id="evt-1",
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        actor_type="user",
        actor_id="u1",
        session_id="s1",
        capability="tasks",
        command_name="list",
        payload_json=payload_json,
        result_json=result_json,
        success=True,
    )


async def test_handle_audit_list_truncates_large_payload_and_result_json() -> None:
    """Large payload_json and result_json are truncated to prevent transport overflow."""
    big_payload = "x" * (_DEFAULT_AUDIT_FIELD_CHAR_LIMIT + 5000)
    big_result = "y" * (_DEFAULT_AUDIT_FIELD_CHAR_LIMIT + 3000)
    event = _make_audit_event(payload_json=big_payload, result_json=big_result)

    api = _audit_ctx(events=[event])

    result = await handle_audit_list(api, {"limit": 80})

    assert result["count"] == 1
    assert result["truncated"] is True
    returned = result["events"][0]
    assert len(returned["payload_json"]) < len(big_payload)
    assert "[truncated" in returned["payload_json"]
    assert len(returned["result_json"]) < len(big_result)
    assert "[truncated" in returned["result_json"]


async def test_handle_audit_list_passes_small_payloads_unchanged() -> None:
    """Small payload_json and result_json pass through without modification."""
    small_payload = '{"task_id": "T1"}'
    small_result = '{"success": true}'
    event = _make_audit_event(payload_json=small_payload, result_json=small_result)

    api = _audit_ctx(events=[event])

    result = await handle_audit_list(api, {"limit": 20})

    assert result["count"] == 1
    assert result["truncated"] is False
    returned = result["events"][0]
    assert returned["payload_json"] == small_payload
    assert returned["result_json"] == small_result
