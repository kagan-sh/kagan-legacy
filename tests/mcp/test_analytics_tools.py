from typing import Any

import pytest

from mcp import ClientSession
from tests.helpers.mcp_helpers import extract_text as _text

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


async def test_analytics_backend_stats_returns_backends_list(
    mcp_board_with_core_client: tuple[ClientSession, Any],
) -> None:
    mcp_session, _core_client = mcp_board_with_core_client

    result = await mcp_session.call_tool("analytics_backend_stats", {"days": 7})

    assert not result.isError
    assert _text(result) == {"backends": []}


async def test_analytics_session_timeline_returns_timeline_list(
    mcp_board_with_core_client: tuple[ClientSession, Any],
) -> None:
    mcp_session, _core_client = mcp_board_with_core_client

    result = await mcp_session.call_tool("analytics_session_timeline", {"days": 7})

    assert not result.isError
    assert _text(result) == {"timeline": []}


async def test_analytics_export_returns_period_and_empty_sections(
    mcp_board_with_core_client: tuple[ClientSession, Any],
) -> None:
    mcp_session, _core_client = mcp_board_with_core_client

    result = await mcp_session.call_tool("analytics_export", {"days": 7})

    assert not result.isError
    payload = _text(result)
    assert payload["period_days"] == 7
    assert payload["backend_stats"] == []
    assert payload["session_timeline"] == []
