"""Tests for scheduler with mock ACP agent."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kagan.agents.scheduler import Scheduler
from kagan.agents.worktree import WorktreeManager
from kagan.config import AgentConfig, GeneralConfig, KaganConfig
from kagan.database.manager import StateManager
from kagan.database.models import TicketCreate, TicketStatus, TicketType


@pytest.fixture
async def state_manager():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = StateManager(db_path)
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
def mock_worktree_manager():
    """Create a mock worktree manager."""
    manager = MagicMock(spec=WorktreeManager)
    manager.get_path = AsyncMock(return_value=Path("/tmp/worktree"))
    manager.create = AsyncMock(return_value=Path("/tmp/worktree"))
    return manager


@pytest.fixture
def config():
    """Create a test config."""
    return KaganConfig(
        general=GeneralConfig(
            auto_start=True,
            max_concurrent_agents=2,
            max_iterations=3,
            iteration_delay_seconds=0.01,
            default_worker_agent="test",
        ),
        agents={
            "test": AgentConfig(
                identity="test.agent",
                name="Test Agent",
                short_name="test",
                run_command={"*": "echo test"},
            )
        },
    )


@pytest.fixture
def scheduler(state_manager, mock_worktree_manager, config):
    """Create a scheduler instance."""
    changed_callback = MagicMock()
    return Scheduler(
        state_manager=state_manager,
        worktree_manager=mock_worktree_manager,
        config=config,
        on_ticket_changed=changed_callback,
    )


class TestSchedulerBasics:
    """Basic scheduler tests."""

    async def test_scheduler_initialization(self, scheduler: Scheduler):
        """Test scheduler initializes correctly."""
        assert scheduler is not None
        assert len(scheduler._running_tickets) == 0
        assert len(scheduler._agents) == 0

    async def test_tick_with_no_tickets(self, scheduler: Scheduler):
        """Test tick does nothing with no tickets."""
        await scheduler.tick()
        assert len(scheduler._running_tickets) == 0

    async def test_tick_ignores_pair_tickets(
        self, scheduler: Scheduler, state_manager: StateManager
    ):
        """Test tick ignores PAIR mode tickets."""
        # Create a PAIR ticket in IN_PROGRESS
        await state_manager.create_ticket(
            TicketCreate(
                title="Pair ticket",
                ticket_type=TicketType.PAIR,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        await scheduler.tick()

        # PAIR tickets should not be picked up
        assert len(scheduler._running_tickets) == 0

    async def test_tick_ignores_backlog_auto_tickets(
        self, scheduler: Scheduler, state_manager: StateManager
    ):
        """Test tick ignores AUTO tickets in BACKLOG."""
        await state_manager.create_ticket(
            TicketCreate(
                title="Auto backlog",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.BACKLOG,
            )
        )

        await scheduler.tick()

        # Backlog tickets should not be picked up
        assert len(scheduler._running_tickets) == 0


class TestSchedulerWithMockAgent:
    """Scheduler tests with mocked ACP agent.

    Note: These tests focus on the signal parsing and state transitions,
    not the full async agent lifecycle which is difficult to test reliably.
    """

    @pytest.fixture
    def mock_agent(self):
        """Create a mock ACP agent."""
        agent = MagicMock()
        agent.set_auto_approve = MagicMock()
        agent.start = MagicMock()
        agent.wait_ready = AsyncMock()
        agent.send_prompt = AsyncMock()
        agent.get_response_text = MagicMock(return_value="Done! <complete/>")
        agent.stop = AsyncMock()
        return agent

    async def test_scheduler_identifies_auto_tickets(
        self,
        scheduler: Scheduler,
        state_manager: StateManager,
    ):
        """Test scheduler correctly identifies AUTO tickets to process."""
        # Create both types of tickets
        auto_ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )
        await state_manager.create_ticket(
            TicketCreate(
                title="Pair ticket",
                ticket_type=TicketType.PAIR,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Get all tickets
        tickets = await state_manager.get_all_tickets()

        # Filter for AUTO IN_PROGRESS (what scheduler should do)
        eligible = [
            t
            for t in tickets
            if t.status == TicketStatus.IN_PROGRESS and t.ticket_type == TicketType.AUTO
        ]

        assert len(eligible) == 1
        assert eligible[0].id == auto_ticket.id

    async def test_scheduler_handles_blocked(
        self,
        scheduler: Scheduler,
        state_manager: StateManager,
        mock_agent,
    ):
        """Test scheduler moves ticket to BACKLOG on blocked."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Mock agent returns <blocked/>
        mock_agent.get_response_text.return_value = '<blocked reason="Need help"/>'

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            await scheduler.tick()
            # Wait for task to complete
            for _ in range(30):  # Max 3 seconds
                await asyncio.sleep(0.1)
                updated = await state_manager.get_ticket(ticket.id)
                if updated and updated.status == TicketStatus.BACKLOG:
                    break

        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.BACKLOG

    async def test_scheduler_max_iterations(
        self,
        scheduler: Scheduler,
        state_manager: StateManager,
        mock_agent,
    ):
        """Test scheduler respects max iterations."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Mock agent always returns <continue/>
        mock_agent.get_response_text.return_value = "Still working... <continue/>"

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            await scheduler.tick()
            # Wait for max iterations (3 iterations * delay + processing)
            for _ in range(50):  # Max 5 seconds
                await asyncio.sleep(0.1)
                updated = await state_manager.get_ticket(ticket.id)
                if updated and updated.status == TicketStatus.BACKLOG:
                    break

        # Should be back in BACKLOG after max iterations
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.BACKLOG

    async def test_get_agent_config_priority(
        self,
        scheduler: Scheduler,
        state_manager: StateManager,
    ):
        """Test agent config selection priority."""
        # Create ticket with agent_backend set
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Test",
                ticket_type=TicketType.AUTO,
                agent_backend="test",
            )
        )
        # Convert to full ticket model
        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None

        # Should get the "test" agent config
        config = scheduler._get_agent_config(full_ticket)
        assert config is not None
        assert config.short_name == "test"


class TestAutoMerge:
    """Tests for auto-merge functionality with agent-based review."""

    @pytest.fixture
    def auto_merge_config(self):
        """Create a test config with auto_merge enabled."""
        return KaganConfig(
            general=GeneralConfig(
                auto_start=True,
                auto_merge=True,
                max_concurrent_agents=2,
                max_iterations=3,
                iteration_delay_seconds=0.01,
                default_worker_agent="test",
                default_base_branch="main",
            ),
            agents={
                "test": AgentConfig(
                    identity="test.agent",
                    name="Test Agent",
                    short_name="test",
                    run_command={"*": "echo test"},
                )
            },
        )

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        manager.kill_session = AsyncMock()
        return manager

    @pytest.fixture
    def mock_review_agent(self):
        """Create a mock agent for review that returns approve signal."""
        agent = MagicMock()
        agent.set_auto_approve = MagicMock()
        agent.start = MagicMock()
        agent.wait_ready = AsyncMock()
        agent.send_prompt = AsyncMock()
        agent.get_response_text = MagicMock(
            return_value='Looks good! <approve summary="Implementation complete"/>'
        )
        agent.stop = AsyncMock()
        return agent

    @pytest.fixture
    def auto_merge_scheduler(
        self, state_manager, mock_worktree_manager, auto_merge_config, mock_session_manager
    ):
        """Create a scheduler with auto_merge enabled."""
        # Add mock methods for review prompt building
        mock_worktree_manager.get_commit_log = AsyncMock(return_value=["feat: add feature"])
        mock_worktree_manager.get_diff_stats = AsyncMock(return_value="1 file changed")
        changed_callback = MagicMock()
        return Scheduler(
            state_manager=state_manager,
            worktree_manager=mock_worktree_manager,
            config=auto_merge_config,
            session_manager=mock_session_manager,
            on_ticket_changed=changed_callback,
        )

    async def test_auto_merge_when_review_approved(
        self,
        auto_merge_scheduler: Scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_session_manager,
        mock_review_agent,
    ):
        """Test auto-merge happens when auto_merge=true and review is approved."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Mock merge success
        mock_worktree_manager.merge_to_main = AsyncMock(return_value=(True, "Merged"))
        mock_worktree_manager.delete = AsyncMock()

        # Mock review agent returning approve signal
        with patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent):
            full_ticket = await state_manager.get_ticket(ticket.id)
            assert full_ticket is not None
            await auto_merge_scheduler._handle_complete(full_ticket)

        # Ticket should be in DONE
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.DONE
        assert updated.checks_passed is True
        assert updated.review_summary == "Implementation complete"

        # Merge and cleanup should have been called
        mock_worktree_manager.merge_to_main.assert_called_once()
        mock_worktree_manager.delete.assert_called_once()
        mock_session_manager.kill_session.assert_called_once_with(ticket.id)

    async def test_no_auto_merge_when_disabled(
        self,
        scheduler: Scheduler,  # Uses default config (auto_merge=false)
        state_manager: StateManager,
        mock_worktree_manager,
    ):
        """Test no auto-merge when auto_merge=false."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Add mock methods for review
        mock_worktree_manager.get_commit_log = AsyncMock(return_value=["feat: add feature"])
        mock_worktree_manager.get_diff_stats = AsyncMock(return_value="1 file changed")

        # Mock review agent returning approve signal
        mock_agent = MagicMock()
        mock_agent.set_auto_approve = MagicMock()
        mock_agent.start = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(return_value='<approve summary="Done"/>')
        mock_agent.stop = AsyncMock()

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            full_ticket = await state_manager.get_ticket(ticket.id)
            assert full_ticket is not None
            await scheduler._handle_complete(full_ticket)

        # Ticket should be in REVIEW (not DONE)
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.checks_passed is True

        # Merge should NOT have been called
        mock_worktree_manager.merge_to_main.assert_not_called()

    async def test_no_auto_merge_when_review_rejected(
        self,
        auto_merge_scheduler: Scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
    ):
        """Test no auto-merge when review is rejected."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Mock review agent returning reject signal
        mock_agent = MagicMock()
        mock_agent.set_auto_approve = MagicMock()
        mock_agent.start = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(
            return_value='Missing tests. <reject reason="No unit tests added"/>'
        )
        mock_agent.stop = AsyncMock()

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            full_ticket = await state_manager.get_ticket(ticket.id)
            assert full_ticket is not None
            await auto_merge_scheduler._handle_complete(full_ticket)

        # Ticket should stay in REVIEW
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.checks_passed is False
        assert updated.review_summary == "No unit tests added"

        # Merge should NOT have been called
        mock_worktree_manager.merge_to_main.assert_not_called()

    async def test_no_auto_merge_when_no_signal(
        self,
        auto_merge_scheduler: Scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
    ):
        """Test no auto-merge when review agent returns no signal."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Mock review agent returning no signal
        mock_agent = MagicMock()
        mock_agent.set_auto_approve = MagicMock()
        mock_agent.start = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(
            return_value="The code looks fine but I need more context."
        )
        mock_agent.stop = AsyncMock()

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            full_ticket = await state_manager.get_ticket(ticket.id)
            assert full_ticket is not None
            await auto_merge_scheduler._handle_complete(full_ticket)

        # Ticket should stay in REVIEW with checks_passed=False
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW
        assert updated.checks_passed is False
        assert "No review signal found" in (updated.review_summary or "")

        # Merge should NOT have been called
        mock_worktree_manager.merge_to_main.assert_not_called()

    async def test_stays_in_review_when_merge_fails(
        self,
        auto_merge_scheduler: Scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
        mock_review_agent,
    ):
        """Test ticket stays in REVIEW if merge fails."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Auto ticket",
                ticket_type=TicketType.AUTO,
                status=TicketStatus.IN_PROGRESS,
            )
        )

        # Mock merge failure
        mock_worktree_manager.merge_to_main = AsyncMock(return_value=(False, "Merge conflict"))

        # Mock review agent returning approve signal
        with patch("kagan.agents.scheduler.Agent", return_value=mock_review_agent):
            full_ticket = await state_manager.get_ticket(ticket.id)
            assert full_ticket is not None
            await auto_merge_scheduler._handle_complete(full_ticket)

        # Ticket should stay in REVIEW (not moved to DONE)
        updated = await state_manager.get_ticket(ticket.id)
        assert updated is not None
        assert updated.status == TicketStatus.REVIEW  # Stays in REVIEW after failed merge

        # Cleanup should NOT have been called since merge failed
        mock_worktree_manager.delete.assert_not_called()

    async def test_run_review_helper(
        self,
        auto_merge_scheduler: Scheduler,
        state_manager: StateManager,
        mock_worktree_manager,
    ):
        """Test _run_review helper method."""
        ticket = await state_manager.create_ticket(
            TicketCreate(
                title="Test ticket",
                ticket_type=TicketType.AUTO,
                description="Test description",
            )
        )
        full_ticket = await state_manager.get_ticket(ticket.id)
        assert full_ticket is not None
        wt_path = Path("/tmp/test-worktree")

        # Test approve signal
        mock_agent = MagicMock()
        mock_agent.set_auto_approve = MagicMock()
        mock_agent.start = MagicMock()
        mock_agent.wait_ready = AsyncMock()
        mock_agent.send_prompt = AsyncMock()
        mock_agent.get_response_text = MagicMock(return_value='<approve summary="All good"/>')
        mock_agent.stop = AsyncMock()

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            passed, summary = await auto_merge_scheduler._run_review(full_ticket, wt_path)
            assert passed is True
            assert summary == "All good"

        # Test reject signal
        mock_agent.get_response_text.return_value = '<reject reason="Needs work"/>'

        with patch("kagan.agents.scheduler.Agent", return_value=mock_agent):
            passed, summary = await auto_merge_scheduler._run_review(full_ticket, wt_path)
            assert passed is False
            assert summary == "Needs work"


