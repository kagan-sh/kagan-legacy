"""Tests: MCP tool dispatch parity for GitHub integration tools.

Tests call the underlying tool functions directly, patching get_context to
return a mock ServerContext backed by a real KaganCore client.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = [pytest.mark.integrations]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(client):
    """Build a minimal ServerContext mock backed by a real KaganCore client."""
    from kagan.server.mcp.server import ServerContext, ServerOptions

    opts = ServerOptions()
    app = ServerContext(
        client=client,
        opts=opts,
        bound_project_id=client.active_project_id,
    )
    return app


def _make_ctx():
    """Return a minimal MCP Context placeholder (not used directly in tests)."""
    return MagicMock()


# ---------------------------------------------------------------------------
# integration_preflight tool
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
@patch("kagan.core.integrations.github.subprocess")
async def test_integration_preflight_tool_returns_expected_keys(
    mock_subprocess, _mock_path, client
) -> None:
    """integration_preflight returns available_integrations, checks, ready."""
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "gho_fake"
    mock_subprocess.TimeoutExpired = TimeoutError

    from kagan.server.mcp.toolsets.integrations import _integration_preflight

    ctx = _make_ctx()
    app = _make_app(client)
    with patch("kagan.server.mcp.toolsets.integrations.get_context", return_value=app):
        result = await _integration_preflight(ctx, integration="github")

    assert "available_integrations" in result
    assert "checks" in result
    assert "ready" in result
    assert "github" in result["available_integrations"]


# ---------------------------------------------------------------------------
# integration_preview tool
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_integration_preview_tool_shape(_mock_path, _mock_auth, mock_fetch, client) -> None:
    """integration_preview returns integration, repo, issues, total keys."""
    mock_fetch.return_value = [
        {
            "number": 1,
            "title": "Bug",
            "body": "body",
            "labels": [],
            "state": "open",
            "url": "https://github.com/octocat/hello-world/issues/1",
        }
    ]

    from kagan.server.mcp.toolsets.integrations import _integration_preview

    ctx = _make_ctx()
    app = _make_app(client)
    with patch("kagan.server.mcp.toolsets.integrations.get_context", return_value=app):
        result = await _integration_preview(
            ctx,
            integration="github",
            repo="octocat/hello-world",
            state="open",
        )

    assert result["integration"] == "github"
    assert result["repo"] == "octocat/hello-world"
    assert "issues" in result
    assert "total" in result
    assert result["total"] == 1


# ---------------------------------------------------------------------------
# integration_sync tool
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_integration_sync_tool_shape(_mock_path, _mock_auth, mock_fetch, client) -> None:
    """integration_sync returns integration, repo, project_id, created, updated, skipped, errors."""
    mock_fetch.return_value = [
        {
            "number": 1,
            "title": "Bug",
            "body": "body",
            "labels": [],
            "state": "open",
            "url": "https://github.com/octocat/hello-world/issues/1",
        }
    ]

    from kagan.server.mcp.toolsets.integrations import _integration_sync

    ctx = _make_ctx()
    app = _make_app(client)
    with patch("kagan.server.mcp.toolsets.integrations.get_context", return_value=app):
        result = await _integration_sync(
            ctx,
            integration="github",
            repo="octocat/hello-world",
            state="open",
        )

    for key in ("integration", "repo", "project_id", "created", "updated", "skipped", "errors"):
        assert key in result, f"missing key: {key}"

    assert result["integration"] == "github"
    assert result["created"] == 1


# ---------------------------------------------------------------------------
# mention_search tool
# ---------------------------------------------------------------------------


async def test_mention_search_tool_shape(client) -> None:
    """mention_search returns mentions and total keys."""
    await client.tasks.create("Auth feature")
    project_id = client.active_project_id

    from kagan.server.mcp.toolsets.integrations import _mention_search

    ctx = _make_ctx()
    app = _make_app(client)
    with (
        patch("kagan.server.mcp.toolsets.integrations.get_context", return_value=app),
        patch(
            "kagan.core.integrations.mentions._fetch_github_mentions",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await _mention_search(ctx, project_id=project_id, q="auth", limit=5)

    assert "mentions" in result
    assert "total" in result
    assert isinstance(result["mentions"], list)


async def test_mention_search_tool_mention_keys(client) -> None:
    """Each mention dict has source, id, title, state."""
    await client.tasks.create("Search target task")
    project_id = client.active_project_id

    from kagan.server.mcp.toolsets.integrations import _mention_search

    ctx = _make_ctx()
    app = _make_app(client)
    with (
        patch("kagan.server.mcp.toolsets.integrations.get_context", return_value=app),
        patch(
            "kagan.core.integrations.mentions._fetch_github_mentions",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        result = await _mention_search(ctx, project_id=project_id, q="search", limit=5)

    for mention in result["mentions"]:
        for key in ("source", "id", "title", "state"):
            assert key in mention, f"mention missing key: {key}"


async def test_integration_sync_tool_params_match_http_route(client) -> None:
    """Verify integration_sync accepts same parameters as the HTTP route."""
    import inspect

    from kagan.server.mcp.toolsets.integrations import _integration_sync

    sig = inspect.signature(_integration_sync)
    params = set(sig.parameters.keys())
    # Required params per HTTP route / plan
    assert "integration" in params
    assert "repo" in params
    assert "state" in params
    assert "labels" in params
    assert "limit" in params
    assert "issue_numbers" in params


async def test_integration_preview_tool_params_match_http_route(client) -> None:
    """Verify integration_preview accepts same parameters as the HTTP route."""
    import inspect

    from kagan.server.mcp.toolsets.integrations import _integration_preview

    sig = inspect.signature(_integration_preview)
    params = set(sig.parameters.keys())
    assert "integration" in params
    assert "repo" in params
    assert "state" in params
    assert "labels" in params
    assert "limit" in params
