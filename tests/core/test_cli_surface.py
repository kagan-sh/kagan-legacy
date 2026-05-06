import importlib.util
import os
import subprocess
from asyncio import run as asyncio_run
from pathlib import Path

import pytest
from click.testing import CliRunner

from kagan.core import KaganCore
from kagan.cli.doctor import DoctorCheck
from kagan.cli.main import _sanitize_startup_environment, cli

_HAS_RICH_CLICK = importlib.util.find_spec("rich_click") is not None

pytestmark = [pytest.mark.core, pytest.mark.smoke]


def _runner_env(tmp_path: Path) -> dict[str, str]:
    return {
        "KAGAN_SKIP_UPDATE_CHECK": "1",
        "KAGAN_DATA_DIR": str(tmp_path),
        "KAGAN_CONFIG_DIR": str(tmp_path),
        "COLUMNS": "120",
        "KAGAN_INTEGRATION_TESTS": "",
    }


@pytest.mark.windows_ci
def test_help_surface_contains_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "chat" in result.output
    assert "doctor" in result.output
    assert "import" in result.output
    assert "list" in result.output
    assert "mcp" in result.output
    assert "reset" in result.output
    assert "tools" in result.output
    assert "tui" in result.output
    assert "update" in result.output
    assert "--skip-update-check" not in result.output
    assert "Usage:" in result.output
    assert "Options" in result.output
    assert "Commands" in result.output
    if _HAS_RICH_CLICK:
        assert "https://docs.kagan.sh/reference/cli/" in result.output


