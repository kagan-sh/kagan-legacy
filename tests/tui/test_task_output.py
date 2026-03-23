from typing import TYPE_CHECKING, cast

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]

if TYPE_CHECKING:
    from kagan.tui.screens.task_screen import TaskScreen


async def _enter_project(pilot) -> None:
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


async def _open_inspector(pilot) -> None:
    await pilot.press("enter")
    await pilot.pause()


async def _open_task_screen_for_selected_detached_task(pilot) -> None:
    await _enter_project(pilot)
    await _open_inspector(pilot)
    await _open_task_screen(pilot)


async def _open_task_screen(pilot) -> None:
    await pilot.press("enter")
    await pilot.pause()


async def test_enter_on_detached_task_opens_task_screen(board_with_task: KaganDriver) -> None:
    from textual.widgets import TabbedContent

    from kagan.tui import KaganApp
    from kagan.tui.widgets.task_inspector import TaskInspector

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
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
        tabs = app.screen.query_one("#ts-tabs", TabbedContent)
        assert tabs.active == "overview"


async def test_task_screen_shows_action_hint_footer(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.task_action_bar import TaskActionBar

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)

        action_row = app.screen.query_one("#ts-actions", TaskActionBar)
        assert action_row.display

        hint = app.screen.query_one("#ts-action-hint", Static)
        hint_text = str(hint.content).lower()
        assert "tabs" in hint_text
        assert "back" in hint_text


async def test_enter_requires_open_inspector_before_task_screen(
    board_with_task: KaganDriver,
) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.task_inspector import TaskInspector

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _enter_project(pilot)

        await pilot.press("v")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"

        inspector = app.screen.query_one(TaskInspector)
        assert not inspector.is_open

        await _open_inspector(pilot)
        assert inspector.is_open

        await _open_task_screen(pilot)
        assert app.screen.id == "task-screen"


async def test_escape_from_task_screen_returns_to_kanban(board_with_task: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_enter_starts_and_ctrl_c_stops_run_indicator(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        status = app.screen.query_one("#ts-status", Static)
        status_text = str(status.content)
        assert "Stopped" in status_text or status_text == "Ready | BACKLOG"


async def test_ctrl_o_on_detached_task_opens_docked_task_chat(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.press("ctrl+i")
        await pilot.pause()

        assert app.screen.id == "task-screen"
        panel = app.screen.query_one(ChatPanel)
        assert panel.has_class("visible")
        assert panel.has_class("docked")
        assert not panel.has_class("fullscreen")
        assert str(panel.query_one("#chat-overlay-session-current", Static).content) == "Task"

        heading = panel.query_one("#chat-overlay-empty-heading", Static)
        assert str(heading.content) == "What are you working on?"


async def test_ctrl_p_on_detached_task_opens_fullscreen_task_chat(
    board_with_task: KaganDriver,
) -> None:
    from textual.containers import Vertical
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.header import KaganHeader

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.press("ctrl+shift+t")
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


async def test_enter_in_task_chat_submits_follow_up_and_restarts_agent(
    board_with_task: KaganDriver,
) -> None:
    from textual.widgets import Input, Static, TabbedContent

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.press("ctrl+shift+t")
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


async def test_tab_switch_does_not_revert_to_previous_tab(board_with_task: KaganDriver) -> None:
    from textual.widgets import TabbedContent

    from kagan.tui import KaganApp
    from kagan.tui.widgets.diff import DiffFileTree

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)

        await pilot.press("2")
        await pilot.pause()

        tree = app.screen.query_one(DiffFileTree)
        tree.focus()
        await pilot.pause()

        cast("TaskScreen", app.screen).action_switch_tab("overview")
        await pilot.pause()
        await pilot.pause()

        tabs = app.screen.query_one("#ts-tabs", TabbedContent)
        assert tabs.active == "overview"


async def test_task_chat_restart_failure_surfaces_error_state(
    board_with_task: KaganDriver,
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

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.press("ctrl+shift+t")
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


async def test_ctrl_o_on_running_detached_task_keeps_task_screen_visible(
    board_with_task: KaganDriver,
) -> None:
    from textual.widgets import Label

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)

        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
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

    from kagan.core.enums import Priority, TaskStatus
    from kagan.tui.widgets.task_inspector import TaskInspector

    @dataclass
    class _InspectorTask:
        id: str
        title: str
        description: str
        status: TaskStatus
        priority: Priority
        agent_backend: str | None
        launcher: str | None
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
        None,
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


async def test_task_stream_uses_bounded_replay_and_merges_chunks(
    board_with_task: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.containers import Vertical

    from kagan.core.enums import SessionEventType
    from kagan.core.models import SessionEvent
    from kagan.tui import KaganApp
    from kagan.tui.widgets.streaming import OutputChunk, StreamingOutput

    replay_limits: list[int | None] = []

    async def fake_stream(task_id: str, *, replay: bool = True, replay_limit: int | None = None):
        del task_id, replay
        replay_limits.append(replay_limit)
        for fragment in ("A", "B", "C"):
            yield SessionEvent(
                task_id="task",
                event_type=SessionEventType.OUTPUT_CHUNK,
                payload={"text": fragment, "kind": "assistant"},
            )

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    monkeypatch.setattr(app.core.tasks.events, "stream", fake_stream)

    async with app.run_test() as pilot:
        await _open_task_screen_for_selected_detached_task(pilot)
        await pilot.pause()
        await pilot.pause()

        assert replay_limits
        assert replay_limits[0] == 400

        output = app.screen.query_one("#chat-overlay-output", StreamingOutput)
        content = output.query_one("#streaming-body-content", Vertical)
        chunks = [child for child in content.children if isinstance(child, OutputChunk)]
        assert len(chunks) == 1
        assert chunks[0]._accumulated_text == "ABC"
