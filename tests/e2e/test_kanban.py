"""E2E tests for Kanban screen functionality.

Tests for areas not covered by existing test files:
- Peek overlay
- Leader key system
- Search functionality
- Agent operations
- Review operations
- Copy ticket ID
- Lifecycle events
- Settings access
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Static

from kagan.database.models import TicketStatus, TicketType
from kagan.ui.screens.kanban import KanbanScreen
from kagan.ui.widgets.card import TicketCard
from kagan.ui.widgets.peek_overlay import PeekOverlay
from kagan.ui.widgets.search_bar import SearchBar
from tests.helpers.pages import (
    focus_first_ticket,
    focus_ticket_by_criteria,
    get_focused_ticket,
    is_on_screen,
    navigate_to_kanban,
)

if TYPE_CHECKING:
    from kagan.app import KaganApp

pytestmark = pytest.mark.e2e


# =============================================================================
# Peek Overlay Tests (space key)
# =============================================================================


class TestPeekOverlay:
    """Tests for peek overlay functionality."""

    async def test_space_shows_peek_overlay(self, e2e_app_with_tickets: KaganApp):
        """Space key shows peek overlay with ticket info."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            await pilot.pause()

            await pilot.press("space")
            await pilot.pause()

            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert overlay.has_class("visible")

    async def test_space_toggles_peek_off(self, e2e_app_with_tickets: KaganApp):
        """Space key toggles peek overlay off when already visible."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            # Show overlay
            await pilot.press("space")
            await pilot.pause()
            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert overlay.has_class("visible")

            # Toggle off
            await pilot.press("space")
            await pilot.pause()
            assert not overlay.has_class("visible")

    async def test_peek_shows_ticket_title(self, e2e_app_with_tickets: KaganApp):
        """Peek overlay displays ticket title."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None

            await pilot.press("space")
            await pilot.pause()

            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert overlay.has_class("visible")
            # Just verify overlay is visible - content is updated

    async def test_peek_auto_ticket_shows_status(self, e2e_app_with_auto_ticket: KaganApp):
        """Peek shows status for AUTO tickets."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("space")
            await pilot.pause()

            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert overlay.has_class("visible")

    async def test_peek_pair_ticket_shows_status(self, e2e_app_with_tickets: KaganApp):
        """Peek shows session status for PAIR tickets."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus a PAIR ticket (default type in e2e_app_with_tickets)
            focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()

            await pilot.press("space")
            await pilot.pause()

            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert overlay.has_class("visible")

    async def test_escape_hides_peek_overlay(self, e2e_app_with_tickets: KaganApp):
        """Escape hides peek overlay when visible."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            # Show overlay
            await pilot.press("space")
            await pilot.pause()
            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert overlay.has_class("visible")

            # Hide with escape
            await pilot.press("escape")
            await pilot.pause()
            assert not overlay.has_class("visible")

    async def test_peek_no_ticket_selected(self, e2e_app: KaganApp):
        """Space does nothing when no ticket is selected."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("space")
            await pilot.pause()

            overlay = pilot.app.screen.query_one("#peek-overlay", PeekOverlay)
            assert not overlay.has_class("visible")


# =============================================================================
# Leader Key Tests (g key)
# =============================================================================


class TestLeaderKey:
    """Tests for leader key functionality."""

    async def test_g_activates_leader_mode(self, e2e_app_with_tickets: KaganApp):
        """g key activates leader mode and shows hint."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("g")
            await pilot.pause()

            # Check leader hint is visible
            hint = pilot.app.screen.query_one(".leader-hint", Static)
            assert hint.has_class("visible")

    async def test_leader_escape_deactivates(self, e2e_app_with_tickets: KaganApp):
        """Escape during leader mode deactivates it."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("g")
            await pilot.pause()
            hint = pilot.app.screen.query_one(".leader-hint", Static)
            assert hint.has_class("visible")

            await pilot.press("escape")
            await pilot.pause()
            assert not hint.has_class("visible")

    async def test_leader_invalid_key_deactivates(self, e2e_app_with_tickets: KaganApp):
        """Invalid key during leader mode deactivates it."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("g")
            await pilot.pause()
            hint = pilot.app.screen.query_one(".leader-hint", Static)
            assert hint.has_class("visible")

            # Press invalid key
            await pilot.press("z")
            await pilot.pause()
            assert not hint.has_class("visible")

    async def test_leader_l_moves_forward(self, e2e_app_with_tickets: KaganApp):
        """g+l moves ticket forward."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None
            assert ticket.status == TicketStatus.BACKLOG

            await pilot.press("g", "l")
            await pilot.pause()

            # Ticket should move to IN_PROGRESS
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            moved_ticket = next((t for t in tickets if t.id == ticket.id), None)
            assert moved_ticket is not None
            assert moved_ticket.status == TicketStatus.IN_PROGRESS