class TestSchedulerHelpers:
    """Tests for scheduler helper methods."""

    async def test_is_running(self, scheduler: Scheduler):
        """Test is_running method."""
        assert not scheduler.is_running("test-id")
        scheduler._running_tickets.add("test-id")
        assert scheduler.is_running("test-id")

    async def test_get_running_agent(self, scheduler: Scheduler):
        """Test get_running_agent method."""
        assert scheduler.get_running_agent("test-id") is None
        mock_agent = MagicMock()
        scheduler._agents["test-id"] = mock_agent
        assert scheduler.get_running_agent("test-id") is mock_agent

    async def test_get_iteration_count(self, scheduler: Scheduler):
        """Test get_iteration_count method."""
        assert scheduler.get_iteration_count("test-id") == 0
        scheduler._iteration_counts["test-id"] = 5
        assert scheduler.get_iteration_count("test-id") == 5

    async def test_stop(self, scheduler: Scheduler):
        """Test stop method cleans up."""
        mock_agent = MagicMock()
        mock_agent.stop = AsyncMock()
        scheduler._agents["test-id"] = mock_agent
        scheduler._running_tickets.add("test-id")
        scheduler._iteration_counts["test-id"] = 3

        await scheduler.stop()

        assert len(scheduler._agents) == 0
        assert len(scheduler._running_tickets) == 0
        assert len(scheduler._iteration_counts) == 0
        mock_agent.stop.assert_called_once()
