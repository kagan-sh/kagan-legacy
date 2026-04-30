"""Tests for project-oriented REST routes."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from kagan.core import KaganCore
from kagan.server._presence import PresenceTracker
from kagan.server.mcp.server import ServerContext, ServerOptions, _set_server_context
from tests.helpers.helpers import make_git_repo
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server

pytestmark = [pytest.mark.smoke]


@pytest.mark.asyncio
async def test_resolve_folder_detects_git_root_and_existing_project(tmp_path) -> None:
    repo_path = tmp_path / "repo"
    nested = repo_path / "src" / "pkg"
    await make_git_repo(repo_path)
    nested.mkdir(parents=True)

    client = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        project = await client.projects.create("Existing Project")
        repo = await client.projects.add_repo(project.id, str(repo_path))

        mcp = make_api_server()
        _set_server_context(
            mcp,
            ServerContext(
                client=client,
                opts=ServerOptions(),
                presence=PresenceTracker(),
            ),
        )
        endpoint = get_http_endpoint(mcp, "/api/projects/resolve-folder", "GET")
        response = await endpoint(
            make_request("GET", f"/api/projects/resolve-folder?path={quote(str(nested))}")
        )
        body = json_body(response)

        assert body["ok"] is True
        data = body["data"]
        assert data["path"] == str(nested.resolve())
        assert data["repo_path"] == str(repo_path.resolve())
        assert data["git_root"] == str(repo_path.resolve())
        assert data["is_git_repo"] is True
        assert data["suggested_project_name"] == "repo"
        assert data["existing_project_id"] == project.id
        assert data["existing_project_name"] == "Existing Project"
        assert data["existing_repo_id"] == repo.id
    finally:
        _set_server_context(mcp, None)
        client.close()


@pytest.mark.asyncio
async def test_resolve_folder_describes_empty_folder(tmp_path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()

    client = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        mcp = make_api_server()
        _set_server_context(
            mcp,
            ServerContext(
                client=client,
                opts=ServerOptions(),
                presence=PresenceTracker(),
            ),
        )
        endpoint = get_http_endpoint(mcp, "/api/projects/resolve-folder", "GET")
        response = await endpoint(
            make_request("GET", f"/api/projects/resolve-folder?path={quote(str(folder))}")
        )
        body = json_body(response)

        assert body["ok"] is True
        data = body["data"]
        assert data["path"] == str(folder.resolve())
        assert data["repo_path"] == str(folder.resolve())
        assert data["git_root"] is None
        assert data["is_git_repo"] is False
        assert data["suggested_project_name"] == "empty"
        assert data["existing_project_id"] is None
        assert data["existing_repo_id"] is None
    finally:
        _set_server_context(mcp, None)
        client.close()
