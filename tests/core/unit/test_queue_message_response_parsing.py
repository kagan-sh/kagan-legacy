from __future__ import annotations

from kagan.sdk._types import QueuedMessage, QueueMessageResponse


def test_queue_message_response_accepts_message_object_payload() -> None:
    response = QueueMessageResponse.model_validate(
        {
            "success": True,
            "message": {
                "content": "Looks good.",
                "author": "orchestrator-overlay",
                "metadata": {"target": "review"},
                "queued_at": "2026-02-20T12:43:00.673142+00:00",
            },
            "code": "MESSAGE_TAKEN",
        }
    )

    assert isinstance(response.message, QueuedMessage)
    assert response.message.content == "Looks good."
    assert response.message.author == "orchestrator-overlay"


def test_queue_message_response_coerces_queue_message_wire_payload() -> None:
    response = QueueMessageResponse.model_validate(
        {
            "success": True,
            "content": "Ship this next.",
            "author": "planner",
            "metadata": {"lane": "implementation"},
            "queued_at": "2026-02-20T12:50:00+00:00",
            "code": "QUEUED",
        }
    )

    assert isinstance(response.message, QueuedMessage)
    assert response.message.content == "Ship this next."
    assert response.message.author == "planner"
