from typing import Any, cast

import pytest

from kagan.cli.chat import (
    SLASH_COMMAND_REGISTRY,
    ChatController,
    format_agent_backend_list,
    format_session_payload,
    parse_slash_invocation,
    resolve_agent_backend_selection,
    resolve_slash_input,
)
from kagan.cli.chat.controller import (
    _bootstrap_noninteractive_message,
    _bootstrap_repository_status,
)
from kagan.core import BackendSpec
from kagan.core.chat.sessions import (
    clean_generated_title as _clean_generated_title,
)
from kagan.core.chat.sessions import (
    format_relative_time as _format_relative_time,
)

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
        ["claude-code", "codex", "opencode"],
        current_backend="codex",
    )
    assert lines[0] == "Available agent backends:"
    assert any("Claude Code (claude-code) [reference]" in line for line in lines)
    assert any("Codex CLI (codex) [reference · current]" in line for line in lines)


def test_orchestrator_controller_rejects_non_acp_backends(monkeypatch) -> None:
    """Phase 5c: backend ACP-capability check now lives in the helper used by
    :class:`LongLivedACPFactory`. Driving it directly mirrors the path taken
    when the controller opens the factory.
    """
    from kagan.cli.chat import acp as cli_chat_acp

    monkeypatch.setattr(
        cli_chat_acp,
        "get_backend_spec",
        lambda _name: BackendSpec(name="custom-backend", executable="custom-backend"),
    )

    with pytest.raises(RuntimeError, match="does not support ACP"):
        cli_chat_acp._resolve_acp_command_for_backend("custom-backend")


def test_bootstrap_status_mentions_detected_git_root(tmp_path) -> None:
    git_root = tmp_path / "repo"
    git_root.mkdir()

    message = _bootstrap_repository_status(
        repo_path=str(git_root),
        git_root=git_root,
        auto_init_git=True,
    )

    assert "Detected git root" in message
    assert "Repository" in message
    assert str(git_root) in message


def test_bootstrap_status_mentions_core_git_init_for_non_git_folder(tmp_path) -> None:
    message = _bootstrap_repository_status(
        repo_path=str(tmp_path),
        git_root=None,
        auto_init_git=True,
    )

    assert "No git repository detected" in message
    assert "core will initialize git" in message
    assert "Project" in message
    assert "Repository" in message


def test_noninteractive_bootstrap_message_is_actionable(tmp_path) -> None:
    message = _bootstrap_noninteractive_message(
        repo_path=str(tmp_path),
        git_root=None,
        auto_init_git=True,
    )

    assert "No Kagan Project is linked" in message
    assert "kg chat" in message
    assert "kg tui" in message
    assert "Open Folder" in message
    assert "--project" not in message


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


def test_resolve_slash_input_quit_alias_requests_close() -> None:
    result = resolve_slash_input(
        "/quit",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code", "opencode"],
    )

    assert result.handled is True
    assert result.close_requested is True


