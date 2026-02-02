"""E2E tests for WelcomeScreen UI interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kagan.app import KaganApp

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e


@pytest.fixture
async def welcome_app(tmp_path: Path, monkeypatch) -> KaganApp:
    """Create app for welcome screen testing (fresh project, no config)."""
    # Set git env vars for CI compatibility
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")

    project = tmp_path / "new_project"
    project.mkdir()

    return KaganApp(
        db_path=str(project / ".kagan" / "state.db"),
        config_path=str(project / ".kagan" / "config.toml"),
        lock_path=None,
    )


class TestWelcomeScreenUI:
    """E2E tests for WelcomeScreen user interactions."""

    async def test_welcome_screen_shows_on_first_boot(self, welcome_app: KaganApp):
        """Welcome screen is shown when no config exists."""
        async with welcome_app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert "WelcomeScreen" in type(pilot.app.screen).__name__

    async def test_welcome_screen_has_agent_select(self, welcome_app: KaganApp):
        """Welcome screen shows agent selection dropdown."""
        from textual.widgets import Select

        async with welcome_app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            agent_select = pilot.app.screen.query_one("#agent-select", Select)
            assert agent_select is not None

    @pytest.mark.parametrize(
        "action,action_type",
        [
            ("click", "#continue-btn"),
            ("key", "escape"),
        ],
        ids=["continue_button", "escape_key"],
    )
    async def test_exit_welcome_screen(self, welcome_app: KaganApp, action: str, action_type: str):
        """Verify actions that exit the welcome screen."""
        async with welcome_app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert "WelcomeScreen" in type(pilot.app.screen).__name__

            if action == "click":
                await pilot.click(action_type)
            else:
                await pilot.press(action_type)
            await pilot.pause()
            await pilot.pause()  # Extra pause for async config write

            assert "WelcomeScreen" not in type(pilot.app.screen).__name__
