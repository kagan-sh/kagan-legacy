"""Shared MCP test helpers."""

from __future__ import annotations

import json
from typing import Any

from mcp.types import TextContent


def extract_text(result: Any) -> dict:
    """Extract and parse JSON text content from an MCP CallToolResult."""
    block = result.content[0]
    assert isinstance(block, TextContent), f"Expected TextContent, got {type(block)}"
    return json.loads(block.text)
