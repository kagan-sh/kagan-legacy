from __future__ import annotations

import json

from kagan.core.acp import messages
from kagan.core.agents.output import serialize_agent_messages, serialize_agent_output
from kagan.core.safety import REDACTED_TOKEN


class _FakeAgent:
    def __init__(self) -> None:
        self._messages = [
            messages.AgentUpdate("text", "Authorization: Bearer super-secret-token"),
        ]
        self._response_text = "token=github_pat_1234567890abcdefghijklmnopqrst"

    def get_messages(self) -> list[messages.AgentUpdate]:
        return list(self._messages)

    def get_response_text(self) -> str:
        return self._response_text


def test_serialize_agent_output_redacts_response_content() -> None:
    payload = serialize_agent_output(_FakeAgent())
    data = json.loads(payload)
    serialized = json.dumps(data)
    assert REDACTED_TOKEN in serialized
    assert "github_pat_1234567890abcdefghijklmnopqrst" not in serialized
    assert "super-secret-token" not in serialized


def test_serialize_agent_messages_redacts_incremental_output() -> None:
    fake_messages = [messages.AgentUpdate("text", "Authorization: Bearer super-secret-token")]
    payload = serialize_agent_messages(fake_messages)
    assert payload is not None
    assert REDACTED_TOKEN in payload
    assert "super-secret-token" not in payload
