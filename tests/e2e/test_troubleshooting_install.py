"""E2E tests for agent installation from troubleshooting screen."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from kagan.ui.screens.troubleshooting import (
    ISSUE_PRESETS,
    AgentSelectModal,
    DetectedIssue,
    InstallModal,
    IssueType,
    TroubleshootingApp,
    create_no_agents_issues,
)

pytestmark = pytest.mark.e2e

# Use TMUX_MISSING as non-agent issue (it's a warning, not about missing agents)
NON_AGENT_ISSUE_TYPE = IssueType.TMUX_MISSING


class TestInstallAgentFlow:
    """Tests for the agent installation flow via 'i' key."""

    async def test_press_i_opens_agent_select_modal(self):
        """Pressing 'i' opens AgentSelectModal when no agents found."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()

            assert isinstance(pilot.app.screen, AgentSelectModal)

    async def test_agent_select_escape_cancels(self):
        """Escape closes AgentSelectModal without proceeding to install."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()
            assert isinstance(pilot.app.screen, AgentSelectModal)

            await pilot.press("escape")
            await pilot.pause()

            # Should return to main screen, not open InstallModal
            assert not isinstance(pilot.app.screen, AgentSelectModal)
            assert not isinstance(pilot.app.screen, InstallModal)

    async def test_agent_select_action_opens_install_modal(self):
        """Triggering select action in AgentSelectModal opens InstallModal."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()
            assert isinstance(pilot.app.screen, AgentSelectModal)

            # Call the action directly since Enter is captured by Select widget
            modal = pilot.app.screen
            assert isinstance(modal, AgentSelectModal)
            modal.action_select()
            await pilot.pause()

            assert isinstance(pilot.app.screen, InstallModal)

    async def test_install_modal_escape_cancels(self):
        """Escape closes InstallModal without installing."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            # Navigate to InstallModal via action
            await pilot.press("i")
            await pilot.pause()
            modal = pilot.app.screen
            assert isinstance(modal, AgentSelectModal)
            modal.action_select()
            await pilot.pause()
            assert isinstance(pilot.app.screen, InstallModal)

            await pilot.press("escape")
            await pilot.pause()

            # Should return to main screen
            assert not isinstance(pilot.app.screen, InstallModal)

    @patch("kagan.agents.installer.install_agent", new_callable=AsyncMock)
    async def test_install_modal_enter_starts_installation(self, mock_install):
        """Enter in InstallModal starts the installation process."""
        mock_install.return_value = (True, "Installed successfully")

        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            # Navigate to InstallModal via action
            await pilot.press("i")
            await pilot.pause()
            select_modal = pilot.app.screen
            assert isinstance(select_modal, AgentSelectModal)
            select_modal.action_select()
            await pilot.pause()
            assert isinstance(pilot.app.screen, InstallModal)

            # Start installation (Enter triggers action_confirm which calls action_install)
            await pilot.press("enter")
            await pilot.pause()

            mock_install.assert_called_once()

    async def test_i_key_ignored_when_not_no_agents_case(self):
        """'i' key shows warning when issues aren't about missing agents."""
        # Use a non-agent issue type (tmux missing is not about missing agents)
        issues = [DetectedIssue(preset=ISSUE_PRESETS[NON_AGENT_ISSUE_TYPE])]
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()

            # Should not open any modal
            assert not isinstance(pilot.app.screen, AgentSelectModal)
            assert not isinstance(pilot.app.screen, InstallModal)


class TestInstallModalUI:
    """Tests for InstallModal UI elements."""

    async def test_install_modal_shows_agent_name(self):
        """InstallModal displays the agent name being installed."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            # Navigate to InstallModal via action
            await pilot.press("i")
            await pilot.pause()
            select_modal = pilot.app.screen
            assert isinstance(select_modal, AgentSelectModal)
            select_modal.action_select()
            await pilot.pause()

            modal = pilot.app.screen
            assert isinstance(modal, InstallModal)

            # Check that the modal has content (title with agent name)
            title_labels = list(modal.query(".install-modal-title"))
            assert len(title_labels) >= 1

    async def test_install_modal_shows_install_command(self):
        """InstallModal displays the installation command."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            # Navigate to InstallModal via action
            await pilot.press("i")
            await pilot.pause()
            select_modal = pilot.app.screen
            assert isinstance(select_modal, AgentSelectModal)
            select_modal.action_select()
            await pilot.pause()

            modal = pilot.app.screen
            assert isinstance(modal, InstallModal)

            # Check for command display
            cmd_label = modal.query_one("#install-command")
            assert cmd_label is not None


class TestAgentSelectModalUI:
    """Tests for AgentSelectModal UI elements."""

    async def test_agent_select_modal_shows_title(self):
        """AgentSelectModal displays selection title."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()

            modal = pilot.app.screen
            assert isinstance(modal, AgentSelectModal)

            # Check that the modal has a title
            title_labels = list(modal.query(".install-modal-title"))
            assert len(title_labels) >= 1

    async def test_agent_select_modal_has_select_widget(self):
        """AgentSelectModal has a Select widget for choosing agents."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()

            modal = pilot.app.screen
            assert isinstance(modal, AgentSelectModal)

            # Check for select widget
            select_widget = modal.query_one("#agent-select")
            assert select_widget is not None


class TestNoAgentsExitHint:
    """Tests for exit hint display in no-agents case."""

    async def test_exit_hint_element_exists_in_no_agents_case(self):
        """Exit hint element is displayed when no agents found."""
        issues = create_no_agents_issues()
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            # Verify the exit hint element exists
            exit_hint = app.query_one("#troubleshoot-exit-hint")
            assert exit_hint is not None

    async def test_exit_hint_element_exists_in_other_cases(self):
        """Exit hint element is displayed for other issue types."""
        issues = [DetectedIssue(preset=ISSUE_PRESETS[NON_AGENT_ISSUE_TYPE])]
        app = TroubleshootingApp(issues)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            # Verify the exit hint element exists
            exit_hint = app.query_one("#troubleshoot-exit-hint")
            assert exit_hint is not None