def test_slash_command_registry_is_canonical() -> None:
    specs = SLASH_COMMAND_REGISTRY.specs()
    names = [spec.name for spec in specs]
    assert names == [
        "agents",
        "analytics",
        "approvals",
        "clear",
        "delete",
        "exit",
        "flow",
        "help",
        "new",
        "project",
        "repo",
        "sessions",
        "status",
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


async def save_chat_session(client: Any, session: dict[str, Any]) -> None:
    """Test helper — upsert a session dict via the aggregate's atomic path."""
    sid = str(session.get("id") or "").strip()
    if not sid:
        return
    history: list[tuple[str, str]] = []
    for pair in session.get("orchestrator_history") or []:
        if isinstance(pair, list | tuple) and len(pair) == 2:
            role = str(pair[0]).strip()
            content = str(pair[1]).strip()
            if role and content:
                history.append((role, content))
    raw_backend = session.get("agent_backend")
    backend: str | None = (
        raw_backend if isinstance(raw_backend, str) and raw_backend.strip() else None
    )
    raw_project = session.get("project_id")
    project: str | None = (
        raw_project if isinstance(raw_project, str) and raw_project.strip() else None
    )
    await client.chat_sessions.upsert_with_history(
        sid,
        label=str(session.get("label") or f"Session {sid[:8]}").strip(),
        source=str(session.get("source") or "repl") or "repl",
        agent_backend=backend,
        project_id=project,
        history=history,
    )


async def set_last_session_id(client: Any, *, scope: str, session_id: str) -> None:
    await client.chat_sessions.set_last_session_id(scope=scope, session_id=session_id)


async def delete_chat_session(client: Any, session_id: str) -> bool:
    return await client.chat_sessions.delete(session_id)


async def get_chat_session(client: Any, session_id: str) -> dict[str, Any] | None:
    pair = await client.chat_sessions.get_with_history(session_id)
    if pair is None:
        return None
    from kagan.cli.chat._session_picker import chat_session_to_legacy_dict

    return chat_session_to_legacy_dict(*pair)


def _make_test_engine():  # type: ignore[return]
    """Create a fully-migrated file-based SQLite engine for unit tests.

    File-based so asyncio.to_thread can access the same DB across threads.
    """
    import tempfile
    from pathlib import Path

    from kagan.core._db import create_db_engine

    tmpdir = tempfile.mkdtemp()
    return create_db_engine(Path(tmpdir) / "test.db")


class _FakeChatEngine:
    """Stub for ``client.chat`` — controller construction requires it.

    Records ``resolve_permission`` calls; the slash-command tests don't
    drive the engine, but the controller's ``__init__`` wires the engine
    into ``PermissionUI`` so the attribute must exist.
    """

    def __init__(self) -> None:
        self.resolve_calls: list[tuple[str, str, str, str | None]] = []

    async def resolve_permission(
        self,
        session_id: str,
        future_id: str,
        *,
        outcome: str,
        feedback: str | None = None,
    ) -> None:
        self.resolve_calls.append((session_id, future_id, outcome, feedback))


class _FakeClient:
    def __init__(self) -> None:
        from kagan.core.chat import ChatSessions

        self.settings = _FakeSettingsOps()
        self.active_project_id: str | None = None
        self._engine = _make_test_engine()
        self.chat = _FakeChatEngine()
        self.chat_sessions = ChatSessions(self._engine, self.settings)


@pytest.mark.asyncio
async def test_open_sessions_reattach_attaches_session(monkeypatch) -> None:
    """Reopening a session attaches it and restores orchestrator_history.

    messages_rendered is no longer stored so no transcript is reprinted —
    only the "Attached session" confirmation line is printed.
    """
    client = _FakeClient()
    await save_chat_session(
        client,
        {
            "id": "cfcee6c1",
            "label": "REPL cfcee6c1",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [["user", "hi"]],
            "messages_rendered": [],
        },
    )

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    should_restart = await controller._open_sessions("cfcee6c1")

    assert should_restart is False
    assert controller._chat_session_id == "cfcee6c1"
    # Session is confirmed as attached
    assert any("Attached session" in line for line in lines)
    # History is loaded — restored as rendered transcript lines
    assert len(controller._rendered_messages) == 1


@pytest.mark.asyncio
async def test_open_sessions_without_query_uses_picker_selection(monkeypatch) -> None:
    client = _FakeClient()
    await save_chat_session(
        client,
        {
            "id": "sess1111",
            "label": "REPL sess1111",
            "source": "repl",
            "agent_backend": "claude-code",
            "orchestrator_history": [["user", "hi"]],
            "messages_rendered": ["You: hi"],
        },
    )

    lines: list[str] = []

    async def _pick_session(title: str, options: list[Any]) -> str | None:
        assert title == "Select session"
        assert any(option.value == "sess1111" for option in options)
        return "sess1111"

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.cli.chat.controller.supports_interactive_picker", lambda: True)
    monkeypatch.setattr("kagan.cli.chat.controller.searchable_picker", _pick_session)
    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    should_restart = await controller._open_sessions(None)

    assert should_restart is False
    assert controller._chat_session_id == "sess1111"
    assert any("Attached session" in line for line in lines)


@pytest.mark.asyncio
async def test_open_sessions_cancelled_picker_keeps_current_session(monkeypatch) -> None:
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

    async def _cancel_picker(_title: str, _options: list[Any]) -> str | None:
        return None

    monkeypatch.setattr("kagan.cli.chat.controller.supports_interactive_picker", lambda: True)
    monkeypatch.setattr("kagan.cli.chat.controller.searchable_picker", _cancel_picker)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    controller._chat_session_id = "current123"

    should_restart = await controller._open_sessions(None)

    assert should_restart is False
    assert controller._chat_session_id == "current123"


@pytest.mark.asyncio
async def test_open_sessions_noninteractive_falls_back_to_static_list(monkeypatch) -> None:
    from io import StringIO

    from rich.console import Console as _RichConsole
    from rich.table import Table

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

    printed: list[Any] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            printed.append(args[0])

    monkeypatch.setattr("kagan.cli.chat.controller.supports_interactive_picker", lambda: False)
    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    should_restart = await controller._open_sessions(None)

    assert should_restart is False
    # Render Table objects to text to check content
    all_text: list[str] = []
    for item in printed:
        if isinstance(item, Table):
            buf = StringIO()
            c = _RichConsole(file=buf, width=120)
            c.print(item)
            all_text.append(buf.getvalue())
        else:
            all_text.append(str(item))
    assert any("claude-code" in t for t in all_text)


@pytest.mark.asyncio
async def test_handle_slash_agents_without_arg_uses_picker_selection(monkeypatch) -> None:
    client = _FakeClient()

    async def _pick_agent(title: str, options: list[Any]) -> str | None:
        assert title == "Select agent backend"
        assert any(option.value == "opencode" for option in options)
        return "opencode"

    selected: list[str] = []

    async def _switch_agent(backend: str) -> bool:
        selected.append(backend)
        return True

    monkeypatch.setattr(
        "kagan.cli.chat.controller.list_registered_agent_backends",
        lambda: ["claude-code", "opencode"],
    )
    monkeypatch.setattr("kagan.cli.chat.controller.supports_interactive_picker", lambda: True)
    monkeypatch.setattr("kagan.cli.chat.controller.searchable_picker", _pick_agent)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    monkeypatch.setattr(controller, "_switch_agent", _switch_agent)

    should_exit = await controller._handle_slash("/agents")

    assert should_exit is True
    assert selected == ["opencode"]


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

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

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
    from kagan.core.chat.sessions import TaskBinding

    client = _FakeClient()

    async def _fake_resolve_task_binding(self, session_id: str) -> TaskBinding | None:
        del self
        assert session_id == "tasksess"
        return TaskBinding(
            id="tasksess",
            label="Task tasksess - Investigate bug",
            source="task-session",
            agent_backend="claude-code",
            task_id="tasksess",
            status="open",
        )

    monkeypatch.setattr(
        "kagan.core.chat.ChatSessions.resolve_task_binding",
        _fake_resolve_task_binding,
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


def test_resolve_slash_input_delete_parses_correctly() -> None:
    result = resolve_slash_input(
        "/delete abc123",
        session_label="Orchestrator",
        session_key="orchestrator",
        runtime_session_id=None,
        current_backend="claude-code",
        available_backends=["claude-code"],
    )
    assert result.handled is True
    assert result.delete_session_query == "abc123"
    assert result.sessions_requested is False


def test_resolve_slash_input_delete_without_arg_errors() -> None:
    result = resolve_slash_input(
        "/delete",
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
        is_orchestrator=False,
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
    from io import StringIO

    from rich.console import Console as _RichConsole
    from rich.panel import Panel

    client = _FakeClient()
    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    printed: list[Any] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            printed.append(args[0])

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    should_exit = await controller._handle_slash("/help")

    assert should_exit is False
    assert any(isinstance(item, Panel) for item in printed)

    buffer = StringIO()
    console = _RichConsole(file=buffer, width=120)
    for item in printed:
        console.print(item)

    output = buffer.getvalue()
    assert "Help Guide" in output
    assert "/help" in output
    assert "/quit" in output
    assert "docs.kagan.sh" in output
