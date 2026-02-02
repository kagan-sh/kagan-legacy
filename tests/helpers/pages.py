"""Thin page helpers for E2E testing.

These are reusable functions for common UI interactions,
not a full Page Object framework. Keep them simple and focused.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from textual.pilot import Pilot

    from kagan.database.models import Ticket, TicketStatus, TicketType


async def skip_welcome_if_shown(pilot: Pilot) -> None:
    """Click continue on welcome screen if it's showing."""
    app = pilot.app
    if "WelcomeScreen" in str(type(app.screen)):
        await pilot.click("#continue-btn")
        await pilot.pause()


async def navigate_to_kanban(pilot: Pilot) -> None:
    """Navigate to Kanban screen from anywhere.

    Handles the case where PlannerScreen is pushed without KanbanScreen
    on the stack (empty board boot) by directly installing KanbanScreen.
    """
    from kagan.ui.screens.kanban import KanbanScreen

    app = pilot.app
    screen_name = type(app.screen).__name__

    if screen_name == "WelcomeScreen":
        await pilot.click("#continue-btn")
        await pilot.pause()

    # Re-check after potential welcome screen navigation
    screen_name = type(app.screen).__name__
    if screen_name == "PlannerScreen":
        # When app boots with empty board, PlannerScreen is the only screen.
        # Pressing escape pops to nothing. Instead, switch to KanbanScreen directly.
        app.switch_screen(KanbanScreen())
        await pilot.pause()
    elif "Kanban" not in screen_name and "SettingsModal" not in screen_name:
        # If we're not on Kanban/Settings, try to get there via switch
        app.switch_screen(KanbanScreen())
        await pilot.pause()


async def create_ticket_via_ui(pilot: Pilot, title: str) -> None:
    """Create a ticket through the UI (press n, type title, save)."""
    await pilot.press("n")
    await pilot.pause()

    # Type the title character by character
    for char in title:
        await pilot.press(char)

    await pilot.press("ctrl+s")
    await pilot.pause()


async def get_tickets_by_status(pilot: Pilot, status: TicketStatus) -> list[Ticket]:
    """Get all tickets in a specific status column."""
    from kagan.ui.widgets.card import TicketCard

    cards = pilot.app.screen.query(TicketCard)
    return [card.ticket for card in cards if card.ticket and card.ticket.status == status]


async def get_all_visible_tickets(pilot: Pilot) -> list[Ticket]:
    """Get all visible tickets on the kanban board."""
    from kagan.ui.widgets.card import TicketCard

    cards = pilot.app.screen.query(TicketCard)
    return [card.ticket for card in cards if card.ticket]


async def get_focused_ticket(pilot: Pilot) -> Ticket | None:
    """Get the currently focused ticket, if any."""
    from kagan.ui.widgets.card import TicketCard

    focused = pilot.app.focused
    if isinstance(focused, TicketCard) and focused.ticket:
        return focused.ticket
    return None


async def focus_first_ticket(pilot: Pilot) -> bool:
    """Focus the first ticket card on the board. Returns True if successful."""
    from kagan.ui.widgets.card import TicketCard

    cards = list(pilot.app.screen.query(TicketCard))
    if cards:
        cards[0].focus()
        await pilot.pause()
        return True
    return False


@asynccontextmanager
async def open_ticket_modal(
    pilot: Pilot, mode: Literal["view", "edit"] = "view"
) -> AsyncIterator[None]:
    """Focus first ticket and open the ticket modal in the specified mode.

    Args:
        pilot: The Textual pilot instance.
        mode: "view" to open with 'v' key, "edit" to open with 'e' key.

    Yields:
        None - use the modal while inside the context.

    Example:
        async with open_ticket_modal(pilot, mode="edit"):
            # Modal is now open in edit mode
            title_input = pilot.app.screen.query_one("#title-input", Input)
            title_input.value = "New title"
    """
    await focus_first_ticket(pilot)
    key = "v" if mode == "view" else "e"
    await pilot.press(key)
    await pilot.pause()
    yield


async def move_ticket_forward(pilot: Pilot) -> None:
    """Move the focused ticket to the next status column using g+l leader key."""
    await pilot.press("g", "l")
    await pilot.pause()


async def move_ticket_backward(pilot: Pilot) -> None:
    """Move the focused ticket to the previous status column using g+h leader key."""
    await pilot.press("g", "h")
    await pilot.pause()


async def delete_focused_ticket(pilot: Pilot, confirm: bool = True) -> None:
    """Delete the focused ticket using Ctrl+D (direct delete, no confirm modal)."""
    await pilot.press("ctrl+d")
    await pilot.pause()


async def toggle_ticket_type(pilot: Pilot) -> None:
    """Toggle the focused ticket between AUTO and PAIR types."""
    await pilot.press("t")
    await pilot.pause()


def get_ticket_count(pilot: Pilot) -> int:
    """Get the total number of tickets on the board."""
    from kagan.ui.widgets.card import TicketCard

    return len(list(pilot.app.screen.query(TicketCard)))


def is_on_screen(pilot: Pilot, screen_name: str) -> bool:
    """Check if we're on a specific screen by name."""
    return screen_name in type(pilot.app.screen).__name__


def focus_review_ticket(pilot: Pilot) -> Ticket | None:
    """Focus a ticket in REVIEW status. Returns the ticket or None."""
    from kagan.database.models import TicketStatus

    return focus_ticket_by_criteria(pilot, status=TicketStatus.REVIEW)


def focus_ticket_by_criteria(
    pilot: Pilot,
    status: TicketStatus | None = None,
    ticket_type: TicketType | None = None,
) -> Ticket | None:
    """Focus a ticket matching the given criteria. Returns the ticket or None.

    Args:
        pilot: The Textual pilot instance.
        status: Optional status to filter by.
        ticket_type: Optional ticket type to filter by.

    Returns:
        The focused ticket, or None if no matching ticket found.
    """
    from kagan.ui.widgets.card import TicketCard

    cards = list(pilot.app.screen.query(TicketCard))
    for card in cards:
        if card.ticket is None:
            continue
        if status is not None and card.ticket.status != status:
            continue
        if ticket_type is not None and card.ticket.ticket_type != ticket_type:
            continue
        card.focus()
        return card.ticket
    return None


@asynccontextmanager
async def open_settings_modal(pilot: Pilot) -> AsyncIterator[None]:
    """Navigate to kanban and open settings modal.

    Note: This context manager opens the modal and yields. It does NOT close
    the modal on exit - the test is responsible for closing it (escape/ctrl+s).

    Yields:
        None - use the modal while inside the context.

    Example:
        async with open_settings_modal(pilot):
            switch = pilot.app.screen.query_one("#auto-start-switch", Switch)
            await pilot.click("#auto-start-switch")
            await pilot.press("escape")  # Test must close modal
    """
    await navigate_to_kanban(pilot)
    await pilot.pause()
    await pilot.press("comma")
    await pilot.pause()
    yield
