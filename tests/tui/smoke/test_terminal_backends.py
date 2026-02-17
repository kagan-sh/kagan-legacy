from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from tests.helpers.wait import wait_for_screen
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Select, Static

from kagan.core.adapters.db.schema import Task
from kagan.core.command_utils import clear_which_cache
from kagan.core.config import KaganConfig
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType
from kagan.tui.terminals.installer import check_terminal_installed, install_terminal
from kagan.tui.ui.modals.settings import SettingsModal
from kagan.tui.ui.modals.task_details_modal import TaskDetailsModal
from kagan.tui.ui.screens.task_editor import TaskEditorScreen

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers & fixtures from test_terminal_installer
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Ensure cached_which cache is empty before every test."""
    clear_which_cache()


class _Proc:
    def __init__(self, *, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        return None

    async def wait(self) -> int:
        return self.returncode


# ---------------------------------------------------------------------------
# Helpers from test_pair_terminal_backend_ui
# ---------------------------------------------------------------------------


class _ModalHarnessApp(App[None]):
    def __init__(self, config: KaganConfig) -> None:
        super().__init__()
        self.config = config
        self.kagan_app = self
        self._ctx = None

    def compose(self) -> ComposeResult:
        yield Static("host")


class _SettingsApiStub:
    def __init__(self, config: KaganConfig, config_path: Path) -> None:
        self._config = config
        self._config_path = config_path

    async def update_settings(
        self,
        fields: dict[str, object],
    ) -> tuple[bool, str, dict[str, object], dict[str, object]]:
        for key, value in fields.items():
            section_name, field_name = key.split(".", 1)
            section = getattr(self._config, section_name)
            setattr(section, field_name, value)
        await self._config.save(self._config_path)
        return True, "Settings updated", dict(fields), {}


# ---------------------------------------------------------------------------
# Tests from test_terminal_installer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_terminal_returns_manual_fallback_when_auto_installer_unavailable() -> None:
    with (
        patch("kagan.tui.terminals.installer.check_terminal_installed", return_value=False),
        patch("kagan.tui.terminals.installer._get_tmux_install_command", return_value=None),
    ):
        success, message = await install_terminal("tmux")

    assert success is False
    assert "install tmux" in message.lower()


@pytest.mark.asyncio
async def test_install_terminal_surfaces_command_failure_with_fallback() -> None:
    with (
        patch("kagan.tui.terminals.installer._get_tmux_install_command", return_value="install"),
        patch("kagan.tui.terminals.installer.check_terminal_installed", return_value=False),
        patch(
            "kagan.tui.terminals.installer.asyncio.create_subprocess_shell",
            new=AsyncMock(return_value=_Proc(returncode=1, stderr=b"boom")),
        ),
    ):
        success, message = await install_terminal("tmux")

    assert success is False
    assert "boom" in message
    assert "install tmux" in message.lower()


@pytest.mark.asyncio
async def test_install_terminal_supports_tmux_auto_install() -> None:
    with (
        patch("kagan.tui.terminals.installer._get_tmux_install_command", return_value="install"),
        patch(
            "kagan.tui.terminals.installer.check_terminal_installed",
            side_effect=[False, True],
        ),
        patch(
            "kagan.tui.terminals.installer.asyncio.create_subprocess_shell",
            new=AsyncMock(return_value=_Proc(returncode=0)),
        ),
    ):
        success, message = await install_terminal("tmux")

    assert success is True
    assert "installed" in message.lower()


@pytest.mark.asyncio
async def test_install_terminal_rejects_non_tmux_backend() -> None:
    success, message = await install_terminal("vscode")
    assert success is False
    assert "only for tmux" in message.lower()


def test_check_terminal_installed_supports_vscode_and_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with patch(
        "shutil.which",
        side_effect=lambda cmd: "/bin/x" if cmd in {"code", "cursor"} else None,
    ):
        assert check_terminal_installed("vscode") is True
        assert check_terminal_installed("cursor") is True


# ---------------------------------------------------------------------------
# Tests from test_pair_terminal_backend_ui
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_details_modal_persists_pair_terminal_backend() -> None:
    app = _ModalHarnessApp(KaganConfig())

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[object | None] = loop.create_future()
        pilot.app.push_screen(
            TaskDetailsModal(),
            callback=lambda result: result_future.set_result(result),
        )
        modal = await wait_for_screen(pilot, TaskDetailsModal, timeout=5.0)

        modal.query_one("#title-input", Input).value = "PAIR terminal test"
        terminal_select = modal.query_one("#pair-terminal-backend-select", Select)
        terminal_select.value = "cursor"
        await pilot.pause()
        modal.query_one("#save-btn", Button).press()

        result = await result_future

    assert isinstance(result, dict)
    assert result["task_type"] == TaskType.PAIR
    assert result["terminal_backend"] == "cursor"


@pytest.mark.asyncio
async def test_task_details_modal_clears_terminal_backend_for_auto_task() -> None:
    app = _ModalHarnessApp(KaganConfig())

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[object | None] = loop.create_future()
        pilot.app.push_screen(
            TaskDetailsModal(),
            callback=lambda result: result_future.set_result(result),
        )
        modal = await wait_for_screen(pilot, TaskDetailsModal, timeout=5.0)

        modal.query_one("#title-input", Input).value = "AUTO terminal test"
        type_select = modal.query_one("#type-select", Select)
        type_select.value = TaskType.AUTO.value
        await pilot.pause()
        modal.query_one("#save-btn", Button).press()

        result = await result_future

    assert isinstance(result, dict)
    assert result["task_type"] == TaskType.AUTO
    assert result["terminal_backend"] is None


@pytest.mark.asyncio
async def test_task_editor_toggles_terminal_backend_with_type_change() -> None:
    now = datetime.now()
    task = Task(
        id="task-1",
        project_id="proj-1",
        title="Editor task",
        description="",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        task_type=TaskType.PAIR,
        created_at=now,
        updated_at=now,
    )
    app = _ModalHarnessApp(KaganConfig())

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[list[Task] | None] = loop.create_future()
        pilot.app.push_screen(
            TaskEditorScreen([task]),
            callback=lambda result: result_future.set_result(result),
        )
        editor = await wait_for_screen(pilot, TaskEditorScreen, timeout=5.0)

        type_select = editor.query_one("#type-1", Select)
        terminal_select = editor.query_one("#terminal-backend-1", Select)
        assert terminal_select.disabled is False

        type_select.value = TaskType.AUTO.value
        await pilot.pause()
        assert terminal_select.disabled

        type_select.value = TaskType.PAIR.value
        terminal_select.value = "cursor"
        await pilot.pause()
        editor.query_one("#finish-btn", Button).press()

        edited = await result_future

    assert edited is not None
    if "terminal_backend" in Task.model_fields:
        assert edited[0].terminal_backend == "cursor"


@pytest.mark.asyncio
async def test_task_editor_invalid_pair_backend_falls_back_to_tmux() -> None:
    now = datetime.now()
    task = Task(
        id="task-2",
        project_id="proj-1",
        title="Editor invalid backend task",
        description="",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        task_type=TaskType.PAIR,
        created_at=now,
        updated_at=now,
    )
    task.terminal_backend = "invalid-launcher"
    app = _ModalHarnessApp(KaganConfig())

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[list[Task] | None] = loop.create_future()
        pilot.app.push_screen(
            TaskEditorScreen([task]),
            callback=lambda result: result_future.set_result(result),
        )
        editor = await wait_for_screen(pilot, TaskEditorScreen, timeout=5.0)

        editor.query_one("#finish-btn", Button).press()
        edited = await result_future

    assert edited is not None
    if "terminal_backend" in Task.model_fields:
        assert edited[0].terminal_backend == "tmux"


@pytest.mark.asyncio
async def test_settings_modal_updates_default_pair_terminal_backend(tmp_path: Path) -> None:
    config = KaganConfig()
    config_path = tmp_path / "config.toml"
    app = _ModalHarnessApp(config)
    settings_api = _SettingsApiStub(config, config_path)

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[object | None] = loop.create_future()
        pilot.app.push_screen(
            SettingsModal(config, settings_api),
            callback=lambda result: result_future.set_result(result),
        )
        modal = await wait_for_screen(pilot, SettingsModal, timeout=5.0)

        select = modal.query_one("#default-pair-terminal-select", Select)
        select.value = "tmux"
        await pilot.pause()
        modal.query_one("#save-btn", Button).press()

        result = await result_future

    assert result is True
    assert config.general.default_pair_terminal_backend == "tmux"


@pytest.mark.asyncio
async def test_settings_modal_updates_worktree_base_ref_strategy(tmp_path: Path) -> None:
    config = KaganConfig()
    config_path = tmp_path / "config.toml"
    app = _ModalHarnessApp(config)
    settings_api = _SettingsApiStub(config, config_path)

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[object | None] = loop.create_future()
        pilot.app.push_screen(
            SettingsModal(config, settings_api),
            callback=lambda result: result_future.set_result(result),
        )
        modal = await wait_for_screen(pilot, SettingsModal, timeout=5.0)

        select = modal.query_one("#worktree-base-ref-strategy-select", Select)
        select.value = "local_if_ahead"
        await pilot.pause()
        modal.query_one("#save-btn", Button).press()
        await pilot.pause()

        result = await result_future

    assert result is True
    assert config.general.worktree_base_ref_strategy == "local_if_ahead"
    config_text = config_path.read_text(encoding="utf-8")
    assert 'worktree_base_ref_strategy = "local_if_ahead"' in config_text


@pytest.mark.asyncio
async def test_settings_modal_updates_additional_default_models(tmp_path: Path) -> None:
    config = KaganConfig()
    config_path = tmp_path / "config.toml"
    app = _ModalHarnessApp(config)
    settings_api = _SettingsApiStub(config, config_path)

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[object | None] = loop.create_future()
        pilot.app.push_screen(
            SettingsModal(config, settings_api),
            callback=lambda result: result_future.set_result(result),
        )
        modal = await wait_for_screen(pilot, SettingsModal, timeout=5.0)

        modal.query_one("#default-model-codex-input", Input).value = "gpt-5.2-codex"
        modal.query_one("#default-model-gemini-input", Input).value = "flash"
        modal.query_one("#default-model-kimi-input", Input).value = "kimi-k2-turbo-preview"
        modal.query_one("#default-model-copilot-input", Input).value = "GPT-5"
        await pilot.pause()
        modal.query_one("#save-btn", Button).press()

        result = await result_future

    assert result is True
    assert config.general.default_model_codex == "gpt-5.2-codex"
    assert config.general.default_model_gemini == "flash"
    assert config.general.default_model_kimi == "kimi-k2-turbo-preview"
    assert config.general.default_model_copilot == "GPT-5"
