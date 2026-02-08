"""Tests for MCP server degraded mode (no active Kagan session)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from kagan.mcp.server import _create_mcp_server, _mcp_lifespan

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_no_git_repo_yields_degraded_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lifespan yields server=None when not inside a git repository."""
    monkeypatch.chdir(tmp_path)

    with patch("kagan.mcp.server.has_git_repo", new_callable=AsyncMock, return_value=False):
        async with _mcp_lifespan(_create_mcp_server()) as ctx:
            assert ctx.server is None
            assert ctx.app_context is None


@pytest.mark.asyncio
async def test_broken_db_yields_degraded_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lifespan yields server=None when app context init fails."""
    monkeypatch.chdir(tmp_path)

    with (
        patch("kagan.mcp.server.has_git_repo", new_callable=AsyncMock, return_value=True),
        patch(
            "kagan.mcp.server.create_app_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB init failed"),
        ),
    ):
        async with _mcp_lifespan(_create_mcp_server()) as ctx:
            assert ctx.server is None
            assert ctx.app_context is None