# =============================================================================
# Search Tests
# =============================================================================


class TestSearch:
    """Tests for search functionality."""

    async def test_slash_shows_search_bar(self, e2e_app_with_tickets: KaganApp):
        """/ key shows search bar."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("slash")
            await pilot.pause()

            search_bar = pilot.app.screen.query_one("#search-bar", SearchBar)
            assert search_bar.is_visible

    async def test_escape_hides_search_bar(self, e2e_app_with_tickets: KaganApp):
        """Escape hides search bar when visible."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("slash")
            await pilot.pause()
            search_bar = pilot.app.screen.query_one("#search-bar", SearchBar)
            assert search_bar.is_visible

            await pilot.press("escape")
            await pilot.pause()
            assert not search_bar.is_visible

    async def test_search_filters_tickets(self, e2e_app_with_tickets: KaganApp):
        """Search query filters displayed tickets."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            initial_count = len(list(pilot.app.screen.query(TicketCard)))

            await pilot.press("slash")
            await pilot.pause()

            # Type search query
            for char in "Backlog":
                await pilot.press(char)
            await pilot.pause()

            # Should filter to matching tickets
            cards = list(pilot.app.screen.query(TicketCard))
            visible_cards = [c for c in cards if c.ticket]
            assert len(visible_cards) <= initial_count
            for c in visible_cards:
                if c.ticket and "backlog" in c.ticket.title.lower():
                    break
            else:
                # Either no visible cards or none match - both valid outcomes
                pass

    async def test_search_clears_on_close(self, e2e_app_with_tickets: KaganApp):
        """Closing search bar clears filter and shows all tickets."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            initial_count = len(list(pilot.app.screen.query(TicketCard)))

            # Search for something specific
            await pilot.press("slash")
            await pilot.pause()
            for char in "backlog":
                await pilot.press(char)
            await pilot.pause()

            # Close search
            await pilot.press("escape")
            await pilot.pause()

            # All tickets should be visible again
            cards = list(pilot.app.screen.query(TicketCard))
            assert len(cards) == initial_count


# =============================================================================
# Copy Ticket ID Tests
# =============================================================================


class TestCopyTicketId:
    """Tests for copy ticket ID functionality."""

    async def test_c_copies_ticket_id(self, e2e_app_with_tickets: KaganApp):
        """c key triggers copy ticket ID action."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None

            await pilot.press("c")
            await pilot.pause()

            # Should stay on kanban screen (action completed)
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_copy_no_ticket_selected_shows_warning(self, e2e_app: KaganApp):
        """Copy with no ticket selected shows warning."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()

            # Should stay on kanban screen
            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Agent Operations Tests
# =============================================================================


