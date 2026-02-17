"""CLI preflight tests for TUI pair-terminal backend, detect_issues, and core auto-start."""

from __future__ import annotations

import platform
import shutil
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from kagan.core.config import KaganConfig
from kagan.core.preflight import IssueType, detect_issues

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_IS_WINDOWS = platform.system() == "Windows"


def _mock_which(mapping: dict[str, str | None]) -> Callable[[str | None], str | None]:
    def _which(cmd: str | None) -> str | None:
        if cmd is None:
            return None
        return mapping.get(cmd.lower())

    return _which


def test_tui_preflight_uses_configured_pair_terminal_backend(
    monkeypatch,
    tmp_path,
) -> None:
    import kagan.cli.commands.tui as tui_command
    from kagan import __main__ as cli_main

    captured: dict[str, object] = {}

    async def fake_detect_issues(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(issues=[])

    class _FakeApp:
        run_called = False

        def __init__(self, db_path: str) -> None:
            self.db_path = db_path

        def run(self) -> None:
            _FakeApp.run_called = True

    config = KaganConfig()
    config.general.default_pair_terminal_backend = "tmux"

    monkeypatch.setattr(tui_command, "_check_for_updates_gate", lambda: None)
    monkeypatch.setattr(tui_command, "_auto_cleanup_done_workspaces", lambda _db: None)
    monkeypatch.setattr(tui_command, "_ensure_core_ready_for_cli", lambda _db: None)
    monkeypatch.setattr(tui_command, "_display_agent_status", lambda: {"claude": True})
    monkeypatch.setattr("kagan.core.config.KaganConfig.load", lambda _path=None: config)
    monkeypatch.setattr("kagan.core.preflight.detect_issues", fake_detect_issues)
    monkeypatch.setattr(
        "kagan.core.builtin_agents.get_first_available_agent",
        lambda: SimpleNamespace(
            config=SimpleNamespace(name="Claude"),
            install_command="install",
        ),
    )
    monkeypatch.setattr("kagan.tui.app.KaganApp", _FakeApp)

    callback = cast("Any", cli_main.tui.callback)
    callback(
        db=str(tmp_path / "kagan.db"),
        skip_preflight=False,
        skip_update_check=True,
    )

    assert captured["default_pair_terminal_backend"] == "tmux"
    assert _FakeApp.run_called is True


@pytest.mark.skipif(_IS_WINDOWS, reason="On Windows tmux defaults are overridden to vscode/cursor")
async def test_detect_issues_defaults_to_tmux_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", _mock_which({}))

    result = await detect_issues(check_git=False, check_terminal=False)

    assert len(result.issues) == 1
    assert result.issues[0].preset.type == IssueType.TMUX_MISSING
    assert result.has_blocking_issues is False


@pytest.mark.skipif(_IS_WINDOWS, reason="On Windows tmux defaults are overridden to vscode/cursor")
async def test_detect_issues_warns_for_tmux_only_when_tmux_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        shutil, "which", _mock_which({"code": "/usr/bin/code", "code.exe": "/usr/bin/code"})
    )

    result = await detect_issues(
        check_git=False,
        check_terminal=False,
        pair_terminal_backend="tmux",
        default_pair_terminal_backend="vscode",
    )

    assert len(result.issues) == 1
    assert result.issues[0].preset.type == IssueType.TMUX_MISSING


@pytest.mark.mock_platform_system("Windows")
async def test_detect_issues_windows_resolves_vscode_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shutil,
        "which",
        _mock_which({"code.exe": r"C:\Program Files\Microsoft VS Code\bin\code.exe"}),
    )

    result = await detect_issues(check_git=False, check_terminal=False)

    assert result.issues == []


@pytest.mark.mock_platform_system("Windows")
async def test_detect_issues_windows_missing_vscode_and_cursor_has_no_pair_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", _mock_which({}))

    result = await detect_issues(check_git=False, check_terminal=False)

    assert result.issues == []


@pytest.mark.mock_platform_system("Windows")
async def test_detect_issues_windows_tmux_prefers_vscode_cursor_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", _mock_which({}))

    result = await detect_issues(
        check_git=False,
        check_terminal=False,
        pair_terminal_backend="tmux",
    )

    assert result.issues == []


def test_tui_autostarts_core_before_app_run(monkeypatch, tmp_path: Path) -> None:
    """`kagan tui` auto-starts core when `general.core_autostart=true`."""
    import kagan.cli.commands.tui as tui_command
    from kagan import __main__ as cli_main

    started: dict[str, object] = {}

    class _FakeApp:
        run_called = False

        def __init__(self, db_path: str) -> None:
            self.db_path = db_path

        def run(self) -> None:
            _FakeApp.run_called = True

    config = KaganConfig()
    config.general.core_autostart = True

    def _fake_ensure(*, config: KaganConfig, config_path: Path, db_path: Path) -> object:
        started["config"] = config
        started["config_path"] = config_path
        started["db_path"] = db_path
        return object()

    monkeypatch.setattr(tui_command, "_check_for_updates_gate", lambda: None)
    monkeypatch.setattr("kagan.core.config.KaganConfig.load", lambda _path=None: config)
    monkeypatch.setattr("kagan.core.services.runtime.ensure_core_running_sync", _fake_ensure)
    monkeypatch.setattr("kagan.tui.app.KaganApp", _FakeApp)

    callback = cast("Any", cli_main.tui.callback)
    db_file = tmp_path / "kagan.db"
    callback(
        db=str(db_file),
        skip_preflight=True,
        skip_update_check=True,
    )

    assert started["config"] is config
    assert started["db_path"] == db_file
    assert _FakeApp.run_called is True
