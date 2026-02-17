from __future__ import annotations

import asyncio
from typing import cast

import pytest
from tests.helpers.wait import wait_for_modal, wait_for_screen, wait_for_widget
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label
from textual.worker import NoActiveWorker

from kagan.tui.ui.modals.branch_select import BaseBranchModal
from kagan.tui.ui.modals.review_flow import ReviewModal
from kagan.tui.ui.modals.task_details_modal import TaskDetailsModal
from kagan.tui.ui.screen_result import await_screen_result
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.widgets.card import TaskCard


# ---------------------------------------------------------------------------
# Helpers (from test_screen_result)
# ---------------------------------------------------------------------------


class _AutoDismissModal(ModalScreen[str]):
    def __init__(self, value: str) -> None:
        super().__init__()
        self._value = value

    def on_mount(self) -> None:
        self.dismiss(self._value)


class _ScreenResultTestApp(App[None]):
    def compose(self) -> ComposeResult:
        yield Label("screen-result-test")


# ---------------------------------------------------------------------------
# External deletion tests (from test_modal_external_deletion)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_review_modal_closes_when_task_is_deleted_externally(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        tasks = await app.ctx.api.list_tasks(project_id=app.ctx.active_project_id)
        task = tasks[0]
        agent_config = task.get_agent_config(app.config)

        app.push_screen(
            ReviewModal(
                task=task,
                agent_config=agent_config,
                is_reviewing=False,
                is_running=False,
                read_only=True,
                initial_tab="review-summary",
            )
        )
        await wait_for_screen(pilot, ReviewModal, timeout=10.0)

        deleted, _ = await app.ctx.api.delete_task(task.id)
        assert deleted is True

        await wait_for_screen(pilot, KanbanScreen, timeout=10.0)
        assert pilot.app.screen is kanban


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_task_details_modal_closes_when_task_is_deleted_externally(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        tasks = await app.ctx.api.list_tasks(project_id=app.ctx.active_project_id)
        task = tasks[0]

        app.push_screen(TaskDetailsModal(task=task))
        await wait_for_screen(pilot, TaskDetailsModal, timeout=10.0)

        deleted, _ = await app.ctx.api.delete_task(task.id)
        assert deleted is True

        await wait_for_screen(pilot, KanbanScreen, timeout=10.0)
        assert pilot.app.screen is kanban


# ---------------------------------------------------------------------------
# Branch popup tests (from test_branch_popup)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_set_task_branch_modal_opens_and_dismisses(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        screen = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        tasks = await app.ctx.task_service.list_tasks(project_id=app.ctx.active_project_id)
        task = tasks[0]

        await wait_for_widget(pilot, f"#card-{task.id}", timeout=10.0)
        card = screen.query_one(f"#card-{task.id}", TaskCard)
        card.focus()
        await pilot.pause()

        await pilot.press("b")
        modal = cast("BaseBranchModal", await wait_for_modal(pilot, BaseBranchModal, timeout=5.0))
        modal.dismiss(None)
        await pilot.pause()

        await wait_for_screen(pilot, KanbanScreen, timeout=5.0)


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_set_task_branch_modal_opens_when_branch_lookup_is_slow(
    e2e_app_with_tasks,
    mock_agent_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async def _slow_branch_lookup(_path) -> list[str]:
        loop = asyncio.get_running_loop()
        gate = loop.create_future()
        loop.call_later(0.2, gate.set_result, None)
        await gate
        return ["main", "develop"]

    monkeypatch.setattr(
        "kagan.tui.ui.screens.branch_candidates.list_local_branches",
        _slow_branch_lookup,
    )

    async with app.run_test(size=(120, 40)) as pilot:
        screen = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        tasks = await app.ctx.task_service.list_tasks(project_id=app.ctx.active_project_id)
        task = tasks[0]

        await wait_for_widget(pilot, f"#card-{task.id}", timeout=10.0)
        card = screen.query_one(f"#card-{task.id}", TaskCard)
        card.focus()
        await pilot.pause()

        await pilot.press("b")
        modal = cast("BaseBranchModal", await wait_for_modal(pilot, BaseBranchModal, timeout=5.0))
        modal.dismiss(None)
        await wait_for_screen(pilot, KanbanScreen, timeout=5.0)


# ---------------------------------------------------------------------------
# Screen result tests (from test_screen_result)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_await_screen_result_falls_back_when_push_screen_wait_has_no_active_worker() -> None:
    app = _ScreenResultTestApp()

    def _raise_no_active_worker(screen: ModalScreen[str]) -> None:
        del screen
        raise NoActiveWorker(
            "push_screen must be run from a worker when `wait_for_dismiss` is True"
        )

    async with app.run_test() as pilot:
        app.push_screen_wait = _raise_no_active_worker  # type: ignore[assignment]
        result = await await_screen_result(app, _AutoDismissModal("repo-123"))
        await pilot.pause()

    assert result == "repo-123"