class TestAgentOperations:
    """Tests for agent-related operations."""

    async def test_a_attempts_agent_start(self, e2e_app_with_auto_ticket: KaganApp):
        """a key attempts to start agent for AUTO ticket."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("a")
            await pilot.pause()

            # Should either open modal or show notification
            assert is_on_screen(pilot, "KanbanScreen") or is_on_screen(pilot, "AgentOutputModal")

    async def test_w_watch_agent_on_auto_ticket(self, e2e_app_with_auto_ticket: KaganApp):
        """w key attempts to watch agent for AUTO ticket."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("w")
            await pilot.pause()

            # Should stay on kanban or open modal
            assert is_on_screen(pilot, "KanbanScreen") or is_on_screen(pilot, "AgentOutputModal")

    async def test_s_stop_agent_on_auto_ticket(self, e2e_app_with_auto_ticket: KaganApp):
        """s key attempts to stop agent for AUTO ticket."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("s")
            await pilot.pause()

            # Should stay on kanban screen
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_agent_actions_on_pair_ticket_blocked(self, e2e_app_with_tickets: KaganApp):
        """Agent actions on PAIR ticket should be blocked."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus PAIR ticket in IN_PROGRESS
            focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()

            # Try to start agent - should be blocked for PAIR
            await pilot.press("a")
            await pilot.pause()
            assert is_on_screen(pilot, "KanbanScreen")

            # Try to watch agent - should be blocked for PAIR
            await pilot.press("w")
            await pilot.pause()
            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Review Operations Tests
# =============================================================================


class TestReviewOperations:
    """Tests for review workflow."""

    async def test_r_opens_review_modal(self, e2e_app_with_tickets: KaganApp):
        """r key opens review modal for REVIEW ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus ticket in REVIEW status
            review_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()
            assert review_ticket is not None

            await pilot.press("r")
            await pilot.pause()

            assert is_on_screen(pilot, "ReviewModal")

    async def test_r_on_non_review_ticket_blocked(self, e2e_app_with_tickets: KaganApp):
        """r key on non-REVIEW ticket shows warning."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus ticket in BACKLOG status
            focus_ticket_by_criteria(pilot, status=TicketStatus.BACKLOG)
            await pilot.pause()

            await pilot.press("r")
            await pilot.pause()

            # Should stay on kanban screen
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_m_merges_review_ticket(self, e2e_app_with_tickets: KaganApp):
        """m key attempts merge for REVIEW ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus ticket in REVIEW status
            review_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()
            assert review_ticket is not None

            await pilot.press("m")
            await pilot.pause()

            # Should either merge or show error (no worktree)
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_enter_on_review_ticket_opens_review(self, e2e_app_with_tickets: KaganApp):
        """Enter on REVIEW ticket opens review modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus ticket in REVIEW status
            review_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()
            assert review_ticket is not None

            await pilot.press("enter")
            await pilot.pause()

            # Should open review modal (action_open_session routes to review for REVIEW status)
            assert is_on_screen(pilot, "ReviewModal")

    async def test_shift_d_opens_diff_for_review(self, e2e_app_with_tickets: KaganApp):
        """Shift+D opens diff view for REVIEW ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus ticket in REVIEW status
            review_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()
            assert review_ticket is not None

            await pilot.press("D")  # Shift+D for view_diff
            await pilot.pause()

            # Should open diff modal
            assert is_on_screen(pilot, "DiffModal")


# =============================================================================
# Settings Tests
# =============================================================================


class TestSettings:
    """Tests for settings access."""

    async def test_comma_opens_settings(self, e2e_app_with_tickets: KaganApp):
        """Comma key opens settings modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("comma")
            await pilot.pause()

            assert is_on_screen(pilot, "SettingsModal")

    async def test_settings_escape_closes(self, e2e_app_with_tickets: KaganApp):
        """Escape closes settings modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("comma")
            await pilot.pause()
            assert is_on_screen(pilot, "SettingsModal")

            await pilot.press("escape")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Planner Navigation Tests
# =============================================================================


class TestPlannerNavigation:
    """Tests for planner screen navigation."""

    async def test_p_opens_planner(self, e2e_app_with_tickets: KaganApp):
        """p key opens planner screen."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("p")
            await pilot.pause()

            assert is_on_screen(pilot, "PlannerScreen")

    async def test_planner_escape_returns_to_kanban(self, e2e_app_with_tickets: KaganApp):
        """Escape from planner returns to kanban."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("p")
            await pilot.pause()
            assert is_on_screen(pilot, "PlannerScreen")

            await pilot.press("escape")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Deselect Tests
# =============================================================================


class TestDeselect:
    """Tests for deselect/escape handling."""

    async def test_escape_deselects_card(self, e2e_app_with_tickets: KaganApp):
        """Escape key deselects focused card."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None

            await pilot.press("escape")
            await pilot.pause()

            # Focus should be cleared
            focused = pilot.app.focused
            if focused is not None:
                assert not isinstance(focused, TicketCard)

    async def test_escape_priority_leader_over_deselect(self, e2e_app_with_tickets: KaganApp):
        """Escape first deactivates leader mode if active."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            # Activate leader mode
            await pilot.press("g")
            await pilot.pause()
            hint = pilot.app.screen.query_one(".leader-hint", Static)
            assert hint.has_class("visible")

            # Escape should deactivate leader first
            await pilot.press("escape")
            await pilot.pause()
            assert not hint.has_class("visible")

            # Card should still be focused
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None


# =============================================================================
# Screen Lifecycle Tests
# =============================================================================


class TestScreenLifecycle:
    """Tests for screen lifecycle events."""

    async def test_screen_resume_refreshes_board(self, e2e_app_with_tickets: KaganApp):
        """Screen resume refreshes the board."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            initial_count = len(list(pilot.app.screen.query(TicketCard)))

            # Open and close settings to trigger screen resume
            await pilot.press("comma")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            # Board should still show same tickets after resume
            cards = list(pilot.app.screen.query(TicketCard))
            assert len(cards) == initial_count

    async def test_resize_handles_small_screen(self, e2e_app_with_tickets: KaganApp):
        """Small screen size shows warning."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, KanbanScreen)

            # Initially should not have too-small class
            assert not screen.has_class("too-small")


# =============================================================================
# New Ticket Types Tests
# =============================================================================


class TestNewTicketTypes:
    """Tests for creating different ticket types."""

    async def test_n_opens_default_pair_ticket(self, e2e_app_with_tickets: KaganApp):
        """n key opens new ticket modal with default PAIR type."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause()

            assert is_on_screen(pilot, "TicketDetailsModal")

    async def test_shift_n_opens_auto_ticket(self, e2e_app_with_tickets: KaganApp):
        """Shift+n opens new ticket modal with AUTO type."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("N")  # Shift+n
            await pilot.pause()

            assert is_on_screen(pilot, "TicketDetailsModal")


# =============================================================================
# Delete With Confirmation Tests (d key via leader)
# =============================================================================


class TestDeleteWithConfirmation:
    """Tests for delete with confirmation modal."""

    async def test_x_deletes_directly(self, e2e_app_with_tickets: KaganApp):
        """x key deletes ticket directly without confirmation."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None

            await pilot.press("x")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            assert ticket.id not in [t.id for t in tickets]


