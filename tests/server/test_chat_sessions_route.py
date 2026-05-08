"""Regression tests for GET /api/chat/sessions.

Covers:
- Correct Content-Length header so h11 does not raise
  ``LocalProtocolError: Too much data for declared Content-Length``
  (regression: SecurityHeadersMiddleware previously forwarded the start
  frame immediately without recalculating the length after injecting
  security headers, which could corrupt the byte count).
- Response envelope shape.
- Query-param filters (source, project_id).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.testclient import TestClient

import kagan.server._helpers as server_helpers
from kagan.core import KaganCore
from kagan.server._middleware import install_security_middleware
from kagan.server._presence import PresenceTracker
from kagan.server.mcp.server import ServerContext, ServerOptions, _set_server_context
from kagan.server.server import ApiServerOptions, create_api_server
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(core: KaganCore) -> SimpleNamespace:
    async def _get_settings() -> dict[str, str]:
        return {}

    return SimpleNamespace(
        client=SimpleNamespace(
            chat_sessions=core.chat_sessions,
            settings=SimpleNamespace(get=_get_settings),
            chat=core.chat,
            active_project_id=core.active_project_id,
            projects=SimpleNamespace(resolve_repo_path=lambda **_: None),
        ),
        opts=ServerOptions(),
    )


@pytest.fixture
async def setup(tmp_path: Path):
    core = KaganCore(db_path=tmp_path / "test.db")
    project = await core.projects.create("Chat Project")
    await core.projects.set_active(project.id)
    try:
        yield core, project.id
    finally:
        await core.aclose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_returns_empty_list_on_fresh_db(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """GET /api/chat/sessions returns [] when no sessions exist."""
    core, _ = setup
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))
    endpoint = get_http_endpoint(mcp, "/api/chat/sessions", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/chat/sessions")))
    assert body["ok"] is True
    assert body["data"] == []


@pytest.mark.asyncio
async def test_list_sessions_returns_created_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """GET /api/chat/sessions lists sessions after creation."""
    core, project_id = setup
    await core.chat_sessions.create(
        source="orchestrator",
        label="Test session",
        agent_backend="claude-code",
        project_id=project_id,
    )
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))
    endpoint = get_http_endpoint(mcp, "/api/chat/sessions", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/chat/sessions")))
    assert body["ok"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["label"] == "Test session"
    assert body["data"][0]["source"] == "orchestrator"


@pytest.mark.asyncio
async def test_list_sessions_content_length_matches_body_through_full_middleware(
    tmp_path: Path,
) -> None:
    """Content-Length header must equal actual body bytes after SecurityHeadersMiddleware.

    Regression: SecurityHeadersMiddleware previously forwarded ``http.response.start``
    before the body arrived, so the Content-Length declared by JSONResponse (based on
    the pre-header-injection body size) did not account for the extra security-header
    bytes injected into the response.  h11 detected the mismatch and raised
    ``LocalProtocolError: Too much data for declared Content-Length``.

    This test exercises the full middleware stack (security headers + CORS + CSRF +
    rate limiting) via TestClient (which uses h11 internally through httpx).  A
    Content-Length mismatch would raise ``httpx.RemoteProtocolError`` here.
    """
    core = KaganCore(db_path=tmp_path / "h11_test.db")
    project = await core.projects.create("H11 Project")
    await core.projects.set_active(project.id)

    # Seed several sessions with messages to exercise non-trivial response bodies.
    for i in range(5):
        row = await core.chat_sessions.create(
            source="orchestrator",
            label=f"Session {i}",
            agent_backend="claude-code",
            project_id=project.id,
        )
        await core.chat_sessions.append_message(row.id, "user", f"prompt {i} " * 50)
        await core.chat_sessions.append_message(row.id, "assistant", f"response {i} " * 100)

    opts = ApiServerOptions(mcp_opts=ServerOptions())
    mcp = create_api_server(opts)
    ctx = ServerContext(
        client=core,
        opts=opts.mcp_opts,
        presence=PresenceTracker(),
        shutdown_event=asyncio.Event(),
    )
    _set_server_context(mcp, ctx)
    app = mcp.streamable_http_app()
    install_security_middleware(app)

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            # This raises httpx.RemoteProtocolError if Content-Length is wrong.
            resp = client.get("/api/chat/sessions")
            assert resp.status_code == 200
            content_length = int(resp.headers["content-length"])
            assert content_length == len(resp.content), (
                f"Content-Length {content_length} != actual body {len(resp.content)}"
            )
            payload = resp.json()
            assert payload["ok"] is True
            assert len(payload["data"]) == 5
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_list_sessions_source_filter(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """?source= query param filters sessions by source field."""
    core, project_id = setup
    await core.chat_sessions.create(
        source="orchestrator", label="Orchestrator", project_id=project_id
    )
    await core.chat_sessions.create(source="repl", label="REPL", project_id=project_id)
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))
    endpoint = get_http_endpoint(mcp, "/api/chat/sessions", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/chat/sessions?source=orchestrator")))
    assert body["ok"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["source"] == "orchestrator"
