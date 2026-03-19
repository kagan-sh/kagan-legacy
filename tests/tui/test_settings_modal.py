import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Settings Project")
    yield driver
    await driver.teardown()


async def test_comma_opens_settings_modal_and_saves(board: KaganDriver) -> None:
    from textual.widgets import Input, Select, Switch

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.action_open_settings()
        await pilot.pause()
        assert app.screen.id == "settings-modal"

        agent_select = app.screen.query_one("#settings-default-agent", Select)
        agent_select.value = "kimi-cli"
        app.screen.query_one("#settings-default-base-branch", Input).value = "develop"
        attached_select = app.screen.query_one("#settings-attached-launcher", Select)
        attached_select.value = "nvim"
        strategy_select = app.screen.query_one("#settings-base-ref-strategy", Select)
        strategy_select.value = "remote"
        app.screen.query_one("#settings-auto-init-repo", Switch).value = True
        app.screen.query_one("#settings-auto-init-commit", Switch).value = False

        await pilot.pause(delay=0.6)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"

        settings = await app.core.settings.get()
        assert settings.get("default_agent_backend") == "kimi-cli"
        assert settings.get("attached_launcher") == "nvim"
        assert settings.get("default_base_branch") == "develop"
        assert settings.get("worktree_base_ref_strategy") == "remote"
        assert settings.get("auto_init_git_repo") == "true"
        assert settings.get("auto_init_git_initial_commit") == "false"


async def test_instructions_section_shows_additional_instructions_field(board: KaganDriver) -> None:
    from textual.widgets import Input, TextArea

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.action_open_settings()
        await pilot.pause()
        assert app.screen.id == "settings-modal"

        await pilot.press("/")
        await pilot.pause()
        app.screen.query_one("#settings-search-input", Input).value = "instructions"
        await pilot.pause()

        instructions = app.screen.query_one("#settings-additional-instructions", TextArea).text
        assert instructions == ""


async def test_show_advanced_toggle_is_clickable_and_updates_navigation_state(
    board: KaganDriver,
) -> None:
    from textual.widgets import Button, Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app.action_open_settings()
        await pilot.pause()
        assert app.screen.id == "settings-modal"

        toggle = app.screen.query_one("#settings-advanced-toggle", Button)
        status = app.screen.query_one("#settings-search-status", Static)
        assert "Show advanced" in str(toggle.label)
        assert "basic sections" in str(status.render())

        await pilot.click("#settings-advanced-toggle")
        await pilot.pause()
        toggle = app.screen.query_one("#settings-advanced-toggle", Button)
        status = app.screen.query_one("#settings-search-status", Static)
        assert "Hide advanced" in str(toggle.label)
        assert "including advanced" in str(status.render())

        await pilot.press("ctrl+.")
        await pilot.pause()
        toggle = app.screen.query_one("#settings-advanced-toggle", Button)
        status = app.screen.query_one("#settings-search-status", Static)
        assert "Show advanced" in str(toggle.label)
        assert "basic sections" in str(status.render())