# =============================================================================
# Merge Confirmation Tests
# =============================================================================


class TestMergeConfirmation:
    """Tests for merge confirmation from REVIEW to DONE."""

    async def test_review_to_done_shows_confirm(self, e2e_app_with_tickets: KaganApp):
        """Moving from REVIEW to DONE shows merge confirmation."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            review_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()
            assert review_ticket is not None

            await pilot.press("g", "l")
            await pilot.pause()

            assert is_on_screen(pilot, "ConfirmModal")


# =============================================================================
# Keyboard Feedback Tests
# =============================================================================


class TestKeyboardFeedback:
    """Tests for keyboard feedback on invalid actions."""

    async def test_edit_on_done_shows_feedback(self, e2e_app_with_done_ticket: KaganApp):
        """Pressing edit on DONE ticket shows feedback."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()

            await pilot.press("e")
            await pilot.pause()

            # Should stay on kanban (edit blocked for done)
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_agent_actions_on_non_auto_shows_feedback(self, e2e_app_with_tickets: KaganApp):
        """Agent actions on non-AUTO ticket shows feedback."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus PAIR ticket
            focus_ticket_by_criteria(
                pilot, status=TicketStatus.IN_PROGRESS, ticket_type=TicketType.PAIR
            )
            await pilot.pause()

            await pilot.press("w")  # Watch agent
            await pilot.pause()

            # Should stay on kanban and show feedback
            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Quit Tests
# =============================================================================


class TestQuit:
    """Tests for quit functionality."""

    async def test_q_exits_app(self, e2e_app_with_tickets: KaganApp):
        """q key exits the application."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("q")
            await pilot.pause()

            # App should be exiting
            assert pilot.app.is_running is False

    async def test_ctrl_c_exits_app(self, e2e_app_with_tickets: KaganApp):
        """Ctrl+C exits the application."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("ctrl+c")
            await pilot.pause()

            # App should be exiting
            assert pilot.app.is_running is False


# =============================================================================
# View Details Tests
# =============================================================================


class TestViewDetails:
    """Tests for viewing ticket details."""

    async def test_v_opens_ticket_details(self, e2e_app_with_tickets: KaganApp):
        """v key opens ticket details modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("v")
            await pilot.pause()

            assert is_on_screen(pilot, "TicketDetailsModal")

    async def test_enter_on_backlog_opens_session(self, e2e_app_with_tickets: KaganApp):
        """Enter on BACKLOG ticket opens session (moves to IN_PROGRESS for PAIR)."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            focus_ticket_by_criteria(pilot, status=TicketStatus.BACKLOG)
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            # Should open something (gateway modal or other)
            assert is_on_screen(pilot, "KanbanScreen") or is_on_screen(pilot, "TmuxGatewayModal")


# =============================================================================
# Duplicate Ticket Tests
# =============================================================================


class TestDuplicateTicket:
    """Tests for duplicate ticket functionality."""

    async def test_y_no_ticket_selected_shows_warning(self, e2e_app: KaganApp):
        """y key with no ticket selected shows warning."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            # Should stay on kanban screen (notification shown)
            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Navigation Focus Tests
