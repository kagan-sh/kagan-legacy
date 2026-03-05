import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Task Chat Persistence Project")
    await driver.create_task("Task chat persistence")
    yield driver
    await driver.teardown()


async def test_ctrl_o_ctrl_p_toggles_keep_task_chat_session(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.chat import ChatPanel

    task = (await board.list_tasks())[0]

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()

        await pilot.press("ctrl+o")
        await pilot.pause()

        panel = app.screen.query_one(ChatPanel)
        current_label = str(panel.query_one("#chat-overlay-session-current", Static).content)
        assert current_label == "Task"

        panel.add_system_message("session anchor")
        await pilot.pause()

        await pilot.press("ctrl+p")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()

        assert panel.has_class("visible")
        assert panel.has_class("fullscreen")
        current_label = str(panel.query_one("#chat-overlay-session-current", Static).content)
        assert current_label == "Task"
        assert "session anchor" in str(panel.query_one("#chat-messages", Static).content)


async def test_task_screen_ctrl_o_cycles_vertical_horizontal_off(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.chat import ChatPanel

    task = (await board.list_tasks())[0]

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()

        await pilot.press("ctrl+o")
        await pilot.pause()

        panel = app.screen.query_one(ChatPanel)
        assert panel.has_class("visible")
        assert app.screen.has_class("ts-chat-vertical")
        assert str(panel.styles.layer) == "default"

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert panel.has_class("visible")
        assert app.screen.has_class("ts-chat-horizontal")
        assert str(panel.styles.layer) == "default"

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert not panel.has_class("visible")


async def test_task_screen_ctrl_k_opens_session_picker_modal(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens.session_picker import SessionPickerModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await board.list_tasks())[0]

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()

        await pilot.press("ctrl+k")
        await pilot.pause()

        assert isinstance(app.screen, SessionPickerModal)


async def test_tab_in_task_chat_cycles_sessions_without_changing_overlay_layout(
    board: KaganDriver,
) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.chat import ChatPanel

    task = (await board.list_tasks())[0]

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()

        await pilot.press("ctrl+o")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()

        panel = app.screen.query_one(ChatPanel)
        current = panel.query_one("#chat-overlay-session-current", Static)
        initial_label = str(current.content)
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        assert app.screen.has_class("ts-chat-horizontal")
        assert initial_label == "Task"

        await pilot.press("tab")
        await pilot.pause()
        current = panel.query_one("#chat-overlay-session-current", Static)
        assert app.screen.id == "task-screen"
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        assert app.screen.has_class("ts-chat-horizontal")
        assert str(current.content) != initial_label

        await pilot.press("tab")
        await pilot.pause()
        current = panel.query_one("#chat-overlay-session-current", Static)
        assert app.screen.id == "task-screen"
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        assert app.screen.has_class("ts-chat-horizontal")
        assert str(current.content) == initial_label
