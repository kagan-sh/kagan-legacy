"""Unit tests for chat attachment parsing and resolve_sse_parameters validation.

Covers:
- _parse_attachments: well-formed, malformed, empty, size guard
- resolve_sse_parameters: attachment-only turn (no text), text+attachment,
  missing-both rejection.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest

from kagan.server._sse_fanout import _parse_attachments, resolve_sse_parameters
from tests.helpers.server import make_request

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _parse_attachments unit tests
# ---------------------------------------------------------------------------


def _b64(data: str) -> str:
    return base64.b64encode(data.encode()).decode()


def test_parse_attachments_returns_none_when_key_missing() -> None:
    result = _parse_attachments({})
    assert result is None


def test_parse_attachments_returns_none_when_not_a_list() -> None:
    result = _parse_attachments({"attachments": "not-a-list"})
    assert result is None


def test_parse_attachments_returns_none_when_all_lack_data() -> None:
    result = _parse_attachments({"attachments": [{"type": "image", "name": "x.png"}]})
    assert result is None


def test_parse_attachments_happy_path_image() -> None:
    body: dict[str, Any] = {
        "attachments": [
            {
                "type": "image",
                "name": "screenshot.png",
                "mime_type": "image/png",
                "data": _b64("fake-png-bytes"),
            }
        ]
    }
    result = _parse_attachments(body)
    assert result is not None
    assert len(result) == 1
    assert result[0].name == "screenshot.png"
    assert result[0].type == "image"
    assert result[0].mime_type == "image/png"
    assert result[0].data == _b64("fake-png-bytes")


def test_parse_attachments_filters_entries_without_data() -> None:
    body: dict[str, Any] = {
        "attachments": [
            {"type": "image", "name": "no-data.png"},
            {"type": "image", "name": "has-data.png", "data": _b64("ok")},
        ]
    }
    result = _parse_attachments(body)
    assert result is not None
    assert len(result) == 1
    assert result[0].name == "has-data.png"


def test_parse_attachments_ignores_extra_fields() -> None:
    """extra='ignore' on Attachment means unknown fields don't cause validation errors."""
    body: dict[str, Any] = {
        "attachments": [
            {
                "type": "image",
                "name": "x.png",
                "data": _b64("bytes"),
                "unknown_future_field": "ignored",
            }
        ]
    }
    result = _parse_attachments(body)
    assert result is not None
    assert len(result) == 1


# ---------------------------------------------------------------------------
# resolve_sse_parameters — text/attachment validation gate
# ---------------------------------------------------------------------------


def _make_permissive_ctx(session_id: str) -> SimpleNamespace:
    """Minimal ServerContext stub that lets access checks pass."""
    from kagan.server._access import AccessTier

    class _FakeSessionView:
        id = session_id
        agent_backend = "claude-code"
        source = "web"
        orchestrator_history: list[Any] = []
        label = "Test"
        project_id = None
        updated_at = "2026-01-01T00:00:00Z"
        session_type = "orchestrator"

    class _FakeSessions:
        async def get_with_history(self, sid: str):
            return (_FakeSessionView(), [])

    class _FakeSettings:
        async def get(self) -> dict[str, str]:
            return {}

    class _FakeTurnStatus:
        active = False
        started_at = None
        partial_chars = 0

    class _FakeChat:
        def turn_status(self, sid: str):
            return _FakeTurnStatus()

    class _FakeProjects:
        async def resolve_repo_path(self, **_kw: Any) -> None:
            return None

    class _FakeClient:
        chat_sessions = _FakeSessions()
        settings = _FakeSettings()
        chat = _FakeChat()
        projects = _FakeProjects()
        active_project_id = None

    class _FakeOpts:
        access_tier = AccessTier.STANDARD

    return SimpleNamespace(client=_FakeClient(), opts=_FakeOpts())


@pytest.mark.asyncio
async def test_resolve_sse_parameters_rejects_empty_text_and_no_attachments() -> None:
    session_id = "sess-001"
    ctx = _make_permissive_ctx(session_id)
    req = make_request("POST", f"/api/chat/{session_id}/stream", body={"text": ""})
    result = await resolve_sse_parameters(req, ctx, session_id)  # type: ignore[arg-type]
    from starlette.responses import JSONResponse

    assert isinstance(result, JSONResponse)
    import json

    body = json.loads(bytes(result.body))
    assert body["ok"] is False
    assert "attachment" in body["error"].lower() or "text" in body["error"].lower()


@pytest.mark.asyncio
async def test_resolve_sse_parameters_accepts_attachment_only_turn() -> None:
    session_id = "sess-002"
    ctx = _make_permissive_ctx(session_id)
    body: dict[str, Any] = {
        "text": "",
        "attachments": [
            {
                "type": "image",
                "name": "diagram.png",
                "mime_type": "image/png",
                "data": _b64("fake-image"),
            }
        ],
    }
    req = make_request("POST", f"/api/chat/{session_id}/stream", body=body)
    result = await resolve_sse_parameters(req, ctx, session_id)  # type: ignore[arg-type]
    from starlette.responses import JSONResponse

    assert not isinstance(result, JSONResponse), "Should succeed with attachment-only turn"
    _session, text, _backend, attachments = result
    assert text == ""
    assert attachments is not None
    assert len(attachments) == 1
    assert attachments[0].name == "diagram.png"
    assert attachments[0].mime_type == "image/png"


@pytest.mark.asyncio
async def test_resolve_sse_parameters_accepts_text_plus_attachments() -> None:
    session_id = "sess-003"
    ctx = _make_permissive_ctx(session_id)
    body: dict[str, Any] = {
        "text": "what is in this image?",
        "attachments": [
            {
                "type": "image",
                "name": "photo.jpg",
                "mime_type": "image/jpeg",
                "data": _b64("jpeg-bytes"),
            }
        ],
    }
    req = make_request("POST", f"/api/chat/{session_id}/stream", body=body)
    result = await resolve_sse_parameters(req, ctx, session_id)  # type: ignore[arg-type]
    from starlette.responses import JSONResponse

    assert not isinstance(result, JSONResponse)
    _session, text, _backend, attachments = result
    assert text == "what is in this image?"
    assert attachments is not None
    assert attachments[0].mime_type == "image/jpeg"