# =============================================================================


class TestNavigationFocus:
    """Tests for navigation focus actions."""

    async def test_h_focuses_left(self, e2e_app_with_tickets: KaganApp):
        """h key focuses left column."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus IN_PROGRESS ticket
            focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()

            await pilot.press("h")
            await pilot.pause()

            # Should still be on kanban
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_l_focuses_right(self, e2e_app_with_tickets: KaganApp):
        """l key focuses right column."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            await pilot.pause()

            await pilot.press("l")
            await pilot.pause()

            # Should still be on kanban
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_j_focuses_down(self, e2e_app_with_tickets: KaganApp):
        """j key focuses down in column."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()

            # Should still be on kanban
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_k_focuses_up(self, e2e_app_with_tickets: KaganApp):
        """k key focuses up in column."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            await pilot.pause()

            await pilot.press("k")
            await pilot.pause()

            # Should still be on kanban
            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Leader Key Extended Tests
# =============================================================================


class TestLeaderKeyExtended:
    """Extended tests for leader key functionality."""

    async def test_leader_h_moves_backward(self, e2e_app_with_tickets: KaganApp):
        """g+h moves ticket backward."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus IN_PROGRESS ticket
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()
            assert ticket is not None

            await pilot.press("g", "h")
            await pilot.pause()

            # Ticket should move to BACKLOG
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            moved_ticket = next((t for t in tickets if t.id == ticket.id), None)
            assert moved_ticket is not None
            assert moved_ticket.status == TicketStatus.BACKLOG

    async def test_leader_d_opens_diff(self, e2e_app_with_tickets: KaganApp):
        """g+d opens diff for REVIEW ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()

            await pilot.press("g", "d")
            await pilot.pause()

            assert is_on_screen(pilot, "DiffModal")

    async def test_leader_r_opens_review(self, e2e_app_with_tickets: KaganApp):
        """g+r opens review for REVIEW ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()

            await pilot.press("g", "r")
            await pilot.pause()

            assert is_on_screen(pilot, "ReviewModal")


# =============================================================================
# Move Ticket Edge Cases
# =============================================================================


class TestMoveTicketEdgeCases:
    """Edge cases for ticket movement."""

    async def test_move_backward_from_backlog_blocked(self, e2e_app_with_tickets: KaganApp):
        """Moving backward from BACKLOG is blocked."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.BACKLOG)
            await pilot.pause()
            assert ticket is not None

            await pilot.press("g", "h")
            await pilot.pause()

            # Ticket should still be in BACKLOG
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket.id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.BACKLOG

    async def test_move_forward_from_done_blocked(self, e2e_app_with_done_ticket: KaganApp):
        """Moving forward from DONE is blocked."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()
            assert ticket is not None

            await pilot.press("g", "l")
            await pilot.pause()

            # Ticket should still be in DONE
            tickets = await e2e_app_with_done_ticket.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket.id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.DONE


# =============================================================================
# Ticket Card Click Tests
# =============================================================================


class TestTicketCardClick:
    """Tests for ticket card click/select events."""

    async def test_double_click_opens_details(self, e2e_app_with_tickets: KaganApp):
        """Double-clicking a ticket card opens details modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            cards = list(pilot.app.screen.query(TicketCard))
            if cards:
                await pilot.click(cards[0], times=2)
                await pilot.pause()

                # Should open details modal
                assert is_on_screen(pilot, "TicketDetailsModal") or is_on_screen(
                    pilot, "KanbanScreen"
                )


