"""Unit tests for kagan.core.permission_ui shared helpers.

Guards the refactor that moved pure permission-UI helpers out of
``kagan.cli.chat._permission_ui`` / ``kagan.cli.chat._approval_types``
into the public core module so the TUI can import them without crossing
the CLI package boundary.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from kagan.core.permission_ui import (
    SessionApprovals,
    format_permission_tool,
    session_approvals,
    tool_action_key,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# tool_action_key
# ---------------------------------------------------------------------------


class TestToolActionKey:
    def test_dict_with_title(self) -> None:
        assert tool_action_key({"title": "bash", "name": "bash_20250124"}) == "bash"

    def test_dict_with_name_only(self) -> None:
        assert tool_action_key({"name": "read_file"}) == "read_file"

    def test_object_with_title(self) -> None:
        obj = SimpleNamespace(title="mcp__kagan__task_get", name="task_get")
        assert tool_action_key(obj) == "mcp__kagan__task_get"

    def test_object_with_name_only(self) -> None:
        obj = SimpleNamespace(title=None, name="write_file")
        assert tool_action_key(obj) == "write_file"

    def test_strips_arg_suffix(self) -> None:
        # Titles like "bash: {cmd: ...}" should reduce to "bash"
        obj = SimpleNamespace(title="bash: {cmd: ls}", name=None)
        assert tool_action_key(obj) == "bash"

    def test_strips_brace_suffix(self) -> None:
        tc: dict[str, Any] = {"title": "read_file{path=/etc/hosts}"}
        assert tool_action_key(tc) == "read_file"

    def test_casefold(self) -> None:
        assert tool_action_key({"title": "BaSh"}) == "bash"

    def test_empty_dict_returns_tool(self) -> None:
        assert tool_action_key({}) == "tool"

    def test_none_attrs_returns_tool(self) -> None:
        obj = SimpleNamespace(title=None, name=None)
        assert tool_action_key(obj) == "tool"


# ---------------------------------------------------------------------------
# format_permission_tool
# ---------------------------------------------------------------------------


class TestFormatPermissionTool:
    def test_title_and_kind(self) -> None:
        obj = SimpleNamespace(title="bash", kind="shell", name=None)
        assert format_permission_tool(obj) == "bash (shell)"

    def test_title_only(self) -> None:
        obj = SimpleNamespace(title="read_file", kind=None, name=None)
        assert format_permission_tool(obj) == "read_file"

    def test_name_fallback(self) -> None:
        obj = SimpleNamespace(title=None, kind=None, name="write_file")
        assert format_permission_tool(obj) == "write_file"

    def test_no_name_or_title(self) -> None:
        obj = SimpleNamespace()
        assert format_permission_tool(obj) == "tool call"

    def test_dict_without_attrs(self) -> None:
        # plain dict: getattr falls back to None for missing keys
        result = format_permission_tool({})
        assert result == "tool call"


# ---------------------------------------------------------------------------
# SessionApprovals
# ---------------------------------------------------------------------------


class TestSessionApprovals:
    def test_initially_nothing_allowed(self) -> None:
        sa = SessionApprovals()
        assert not sa.is_allowed("bash")

    def test_grant_single(self) -> None:
        sa = SessionApprovals()
        sa.grant("bash")
        assert sa.is_allowed("bash")
        assert not sa.is_allowed("read_file")

    def test_revoke(self) -> None:
        sa = SessionApprovals()
        sa.grant("bash")
        sa.revoke("bash")
        assert not sa.is_allowed("bash")

    def test_revoke_nonexistent_is_noop(self) -> None:
        sa = SessionApprovals()
        sa.revoke("nonexistent")  # must not raise
        assert not sa.is_allowed("nonexistent")

    def test_grant_all(self) -> None:
        sa = SessionApprovals()
        sa.grant_all()
        assert sa.is_allowed("bash")
        assert sa.is_allowed("anything")

    def test_list_granted(self) -> None:
        sa = SessionApprovals()
        sa.grant("bash")
        sa.grant("read_file")
        assert sa.list_granted() == ["bash", "read_file"]

    def test_list_granted_empty(self) -> None:
        sa = SessionApprovals()
        assert sa.list_granted() == []


# ---------------------------------------------------------------------------
# module-level singleton is the right type
# ---------------------------------------------------------------------------


def test_module_singleton_is_session_approvals_instance() -> None:
    assert isinstance(session_approvals, SessionApprovals)


# ---------------------------------------------------------------------------
# CLI re-export compatibility: _approval_types must still expose the same
# symbols under their underscore aliases so existing CLI callers are intact.
# ---------------------------------------------------------------------------


def test_cli_internal_aliases_still_resolve() -> None:
    from kagan.cli.chat._approval_types import (
        _session_approvals,
        _SessionApprovals,
        _tool_action_key,
        get_session_approvals,
    )

    # The re-exported aliases must be the same objects / types as the core ones.
    assert _SessionApprovals is SessionApprovals
    assert _session_approvals is session_approvals
    assert _tool_action_key is tool_action_key
    assert get_session_approvals() is session_approvals
