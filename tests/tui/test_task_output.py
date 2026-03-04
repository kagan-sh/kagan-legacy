from typing import TYPE_CHECKING, cast

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]

if TYPE_CHECKING:
    from kagan.tui.screens.task_screen import TaskScreen


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Output Project")
    await driver.create_task("Auto task")
    yield driver
    await driver.teardown()


async def _enter_project(pilot) -> None:
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


async def _open_inspector(pilot) -> None:
    await pilot.press("enter")
    await pilot.pause()


async def _open_task_screen_for_selected_auto_task(pilot) -> None:
    await _enter_project(pilot)
    await _open_inspector(pilot)
    await _open_task_screen(pilot)


async def _open_task_screen(pilot) -> None:
    await pilot.press("o")
    await pilot.pause()


async def test_enter_on_auto_task_opens_task_screen(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.task_inspector import TaskInspector

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _enter_project(pilot)
        await _open_inspector(pilot)
        assert app.screen.id == "kanban-screen"
        inspector = app.screen.query_one(TaskInspector)
        assert inspector.is_open
        assert inspector.display
        assert inspector.has_class("is-open")
        await _open_task_screen(pilot)
        assert app.screen.id == "task-screen"


async def test_open_session_shortcut_requires_open_inspector(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.task_inspector import TaskInspector

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _enter_project(pilot)

        await pilot.press("o")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"

        inspector = app.screen.query_one(TaskInspector)
        assert not inspector.is_open

        await _open_inspector(pilot)
        assert inspector.is_open

        await _open_task_screen(pilot)
        assert app.screen.id == "task-screen"


async def test_escape_from_task_screen_returns_to_kanban(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_enter_starts_and_ctrl_c_stops_run_indicator(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        status = app.screen.query_one("#ts-status", Static)
        assert "Stopped" in str(status.content)


async def test_ctrl_o_on_auto_task_opens_docked_task_chat(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)
        await pilot.press("ctrl+o")
        await pilot.pause()

        assert app.screen.id == "task-screen"
        panel = app.screen.query_one(ChatPanel)
        assert panel.has_class("visible")
        assert panel.has_class("docked")
        assert not panel.has_class("fullscreen")
        assert str(panel.query_one("#chat-overlay-session-current", Static).content) == "Task"

        heading = panel.query_one("#chat-overlay-empty-heading", Static)
        assert str(heading.content) == "What are you working on?"


async def test_ctrl_p_on_auto_task_opens_fullscreen_task_chat(
    board: KaganDriver,
) -> None:
    from textual.containers import Vertical
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.header import KaganHeader

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)
        await pilot.press("ctrl+p")
        await pilot.pause()

        assert app.screen.id == "task-screen"
        panel = app.screen.query_one(ChatPanel)
        assert panel.has_class("visible")
        assert panel.has_class("fullscreen")
        assert str(panel.query_one("#chat-overlay-session-current", Static).content) == "Task"

        header = app.screen.query_one(KaganHeader)
        root = app.screen.query_one("#task-screen-root", Vertical)
        assert header.display
        assert panel.parent is root


async def test_enter_in_task_chat_submits_follow_up_and_restarts_agent(board: KaganDriver) -> None:
    from textual.widgets import Input, Static, TabbedContent

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)
        await pilot.press("ctrl+p")
        await pilot.pause()

        session = app.screen.query_one("#chat-overlay-session-current", Static)
        assert str(session.content) == "Task"
        tabs = app.screen.query_one("#ts-tabs", TabbedContent)
        active_before_send = tabs.active

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("y", "o")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        message_output = app.screen.query_one("#chat-messages", Static)
        assert "yo" in str(message_output.content)
        assert tabs.active == active_before_send


async def test_tab_switch_does_not_revert_to_previous_tab(board: KaganDriver) -> None:
    from textual.widgets import TabbedContent

    from kagan.tui import KaganApp
    from kagan.tui.widgets.diff import DiffFileTree

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)

        await pilot.press("2")
        await pilot.pause()

        tree = app.screen.query_one(DiffFileTree)
        tree.focus()
        await pilot.pause()

        cast("TaskScreen", app.screen).action_switch_tab("review")
        await pilot.pause()
        await pilot.pause()

        tabs = app.screen.query_one("#ts-tabs", TabbedContent)
        assert tabs.active == "review"


async def test_task_chat_restart_failure_surfaces_error_state(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens import task_screen as task_screen_module
    from kagan.tui.widgets.chat import ChatPanel

    async def fake_start_or_attach_session(self, *, backend_hint: str | None = None) -> str | None:
        del self, backend_hint
        return "agent initialization failed"

    monkeypatch.setattr(
        task_screen_module.TaskScreen,
        "_start_or_attach_session",
        fake_start_or_attach_session,
    )

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)
        await pilot.press("ctrl+p")
        await pilot.pause()

        session = app.screen.query_one("#chat-overlay-session-current", Static)
        assert str(session.content) == "Task"

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("y", "o")
        await pilot.press("enter")
        await pilot.pause()

        panel = app.screen.query_one(ChatPanel)
        status = panel.query_one("#chat-overlay-status-left", Static)
        current_action = panel.query_one("#stream-current-action", Static)

        for _ in range(20):
            if "Error" in str(status.content) and "Unable to restart task agent" in str(
                current_action.content
            ):
                break
            await pilot.pause()

        assert "Error" in str(status.content)
        assert "Unable to restart task agent" in str(current_action.content)
        assert not input_widget.disabled


async def test_ctrl_o_on_running_auto_task_keeps_task_screen_visible(board: KaganDriver) -> None:
    from textual.widgets import Label

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_auto_task(pilot)

        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()

        assert app.screen.id == "task-screen"
        panel = app.screen.query_one(ChatPanel)
        assert panel.has_class("visible")
        assert panel.has_class("docked")
        assert not panel.has_class("fullscreen")

        title = app.screen.query_one("#ts-title", Label)
        assert str(title.content) != "Task"  # Title set to actual task name


async def test_inspector_scrolls_when_description_is_long() -> None:
    from dataclasses import dataclass

    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll

    from kagan.core.enums import Priority, TaskStatus, WorkMode
    from kagan.tui.widgets.task_inspector import TaskInspector

    @dataclass
    class _InspectorTask:
        id: str
        title: str
        description: str
        status: TaskStatus
        priority: Priority
        execution_mode: WorkMode
        agent_backend: str | None
        base_branch: str | None
        acceptance_criteria: list[str]
        review_approved: bool

    class InspectorHarness(App[None]):
        def compose(self) -> ComposeResult:
            yield TaskInspector(id="task-inspector")

    task = _InspectorTask(
        "abc12345",
        "Long description task",
        "\n".join(f"Line {index}: {'x' * 100}" for index in range(120)),
        TaskStatus.IN_PROGRESS,
        Priority.MEDIUM,
        WorkMode.PAIR,
        None,
        None,
        [],
        False,
    )

    app = InspectorHarness()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()

        inspector = app.query_one(TaskInspector)
        inspector.show_task(task)
        await pilot.pause()

        scroll = inspector.query_one("#inspector-scroll", VerticalScroll)
        assert scroll.max_scroll_y > 0

        initial_scroll = scroll.scroll_y
        scroll.scroll_page_down(animate=False)
        await pilot.pause()
        assert scroll.scroll_y > initial_scroll
