from typing import Any, cast

import pytest
from rich.panel import Panel

from kagan.chat import (
    SLASH_COMMAND_REGISTRY,
    ChatController,
    delete_chat_session,
    format_agent_backend_list,
    format_session_payload,
    parse_slash_invocation,
    resolve_agent_backend_selection,
    resolve_slash_input,
    save_chat_session,
    set_last_session_id,
)
from kagan.chat.sessions import _clean_generated_title, _format_relative_time

pytestmark = [pytest.mark.unit]


def test_format_session_payload_includes_session_descriptor_and_runtime() -> None:
    descriptor, runtime = format_session_payload(
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id="abc12345",
    )
    assert descriptor == "Session: Orchestrator (orchestrator)"
    assert runtime == "Runtime session id: abc12345"


def test_format_agent_backend_list_marks_current_backend() -> None:
    lines = format_agent_backend_list(
        ["claude-code", "opencode"],
        current_backend="opencode",
    )
    assert lines[0] == "Available agent backends:"
    assert any("opencode ◀ current" in line for line in lines)


def test_resolve_agent_backend_selection_accepts_index_and_prefix() -> None:
    backends = ["claude-code", "opencode", "sisyphus"]
    by_index, by_index_error = resolve_agent_backend_selection("2", backends)
    by_prefix, by_prefix_error = resolve_agent_backend_selection("sis", backends)
    assert (by_index, by_index_error) == ("opencode", None)
    assert (by_prefix, by_prefix_error) == ("sisyphus", None)


def test_resolve_agent_backend_selection_reports_ambiguous_and_unknown() -> None:
    backends = ["kimi", "kimi-code", "opencode"]
    ambiguous, ambiguous_error = resolve_agent_backend_selection("kim", backends)
    unknown, unknown_error = resolve_agent_backend_selection("ghost", backends)
    assert ambiguous is None and ambiguous_error is not None
    assert unknown is None and unknown_error is not None


