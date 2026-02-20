"""Command transport truncation behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kagan.core.commands._transport_truncation import (
    DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
    truncate_for_transport,
)
from kagan.core.commands.automation import handle_audit_list
from kagan.core.commands.projects import list_audit_events


@dataclass(slots=True)
class _AuditEvent:
    id: int
    occurred_at: datetime | None
    actor_type: str
    actor_id: str
    session_id: str
    capability: str
    command_name: str
    payload_json: str | None
    result_json: str | None
    success: bool


class _AuditRepository:
    def __init__(self, events: list[_AuditEvent]) -> None:
        self._events = events

    async def list_events(
        self,
        *,
        capability: object = None,
        limit: int = 50,
        cursor: object = None,
    ) -> list[_AuditEvent]:
        del capability, limit, cursor
        return self._events


class _AutomationAPI:
    def __init__(self, events: list[_AuditEvent]) -> None:
        self._events = events

    async def list_audit_events(
        self,
        *,
        capability: object = None,
        limit: int = 50,
        cursor: object = None,
    ) -> list[_AuditEvent]:
        del capability, limit, cursor
        return self._events


class _ProjectsContext:
    def __init__(self, events: list[_AuditEvent]) -> None:
        self.audit_repository = _AuditRepository(events)


class _AutomationContext:
    def __init__(self, events: list[_AuditEvent]) -> None:
        self.api = _AutomationAPI(events)


def _base_event(*, payload_json: str | None, result_json: str | None) -> _AuditEvent:
    return _AuditEvent(
        id=1,
        occurred_at=datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC),
        actor_type="user",
        actor_id="u-1",
        session_id="s-1",
        capability="tasks",
        command_name="get",
        payload_json=payload_json,
        result_json=result_json,
        success=True,
    )


def _assert_transport_truncated(
    payload: dict[str, Any],
    *,
    payload_omitted: int,
    result_omitted: int,
) -> None:
    payload_suffix = f"[truncated {payload_omitted} chars for transport]"
    result_suffix = f"[truncated {result_omitted} chars for transport]"

    payload_json = str(payload["payload_json"])
    result_json = str(payload["result_json"])
    assert payload_json.startswith("p" * DEFAULT_AUDIT_FIELD_CHAR_LIMIT)
    assert payload_json.endswith(payload_suffix)
    assert result_json.startswith("r" * DEFAULT_AUDIT_FIELD_CHAR_LIMIT)
    assert result_json.endswith(result_suffix)


def test_truncate_for_transport_preserves_prefix_and_suffix() -> None:
    content = "abcdef"
    truncated, did_truncate = truncate_for_transport(content, limit=4)

    assert did_truncate is True
    assert truncated == "abcd\n\n[truncated 2 chars for transport]"


def test_truncate_for_transport_zero_limit() -> None:
    truncated, did_truncate = truncate_for_transport("abc", limit=0)
    assert truncated == ""
    assert did_truncate is True


async def test_projects_audit_list_uses_transport_truncation() -> None:
    event = _base_event(
        payload_json="p" * (DEFAULT_AUDIT_FIELD_CHAR_LIMIT + 5),
        result_json="r" * (DEFAULT_AUDIT_FIELD_CHAR_LIMIT + 3),
    )
    result = await list_audit_events(_ProjectsContext([event]), params={})

    assert result["count"] == 1
    assert result["truncated"] is True
    _assert_transport_truncated(result["events"][0], payload_omitted=5, result_omitted=3)


async def test_automation_audit_list_uses_transport_truncation() -> None:
    event = _base_event(
        payload_json="p" * (DEFAULT_AUDIT_FIELD_CHAR_LIMIT + 2),
        result_json="r" * (DEFAULT_AUDIT_FIELD_CHAR_LIMIT + 7),
    )
    result = await handle_audit_list(_AutomationContext([event]), params={})

    assert result["count"] == 1
    assert result["truncated"] is True
    _assert_transport_truncated(result["events"][0], payload_omitted=2, result_omitted=7)
