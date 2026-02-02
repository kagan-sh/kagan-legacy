"""E2E tests for HelpModal."""

from __future__ import annotations

import pytest

from kagan.ui.modals.help import HelpModal
from tests.helpers.pages import is_on_screen, navigate_to_kanban

pytestmark = pytest.mark.e2e


class TestHelpModalOpen:
    """Tests for opening the help modal."""

    @pytest.mark.parametrize("key", ["f1", "question_mark"])
    async def test_open_help_from_kanban(self, e2e_app, key):
        """Help modal opens with F1 or ? from kanban screen."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            # Press the key to open help
            await pilot.press(key)
            await pilot.pause()

            # When a ModalScreen is active, it becomes the current screen
            assert isinstance(pilot.app.screen, HelpModal), (
                f"HelpModal should be open after pressing {key}, "
                f"but screen is {type(pilot.app.screen).__name__}"
            )


class TestHelpModalClose:
    """Tests for closing the help modal."""

    @pytest.mark.parametrize("key", ["escape", "q"])
    async def test_close_help_modal(self, e2e_app, key):
        """Help modal closes with Escape or q key."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            # Open help modal via f1
            await pilot.press("f1")
            await pilot.pause()

            # Verify it's open
            assert isinstance(pilot.app.screen, HelpModal), "HelpModal should be open"

            # Close with the key
            await pilot.press(key)
            await pilot.pause()

            # Verify it's closed (should be back on kanban)
            assert not isinstance(pilot.app.screen, HelpModal), (
                "HelpModal should be closed after pressing " + key
            )
            assert is_on_screen(pilot, "Kanban"), "Should be back on Kanban after closing help"


class TestHelpModalTabs:
    """Tests for help modal tab navigation."""

    async def test_help_modal_has_tabs(self, e2e_app):
        """Help modal contains tabbed content with keybindings, navigation, concepts, workflows."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            # Open help modal
            await pilot.press("f1")
            await pilot.pause()

            # Verify TabbedContent exists with expected tabs
            from textual.widgets import TabbedContent

            tabbed = pilot.app.screen.query_one("#help-tabs", TabbedContent)
            assert tabbed is not None

            # Check tab panes exist
            tab_ids = ["tab-keys", "tab-nav", "tab-concepts", "tab-workflows"]
            for tab_id in tab_ids:
                pane = pilot.app.screen.query_one(f"#{tab_id}")
                assert pane is not None, f"Tab pane {tab_id} should exist"


class TestHelpModalContent:
    """Tests for help modal content rendering."""

    async def test_keybindings_section_renders(self, e2e_app):
        """Keybindings tab renders navigation and primary action keys."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            # Open help modal
            await pilot.press("f1")
            await pilot.pause()

            # Verify keybindings content exists
            keybindings = pilot.app.screen.query_one("#keybindings-content")
            assert keybindings is not None

    async def test_help_modal_shows_title(self, e2e_app):
        """Help modal displays the title 'Kagan Help'."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            # Open help modal
            await pilot.press("f1")
            await pilot.pause()

            # Look for title label by CSS class
            from textual.widgets import Label

            title_label = pilot.app.screen.query_one(".modal-title", Label)
            # Render as text and check for "Kagan Help"
            rendered = str(title_label.render())
            assert "Kagan" in rendered and "Help" in rendered