def test_resolve_slash_input_help_and_unknown_are_structured() -> None:
    help_result = resolve_slash_input(
        "/help",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )
    unknown_result = resolve_slash_input(
        "/ghost",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert help_result.handled is True
    assert help_result.help_overlay_requested is True
    assert unknown_result.handled is True
    assert any("Unknown command" in line for line in unknown_result.error_lines)


def test_slash_command_registry_is_canonical() -> None:
    specs = SLASH_COMMAND_REGISTRY.specs()
    names = [spec.name for spec in specs]
    assert names == [
        "agents",
        "clear",
        "exit",
        "flow",
        "help",
        "new",
        "session",
        "sessions",
        "tool",
    ]
    assert SLASH_COMMAND_REGISTRY.get("help") is not None
    assert SLASH_COMMAND_REGISTRY.get("flow") is not None
    assert SLASH_COMMAND_REGISTRY.get("sessions") is not None
    assert SLASH_COMMAND_REGISTRY.get("tool") is not None
    assert SLASH_COMMAND_REGISTRY.get("ghost") is None


def test_parse_slash_invocation_contract_lowercases_name_and_strips_argument() -> None:
    parsed = parse_slash_invocation("  /AGENTS   opencode  ")
    assert parsed is not None
    assert parsed.name == "agents"
    assert parsed.arg == "opencode"
    assert parse_slash_invocation("hello") is None


def test_resolve_slash_input_agents_selection_and_legacy_mode_removed() -> None:
    mode_result = resolve_slash_input(
        "/mode plan",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )
    legacy_agent_result = resolve_slash_input(
        "/agent 2",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )
    agent_result = resolve_slash_input(
        "/agents 2",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert mode_result.handled is True
    assert any("Unknown command" in line for line in mode_result.error_lines)
    assert legacy_agent_result.handled is True
    assert any("Unknown command" in line for line in legacy_agent_result.error_lines)
    assert agent_result.selected_agent == "opencode"
    assert agent_result.info_lines == ()


def test_resolve_slash_input_agents_lists_registered_backends() -> None:
    agents_result = resolve_slash_input(
        "/agents",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert agents_result.handled is True
    assert agents_result.selected_agent is None
    assert agents_result.agent_picker_requested is True


def test_resolve_slash_input_bare_slash_falls_back_to_help() -> None:
    result = resolve_slash_input(
        "/",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert result.handled is True
    assert result.help_overlay_requested is True


def test_resolve_slash_input_sessions_requests_session_management() -> None:
    sessions_result = resolve_slash_input(
        "/sessions 2",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert sessions_result.handled is True
    assert sessions_result.sessions_requested is True
    assert sessions_result.sessions_query == "2"


class _FakeSettingsOps:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self) -> dict[str, str]:
        return dict(self._store)

    async def set(self, updates: dict[str, str]) -> None:
        self._store.update(updates)

    async def update(self, updates: dict[str, str]) -> None:
        self._store.update(updates)


class _FakeClient:
    def __init__(self) -> None:
        self.settings = _FakeSettingsOps()


@pytest.mark.asyncio
async def test_open_sessions_reattach_prints_restored_transcript(monkeypatch) -> None:
    client = _FakeClient()
    await save_chat_session(
        client,
        {
            "id": "cfcee6c1",
            "label": "REPL cfcee6c1",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [["user", "hi"]],
            "messages_rendered": ["You: hi", "Agent: hello"],
        },
    )

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    should_restart = await controller._open_sessions("cfcee6c1")

    assert should_restart is False
    assert any("Resumed transcript" in line for line in lines)
    assert any("You: hi" in line for line in lines)


@pytest.mark.asyncio
async def test_open_sessions_list_includes_agent_backend(monkeypatch) -> None:
    client = _FakeClient()
    await save_chat_session(
        client,
        {
            "id": "sess1111",
            "label": "REPL sess1111",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [],
            "messages_rendered": [],
        },
    )

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    should_restart = await controller._open_sessions(None)

    assert should_restart is False
    assert any("claude-code" in line for line in lines)


def test_resolve_slash_input_new_requests_new_session() -> None:
    result = resolve_slash_input(
        "/new",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert result.handled is True
    assert result.new_session_requested is True
    assert result.error_lines == ()


@pytest.mark.asyncio
async def test_create_new_session_creates_fresh_session(monkeypatch) -> None:
    client = _FakeClient()
    # Seed an existing session
    await save_chat_session(
        client,
        {
            "id": "old12345",
            "label": "REPL old12345",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [["user", "old message"]],
            "messages_rendered": ["You: old message"],
        },
    )

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    should_restart = await controller._create_new_session()

    assert should_restart is False
    assert controller._chat_session_id is not None
    assert controller._chat_session_id != "old12345"
    assert any("New session" in line for line in lines)


@pytest.mark.asyncio
async def test_resolve_initial_session_returns_none_without_explicit_id() -> None:
    """Startup always creates a fresh session (no auto-restore of last session)."""
    client = _FakeClient()
    # Seed a session and mark it as last
    await save_chat_session(
        client,
        {
            "id": "prev1234",
            "label": "REPL prev1234",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [],
            "messages_rendered": [],
        },
    )

    await set_last_session_id(client, scope="repl", session_id="prev1234")

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    result = await controller._resolve_initial_session(None)

    # Should return None — forces hydrate_persistent_session to create a fresh session
    assert result is None


@pytest.mark.asyncio
async def test_resolve_initial_session_uses_task_session_binding(monkeypatch) -> None:
    client = _FakeClient()

    async def _fake_resolve_task_session_binding(
        _client: Any, session_id: str
    ) -> dict[str, Any] | None:
        assert session_id == "tasksess"
        return {
            "id": "tasksess",
            "label": "Task tasksess - Investigate bug",
            "source": "task-session",
            "agent_backend": "claude-code",
            "orchestrator_history": [],
            "messages_rendered": [],
        }

    monkeypatch.setattr(
        "kagan.chat.controller.resolve_task_session_binding",
        _fake_resolve_task_session_binding,
    )

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    result = await controller._resolve_initial_session("tasksess")

    assert result is not None
    assert result["id"] == "tasksess"
    assert result["source"] == "task-session"


@pytest.mark.asyncio
async def test_attach_task_scoped_session_does_not_persist_repl_state() -> None:
    client = _FakeClient()
    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    await controller._attach_session(
        {
            "id": "tasksess",
            "label": "Task tasksess - Investigate bug",
            "source": "task-session",
            "agent_backend": "claude-code",
            "orchestrator_history": [],
            "messages_rendered": [],
        },
        switching=False,
    )

    settings = await client.settings.get()
    assert "chat_sessions_v1" not in settings
    assert "chat_last_session_repl" not in settings


@pytest.mark.asyncio
async def test_delete_chat_session_removes_session() -> None:
    client = _FakeClient()
    await save_chat_session(
        client,
        {
            "id": "del12345",
            "label": "Doomed session",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [],
            "messages_rendered": [],
        },
    )

    deleted = await delete_chat_session(client, "del12345")
    assert deleted is True

    from kagan.chat import get_chat_session

    result = await get_chat_session(client, "del12345")
    assert result is None


@pytest.mark.asyncio
async def test_delete_chat_session_returns_false_for_missing() -> None:
    client = _FakeClient()
    deleted = await delete_chat_session(client, "nonexist")
    assert deleted is False


def test_clean_generated_title_strips_think_tags_and_quotes() -> None:
    assert _clean_generated_title('"My Session Title"') == "My Session Title"
    assert _clean_generated_title("<think>reasoning</think>Real Title") == "Real Title"
    assert _clean_generated_title("Multi\nLine\nTitle") == "Multi"
    assert _clean_generated_title("") == ""
    long = "A" * 200
    assert len(_clean_generated_title(long)) <= 80


def test_format_relative_time_handles_recent_and_old() -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC).isoformat()
    assert _format_relative_time(now) == "just now"

    five_min_ago = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert _format_relative_time(five_min_ago) == "5m ago"

    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    assert _format_relative_time(two_hours_ago) == "2h ago"

    three_days_ago = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    assert _format_relative_time(three_days_ago) == "3d ago"

    assert _format_relative_time("invalid") == ""


def test_resolve_slash_input_sessions_delete_parses_correctly() -> None:
    result = resolve_slash_input(
        "/sessions delete abc123",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )
    assert result.handled is True
    assert result.delete_session_query == "abc123"
    assert result.sessions_requested is False


def test_resolve_slash_input_sessions_delete_without_arg_errors() -> None:
    result = resolve_slash_input(
        "/sessions delete",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )
    assert result.handled is True
    assert result.delete_session_query is None
    assert any("Usage" in line for line in result.error_lines)


def test_resolve_slash_input_tool_without_id_requests_tool_listing() -> None:
    result = resolve_slash_input(
        "/tool",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )

    assert result.handled is True
    assert result.tool_requested is True
    assert result.tool_query is None


def test_resolve_slash_input_tool_with_id_requests_tool_details() -> None:
    result = resolve_slash_input(
        "/tool t007",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )

    assert result.handled is True
    assert result.tool_requested is True
    assert result.tool_query == "t007"


def test_resolve_slash_input_flow_returns_guided_phases() -> None:
    result = resolve_slash_input(
        "/flow Build onboarding",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )

    assert result.handled is True
    assert any("Plan -> Execute -> Orchestrate" in line for line in result.info_lines)
    assert any(line.startswith("Goal: Build onboarding") for line in result.info_lines)


def test_resolve_slash_input_flow_rejected_in_non_orchestrator_session() -> None:
    """/flow should be rejected in non-orchestrator sessions (e.g., task agents)."""
    result = resolve_slash_input(
        "/flow Build onboarding",
        session_label="Task Agent",
        session_key="task-abc123",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )

    assert result.handled is True
    assert any("only available in orchestrator sessions" in line for line in result.error_lines)


def test_flow_command_is_orchestrator_only() -> None:
    """The /flow command spec should have orchestrator_only=True."""
    flow_cmd = SLASH_COMMAND_REGISTRY.get("flow")
    assert flow_cmd is not None
    assert flow_cmd.spec.orchestrator_only is True


def test_slash_command_registry_filters_by_orchestrator_only() -> None:
    """specs() should filter by orchestrator_only flag when requested."""
    all_specs = SLASH_COMMAND_REGISTRY.specs()
    orchestrator_only_specs = SLASH_COMMAND_REGISTRY.specs(orchestrator_only=True)
    non_orchestrator_specs = SLASH_COMMAND_REGISTRY.specs(orchestrator_only=False)

    # /flow should be the only orchestrator-only command
    assert any(spec.name == "flow" for spec in all_specs)
    assert any(spec.name == "flow" for spec in orchestrator_only_specs)
    assert not any(spec.name == "flow" for spec in non_orchestrator_specs)

    # Other commands should not be orchestrator-only
    assert any(spec.name == "help" for spec in non_orchestrator_specs)
    assert not any(spec.name == "help" for spec in orchestrator_only_specs)


@pytest.mark.asyncio
async def test_handle_slash_help_prints_structured_help_documentation(monkeypatch) -> None:
    client = _FakeClient()
    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    printed: list[Any] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            printed.append(args[0])

    monkeypatch.setattr("kagan.chat.repl._console.print", _capture_print)

    should_exit = await controller._handle_slash("/help")

    assert should_exit is False
    panels = [item for item in printed if isinstance(item, Panel)]
    panel_titles = {str(panel.title) for panel in panels}
    assert "kagan chat" in panel_titles
    assert "Commands" in panel_titles
    assert "Quick refs" in panel_titles
    assert any(
        isinstance(item, str) and "Documentation: https://docs.kagan.sh/" in item
        for item in printed
    )
