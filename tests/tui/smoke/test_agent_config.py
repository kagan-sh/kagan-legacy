"""Agent configuration: global indicator, backend select fallback, and terminal backend pairing."""

from __future__ import annotations

import asyncio
import platform
from typing import cast

import pytest
from tests.helpers.wait import wait_for_modal, wait_for_screen, wait_until
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label, Select, Static

from kagan.core.config import KaganConfig
from kagan.tui.ui.modals.task_details_modal import TaskDetailsModal
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.planner import PlannerScreen
from kagan.tui.ui.widgets.header import KaganHeader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _header_agent_text(screen: KanbanScreen | PlannerScreen) -> str:
    header = screen.query_one(KaganHeader)
    return str(header.query_one("#header-agent", Label).content)


class _HarnessApp(App[None]):
    def __init__(self, config: KaganConfig) -> None:
        super().__init__()
        self.config = config
        self.kagan_app = self
        self._ctx = None

    def compose(self) -> ComposeResult:
        yield Static("host")


# ---------------------------------------------------------------------------
# Global agent indicator
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_switch_global_agent_updates_indicator_and_config(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from kagan.tui.ui.modals.global_agent_picker import GlobalAgentPickerModal

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))

        await pilot.press("A")
        modal = cast(
            "GlobalAgentPickerModal",
            await wait_for_modal(pilot, GlobalAgentPickerModal, timeout=5.0),
        )
        modal.dismiss("codex")
        await wait_for_screen(pilot, KanbanScreen, timeout=10.0)
        await wait_until(
            lambda: app.config.general.default_worker_agent == "codex",
            timeout=3.0,
            check_interval=0.05,
            description="global agent config update",
        )

        kanban = cast("KanbanScreen", pilot.app.screen)
        assert app.config.general.default_worker_agent == "codex"
        assert _header_agent_text(kanban) == "AI: Codex"

        config_text = app.config_path.read_text()
        assert 'default_worker_agent = "codex"' in config_text

        kanban.action_open_planner()
        planner = cast("PlannerScreen", await wait_for_screen(pilot, PlannerScreen, timeout=10.0))
        assert _header_agent_text(planner) == "AI: Codex"


# ---------------------------------------------------------------------------
# Agent backend select fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_details_modal_mounts_with_unknown_agent_backend() -> None:
    """TaskDetailsModal does not crash when task has an agent_backend not in options."""
    from datetime import datetime

    from kagan.core.adapters.db.schema import Task
    from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType

    now = datetime.now()
    task = Task(
        id="task-unknown-agent",
        project_id="proj-1",
        title="Unknown agent task",
        description="",
        status=TaskStatus.BACKLOG,
        priority=TaskPriority.MEDIUM,
        task_type=TaskType.AUTO,
        created_at=now,
        updated_at=now,
    )
    task.agent_backend = "nonexistent-agent"

    app = _HarnessApp(KaganConfig())

    async with app.run_test(size=(120, 40)) as pilot:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[object | None] = loop.create_future()
        pilot.app.push_screen(
            TaskDetailsModal(task, start_editing=True),
            callback=lambda result: result_future.set_result(result),
        )
        modal = await wait_for_screen(pilot, TaskDetailsModal, timeout=5.0)

        # Modal should mount without InvalidSelectValueError.
        agent_select = modal.query_one("#agent-backend-select", Select)
        assert agent_select.value is not Select.BLANK

        modal.query_one("#title-input", Input).value = "Fixed title"
        modal.query_one("#save-btn", Button).press()

        result = await result_future

    assert isinstance(result, dict)
    # The agent_backend should be a valid agent key, not the original invalid one.
    assert result["agent_backend"] != "nonexistent-agent"


# ---------------------------------------------------------------------------
# Config pair terminal backend
# ---------------------------------------------------------------------------


def test_default_pair_terminal_backend_is_tmux() -> None:
    config = KaganConfig()
    expected = "vscode" if platform.system() == "Windows" else "tmux"
    assert config.general.default_pair_terminal_backend == expected


@pytest.mark.asyncio
async def test_pair_terminal_backend_persists_across_save_load(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config = KaganConfig()
    config.general.default_pair_terminal_backend = "cursor"  # type: ignore[assignment]

    await config.save(config_path)
    loaded = KaganConfig.load(config_path)

    assert loaded.general.default_pair_terminal_backend == "cursor"


def test_invalid_pair_terminal_backend_falls_back_to_tmux(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[general]",
                'default_pair_terminal_backend = "invalid-launcher"',
            ]
        ),
        encoding="utf-8",
    )

    loaded = KaganConfig.load(config_path)

    expected = "vscode" if platform.system() == "Windows" else "tmux"
    assert loaded.general.default_pair_terminal_backend == expected
