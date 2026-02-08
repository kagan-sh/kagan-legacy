from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, Mock

import pytest
from tests.helpers.wait import wait_for_modal, wait_for_screen

from kagan.core.models.enums import TaskStatus, TaskType
from kagan.ui.modals.tmux_gateway import PairInstructionsModal
from kagan.ui.screens.kanban import KanbanScreen

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_open_session_flow_shows_instructions_popup_for_external_launcher(
    e2e_app_with_tasks,
    mock_agent_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        screen = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        screen.kagan_app.config.ui.skip_pair_instructions = False

        tasks = await app.ctx.task_service.list_tasks(project_id=app.ctx.active_project_id)
        task = next(
            t for t in tasks if t.task_type == TaskType.PAIR and t.status == TaskStatus.BACKLOG
        )

        monkeypatch.setattr("kagan.agents.installer.check_agent_installed", lambda _name: True)
        monkeypatch.setattr("kagan.mcp.global_config.is_global_mcp_configured", lambda _name: True)
        monkeypatch.setattr(app.ctx.workspace_service, "get_path", AsyncMock(return_value=tmp_path))
        monkeypatch.setattr(
            screen._session,
            "resolve_pair_terminal_backend",
            lambda _task: "vscode",
        )

        session_exists = AsyncMock(return_value=True)
        monkeypatch.setattr(app.ctx.session_service, "session_exists", session_exists)

        do_open_pair = AsyncMock()
        monkeypatch.setattr(screen._session, "do_open_pair_session", do_open_pair)

        screen.run_worker(
            screen._session.open_session_flow(task),
            group="test-session-flow-external-launcher",
            exclusive=True,
            exit_on_error=False,
        )
        modal = cast(
            "PairInstructionsModal",
            await wait_for_modal(pilot, PairInstructionsModal, timeout=5.0),
        )
        modal.dismiss(None)
        await pilot.pause()
        do_open_pair.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_launcher_attach_does_not_prompt_session_complete(
    e2e_app_with_tasks,
    mock_agent_factory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        screen = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))

        tasks = await app.ctx.task_service.list_tasks(project_id=app.ctx.active_project_id)
        task = next(
            t for t in tasks if t.task_type == TaskType.PAIR and t.status == TaskStatus.IN_PROGRESS
        )

        attach_session = AsyncMock(return_value=True)
        session_exists = AsyncMock(return_value=False)
        monkeypatch.setattr(app.ctx.session_service, "attach_session", attach_session)
        monkeypatch.setattr(app.ctx.session_service, "session_exists", session_exists)

        push_screen = Mock(return_value=True)
        monkeypatch.setattr(screen.app, "push_screen", push_screen)
        monkeypatch.setattr(screen.app, "suspend", lambda: nullcontext())

        notify = Mock()
        monkeypatch.setattr(screen, "notify", notify)

        await screen._session.do_open_pair_session(task, tmp_path, "vscode")

        attach_session.assert_awaited_once_with(task.id)
        push_screen.assert_not_called()
        notify.assert_called_once()
        assert "Workspace opened externally." in notify.call_args.args[0]
        assert "start_prompt.md" in notify.call_args.args[0]