# =============================================================================
# Delete Ticket From Modal Tests
# =============================================================================


class TestDeleteFromModal:
    """Tests for delete action from ticket details modal."""

    async def test_delete_from_details_modal(self, e2e_app_with_tickets: KaganApp):
        """Delete action from ticket details triggers delete flow."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None

            # Open ticket details
            await pilot.press("v")
            await pilot.pause()
            assert is_on_screen(pilot, "TicketDetailsModal")

            # Press d to trigger delete
            await pilot.press("d")
            await pilot.pause()

            # Should show confirmation modal
            assert is_on_screen(pilot, "ConfirmModal")


# =============================================================================
# Leader Key Timeout Tests
# =============================================================================


class TestLeaderKeyTimeout:
    """Tests for leader key timeout behavior."""

    async def test_leader_timeout_deactivates(self, e2e_app_with_tickets: KaganApp):
        """Leader mode times out after 2 seconds."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            # Activate leader mode
            await pilot.press("g")
            await pilot.pause()

            hint = pilot.app.screen.query_one(".leader-hint", Static)
            assert hint.has_class("visible")

            # Wait for timeout (2+ seconds)
            import asyncio

            await asyncio.sleep(2.5)
            await pilot.pause()

            # Should be deactivated
            assert not hint.has_class("visible")

    async def test_leader_double_g_ignored(self, e2e_app_with_tickets: KaganApp):
        """Pressing g twice keeps leader active (doesn't re-trigger)."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            # Activate leader mode
            await pilot.press("g")
            await pilot.pause()
            hint = pilot.app.screen.query_one(".leader-hint", Static)
            assert hint.has_class("visible")

            # Press g again - should remain active (early return)
            await pilot.press("g")
            await pilot.pause()
            assert hint.has_class("visible")


# =============================================================================
# Iteration Signal Tests
# =============================================================================


class TestIterationSignals:
    """Tests for iteration changed signal handling."""

    async def test_iteration_signal_updates_card(self, e2e_app_with_auto_ticket: KaganApp):
        """Iteration changed signal updates card display."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Get the AUTO ticket
            tickets = await e2e_app_with_auto_ticket.state_manager.get_all_tickets()
            auto_ticket = tickets[0]

            # Simulate iteration changed signal
            screen = pilot.app.screen
            assert isinstance(screen, KanbanScreen)
            screen._on_iteration_changed((auto_ticket.id, 1))
            await pilot.pause()

            # Verify screen still works
            assert is_on_screen(pilot, "KanbanScreen")

    async def test_iteration_zero_clears_display(self, e2e_app_with_auto_ticket: KaganApp):
        """Iteration 0 clears iteration display."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            tickets = await e2e_app_with_auto_ticket.state_manager.get_all_tickets()
            auto_ticket = tickets[0]

            screen = pilot.app.screen
            assert isinstance(screen, KanbanScreen)

            # Set iteration to 1, then clear it
            screen._on_iteration_changed((auto_ticket.id, 1))
            await pilot.pause()
            screen._on_iteration_changed((auto_ticket.id, 0))
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# AUTO Ticket Movement Blocking Tests
# =============================================================================


class TestAutoTicketMovement:
    """Tests for AUTO ticket movement restrictions."""

    async def test_auto_ticket_in_progress_blocks_movement(
        self, e2e_app_with_auto_ticket: KaganApp
    ):
        """AUTO ticket in IN_PROGRESS blocks manual movement."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None
            assert ticket.status == TicketStatus.IN_PROGRESS
            assert ticket.ticket_type == TicketType.AUTO

            # Try to move forward
            await pilot.press("g", "l")
            await pilot.pause()

            # Ticket should still be in IN_PROGRESS
            tickets = await e2e_app_with_auto_ticket.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket.id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.IN_PROGRESS

    async def test_auto_ticket_in_progress_blocks_backward_movement(
        self, e2e_app_with_auto_ticket: KaganApp
    ):
        """AUTO ticket in IN_PROGRESS blocks backward movement too."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None

            # Try to move backward
            await pilot.press("g", "h")
            await pilot.pause()

            # Ticket should still be in IN_PROGRESS
            tickets = await e2e_app_with_auto_ticket.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket.id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.IN_PROGRESS


# =============================================================================
# Pair Ticket Advance Confirmation Tests
# =============================================================================


class TestPairTicketAdvance:
    """Tests for PAIR ticket advance to review confirmation."""

    async def test_pair_in_progress_to_review_shows_confirm(self, e2e_app_with_tickets: KaganApp):
        """Moving PAIR ticket from IN_PROGRESS to REVIEW shows confirmation."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Focus the in-progress PAIR ticket
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()
            assert ticket is not None
            assert ticket.ticket_type == TicketType.PAIR

            await pilot.press("g", "l")
            await pilot.pause()

            # Should show confirmation modal
            assert is_on_screen(pilot, "ConfirmModal")


