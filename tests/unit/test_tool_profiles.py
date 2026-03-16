"""Tests for MCP tool profile filtering."""

import pytest

from kagan.core.enums import ToolProfile
from kagan.mcp._policy import TOOL_PROFILES, TOOL_TIERS, is_tool_allowed
from kagan.mcp.server import ServerOptions


@pytest.mark.unit
def test_task_profile_visibility() -> None:
    opts = ServerOptions(profile=ToolProfile.TASK)
    allowed = {name for name in TOOL_TIERS if is_tool_allowed(name, opts)}
    assert allowed == {
        "task_get",
        "task_list",
        "task_search",
        "task_events",
        "task_add_note",
        "run_update",
        "run_summary",
        "settings_get",
    }


@pytest.mark.unit
def test_no_profile_backwards_compat() -> None:
    opts = ServerOptions()
    allowed = {name for name in TOOL_TIERS if is_tool_allowed(name, opts)}
    expected_standard = {
        name
        for name, tier in TOOL_TIERS.items()
        if tier.value <= 2  # READONLY (1) and STANDARD (2)
    }
    assert allowed == expected_standard


@pytest.mark.unit
def test_profile_composition_with_readonly() -> None:
    opts = ServerOptions(readonly=True, profile=ToolProfile.TASK)
    allowed = {name for name in TOOL_TIERS if is_tool_allowed(name, opts)}
    assert allowed == {
        "task_get",
        "task_list",
        "task_search",
        "task_events",
        "run_summary",
        "settings_get",
    }


@pytest.mark.unit
def test_profile_exhaustiveness() -> None:
    all_profiled = set()
    for tools in TOOL_PROFILES.values():
        all_profiled |= tools
    assert all_profiled == set(TOOL_TIERS.keys())
