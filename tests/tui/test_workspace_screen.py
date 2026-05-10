import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def test_w_toggles_between_kanban_and_workspace(board_with_task: KaganDriver) -> None:
    from textual.widgets import Input, OptionList, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, KanbanScreen)

        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, WorkspaceScreen)
        assert app.screen.focused is app.screen.query_one("#workspace-session-list", OptionList)
        assert "j/k nav" in str(app.screen.query_one("#workspace-footer", Static).content)
        assert (
            str(app.screen.query_one("#workspace-main-title", Static).content)
            == app.orchestrator_sessions.list_items()[0].label
        )

        await pilot.press("ctrl+period")
        await pilot.pause()
        assert app.screen.focused is app.screen.query_one("#chat-overlay-input", Input)
        assert "enter send" in str(app.screen.query_one("#workspace-footer", Static).content)

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.focused is app.screen.query_one("#workspace-session-list", OptionList)
        assert "j/k nav" in str(app.screen.query_one("#workspace-footer", Static).content)

        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, KanbanScreen)


async def test_workspace_can_create_and_delete_sessions(board_with_task: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, WorkspaceScreen)

        assert len(app.orchestrator_sessions.list_items()) == 1

        await pilot.press("n")
        await pilot.pause()
        assert len(app.orchestrator_sessions.list_items()) == 2

        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.orchestrator_sessions.list_items()) == 1


async def test_workspace_search_esc_clears_then_returns_to_sidebar(
    board_with_task: KaganDriver,
) -> None:
    from textual.widgets import Input, OptionList, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("w")
        await pilot.pause()
        assert isinstance(app.screen, WorkspaceScreen)

        session_id = app.orchestrator_sessions.list_items()[0].session_id
        search = app.screen.query_one("#workspace-search", Input)
        session_list = app.screen.query_one("#workspace-session-list", OptionList)

        await pilot.press("/")
        await pilot.pause()
        assert app.screen.focused is search
        assert "Type to filter" in str(app.screen.query_one("#workspace-footer", Static).content)

        search.value = session_id[:4]
        await pilot.pause()
        assert search.value == session_id[:4]

        await pilot.press("escape")
        await pilot.pause()
        assert search.value == ""
        assert app.screen.focused is search
        assert "Esc list" in str(app.screen.query_one("#workspace-footer", Static).content)

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.focused is session_list
