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

        app.screen.query_one("#settings-default-agent", Input).value = "kimi-cli"
        app.screen.query_one("#settings-default-base-branch", Input).value = "develop"
        pair_select = app.screen.query_one("#settings-pair-launcher", Select)
        pair_select.value = "nvim"
        strategy_select = app.screen.query_one("#settings-base-ref-strategy", Select)
        strategy_select.value = "remote"
        app.screen.query_one("#settings-auto-init-repo", Switch).value = True
        app.screen.query_one("#settings-auto-init-commit", Switch).value = False

        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"

        settings = await app.core.settings.get()
        assert settings.get("default_agent_backend") == "kimi-cli"
        assert settings.get("pair_launcher") == "nvim"
        assert settings.get("default_base_branch") == "develop"
        assert settings.get("worktree_base_ref_strategy") == "remote"
        assert settings.get("auto_init_git_repo") == "true"
        assert settings.get("auto_init_git_initial_commit") == "false"


async def test_prompts_section_prefills_default_prompt_templates(board: KaganDriver) -> None:
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
        app.screen.query_one("#settings-search-input", Input).value = "prompts"
        await pilot.pause()

        orchestrator = app.screen.query_one("#settings-custom-orchestrator-prompt", TextArea).text
        task_prompt = app.screen.query_one("#settings-custom-task-prompt", TextArea).text
        review_prompt = app.screen.query_one("#settings-custom-review-prompt", TextArea).text
        orchestrator_editor = app.screen.query_one("#settings-custom-orchestrator-prompt", TextArea)

        assert "<identity>" in orchestrator
        assert "MUST DO:" in task_prompt
        assert "<review-protocol>" in review_prompt
        assert orchestrator_editor.has_focus
        assert orchestrator_editor.cursor_location == orchestrator_editor.document.end


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