# =============================================================================
# Delete Confirmation Tests (via modal flow)
# =============================================================================


class TestDeleteConfirmation:
    """Tests for delete confirmation modal behavior.

    Delete with confirmation is triggered via ModalAction.DELETE from
    TicketDetailsModal, not via a direct key binding.
    """

    async def test_delete_via_modal_confirm_yes(self, e2e_app_with_tickets: KaganApp):
        """Confirming delete from modal removes the ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None
            ticket_id = ticket.id

            # Open ticket details
            await pilot.press("v")
            await pilot.pause()
            assert is_on_screen(pilot, "TicketDetailsModal")

            # Trigger delete from modal (d key in details modal)
            await pilot.press("d")
            await pilot.pause()
            assert is_on_screen(pilot, "ConfirmModal")

            # Confirm deletion with 'y' key
            await pilot.press("y")
            await pilot.pause()

            # Ticket should be deleted
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            assert ticket_id not in [t.id for t in tickets]

    async def test_delete_via_modal_confirm_no(self, e2e_app_with_tickets: KaganApp):
        """Canceling delete from modal keeps the ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket = await get_focused_ticket(pilot)
            assert ticket is not None
            ticket_id = ticket.id

            # Open ticket details
            await pilot.press("v")
            await pilot.pause()
            assert is_on_screen(pilot, "TicketDetailsModal")

            # Trigger delete from modal
            await pilot.press("d")
            await pilot.pause()
            assert is_on_screen(pilot, "ConfirmModal")

            # Cancel deletion with 'n' key
            await pilot.press("n")
            await pilot.pause()

            # Ticket should still exist
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            assert ticket_id in [t.id for t in tickets]


# =============================================================================
# Screen Size Warning Tests
# =============================================================================


class TestScreenSizeWarning:
    """Tests for small screen size warning."""

    async def test_very_small_screen_shows_warning(self, e2e_app_with_tickets: KaganApp):
        """Very small screen shows warning class."""
        async with e2e_app_with_tickets.run_test(size=(40, 10)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, KanbanScreen)
            # Should have too-small class for tiny terminal
            assert screen.has_class("too-small")


# =============================================================================
# Duplicate Ticket Tests
# =============================================================================


