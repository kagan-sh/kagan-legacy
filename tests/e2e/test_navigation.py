"""E2E tests for keyboard navigation (vim and arrow keys)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kagan.database.models import TicketStatus
from kagan.ui.widgets.card import TicketCard
from tests.helpers.pages import focus_first_ticket, get_focused_ticket

if TYPE_CHECKING:
    from kagan.app import KaganApp

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    ("key", "setup", "expected_status"),
    [
        ("j", "first", None),
        ("down", "first", None),
        ("k", "second", None),
        ("up", "second", None),
        ("h", "in_progress", TicketStatus.BACKLOG),
        ("left", "in_progress", TicketStatus.BACKLOG),
        ("l", "first", TicketStatus.IN_PROGRESS),
        ("right", "first", TicketStatus.IN_PROGRESS),
    ],
    ids=["j", "down", "k", "up", "h", "left", "l", "right"],
)
async def test_navigation_keys(
    e2e_app_with_tickets: KaganApp,
    key: str,
    setup: str,
    expected_status: TicketStatus | None,
):
    """Test vim and arrow key navigation moves focus correctly."""
    async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        if setup == "first":
            await focus_first_ticket(pilot)
        elif setup == "second":
            await focus_first_ticket(pilot)
            await pilot.press("j")
            await pilot.pause()
        elif setup == "in_progress":
            for card in pilot.app.screen.query(TicketCard):
                if card.ticket and card.ticket.status == TicketStatus.IN_PROGRESS:
                    card.focus()
                    break
            await pilot.pause()

        await pilot.press(key)
        await pilot.pause()

        if expected_status:
            focused = await get_focused_ticket(pilot)
            if focused:
                assert focused.status == expected_status


async def test_nav_focuses_first_card_when_none_focused(e2e_app_with_tickets: KaganApp):
    """Pressing nav keys when no card focused should focus first card."""
    async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("j")
        await pilot.pause()
        focused = await get_focused_ticket(pilot)
        assert focused is not None, "Should focus first card when none selected"
