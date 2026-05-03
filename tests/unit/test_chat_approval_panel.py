"""Unit tests for the chat approval panel and arrow-key navigation logic."""

from __future__ import annotations

from typing import Any

import pytest

import kagan.cli.chat._permission_ui as chat_acp_module
from kagan.cli.chat._approval_panel import (
    _build_display_options,
    _extract_key_args_preview,
    _is_shell_command,
    _tool_display_name,
    build_approval_panel,
    strip_tool_prefix,
)
from kagan.cli.chat._permission_ui import (
    _map_decision_from_approval,
    _run_legacy_input,
    _session_approvals,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _approval_panel helpers
# ---------------------------------------------------------------------------


def teststrip_tool_prefix_removes_mcp_kagan_prefix() -> None:
    assert strip_tool_prefix("mcp__kagan__task_get") == "task get"


def teststrip_tool_prefix_removes_mcp_prefix() -> None:
    assert strip_tool_prefix("mcp__bash") == "bash"


def teststrip_tool_prefix_leaves_plain_names_unchanged() -> None:
    assert strip_tool_prefix("read_file") == "read file"


def test_tool_display_name_uses_title_attr() -> None:
    class _FakeCall:
        title = "mcp__kagan__run_get"
        name = None

    assert _tool_display_name(_FakeCall()) == "run get"


def test_tool_display_name_falls_back_to_name_attr() -> None:
    class _FakeCall:
        title = None
        name = "bash"

    assert _tool_display_name(_FakeCall()) == "bash"


def test_is_shell_command_detects_bash_keyword() -> None:
    class _FakeCall:
        title = "mcp__bash"
        name = None

    assert _is_shell_command(_FakeCall())


def test_is_shell_command_false_for_non_shell() -> None:
    class _FakeCall:
        title = "task_get"
        name = None

    assert not _is_shell_command(_FakeCall())


def test_extract_key_args_preview_returns_dict_lines() -> None:
    import json

    class _FakeCall:
        title = None
        name = None
        raw_input = json.dumps({"command": "ls -la", "cwd": "/tmp"})
        rawInput = None
        arguments = None
        args = None

    result = _extract_key_args_preview(_FakeCall())
    assert result is not None
    assert "command" in result
    assert "ls -la" in result


def test_extract_key_args_preview_truncates_long_values() -> None:
    import json

    class _FakeCall:
        title = None
        name = None
        raw_input = json.dumps({"long_key": "x" * 200})
        rawInput = None
        arguments = None
        args = None

    result = _extract_key_args_preview(_FakeCall())
    assert result is not None
    assert "..." in result


def test_build_display_options_always_returns_four_slots() -> None:
    result = _build_display_options()
    assert len(result) == 4
    assert result[0] == ("Approve once", "allow_once")
    assert result[1] == ("Approve for this session", "allow_always")
    assert result[2] == ("Reject", "reject_once")
    assert result[3] == ("Reject — tell the model what to do", "reject_feedback")


def test_build_approval_panel_highlights_selected_index() -> None:
    import io

    from rich.console import Console

    class _FakeCall:
        title = "mcp__kagan__task_get"
        name = None
        raw_input = None
        rawInput = None
        arguments = None
        args = None
        agent_id = None
        subagent_type = None
        source_description = None

    panel = build_approval_panel(
        _FakeCall(),
        selected_index=1,
        feedback_draft="",
        queue_depth=1,
        queue_position=1,
    )

    buf = io.StringIO()
    console = Console(file=buf, highlight=False, width=80, no_color=True)
    console.print(panel)
    output = buf.getvalue()

    # Selected index 1 should show arrow
    assert "→ [2]" in output
    # Non-selected should not have arrow prefix on first option
    assert "  [1]" in output


# ---------------------------------------------------------------------------
# _map_approval_result logic
# ---------------------------------------------------------------------------


def test_map_decision_allow_once_returns_decision() -> None:
    decision = _map_decision_from_approval(0, "", action_key="test_tool")
    assert decision.outcome == "allow_once"
    assert decision.feedback is None


def test_map_decision_allow_always_grants_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = type("_FC", (), {"print": lambda *a, **kw: None})()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)

    decision = _map_decision_from_approval(1, "", action_key="my_tool")
    assert decision.outcome == "allow_always"
    assert _session_approvals.is_allowed("my_tool")
    _session_approvals.revoke("my_tool")


