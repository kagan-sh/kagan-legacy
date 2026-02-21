from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.commands._parsing import str_object_dict
from kagan.core.commands._responses import (
    CommandCode,
    invalid_params_response,
    require_non_empty_param,
)
from kagan.core.commands.automation_shared import api_from_context, parse_queue_lane_or_error
from kagan.core.policy import command

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


@command(
    "automation",
    "queue_message",
    profile="pair_worker",
    mutating=True,
    description="Queue a follow-up message for a session lane.",
)
async def handle_automation_queue_message(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    session_id, session_id_error = require_non_empty_param(params, "session_id")
    if session_id_error is not None:
        return session_id_error
    content, content_error = require_non_empty_param(params, "content")
    if content_error is not None:
        return content_error

    lane, lane_error = parse_queue_lane_or_error(params)
    if lane_error is not None:
        return lane_error

    assert session_id is not None
    assert content is not None
    assert lane is not None
    author = params.get("author")
    metadata = str_object_dict(params.get("metadata"))
    msg = await api.queue_message(
        session_id,
        content,
        lane=lane,
        author=author if isinstance(author, str) and author.strip() else None,
        metadata=metadata,
    )
    return {
        "success": True,
        "content": msg.content,
        "author": msg.author,
        "queued_at": msg.queued_at.isoformat(),
        "code": CommandCode.QUEUED.value,
    }


@command(
    "automation",
    "get_queue_status",
    profile="pair_worker",
    description="Get queue status for a session lane.",
)
async def handle_automation_get_queue_status(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    session_id, session_id_error = require_non_empty_param(params, "session_id")
    if session_id_error is not None:
        return session_id_error

    lane, lane_error = parse_queue_lane_or_error(params)
    if lane_error is not None:
        return lane_error

    assert session_id is not None
    assert lane is not None
    status = await api.get_queue_status(session_id, lane=lane)
    return {
        "success": True,
        "has_queued": status.has_queued,
        "queued_at": status.queued_at.isoformat() if status.queued_at else None,
        "content_preview": status.content_preview,
        "author": status.author,
        "lane": lane.value,
    }


@command(
    "automation",
    "get_queued_messages",
    profile="pair_worker",
    description="List queued messages for a session lane.",
)
async def handle_automation_get_queued_messages(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    session_id, session_id_error = require_non_empty_param(params, "session_id")
    if session_id_error is not None:
        return session_id_error

    lane, lane_error = parse_queue_lane_or_error(params)
    if lane_error is not None:
        return lane_error

    assert session_id is not None
    assert lane is not None
    messages = await api.get_queued_messages(session_id, lane=lane)
    return {
        "success": True,
        "messages": [
            {
                "content": message.content,
                "author": message.author,
                "metadata": message.metadata,
                "queued_at": message.queued_at.isoformat(),
            }
            for message in messages
        ],
        "count": len(messages),
    }


@command(
    "automation",
    "take_queued_message",
    profile="pair_worker",
    mutating=True,
    description="Consume and return the next queued message for a session lane.",
)
async def handle_automation_take_queued_message(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    session_id, session_id_error = require_non_empty_param(params, "session_id")
    if session_id_error is not None:
        return session_id_error

    lane, lane_error = parse_queue_lane_or_error(params)
    if lane_error is not None:
        return lane_error

    assert session_id is not None
    assert lane is not None
    msg = await api.take_queued_message(session_id, lane=lane)
    if msg is None:
        return {"success": True, "message": None, "code": CommandCode.QUEUE_EMPTY.value}
    return {
        "success": True,
        "message": {
            "content": msg.content,
            "author": msg.author,
            "metadata": msg.metadata,
            "queued_at": msg.queued_at.isoformat(),
        },
        "code": CommandCode.MESSAGE_TAKEN.value,
    }


@command(
    "automation",
    "remove_queued_message",
    profile="pair_worker",
    mutating=True,
    description="Remove a queued message by index from a session lane.",
)
async def handle_automation_remove_queued_message(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    session_id, session_id_error = require_non_empty_param(params, "session_id")
    if session_id_error is not None:
        return session_id_error

    lane, lane_error = parse_queue_lane_or_error(params)
    if lane_error is not None:
        return lane_error

    index_raw = params.get("index")
    if not isinstance(index_raw, int) or isinstance(index_raw, bool):
        return invalid_params_response("index must be an integer")

    assert session_id is not None
    assert lane is not None
    removed = await api.remove_queued_message(session_id, index_raw, lane=lane)
    return {
        "success": removed,
        "message": "Removed" if removed else "Message not found at index",
        "code": CommandCode.REMOVED.value if removed else CommandCode.NOT_FOUND.value,
    }


__all__ = [
    "handle_automation_get_queue_status",
    "handle_automation_get_queued_messages",
    "handle_automation_queue_message",
    "handle_automation_remove_queued_message",
    "handle_automation_take_queued_message",
]
