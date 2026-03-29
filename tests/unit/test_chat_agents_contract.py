"""Unit tests for the `/api/chat/agents` wire contract."""

import pytest

from kagan.chat import agents as agents_module
from kagan.server.responses import ChatAgentsResponse

pytestmark = [pytest.mark.unit]


def test_list_backends_with_availability_includes_reference_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agents_module,
        "list_available_backends",
        lambda: {"claude-code": True, "codex": False},
    )

    backends = agents_module.list_backends_with_availability()
    selected = {
        backend["name"]: backend
        for backend in backends
        if backend["name"] in {"claude-code", "codex"}
    }

    assert selected == {
        "claude-code": {"name": "claude-code", "available": True, "reference": True},
        "codex": {"name": "codex", "available": False, "reference": True},
    }

    payload = ChatAgentsResponse(backends=backends, default="claude-code").model_dump(mode="json")
    payload_backends = {
        backend["name"]: backend
        for backend in payload["backends"]
        if backend["name"] in {"claude-code", "codex"}
    }
    assert payload_backends == {
        "claude-code": {"name": "claude-code", "available": True, "reference": True},
        "codex": {"name": "codex", "available": False, "reference": True},
    }
    assert payload["default"] == "claude-code"
