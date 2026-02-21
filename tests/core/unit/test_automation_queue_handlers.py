"""Queue command lane parsing behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kagan.core.commands import automation as automation_commands
from kagan.core.domain.enums import QueueLane


def _ctx_with_api() -> tuple[SimpleNamespace, SimpleNamespace]:
    api = SimpleNamespace(
        queue_message=AsyncMock(),
        get_queue_status=AsyncMock(),
        get_queued_messages=AsyncMock(),
        take_queued_message=AsyncMock(),
        remove_queued_message=AsyncMock(),
    )
    return SimpleNamespace(api=api), api


@pytest.mark.parametrize(
    ("handler", "params", "api_method"),
    [
        (
            automation_commands.handle_automation_queue_message,
            {"session_id": "session-1", "content": "hello", "lane": "deploy"},
            "queue_message",
        ),
        (
            automation_commands.handle_automation_get_queue_status,
            {"session_id": "session-1", "lane": "deploy"},
            "get_queue_status",
        ),
        (
            automation_commands.handle_automation_get_queued_messages,
            {"session_id": "session-1", "lane": "deploy"},
            "get_queued_messages",
        ),
        (
            automation_commands.handle_automation_take_queued_message,
            {"session_id": "session-1", "lane": "deploy"},
            "take_queued_message",
        ),
        (
            automation_commands.handle_automation_remove_queued_message,
            {"session_id": "session-1", "index": 0, "lane": "deploy"},
            "remove_queued_message",
        ),
    ],
)
async def test_queue_handlers_map_lane_parse_errors_to_invalid_lane_code(
    handler,
    params: dict[str, object],
    api_method: str,
) -> None:
    ctx, api = _ctx_with_api()

    result = await handler(ctx, params)

    assert result == {
        "success": False,
        "message": "lane must be one of: implementation, review, planner",
        "code": "INVALID_LANE",
    }
    getattr(api, api_method).assert_not_awaited()


async def test_queue_status_normalizes_lane_and_keeps_wire_value() -> None:
    ctx, api = _ctx_with_api()
    api.get_queue_status.return_value = SimpleNamespace(
        has_queued=True,
        queued_at=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
        content_preview="review notes",
        author="agent",
    )

    result = await automation_commands.handle_automation_get_queue_status(
        ctx,
        {"session_id": "session-1", "lane": "REVIEW"},
    )

    assert result["success"] is True
    assert result["lane"] == QueueLane.REVIEW.value
    api.get_queue_status.assert_awaited_once()
    assert api.get_queue_status.await_args.kwargs["lane"] is QueueLane.REVIEW
