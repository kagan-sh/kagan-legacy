"""Shared fixtures for tests/server/."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import kagan.server._helpers as server_helpers
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint
from tests.helpers.server_ws import make_api_server


def _make_browse_ctx() -> SimpleNamespace:
    async def _get_settings() -> dict[str, str]:
        return {}

    async def _no_repo_path(**_kwargs: Any) -> None:
        return None

    return SimpleNamespace(
        client=SimpleNamespace(
            settings=SimpleNamespace(get=_get_settings),
            projects=SimpleNamespace(resolve_repo_path=_no_repo_path),
        ),
        opts=ServerOptions(),
    )


@pytest.fixture()
def browse_endpoint(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return the browse endpoint with a real ctx stub."""
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _make_browse_ctx())
    return get_http_endpoint(mcp, "/api/fs/browse", "GET")