def test_version_flag_prints_version(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert result.output.strip()


def test_import_help_contains_github_subcommand(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["import", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "github" in result.output


def test_unknown_command_returns_usage_exit_code_2(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["unknown"], env=_runner_env(tmp_path))

    assert result.exit_code == 2


def test_bare_kagan_delegates_to_tui(monkeypatch, tmp_path: Path) -> None:
    called = []

    def fake_launch(**_kw) -> None:
        called.append(True)

    monkeypatch.setattr("kagan.cli.tui._launch_tui", fake_launch)
    runner = CliRunner()
    result = runner.invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert called


def _seed_surface_chooser_seen(
    tmp_path: Path,
    choice: str = "tui",
    *,
    startup_surface: str | None = None,
) -> None:
    client = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        asyncio_run(
            client.settings.set(
                {
                    "ui.surface_chooser_seen": "true",
                    "ui.surface_chooser_last_choice": choice,
                    "startup_default_surface": startup_surface or choice,
                }
            )
        )
    finally:
        client.close()


def _seed_project(tmp_path: Path, name: str = "Seed Project") -> None:
    client = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        asyncio_run(client.projects.create(name))
    finally:
        client.close()


def test_first_run_shows_surface_chooser_and_persists_choice(monkeypatch, tmp_path: Path) -> None:
    called = []

    def fake_launch(**_kw) -> None:
        called.append(True)

    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr("click.prompt", lambda *args, **kwargs: "tui")
    monkeypatch.setattr("kagan.cli.tui._launch_tui", fake_launch)

    runner = CliRunner()
    result = runner.invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "First launch - choose where to start" in result.output
    assert called

    client = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        settings = asyncio_run(client.settings.get())
    finally:
        client.close()
    assert settings["ui.surface_chooser_seen"] == "true"
    assert settings["ui.surface_chooser_last_choice"] == "tui"
    assert settings["startup_default_surface"] == "tui"


def test_first_run_web_choice_becomes_default_surface(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr("click.prompt", lambda *args, **kwargs: "web")
    monkeypatch.setattr(
        "kagan.cli.main._dispatch_surface_choice",
        lambda _ctx, choice: captured.setdefault("choice", choice),
    )

    result = CliRunner().invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert captured["choice"] == "web"

    client = KaganCore(db_path=tmp_path / "kagan.db")
    try:
        settings = asyncio_run(client.settings.get())
    finally:
        client.close()
    assert settings["startup_default_surface"] == "web"


def test_surface_chooser_is_skipped_after_choice_saved(monkeypatch, tmp_path: Path) -> None:
    called = []

    def fake_launch(**_kw) -> None:
        called.append(True)

    _seed_surface_chooser_seen(tmp_path)
    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr(
        "click.prompt", lambda *args, **kwargs: pytest.fail("prompt should not run")
    )
    monkeypatch.setattr("kagan.cli.tui._launch_tui", fake_launch)

    result = CliRunner().invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert called
    assert "First launch - choose where to start" not in result.output


def test_saved_startup_surface_is_used_for_bare_kagan(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    _seed_surface_chooser_seen(tmp_path, choice="web", startup_surface="web")
    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr(
        "click.prompt", lambda *args, **kwargs: pytest.fail("prompt should not run")
    )
    monkeypatch.setattr(
        "kagan.cli.main._dispatch_surface_choice",
        lambda _ctx, choice: captured.setdefault("choice", choice),
    )

    result = CliRunner().invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert captured["choice"] == "web"


def test_startup_surface_ask_reopens_surface_chooser(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    _seed_surface_chooser_seen(tmp_path, startup_surface="ask")
    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr("click.prompt", lambda *args, **kwargs: "chat")
    monkeypatch.setattr(
        "kagan.cli.main._dispatch_surface_choice",
        lambda _ctx, choice: captured.setdefault("choice", choice),
    )

    result = CliRunner().invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "First launch - choose where to start" in result.output
    assert captured["choice"] == "chat"


def test_surface_chooser_is_skipped_when_projects_exist(monkeypatch, tmp_path: Path) -> None:
    called = []

    def fake_launch(**_kw) -> None:
        called.append(True)

    _seed_project(tmp_path)
    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr(
        "click.prompt", lambda *args, **kwargs: pytest.fail("prompt should not run")
    )
    monkeypatch.setattr("kagan.cli.tui._launch_tui", fake_launch)

    result = CliRunner().invoke(cli, [], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert called
    assert "First launch - choose where to start" not in result.output


def test_explicit_subcommand_bypasses_surface_chooser(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("kagan.cli.main._surface_chooser_available", lambda: True)
    monkeypatch.setattr(
        "click.prompt", lambda *args, **kwargs: pytest.fail("prompt should not run")
    )

    result = CliRunner().invoke(cli, ["web", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Open the Kagan web UI in your browser." in result.output


def test_tui_help_lists_session_attach_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tui", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "-s" in result.output
    assert "--session-id" in result.output


def test_tui_session_id_is_forwarded_to_app_launch(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, str | None] = {}

    def _fake_launch(
        *,
        db_path: str | Path | None = None,
        startup_chat_session_id: str | None = None,
        startup_checks: object = None,
    ) -> None:
        del db_path, startup_checks
        captured["session_id"] = startup_chat_session_id

    monkeypatch.setattr("kagan.cli.tui._launch_tui", _fake_launch)
    monkeypatch.setattr("kagan.cli.tui._collect_startup_checks", lambda **_kw: [])

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["tui", "-s", "tui12345"],
        env=_runner_env(tmp_path),
    )

    assert result.exit_code == 0
    assert captured["session_id"] == "tui12345"


def test_doctor_short_warns_exit_zero(monkeypatch, tmp_path: Path) -> None:
    checks = [
        DoctorCheck("git", "pass", "ok", "", "git --version"),
        DoctorCheck("tmux", "warn", "missing", "install", "tmux -V"),
    ]
    monkeypatch.setattr("kagan.cli.doctor._collect_doctor_checks", lambda: checks)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "WARN" in result.output


def test_doctor_short_collapses_optional_backend_warnings(monkeypatch, tmp_path: Path) -> None:
    checks = [
        DoctorCheck("git", "pass", "git found", "", "git --version"),
        DoctorCheck(
            "agent backends",
            "pass",
            "Default backend 'claude-code' ready - 1/3 backends installed",
            "",
            "claude --version",
            category="backend",
        ),
        DoctorCheck(
            "backend: claude-code (default)",
            "pass",
            "found",
            "",
            "claude --version",
            category="backend",
        ),
        DoctorCheck(
            "backend: codex",
            "warn",
            "missing",
            "Install 'codex' to enable the 'codex' backend",
            "codex --version",
            category="backend",
        ),
        DoctorCheck(
            "backend: gemini-cli",
            "warn",
            "missing",
            "Install 'gemini' to enable the 'gemini-cli' backend",
            "gemini --version",
            category="backend",
        ),
    ]
    monkeypatch.setattr("kagan.cli.doctor._collect_doctor_checks", lambda: checks)

    result = CliRunner().invoke(cli, ["doctor"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Agent backends" in result.output
    assert "Optional missing:" in result.output
    assert "codex, gemini-cli" in result.output
    assert "Install 'codex'" not in result.output
    assert "Install 'gemini'" not in result.output


def test_doctor_short_keeps_required_quick_fixes(monkeypatch, tmp_path: Path) -> None:
    checks = [
        DoctorCheck("git", "pass", "git found", "", "git --version"),
        DoctorCheck("tmux", "warn", "tmux missing", "Use an IDE launcher", "tmux -V"),
        DoctorCheck(
            "project config",
            "warn",
            "pyproject.toml not found",
            "Run this command from your project root",
            "test -f pyproject.toml",
        ),
    ]
    monkeypatch.setattr("kagan.cli.doctor._collect_doctor_checks", lambda: checks)

    result = CliRunner().invoke(cli, ["doctor"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Required environment" in result.output
    assert "Use an IDE launcher" in result.output
    assert "Run this command from your project root" in result.output


def test_doctor_fail_exits_one(monkeypatch, tmp_path: Path) -> None:
    checks = [
        DoctorCheck("db", "fail", "broken", "fix", "kagan list"),
    ]
    monkeypatch.setattr("kagan.cli.doctor._collect_doctor_checks", lambda: checks)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--verbosity", "tldr"], env=_runner_env(tmp_path))

    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_list_exits_zero_on_empty_state(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Project" in result.output


def test_mcp_mutually_exclusive_flags_is_usage_error(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "--readonly", "--admin"], env=_runner_env(tmp_path))

    assert result.exit_code == 2


def test_mcp_help_includes_access_tier_guidance(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Agent roles:" in result.output
    assert "--role" in result.output


def test_web_help_does_not_mark_admin_as_default(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["web", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Admin access tier (default: on)" not in result.output


@pytest.mark.parametrize("source_mode", ["prompt", "file"])
def test_tools_enhance_full_flow_outputs_refined_result(
    monkeypatch,
    tmp_path: Path,
    source_mode: str,
) -> None:
    prompt = "stabilize cli tests"
    expected = "As a QA engineer, stabilize CLI tests with deterministic assertions."
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text(f"  {prompt}  ", encoding="utf-8")
    args = ["tools", "enhance", "--agent", "kimi", prompt]
    if source_mode == "file":
        args = ["tools", "enhance", "--agent", "kimi", "--file", str(prompt_file)]

    def _fake_run(
        command: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str] | None = None,
    ):
        assert command[0] == "kimi" and capture_output and text and not check
        assert env is not None
        return subprocess.CompletedProcess(
            command, 0, stdout=f"<result>{expected}</result>", stderr=""
        )

    monkeypatch.setattr("kagan.cli.tools.subprocess.run", _fake_run)
    result = CliRunner().invoke(cli, args, env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert expected in result.output


def test_tools_help_lists_prompts_subcommand(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "enhance" in result.output
    assert "prompts" in result.output


@pytest.mark.parametrize("source_mode", ["prompt", "file"])
def test_tools_enhance_full_flow_falls_back_to_original_on_short_agent_result(
    monkeypatch,
    tmp_path: Path,
    source_mode: str,
) -> None:
    prompt = "improve validation behavior"
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text(f"  {prompt}  ", encoding="utf-8")
    args = ["tools", "enhance", "--agent", "kimi", prompt]
    if source_mode == "file":
        args = ["tools", "enhance", "--agent", "kimi", "--file", str(prompt_file)]

    def _fake_run(
        command: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str] | None = None,
    ):
        assert command[0] == "kimi" and capture_output and text and not check
        assert env is not None
        return subprocess.CompletedProcess(command, 0, stdout="<result>ok</result>", stderr="")

    monkeypatch.setattr("kagan.cli.tools.subprocess.run", _fake_run)
    result = CliRunner().invoke(cli, args, env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert prompt in result.output


def test_chat_prompt_single_shot_prints_response(monkeypatch, tmp_path: Path) -> None:
    """Single-shot chat with no projects prints a helpful message and exits 0."""
    # chdir to tmp_path so _bootstrap_project doesn't find the repo git root
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "--prompt", "hello"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "project" in result.output.lower() or "hello" in result.output


def test_chat_positional_prompt_is_single_shot(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, str | None] = {}

    async def _fake_run_chat_async(
        *,
        prompt: str | None = None,
        session_id: str | None = None,
        agent: str | None = None,
        yolo: bool = False,
    ) -> None:
        captured["prompt"] = prompt
        captured["session_id"] = session_id
        captured["agent"] = agent
        captured["yolo"] = yolo

    monkeypatch.setattr("kagan.cli.chat.run_chat_async", _fake_run_chat_async)

    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "fix the bug"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert captured == {
        "prompt": "fix the bug",
        "session_id": None,
        "agent": None,
        "yolo": False,
    }


def test_chat_rejects_positional_prompt_with_prompt_option(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["chat", "fix the bug", "--prompt", "other"],
        env=_runner_env(tmp_path),
    )

    assert result.exit_code != 0
    assert "Use either PROMPT or --prompt" in result.output


def test_chat_ctrl_c_exits_one(monkeypatch, tmp_path: Path) -> None:
    def _raise_keyboard_interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("kagan.cli.chat.run_chat_async", _raise_keyboard_interrupt)

    runner = CliRunner()
    result = runner.invoke(cli, ["chat"], env=_runner_env(tmp_path))

    assert result.exit_code == 1


def test_web_ctrl_c_exits_cleanly(monkeypatch, tmp_path: Path) -> None:
    def _raise_keyboard_interrupt(coro):
        coro.close()
        raise KeyboardInterrupt

    # CLI does `from kagan.server import has_web_bundle` (public re-export
    # since R4); patch the bound name in the consumer module.
    monkeypatch.setattr("kagan.cli.web.has_web_bundle", lambda: True, raising=False)
    monkeypatch.setattr("kagan.server.has_web_bundle", lambda: True)
    monkeypatch.setattr("kagan.cli.web._is_server_running", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("kagan.cli.web.run_async", _raise_keyboard_interrupt)

    runner = CliRunner()
    result = runner.invoke(cli, ["web", "--no-open", "--port", "9999"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Stopping Kagan web dashboard" in result.output
    assert "Aborted!" not in result.output


def test_chat_help_uses_structured_options_panel(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["chat", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "chat" in result.output
    assert "Options" in result.output
    assert "--prompt" in result.output and "TEXT" in result.output
    assert "--session-id" in result.output and "TEXT" in result.output
    assert "--agent" in result.output and "TEXT" in result.output


def test_reset_force_completes_without_confirmation(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["reset", "--force"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Reset complete" in result.output


def test_update_check_only_reports_status(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "kagan.cli.update.check_and_install_update",
        lambda check_only, prerelease, force: (True, "Update available: 0.1.0 -> 0.2.0"),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--check-only"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "Update available" in result.output


def test_startup_update_hint_prints_before_command_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("kagan.cli.main.maybe_check_for_updates", lambda skip: "9.9.9")

    runner = CliRunner()
    result = runner.invoke(cli, ["list"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert lines[0].startswith("hint: kagan 9.9.9 available")


def test_sanitize_startup_environment_removes_macos_malloc_keys(monkeypatch) -> None:
    monkeypatch.setattr("kagan.cli._env.sys.platform", "darwin")
    monkeypatch.setenv("MALLOCSTACKLOGGING", "1")
    monkeypatch.setenv("MALLOCSTACKLOGGINGNOCOMPACT", "1")
    monkeypatch.setenv("MALLOCSTACKLOGGINGDIRECTORY", "/tmp/msl")
    monkeypatch.setenv("__XPC_MALLOCSTACKLOGGING", "1")

    _sanitize_startup_environment()

    assert os.environ.get("MALLOCSTACKLOGGING") is None
    assert os.environ.get("MALLOCSTACKLOGGINGNOCOMPACT") is None
    assert os.environ.get("MALLOCSTACKLOGGINGDIRECTORY") is None
    assert os.environ.get("__XPC_MALLOCSTACKLOGGING") is None


def test_tools_prompts_help_lists_export_subcommand(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "prompts", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "export" in result.output


def test_tools_prompts_export_writes_valid_yml_to_stdout(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["tools", "prompts", "export", "--type", "orchestrator"], env=_runner_env(tmp_path)
    )

    assert result.exit_code == 0
    assert "name: kagan-orchestrator" in result.output
    assert "model:" in result.output
    assert "messages:" in result.output


def test_tools_prompts_export_writes_file(tmp_path: Path) -> None:
    dest = tmp_path / "out.prompt.yml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["tools", "prompts", "export", "--type", "review", "-o", str(dest)],
        env=_runner_env(tmp_path),
    )

    assert result.exit_code == 0
    assert dest.exists()
    assert "kagan-review" in dest.read_text()


def test_tools_prompts_export_text_format_outputs_raw_prompt(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["tools", "prompts", "export", "--type", "orchestrator", "--format", "text"],
        env=_runner_env(tmp_path),
    )

    assert result.exit_code == 0
    # Raw text should NOT have YAML structure
    assert "name:" not in result.output
    assert "messages:" not in result.output
    # But SHOULD have actual prompt content
    assert "kagan" in result.output.lower()


def test_root_cli_no_longer_exposes_prompt_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["prompts", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 2
    assert "No such command 'prompts'" in result.output


def test_crash_footer_mentions_kagan_doctor(monkeypatch, tmp_path: Path) -> None:
    """Crash footer must tell users to run `kagan doctor` for self-diagnosis."""
    from kagan.core.errors import KaganError

    def _raise_kagan_error(*_args, **_kwargs):
        raise KaganError("simulated failure")

    monkeypatch.setattr("kagan.cli.tui._launch_tui", _raise_kagan_error)
    monkeypatch.setattr("kagan.cli.tui._collect_startup_checks", lambda **_kw: [])

    runner = CliRunner(mix_stderr=True)
    result = runner.invoke(cli, ["tui"], env=_runner_env(tmp_path))

    assert result.exit_code != 0
    combined = result.output
    assert "kagan doctor" in combined


def test_tools_help_describes_subcommands_inline(tmp_path: Path) -> None:
    """kagan tools --help must list subcommands and their purpose without traversal."""
    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "--help"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert "enhance" in result.output
    assert "prompts" in result.output
    # The updated docstring describes the commands inline
    assert "Stateless utilities" in result.output


@pytest.mark.xfail(
    reason=(
        "Click CliRunner does not simulate an interactive TTY so the REPL banner "
        "interactive hint line cannot be exercised without a real terminal."
    ),
    strict=False,
)
def test_chat_interactive_banner_contains_help_hint(monkeypatch, tmp_path: Path) -> None:
    """Interactive REPL banner must include /help and Ctrl-C guidance."""
    captured_kwargs: dict = {}

    def _fake_write_boot_banner(*args, **kwargs):
        captured_kwargs.update(kwargs)

    monkeypatch.setattr("kagan.cli.chat.repl._write_boot_banner", _fake_write_boot_banner)

    async def _fake_run_chat_async(*, prompt=None, session_id=None, agent=None, yolo=False):
        # Simulate interactive call: no prompt
        from kagan.cli.chat.repl import _write_boot_banner

        _write_boot_banner(interactive=prompt is None)

    monkeypatch.setattr("kagan.cli.chat.run_chat_async", _fake_run_chat_async)

    runner = CliRunner()
    result = runner.invoke(cli, ["chat"], env=_runner_env(tmp_path))

    assert result.exit_code == 0
    assert captured_kwargs.get("interactive") is True
