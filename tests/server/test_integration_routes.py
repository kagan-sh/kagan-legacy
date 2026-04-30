"""Tests: REST routes for /api/integrations/*."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from starlette.responses import Response

from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server

pytestmark = [pytest.mark.smoke]


def _status_code(response: object) -> int:
    assert isinstance(response, Response)
    return response.status_code


# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


class _FakeSettings:
    async def get(self) -> dict[str, str]:
        return {}


class _FakeProjects:
    async def resolve_repo_path(self, *, settings: dict) -> None:
        return None


class _FakeClient:
    active_project_id: str | None = "project-1"
    settings = _FakeSettings()
    projects = _FakeProjects()


def _make_ctx(client: Any = None):
    from types import SimpleNamespace

    return SimpleNamespace(client=client or _FakeClient())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server_with_ctx(mcp, client=None, *, admin: bool = False, readonly: bool = False):
    """Register a fake ServerContext so require_context passes."""
    from kagan.server._presence import PresenceTracker
    from kagan.server.mcp.server import ServerContext, _set_server_context

    ctx = ServerContext(
        client=client or _FakeClient(),
        opts=ServerOptions(admin=admin, readonly=readonly),
        presence=PresenceTracker(),
    )
    _set_server_context(mcp, ctx)
    return ctx


# ---------------------------------------------------------------------------
# GET /api/integrations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_integrations_returns_github() -> None:
    mcp = make_api_server()
    _make_server_with_ctx(mcp)
    endpoint = get_http_endpoint(mcp, "/api/integrations", "GET")
    request = make_request("GET", "/api/integrations")
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is True
    ids = [i["id"] for i in body["data"]["integrations"]]
    assert "github" in ids


# ---------------------------------------------------------------------------
# GET /api/integrations/{id}/preflight
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
@patch("kagan.core.integrations.github.subprocess")
@pytest.mark.asyncio
async def test_integration_preflight_github_ok(_mock_subprocess, _mock_gh_path) -> None:
    _mock_subprocess.run.return_value.returncode = 0
    _mock_subprocess.run.return_value.stdout = "gho_fake_token"
    _mock_subprocess.TimeoutExpired = TimeoutError

    mcp = make_api_server()
    _make_server_with_ctx(mcp)
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/preflight", "GET")
    request = make_request(
        "GET", "/api/integrations/github/preflight", path_params={"id": "github"}
    )
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["id"] == "github"
    assert isinstance(body["data"]["checks"], list)
    assert body["data"]["ready"] is True


@pytest.mark.asyncio
async def test_integration_preflight_unknown_returns_404() -> None:
    mcp = make_api_server()
    _make_server_with_ctx(mcp)
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/preflight", "GET")
    request = make_request(
        "GET", "/api/integrations/jira/preflight", path_params={"id": "jira"}
    )
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is False
    assert _status_code(response) == 404


# ---------------------------------------------------------------------------
# GET /api/integrations/{id}/preview
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated",
    new_callable=AsyncMock,
    return_value=True,
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
@pytest.mark.asyncio
async def test_integration_preview_returns_items(
    _mock_path, _mock_auth, mock_fetch
) -> None:
    mock_fetch.return_value = [
        {
            "number": 1,
            "title": "Fix bug",
            "body": "Details",
            "labels": [{"name": "bug"}],
            "state": "OPEN",
            "url": "https://github.com/octocat/hello-world/issues/1",
        }
    ]

    mcp = make_api_server()
    _make_server_with_ctx(mcp)
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/preview", "GET")
    request = make_request(
        "GET",
        "/api/integrations/github/preview?repo_slug=octocat/hello-world",
        path_params={"id": "github"},
    )
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["issues"][0]["title"] == "Fix bug"


@pytest.mark.asyncio
async def test_integration_preview_missing_project_id() -> None:
    class _NoProjectClient(_FakeClient):
        active_project_id: str | None = None

    mcp = make_api_server()
    _make_server_with_ctx(mcp, client=_NoProjectClient())
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/preview", "GET")
    request = make_request(
        "GET",
        "/api/integrations/github/preview?repo_slug=octocat/hello-world",
        path_params={"id": "github"},
    )
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is False


# ---------------------------------------------------------------------------
# POST /api/integrations/{id}/sync
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated",
    new_callable=AsyncMock,
    return_value=True,
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
@pytest.mark.asyncio
async def test_integration_sync_returns_counts(
    _mock_path, _mock_auth, mock_fetch
) -> None:
    mock_fetch.return_value = [
        {
            "number": 5,
            "title": "New task",
            "body": "",
            "labels": [],
            "state": "OPEN",
            "url": "https://github.com/octocat/hello-world/issues/5",
        }
    ]

    import os
    import tempfile

    from kagan.core import KaganCore

    tmp = tempfile.mkdtemp()
    real_client = KaganCore(db_path=os.path.join(tmp, "test.db"))
    project = await real_client.projects.create("Test")
    await real_client.projects.set_active(project.id)

    mcp = make_api_server()
    _make_server_with_ctx(mcp, client=real_client)
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/sync", "POST")
    request = make_request(
        "POST",
        "/api/integrations/github/sync",
        path_params={"id": "github"},
        body={"repo_slug": "octocat/hello-world", "state": "open"},
    )
    response = await endpoint(request)
    body = json_body(response)

    real_client.close()
    assert body["ok"] is True
    assert body["data"]["created"] == 1
    assert body["data"]["skipped"] == 0
    assert body["data"]["id"] == "github"


@pytest.mark.asyncio
async def test_integration_sync_unknown_integration() -> None:
    mcp = make_api_server()
    _make_server_with_ctx(mcp)
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/sync", "POST")
    request = make_request(
        "POST",
        "/api/integrations/jira/sync",
        path_params={"id": "jira"},
        body={},
    )
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is False
    assert _status_code(response) == 404


@pytest.mark.asyncio
async def test_integration_sync_rejects_readonly() -> None:
    mcp = make_api_server()
    _make_server_with_ctx(mcp, readonly=True)
    endpoint = get_http_endpoint(mcp, "/api/integrations/{id}/sync", "POST")
    request = make_request(
        "POST",
        "/api/integrations/github/sync",
        path_params={"id": "github"},
        body={"repo_slug": "octocat/hello-world", "state": "open"},
    )
    response = await endpoint(request)
    body = json_body(response)

    assert body["ok"] is False
    assert body["error_code"] == "ACCESS_TIER_FORBIDDEN"
    assert _status_code(response) == 403
