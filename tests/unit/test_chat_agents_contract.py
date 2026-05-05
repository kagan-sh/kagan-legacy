"""Unit tests for the `/api/chat/agents` wire contract."""

import pytest

from kagan.cli.chat import agents as agents_module
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
    monkeypatch.setattr(agents_module.shutil, "which", lambda exe: f"/usr/bin/{exe}")

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


def test_list_backends_with_availability_requires_acp_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat availability reflects the ACP command, not just the base CLI."""
    monkeypatch.setattr(
        agents_module,
        "list_available_backends",
        lambda: {"claude-code": True},
    )
    monkeypatch.setattr(
        agents_module.shutil,
        "which",
        lambda exe: "/usr/bin/claude" if exe == "claude" else None,
    )

    backends = agents_module.list_backends_with_availability()
    claude = next(backend for backend in backends if backend["name"] == "claude-code")

    assert claude == {"name": "claude-code", "available": False, "reference": True}


def test_resolve_available_chat_backend_falls_back_from_unlaunchable_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agents_module,
        "list_backends_with_availability",
        lambda: [
            {"name": "claude-code", "available": False, "reference": True},
            {"name": "kimi-cli", "available": True, "reference": False},
        ],
    )

    assert (
        agents_module.resolve_available_chat_backend({"default_agent_backend": "claude-code"})
        == "kimi-cli"
    )
