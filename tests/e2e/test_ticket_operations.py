"""E2E tests for ticket operations (create, view, edit, delete, move) and modal interactions.

Tests: n/v/e/x keybindings, ticket movement with g+h/g+l, modal view/edit modes,
saving changes, acceptance criteria.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Input, TextArea

from kagan.database.models import TicketStatus, TicketType
from kagan.ui.widgets.card import TicketCard
from tests.helpers.pages import (
    focus_first_ticket,
    focus_ticket_by_criteria,
    get_focused_ticket,
    get_tickets_by_status,
    is_on_screen,
    open_ticket_modal,
)

if TYPE_CHECKING:
    from kagan.app import KaganApp
    from kagan.ui.modals.ticket_details_modal import TicketDetailsModal

pytestmark = pytest.mark.e2e


def get_modal(pilot) -> TicketDetailsModal:
    """Get the current screen as TicketDetailsModal."""
    return cast("TicketDetailsModal", pilot.app.screen)


# =============================================================================
# Core Ticket Operations (n/v/e/x keybindings)
# =============================================================================


class TestTicketOperations:
    """Test ticket operation keybindings."""

    async def test_n_opens_new_ticket_modal(self, e2e_app_with_tickets: KaganApp):
        """Pressing 'n' opens the new ticket modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert is_on_screen(pilot, "KanbanScreen")
            await pilot.press("n")
            await pilot.pause()
            assert is_on_screen(pilot, "TicketDetailsModal")

    async def test_escape_closes_modal(self, e2e_app_with_tickets: KaganApp):
        """Pressing escape closes the new ticket modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            assert is_on_screen(pilot, "TicketDetailsModal")
            await pilot.press("escape")
            await pilot.pause()
            assert is_on_screen(pilot, "KanbanScreen")

    @pytest.mark.parametrize(
        "mode,expected_editing",
        [
            ("view", False),
            ("edit", True),
        ],
        ids=["view-mode", "edit-mode"],
    )
    async def test_modal_opens_in_correct_mode(
        self, e2e_app_with_tickets: KaganApp, mode: str, expected_editing: bool
    ):
        """Pressing 'v'/'e' opens modal in view/edit mode respectively."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode=mode):  # type: ignore[arg-type]
                assert is_on_screen(pilot, "TicketDetailsModal")
                modal = get_modal(pilot)
                assert modal.editing == expected_editing

    async def test_x_deletes_ticket_directly(self, e2e_app_with_tickets: KaganApp):
        """Pressing 'x' deletes ticket directly without confirmation."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket_before = await get_focused_ticket(pilot)
            assert ticket_before is not None

            await pilot.press("x")
            await pilot.pause()

            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            assert ticket_before.id not in [t.id for t in tickets]


# =============================================================================
# Ticket Movement (g+l/g+h keybindings)
# =============================================================================


class TestTicketMovement:
    """Test ticket movement keybindings."""

    async def test_g_l_moves_forward(self, e2e_app_with_tickets: KaganApp):
        """Pressing 'g' then 'l' moves ticket to next status."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            ticket_before = await get_focused_ticket(pilot)
            assert ticket_before is not None
            assert ticket_before.status == TicketStatus.BACKLOG
            await pilot.press("g", "l")
            await pilot.pause()
            in_progress = await get_tickets_by_status(pilot, TicketStatus.IN_PROGRESS)
            assert any(t.id == ticket_before.id for t in in_progress)

    async def test_g_h_moves_backward(self, e2e_app_with_tickets: KaganApp):
        """Pressing 'g' then 'h' moves ticket to previous status."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.IN_PROGRESS)
            assert ticket is not None
            await pilot.pause()
            await pilot.press("g", "h")
            await pilot.pause()
            backlog = await get_tickets_by_status(pilot, TicketStatus.BACKLOG)
            assert any(t.id == ticket.id for t in backlog)


# =============================================================================
# Movement Rules for Special Ticket Types
# =============================================================================


class TestTicketMovementRules:
    """Test ticket movement rules for PAIR/AUTO types."""

    @pytest.mark.parametrize(
        "direction,keys",
        [
            ("forward", ["g", "l"]),
            ("backward", ["g", "h"]),
        ],
        ids=["forward-blocked", "backward-blocked"],
    )
    async def test_auto_ticket_in_progress_blocks_movement(
        self, e2e_app_with_auto_ticket: KaganApp, direction: str, keys: list[str]
    ):
        """AUTO ticket in IN_PROGRESS should block movement in both directions."""
        async with e2e_app_with_auto_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            auto_ticket = focus_ticket_by_criteria(
                pilot, status=TicketStatus.IN_PROGRESS, ticket_type=TicketType.AUTO
            )
            await pilot.pause()
            assert auto_ticket is not None, "Should have AUTO ticket in IN_PROGRESS"

            await pilot.press(*keys)
            await pilot.pause()

            in_progress = await get_tickets_by_status(pilot, TicketStatus.IN_PROGRESS)
            assert any(t.id == auto_ticket.id for t in in_progress)

    @pytest.mark.parametrize(
        "direction,keys",
        [
            ("forward", ["g", "l"]),
            ("backward", ["g", "h"]),
        ],
        ids=["forward-blocked", "backward-blocked"],
    )
    async def test_done_ticket_movement_blocked(
        self, e2e_app_with_done_ticket: KaganApp, direction: str, keys: list[str]
    ):
        """DONE ticket movement should be blocked in both directions."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            done_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()
            assert done_ticket is not None, "Should have DONE ticket"

            await pilot.press(*keys)
            await pilot.pause()

            done_tickets = await get_tickets_by_status(pilot, TicketStatus.DONE)
            assert any(t.id == done_ticket.id for t in done_tickets)

    async def test_pair_ticket_in_progress_forward_shows_confirm(
        self, e2e_app_with_tickets: KaganApp
    ):
        """PAIR ticket in IN_PROGRESS forward movement should show warning."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            pair_ticket = focus_ticket_by_criteria(
                pilot, status=TicketStatus.IN_PROGRESS, ticket_type=TicketType.PAIR
            )
            await pilot.pause()
            assert pair_ticket is not None, "Should have PAIR ticket in IN_PROGRESS"

            await pilot.press("g", "l")
            await pilot.pause()

            assert is_on_screen(pilot, "ConfirmModal")


# =============================================================================
# Done Ticket Restrictions
# =============================================================================


class TestDoneTicketRestrictions:
    """Test immutable Done state restrictions."""

    async def test_done_ticket_edit_is_blocked(self, e2e_app_with_done_ticket: KaganApp):
        """Pressing 'e' on Done ticket should not open edit mode."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            done_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()
            assert done_ticket is not None, "Should have DONE ticket"

            await pilot.press("e")
            await pilot.pause()

            assert not is_on_screen(pilot, "TicketDetailsModal")

    async def test_done_ticket_view_still_works(self, e2e_app_with_done_ticket: KaganApp):
        """Pressing 'v' on Done ticket should open view details (read-only)."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            assert is_on_screen(pilot, "TicketDetailsModal")

    async def test_done_ticket_delete_still_works(self, e2e_app_with_done_ticket: KaganApp):
        """Pressing 'x' on Done ticket should delete it."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            done_ticket = focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()
            assert done_ticket is not None

            await pilot.press("x")
            await pilot.pause()

            tickets = await e2e_app_with_done_ticket.state_manager.get_all_tickets()
            assert done_ticket.id not in [t.id for t in tickets]


