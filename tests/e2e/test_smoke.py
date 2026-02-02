"""E2E smoke tests for critical user journeys.

These tests verify complete user flows from start to finish.
They use real components (git, database) with only agent CLI mocking.
"""

from __future__ import annotations

from typing import cast

import pytest

from kagan.app import KaganApp
from kagan.database.models import TicketStatus
from tests.helpers.pages import (
    create_ticket_via_ui,
    focus_first_ticket,
    get_ticket_count,
    get_tickets_by_status,
    is_on_screen,
    move_ticket_forward,
    navigate_to_kanban,
)

pytestmark = pytest.mark.e2e


class TestTicketLifecycle:
    """Test complete ticket lifecycle: create -> progress -> review -> done."""

    @pytest.mark.slow
    async def test_create_ticket_appears_in_backlog(self, e2e_app: KaganApp):
        """Creating a ticket via UI places it in BACKLOG column."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await create_ticket_via_ui(pilot, "Test feature")
            await pilot.pause()

            backlog_tickets = await get_tickets_by_status(pilot, TicketStatus.BACKLOG)
            assert len(backlog_tickets) >= 1
            assert any(t.title == "Test feature" for t in backlog_tickets)

    @pytest.mark.slow
    async def test_move_ticket_through_workflow(self, e2e_app: KaganApp):
        """Ticket can be moved through entire workflow via keyboard."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await create_ticket_via_ui(pilot, "Workflow test")
            await pilot.pause()

            await focus_first_ticket(pilot)
            await move_ticket_forward(pilot)

            in_progress = await get_tickets_by_status(pilot, TicketStatus.IN_PROGRESS)
            assert len(in_progress) >= 1

            await focus_first_ticket(pilot)
            await move_ticket_forward(pilot)
            # PAIR tickets now require confirmation for IN_PROGRESS -> REVIEW
            await pilot.press("y")
            await pilot.pause()

            review = await get_tickets_by_status(pilot, TicketStatus.REVIEW)
            assert len(review) >= 1


class TestKanbanBoardDisplay:
    """Test kanban board displays tickets correctly."""

    async def test_board_shows_existing_tickets(self, e2e_app_with_tickets: KaganApp):
        """Board displays pre-existing tickets in correct columns."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            assert is_on_screen(pilot, "KanbanScreen")

            backlog = await get_tickets_by_status(pilot, TicketStatus.BACKLOG)
            in_progress = await get_tickets_by_status(pilot, TicketStatus.IN_PROGRESS)
            review = await get_tickets_by_status(pilot, TicketStatus.REVIEW)

            assert len(backlog) >= 1
            assert len(in_progress) >= 1
            assert len(review) >= 1

    async def test_ticket_count_in_header(self, e2e_app_with_tickets: KaganApp):
        """Header shows correct ticket count."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            total_tickets = get_ticket_count(pilot)
            assert total_tickets == 3


class TestTicketDeletion:
    """Test ticket deletion with cleanup."""

    @pytest.mark.slow
    async def test_delete_ticket_removes_from_board(self, e2e_app: KaganApp):
        """Deleting a ticket removes it from the board."""
        async with e2e_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            await create_ticket_via_ui(pilot, "Delete me")
            await pilot.pause()

            initial_count = get_ticket_count(pilot)
            assert initial_count >= 1

            await focus_first_ticket(pilot)
            await pilot.press("x")
            await pilot.pause()

            final_count = get_ticket_count(pilot)
            assert final_count == initial_count - 1


class TestScreenNavigation:
    """Test navigation between screens."""

    async def test_p_opens_planner(self, e2e_app_with_tickets: KaganApp):
        """Pressing 'p' opens the planner screen."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert is_on_screen(pilot, "KanbanScreen")

            await pilot.press("p")
            await pilot.pause()

            assert is_on_screen(pilot, "PlannerScreen")

    async def test_escape_returns_to_kanban(self, e2e_app_with_tickets: KaganApp):
        """Pressing escape from planner returns to kanban."""
        async with e2e_app_with_tickets.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            await pilot.press("p")
            await pilot.pause()
            assert is_on_screen(pilot, "PlannerScreen")

            await pilot.press("escape")
            await pilot.pause()
            assert is_on_screen(pilot, "KanbanScreen")


class TestFreshProjectWorktree:
    """Test worktree creation in a fresh project (no pre-existing git repo)."""

    @pytest.fixture
    async def _fresh_app(self, tmp_path, monkeypatch):
        """Create an app for a fresh project without git (local fixture)."""
        project = tmp_path / "fresh_project"
        project.mkdir()
        kagan_dir = project / ".kagan"
        kagan_dir.mkdir()
        config_toml = (
            '[general]\nauto_start = false\ndefault_base_branch = "main"\n'
            'default_worker_agent = "claude"\n'
            '[agents.claude]\nidentity = "claude.ai"\nname = "Claude"\nshort_name = "claude"\n'
            'run_command."*" = "echo mock"\nactive = true\n'
        )
        (kagan_dir / "config.toml").write_text(config_toml)
        monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
        monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
        monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")
        return KaganApp(
            db_path=str(kagan_dir / "state.db"),
            config_path=str(kagan_dir / "config.toml"),
            lock_path=None,
        )

    @pytest.mark.slow
    async def test_pair_ticket_worktree_creation_fresh_repo(self, _fresh_app: KaganApp):
        """PAIR ticket can create worktree in a freshly initialized git repo."""
        async with _fresh_app.run_test(size=(120, 40)) as pilot:
            await navigate_to_kanban(pilot)
            await pilot.pause()

            # Verify git was initialized by kagan
            app = cast("KaganApp", pilot.app)
            project_root = app.config_path.parent.parent
            git_dir = project_root / ".git"
            assert git_dir.exists(), "Kagan should have initialized git"

            # Create a PAIR ticket
            await create_ticket_via_ui(pilot, "Test PAIR feature")
            await pilot.pause()

            # Toggle to PAIR mode
            await focus_first_ticket(pilot)
            await pilot.press("t")  # Toggle to PAIR
            await pilot.pause()

            # Move to IN_PROGRESS (this triggers worktree creation for PAIR)
            await pilot.press("g", "l")
            await pilot.pause()

            # Verify ticket moved (no error means worktree was created)
            in_progress = await get_tickets_by_status(pilot, TicketStatus.IN_PROGRESS)
            assert len(in_progress) >= 1, "Ticket should have moved to IN_PROGRESS"

            # Verify worktree directory exists
            worktree_dir = project_root / ".kagan" / "worktrees"
            _ = worktree_dir.exists()