def test_map_decision_reject_once_returns_deny() -> None:
    decision = _map_decision_from_approval(2, "", action_key="test_tool")
    assert decision.outcome == "deny"
    assert decision.feedback is None


def test_map_decision_reject_feedback_carries_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[str] = []
    monkeypatch.setattr(
        chat_acp_module.logger,
        "info",
        lambda msg, *args, **kw: logged.append(str(args[0]) if args else msg),
    )
    decision = _map_decision_from_approval(3, "please use a different file", action_key="test_tool")
    assert decision.outcome == "deny_feedback"
    assert decision.feedback == "please use a different file"
    assert any("please use a different file" in entry for entry in logged)


def test_map_decision_reject_feedback_empty_falls_back_to_deny() -> None:
    decision = _map_decision_from_approval(3, "", action_key="test_tool")
    assert decision.outcome == "deny"
    assert decision.feedback is None


# ---------------------------------------------------------------------------
# _run_legacy_input fallback
# ---------------------------------------------------------------------------


def test_run_legacy_input_enter_confirms_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty Enter with no prior selection confirms index 0."""
    inputs = iter([""])
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    class _FakeCall:
        title = "mcp__task_get"
        name = None
        raw_input = None
        rawInput = None
        arguments = None
        args = None
        agent_id = None
        subagent_type = None
        source_description = None

    class _Opt:
        kind = "allow_once"

    fake_console = type("_FC", (), {"print": lambda *a, **kw: None})()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)

    idx, fb = _run_legacy_input(
        _FakeCall(),
        permission_options=[_Opt()],
        queue_position=1,
        queue_depth=1,
    )
    assert idx == 0
    assert fb == ""


def test_run_legacy_input_number_selects_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["2"])
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    class _FakeCall:
        title = "task"
        name = None
        raw_input = None
        rawInput = None
        arguments = None
        args = None
        agent_id = None
        subagent_type = None
        source_description = None

    class _Opt:
        kind = "allow_once"

    fake_console = type("_FC", (), {"print": lambda *a, **kw: None})()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)

    idx, fb = _run_legacy_input(
        _FakeCall(),
        permission_options=[_Opt()],
        queue_position=1,
        queue_depth=1,
    )
    assert idx == 1


def test_run_legacy_input_eof_defaults_to_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise():
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)

    class _FakeCall:
        title = "task"
        name = None
        raw_input = None
        rawInput = None
        arguments = None
        args = None
        agent_id = None
        subagent_type = None
        source_description = None

    class _Opt:
        kind = "allow_once"

    fake_console = type("_FC", (), {"print": lambda *a, **kw: None})()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)

    idx, fb = _run_legacy_input(
        _FakeCall(),
        permission_options=[_Opt()],
        queue_position=1,
        queue_depth=1,
    )
    assert idx == 2  # reject


# ---------------------------------------------------------------------------
# _run_approval_panel_async — fallback to legacy on modal failure
# ---------------------------------------------------------------------------


async def test_run_approval_panel_falls_back_to_legacy_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the interactive modal raises, the legacy input() path is used."""

    async def _fail(*_a: Any, **_kw: Any) -> tuple[int, str]:
        raise RuntimeError("no terminal")

    monkeypatch.setattr(chat_acp_module, "_run_interactive_modal", _fail)

    inputs = iter(["1"])
    monkeypatch.setattr("builtins.input", lambda: next(inputs))

    class _FakeCall:
        title = "test_tool"
        name = None
        raw_input = None
        rawInput = None
        arguments = None
        args = None
        agent_id = None
        subagent_type = None
        source_description = None

    class _Opt:
        kind = "allow_once"

    fake_console = type("_FC", (), {"print": lambda *a, **kw: None})()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)

    idx, fb = await chat_acp_module._run_approval_panel_async(
        _FakeCall(),
        permission_options=[_Opt()],
        queue_position=1,
        queue_depth=1,
    )
    assert idx == 0
    assert fb == ""