# =============================================================================
# Duplicate Ticket
# =============================================================================


class TestDuplicateTicket:
    """Test ticket duplication feature."""

    async def test_y_opens_duplicate_modal(self, e2e_app_with_tickets: KaganApp):
        """Pressing 'y' opens the duplicate ticket modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await focus_first_ticket(pilot)
            await pilot.press("y")
            await pilot.pause()
            assert is_on_screen(pilot, "DuplicateTicketModal")

    async def test_duplicate_creates_new_ticket_in_backlog(
        self, e2e_app_with_done_ticket: KaganApp
    ):
        """Duplicating a ticket creates a new ticket in BACKLOG."""
        async with e2e_app_with_done_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            initial_count = len(await e2e_app_with_done_ticket.state_manager.get_all_tickets())

            focus_ticket_by_criteria(pilot, status=TicketStatus.DONE)
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()
            assert is_on_screen(pilot, "DuplicateTicketModal")

            await pilot.press("ctrl+s")
            await pilot.pause()

            tickets = await e2e_app_with_done_ticket.state_manager.get_all_tickets()
            assert len(tickets) == initial_count + 1

            backlog_tickets = [t for t in tickets if t.status == TicketStatus.BACKLOG]
            assert len(backlog_tickets) >= 1

    async def test_duplicate_escape_cancels(self, e2e_app_with_tickets: KaganApp):
        """Pressing escape in duplicate modal cancels without creating ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            initial_count = len(await e2e_app_with_tickets.state_manager.get_all_tickets())

            await focus_first_ticket(pilot)
            await pilot.press("y")
            await pilot.pause()
            assert is_on_screen(pilot, "DuplicateTicketModal")

            await pilot.press("escape")
            await pilot.pause()

            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            assert len(tickets) == initial_count
            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Modal View/Edit Mode Interactions
