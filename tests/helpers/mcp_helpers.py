"""Shared MCP test helpers."""

from __future__ import annotations

import json
from typing import Any


def extract_text(result: Any) -> Any:
    """Extract and parse JSON text content from an MCP CallToolResult."""
    return json.loads(result.content[0].text)
