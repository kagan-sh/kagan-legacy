"""Thin page helpers for E2E testing.

These are reusable functions for common UI interactions,
not a full Page Object framework. Keep them simple and focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from kagan.database.models import Ticket, TicketStatus


async def skip_welcome_if_shown(pilot: Pilot) -> None:
    """Click continue on welcome screen if it's showing."""
    app = pilot.app
    if "WelcomeScreen" in str(type(app.screen)):
        await pilot.click("#continue-btn")
        await pilot.pause()


async def navigate_to_kanban(pilot: Pilot) -> None:
    """Navigate to Kanban screen from anywhere."""
    app = pilot.app
    screen_name = type(app.screen).__name__

    if screen_name == "WelcomeScreen":
        await pilot.click("#continue-btn")
        await pilot.pause()

    # Re-check after potential welcome screen navigation
    screen_name = type(app.screen).__name__
    if screen_name == "PlannerScreen":
        await pilot.press("escape")
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