# =============================================================================


class TestTicketDetailsView:
    """Test opening ticket details in view mode."""

    async def test_view_mode_shows_ticket_data(self, e2e_app_with_tickets: KaganApp):
        """View mode displays ticket title and description."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                modal = get_modal(pilot)
                assert modal.ticket is not None
                assert modal.ticket.title == "Backlog task"

    async def test_view_mode_has_edit_button(self, e2e_app_with_tickets: KaganApp):
        """View mode shows edit button."""
        from textual.widgets import Button

        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                edit_btn = pilot.app.screen.query_one("#edit-btn", Button)
                assert edit_btn is not None


class TestTicketDetailsEdit:
    """Test edit mode behavior."""

    @pytest.mark.parametrize(
        "action,action_type",
        [
            ("click", "#edit-btn"),
            ("key", "e"),
        ],
        ids=["click-edit-button", "press-e-key"],
    )
    async def test_toggle_to_edit_mode(
        self, e2e_app_with_tickets: KaganApp, action: str, action_type: str
    ):
        """Clicking edit button or pressing 'e' switches from view to edit mode."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                modal = get_modal(pilot)
                assert not modal.editing

                if action == "click":
                    await pilot.click(action_type)
                else:
                    await pilot.press(action_type)
                await pilot.pause()

                assert modal.editing

    async def test_edit_mode_shows_input_fields(self, e2e_app_with_tickets: KaganApp):
        """Edit mode shows input fields for title and description."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                title_input = pilot.app.screen.query_one("#title-input", Input)
                desc_input = pilot.app.screen.query_one("#description-input", TextArea)
                assert title_input is not None
                assert desc_input is not None


class TestTicketDetailsSave:
    """Test saving changes."""

    async def test_ctrl_s_saves_changes(self, e2e_app_with_tickets: KaganApp):
        """Ctrl+S saves edited ticket."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                title_input = pilot.app.screen.query_one("#title-input", Input)
                title_input.value = "Updated title"
                await pilot.pause()

                await pilot.press("ctrl+s")
                await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            assert any(t.title == "Updated title" for t in tickets)

    async def test_empty_title_shows_error(self, e2e_app_with_tickets: KaganApp):
        """Empty title prevents save and shows error."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                title_input = pilot.app.screen.query_one("#title-input", Input)
                title_input.value = ""
                await pilot.pause()

                await pilot.press("ctrl+s")
                await pilot.pause()

                assert is_on_screen(pilot, "TicketDetailsModal")


class TestTicketDetailsCancel:
    """Test escape/cancel behavior."""

    async def test_escape_in_view_mode_closes(self, e2e_app_with_tickets: KaganApp):
        """Escape in view mode closes the modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                assert is_on_screen(pilot, "TicketDetailsModal")

                await pilot.press("escape")
                await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

    async def test_escape_in_edit_mode_cancels_to_view(self, e2e_app_with_tickets: KaganApp):
        """Escape in edit mode returns to view mode (existing ticket)."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                modal = get_modal(pilot)
                assert modal.editing

                await pilot.press("escape")
                await pilot.pause()

                assert is_on_screen(pilot, "TicketDetailsModal")
                assert not modal.editing

    async def test_escape_cancels_and_resets_form(self, e2e_app_with_tickets: KaganApp):
        """Escape in edit mode discards unsaved changes."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                title_input = pilot.app.screen.query_one("#title-input", Input)
                original = title_input.value
                title_input.value = "Changed title"
                await pilot.pause()

                await pilot.press("escape")
                await pilot.pause()

                assert title_input.value == original

    async def test_close_button_in_view_mode(self, e2e_app_with_tickets: KaganApp):
        """Close button dismisses modal."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                await pilot.click("#close-btn")
                await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")


# =============================================================================
# Acceptance Criteria
# =============================================================================


class TestAcceptanceCriteria:
    """Test acceptance criteria display and editing."""

    async def test_ac_displayed_in_view_mode(self, e2e_app_with_ac_ticket: KaganApp):
        """Acceptance criteria displayed in view mode."""
        async with e2e_app_with_ac_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                assert is_on_screen(pilot, "TicketDetailsModal")
                modal = get_modal(pilot)
                assert modal.ticket is not None
                assert len(modal.ticket.acceptance_criteria) == 2
                ac_section = pilot.app.screen.query("#ac-section")
                assert len(ac_section) == 1

    async def test_ac_editable_in_edit_mode(self, e2e_app_with_ac_ticket: KaganApp):
        """Acceptance criteria TextArea visible in edit mode."""
        async with e2e_app_with_ac_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                ac_input = pilot.app.screen.query_one("#ac-input", TextArea)
                assert "User can login" in ac_input.text
                assert "Error messages shown" in ac_input.text

    async def test_ac_saved_on_edit(self, e2e_app_with_ac_ticket: KaganApp):
        """Edited acceptance criteria saved to database."""
        async with e2e_app_with_ac_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="edit"):
                ac_input = pilot.app.screen.query_one("#ac-input", TextArea)
                ac_input.text = "New criterion 1\nNew criterion 2\nNew criterion 3"
                await pilot.pause()

                await pilot.press("ctrl+s")
                await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")
            tickets = await e2e_app_with_ac_ticket.state_manager.get_all_tickets()
            ticket = tickets[0]
            assert len(ticket.acceptance_criteria) == 3
            assert "New criterion 1" in ticket.acceptance_criteria

    async def test_ac_count_badge_on_card(self, e2e_app_with_ac_ticket: KaganApp):
        """Ticket card shows [AC:N] badge when criteria exist."""
        async with e2e_app_with_ac_ticket.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            cards = pilot.app.screen.query(TicketCard)
            assert len(cards) >= 1
            card = cards[0]
            assert card.ticket is not None
            assert len(card.ticket.acceptance_criteria) == 2

    async def test_ac_empty_not_displayed(self, e2e_app_with_tickets: KaganApp):
        """No AC section when ticket has no acceptance criteria."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            async with open_ticket_modal(pilot, mode="view"):
                assert is_on_screen(pilot, "TicketDetailsModal")
                ac_items = pilot.app.screen.query(".ac-item")
                assert len(ac_items) == 0

    async def test_ac_create_new_ticket_with_criteria(self, e2e_app_with_tickets: KaganApp):
        """Can create new ticket with acceptance criteria."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()

            assert is_on_screen(pilot, "TicketDetailsModal")
            modal = get_modal(pilot)
            assert modal.is_create

            title_input = pilot.app.screen.query_one("#title-input", Input)
            title_input.value = "New feature ticket"

            ac_input = pilot.app.screen.query_one("#ac-input", TextArea)
            ac_input.text = "Feature works correctly\nTests pass"
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")
            tickets = await e2e_app_with_tickets.state_manager.get_all_tickets()
            new_ticket = next((t for t in tickets if t.title == "New feature ticket"), None)
            assert new_ticket is not None
            assert len(new_ticket.acceptance_criteria) == 2
            assert "Feature works correctly" in new_ticket.acceptance_criteria