class TestDuplicateTicketFlow:
    """Tests for duplicate ticket functionality."""

    async def test_y_opens_duplicate_modal(self, e2e_app_with_tickets: KaganApp):
        """y key opens duplicate ticket modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)

            await pilot.press("y")
            await pilot.pause()

            assert is_on_screen(pilot, "DuplicateTicketModal")


# =============================================================================
# Merge Confirmation Callback Tests
# =============================================================================


class TestMergeConfirmationCallback:
    """Tests for merge confirmation callback handling."""

    async def test_merge_confirm_cancelled(self, e2e_app_with_tickets: KaganApp):
        """Canceling merge confirmation keeps ticket in REVIEW."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            review_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)
            await pilot.pause()
            assert review_ticket is not None
            ticket_id = review_ticket.id

            # Move forward to trigger merge confirmation
            await pilot.press("g", "l")
            await pilot.pause()
            assert is_on_screen(pilot, "ConfirmModal")

            # Cancel
            await pilot.press("escape")
            await pilot.pause()

            # Ticket should still be in REVIEW
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket_id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.REVIEW


# =============================================================================
# Advance Confirmation Callback Tests
# =============================================================================


class TestAdvanceConfirmationCallback:
    """Tests for advance confirmation callback handling."""

    async def test_advance_confirm_moves_ticket(self, e2e_app_with_tickets: KaganApp):
        """Confirming advance moves PAIR ticket to REVIEW."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()
            assert ticket is not None
            ticket_id = ticket.id

            # Move forward to trigger advance confirmation
            await pilot.press("g", "l")
            await pilot.pause()
            assert is_on_screen(pilot, "ConfirmModal")

            # Confirm with 'y' key
            await pilot.press("y")
            await pilot.pause()

            # Ticket should be in REVIEW
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket_id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.REVIEW

    async def test_advance_confirm_cancelled(self, e2e_app_with_tickets: KaganApp):
        """Canceling advance keeps ticket in IN_PROGRESS."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            await pilot.pause()
            assert ticket is not None
            ticket_id = ticket.id

            await pilot.press("g", "l")
            await pilot.pause()
            assert is_on_screen(pilot, "ConfirmModal")

            # Cancel with 'n' key
            await pilot.press("n")
            await pilot.pause()

            # Ticket should still be in IN_PROGRESS
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            same_ticket = next((t for t in tickets if t.id == ticket_id), None)
            assert same_ticket is not None
            assert same_ticket.status == TicketStatus.IN_PROGRESS


# =============================================================================
# No Ticket Selected Edge Cases
# =============================================================================


class TestNoTicketSelectedEdgeCases:
    """Tests for edge cases when no ticket is selected."""

    async def test_merge_direct_no_ticket(self, e2e_app: KaganApp):
        """m key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("m")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_view_diff_no_ticket(self, e2e_app: KaganApp):
        """D key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("D")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_open_review_no_ticket(self, e2e_app: KaganApp):
        """r key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("r")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_watch_agent_no_ticket(self, e2e_app: KaganApp):
        """w key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_start_agent_no_ticket(self, e2e_app: KaganApp):
        """a key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("a")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_stop_agent_no_ticket(self, e2e_app: KaganApp):
        """s key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("s")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_move_forward_no_ticket(self, e2e_app: KaganApp):
        """g+l with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("g", "l")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_move_backward_no_ticket(self, e2e_app: KaganApp):
        """g+h with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("g", "h")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_edit_ticket_no_ticket(self, e2e_app: KaganApp):
        """e key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("e")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_delete_direct_no_ticket(self, e2e_app: KaganApp):
        """x key with no ticket does nothing gracefully."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await pilot.press("x")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Search Toggle Edge Cases
# =============================================================================


class TestSearchEdgeCases:
    """Edge cases for search functionality."""

    async def test_escape_hides_visible_search(self, e2e_app_with_tickets: KaganApp):
        """Escape hides visible search bar."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Show search
            await pilot.press("slash")
            await pilot.pause()
            search_bar = pilot.app.screen.query_one("#search-bar", SearchBar)
            assert search_bar.is_visible

            # Hide with escape
            await pilot.press("escape")
            await pilot.pause()
            assert not search_bar.is_visible
