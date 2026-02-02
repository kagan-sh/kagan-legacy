"""Reactive scheduler for automatic ticket-to-agent assignment (AUTO mode).

Uses event-driven architecture: reacts to ticket status changes instead of polling.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual import log

from kagan.acp.agent import Agent
from kagan.agents.config_resolver import resolve_agent_config
from kagan.agents.prompt import build_prompt
from kagan.agents.prompt_loader import get_review_prompt
from kagan.agents.signals import Signal, SignalResult, parse_signal
from kagan.constants import MODAL_TITLE_MAX_LENGTH
from kagan.database.models import TicketStatus, TicketType
from kagan.limits import AGENT_TIMEOUT_LONG

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from kagan.agents.worktree import WorktreeManager
    from kagan.config import AgentConfig, KaganConfig
    from kagan.database.manager import StateManager
    from kagan.database.models import Ticket
    from kagan.sessions.manager import SessionManager


@dataclass(slots=True)
class RunningTicketState:
    """State for a currently running ticket."""

    task: asyncio.Task[None] | None = None
    agent: Agent | None = None
    iteration: int = 0


class Scheduler:
    """Reactive scheduler for AUTO ticket processing.

    Instead of polling, reacts to ticket status changes via a queue.
    Single worker loop processes all spawn/stop requests sequentially,
    eliminating race conditions.
    """

    def __init__(
        self,
        state_manager: StateManager,
        worktree_manager: WorktreeManager,
        config: KaganConfig,
        session_manager: SessionManager | None = None,
        on_ticket_changed: Callable[[], None] | None = None,
        on_iteration_changed: Callable[[str, int], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        self._state = state_manager
        self._worktrees = worktree_manager
        self._config = config
        self._sessions = session_manager
        self._running: dict[str, RunningTicketState] = {}
        self._on_ticket_changed = on_ticket_changed
        self._on_iteration_changed = on_iteration_changed
        self._on_error = on_error

        # Event queue for reactive processing
        self._event_queue: asyncio.Queue[tuple[str, TicketStatus | None, TicketStatus | None]] = (
            asyncio.Queue()
        )
        self._worker_task: asyncio.Task[None] | None = None
        self._started = False

    def start(self) -> None:
        """Start the scheduler's event processing loop."""
        if self._started:
            return
        self._started = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        log.info("Scheduler started (reactive mode)")

    async def initialize_existing_tickets(self) -> None:
        """Spawn agents for existing IN_PROGRESS AUTO tickets.

        Called on startup to handle tickets that were already in progress
        before the scheduler started listening for changes.
        Only runs if auto_start is enabled in config.
        """
        if not self._config.general.auto_start:
            log.info("auto_start disabled, skipping initialization of existing tickets")
            return

        tickets = await self._state.get_tickets_by_status(TicketStatus.IN_PROGRESS)
        for ticket in tickets:
            if ticket.ticket_type == TicketType.AUTO:
                log.info(f"Queueing existing IN_PROGRESS ticket: {ticket.id}")
                await self._event_queue.put((ticket.id, None, TicketStatus.IN_PROGRESS))

    async def handle_status_change(
        self, ticket_id: str, old_status: TicketStatus | None, new_status: TicketStatus | None
    ) -> None:
        """Handle a ticket status change event.

        Called by StateManager when ticket status changes.
        Queues the event for processing by the worker loop.
        """
        await self._event_queue.put((ticket_id, old_status, new_status))
        log.debug(f"Queued status change: {ticket_id} {old_status} -> {new_status}")

    async def _worker_loop(self) -> None:
        """Single worker that processes all events sequentially.

        This eliminates race conditions because all spawn/stop decisions
        happen in one place, one at a time.
        """
        log.info("Scheduler worker loop started")
        while True:
            try:
                ticket_id, old_status, new_status = await self._event_queue.get()
                await self._process_event(ticket_id, old_status, new_status)
            except asyncio.CancelledError:
                log.info("Scheduler worker loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in scheduler worker: {e}")

    async def _process_event(
        self, ticket_id: str, old_status: TicketStatus | None, new_status: TicketStatus | None
    ) -> None:
        """Process a single status change event."""
        # Ticket deleted
        if new_status is None:
            await self._stop_if_running(ticket_id)
            return

        # Get full ticket to check type
        ticket = await self._state.get_ticket(ticket_id)
        if ticket is None:
            await self._stop_if_running(ticket_id)
            return

        # Only handle AUTO tickets
        if ticket.ticket_type != TicketType.AUTO:
            return

        # React to status
        if new_status == TicketStatus.IN_PROGRESS:
            await self._ensure_running(ticket)
        elif old_status == TicketStatus.IN_PROGRESS:
            # Moved OUT of IN_PROGRESS - stop if running
            await self._stop_if_running(ticket_id)

    async def _ensure_running(self, ticket: Ticket) -> None:
        """Ensure an agent is running for this ticket."""
        if ticket.id in self._running:
            log.debug(f"Ticket {ticket.id} already running")
            return

        max_agents = self._config.general.max_concurrent_agents
        if len(self._running) >= max_agents:
            log.info(f"At capacity ({max_agents}), queueing {ticket.id} for retry")
            # Re-queue for later attempt
            await asyncio.sleep(1)
            await self._event_queue.put((ticket.id, None, TicketStatus.IN_PROGRESS))
            return

        await self._spawn(ticket)

    async def _spawn(self, ticket: Ticket) -> None:
        """Spawn an agent for a ticket. Called only from worker loop."""
        title = ticket.title[:MODAL_TITLE_MAX_LENGTH]
        log.info(f"Spawning agent for AUTO ticket {ticket.id}: {title}")

        # Add to _running BEFORE creating task to avoid race condition
        # where task checks _running before we've added the entry
        state = RunningTicketState()
        self._running[ticket.id] = state

        task = asyncio.create_task(self._run_ticket_loop(ticket))
        state.task = task

        def on_done(_: asyncio.Task[None]) -> None:
            # Cleanup when task completes - safe because worker loop is separate
            self._running.pop(ticket.id, None)
            if self._on_iteration_changed:
                self._on_iteration_changed(ticket.id, 0)

        task.add_done_callback(on_done)

    async def _stop_if_running(self, ticket_id: str) -> None:
        """Stop agent if running. Called only from worker loop."""
        state = self._running.get(ticket_id)
        if state is None:
            return

        log.info(f"Stopping agent for ticket {ticket_id}")

        if state.agent is not None:
            await state.agent.stop()

        if state.task is not None and not state.task.done():
            state.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.task

        self._running.pop(ticket_id, None)

        if self._on_iteration_changed:
            self._on_iteration_changed(ticket_id, 0)

    # --- Public API (thread-safe via queue) ---

    @property
    def _running_tickets(self) -> set[str]:
        """Get set of currently running ticket IDs (for UI compatibility)."""
        return set(self._running.keys())

    def is_running(self, ticket_id: str) -> bool:
        """Check if a ticket is currently being processed."""
        return ticket_id in self._running

    def get_running_agent(self, ticket_id: str) -> Agent | None:
        """Get the running agent for a ticket (for watch functionality)."""
        state = self._running.get(ticket_id)
        return state.agent if state else None

    def get_iteration_count(self, ticket_id: str) -> int:
        """Get current iteration count for a ticket."""
        state = self._running.get(ticket_id)
        return state.iteration if state else 0

    def reset_iterations(self, ticket_id: str) -> None:
        """Reset the session iteration counter for a ticket.

        This resets the in-memory "leash" counter used for the current session,
        not the lifetime total_iterations stored in the database.
        Called when a ticket is rejected and retried.
        """
        state = self._running.get(ticket_id)
        if state is not None:
            log.info(f"Resetting session iteration counter for ticket {ticket_id}")
            state.iteration = 0
            if self._on_iteration_changed:
                self._on_iteration_changed(ticket_id, 0)
        else:
            log.debug(f"Cannot reset iterations for {ticket_id}: not running")

    async def stop_ticket(self, ticket_id: str) -> bool:
        """Request to stop a ticket. Returns True if was running."""
        if ticket_id not in self._running:
            return False
        # Queue a "moved out of IN_PROGRESS" event
        await self._event_queue.put((ticket_id, TicketStatus.IN_PROGRESS, TicketStatus.BACKLOG))
        return True

    async def spawn_for_ticket(self, ticket: Ticket) -> bool:
        """Manually request to spawn an agent for a ticket.

        Used by UI for manual agent starts. Returns True if spawn was queued.
        """
        if ticket.id in self._running:
            return False  # Already running
        if ticket.ticket_type != TicketType.AUTO:
            return False  # Only AUTO tickets

        # Queue a spawn event
        await self._event_queue.put((ticket.id, None, TicketStatus.IN_PROGRESS))
        return True

    async def stop(self) -> None:
        """Stop the scheduler and all running agents."""
        log.info("Stopping scheduler")

        # Stop worker loop
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        # Stop all agents
        for ticket_id, state in list(self._running.items()):
            log.info(f"Stopping agent for ticket {ticket_id}")
            if state.agent is not None:
                await state.agent.stop()
            if state.task is not None and not state.task.done():
                state.task.cancel()

        self._running.clear()
        self._started = False

    # --- Internal: ticket processing loop ---

    def _notify_ticket_changed(self) -> None:
        """Notify that a ticket has changed status."""
        if self._on_ticket_changed:
            self._on_ticket_changed()

    def _notify_error(self, ticket_id: str, message: str) -> None:
        """Notify that an error occurred for a ticket."""
        if self._on_error:
            self._on_error(ticket_id, message)

    async def _run_ticket_loop(self, ticket: Ticket) -> None:
        """Run the iterative loop for a ticket until completion."""
        log.info(f"Starting ticket loop for {ticket.id}")
        self._notify_error(ticket.id, "Agent starting...")

        try:
            # Ensure worktree exists
            wt_path = await self._worktrees.get_path(ticket.id)
            if wt_path is None:
                log.info(f"Creating worktree for {ticket.id}")
                wt_path = await self._worktrees.create(
                    ticket.id, ticket.title, self._config.general.default_base_branch
                )
            log.info(f"Worktree path: {wt_path}")

            # Get agent config
            agent_config = self._get_agent_config(ticket)
            log.debug(f"Agent config: {agent_config.name}")
            max_iterations = self._config.general.max_iterations
            log.info(f"Starting iterations for {ticket.id}, max={max_iterations}")

            for iteration in range(1, max_iterations + 1):
                # Check if we're still supposed to be running
                if ticket.id not in self._running:
                    log.info(f"Ticket {ticket.id} stopped, exiting loop")
                    return

                state = self._running[ticket.id]
                state.iteration = iteration

                # Increment lifetime total_iterations in database (the "odometer")
                await self._state.increment_total_iterations(ticket.id)

                if self._on_iteration_changed:
                    self._on_iteration_changed(ticket.id, iteration)
                log.debug(f"Ticket {ticket.id} iteration {iteration}/{max_iterations}")

                signal = await self._run_iteration(
                    ticket, wt_path, agent_config, iteration, max_iterations
                )
                log.debug(f"Ticket {ticket.id} iteration {iteration} signal: {signal}")

                if signal.signal == Signal.COMPLETE:
                    log.info(f"Ticket {ticket.id} completed, moving to REVIEW")
                    await self._handle_complete(ticket)
                    return
                elif signal.signal == Signal.BLOCKED:
                    log.warning(f"Ticket {ticket.id} blocked: {signal.reason}")
                    self._notify_error(ticket.id, f"Blocked: {signal.reason}")
                    await self._handle_blocked(ticket, signal.reason)
                    return

                await asyncio.sleep(self._config.general.iteration_delay_seconds)

            log.warning(f"Ticket {ticket.id} reached max iterations")
            self._notify_error(ticket.id, "Reached max iterations without completing")
            await self._handle_max_iterations(ticket)

        except asyncio.CancelledError:
            log.info(f"Ticket {ticket.id} cancelled")
            raise
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            log.error(f"Exception in ticket loop for {ticket.id}: {e}")
            log.error(f"Traceback:\n{tb}")
            self._notify_error(ticket.id, f"Agent failed: {e}")
            await self._update_ticket_status(ticket.id, TicketStatus.BACKLOG)
        finally:
            log.info(f"Ticket loop ended for {ticket.id}")

    def _get_agent_config(self, ticket: Ticket) -> AgentConfig:
        """Get agent config for a ticket using unified resolver."""
        return resolve_agent_config(ticket, self._config)

    async def _run_iteration(
        self,
        ticket: Ticket,
        wt_path: Path,
        agent_config: AgentConfig,
        iteration: int,
        max_iterations: int,
    ) -> SignalResult:
        """Run a single iteration for a ticket."""
        # Get or create agent
        state = self._running.get(ticket.id)
        agent = state.agent if state else None

        if agent is None:
            agent = Agent(wt_path, agent_config)
            agent.set_auto_approve(self._config.general.auto_approve)
            agent.start()
            if state:
                state.agent = agent

            try:
                await agent.wait_ready(timeout=AGENT_TIMEOUT_LONG)
            except TimeoutError:
                log.error(f"Agent timeout for ticket {ticket.id}")
                return parse_signal('<blocked reason="Agent failed to start"/>')
        else:
            # Re-sync auto_approve from config in case it changed
            agent.set_auto_approve(self._config.general.auto_approve)

        # Build prompt with scratchpad context
        scratchpad = await self._state.get_scratchpad(ticket.id)
        prompt = build_prompt(
            ticket=ticket,
            iteration=iteration,
            max_iterations=max_iterations,
            scratchpad=scratchpad,
        )

        # Send prompt and get response
        log.info(f"Sending prompt to agent for ticket {ticket.id}, iteration {iteration}")
        try:
            await agent.send_prompt(prompt)
        except Exception as e:
            log.error(f"Agent prompt failed for {ticket.id}: {e}")
            return parse_signal(f'<blocked reason="Agent error: {e}"/>')

        # Get response and parse signal
        response = agent.get_response_text()
        signal_result = parse_signal(response)

        # Update scratchpad with progress
        progress_note = f"\n\n--- Iteration {iteration} ---\n{response[-2000:]}"
        await self._state.update_scratchpad(ticket.id, scratchpad + progress_note)

        return signal_result

    async def _handle_complete(self, ticket: Ticket) -> None:
        """Handle ticket completion - run review, optionally auto-merge."""
        wt_path = await self._worktrees.get_path(ticket.id)
        checks_passed = False
        review_summary = ""

        if wt_path is not None:
            checks_passed, review_summary = await self._run_review(ticket, wt_path)
            status = "approved" if checks_passed else "rejected"
            log.info(f"Ticket {ticket.id} review: {status}")

        # Update ticket with review results and move to REVIEW
        await self._state.update_ticket(
            ticket.id,
            status=TicketStatus.REVIEW,
            checks_passed=checks_passed,
            review_summary=review_summary,
        )
        self._notify_ticket_changed()

        # Auto-merge if enabled and review passed
        if self._config.general.auto_merge and checks_passed:
            log.info(f"Auto-merging ticket {ticket.id}")
            await self._auto_merge(ticket)

    async def _run_review(self, ticket: Ticket, wt_path: Path) -> tuple[bool, str]:
        """Run agent-based review and return (passed, summary)."""
        agent_config = self._get_agent_config(ticket)
        prompt = await self._build_review_prompt(ticket)

        agent = Agent(wt_path, agent_config, read_only=True)
        agent.set_auto_approve(True)
        agent.start()

        try:
            await agent.wait_ready(timeout=AGENT_TIMEOUT_LONG)
            await agent.send_prompt(prompt)
            response = agent.get_response_text()

            signal = parse_signal(response)
            if signal.signal == Signal.APPROVE:
                return True, signal.reason
            elif signal.signal == Signal.REJECT:
                return False, signal.reason
            else:
                return False, "No review signal found in agent response"
        except TimeoutError:
            log.error(f"Review agent timeout for ticket {ticket.id}")
            return False, "Review agent timed out"
        except Exception as e:
            log.error(f"Review agent failed for {ticket.id}: {e}")
            return False, f"Review agent error: {e}"
        finally:
            await agent.stop()

    async def _build_review_prompt(self, ticket: Ticket) -> str:
        """Build review prompt from template with commits and diff."""
        base = self._config.general.default_base_branch
        commits = await self._worktrees.get_commit_log(ticket.id, base)
        diff_summary = await self._worktrees.get_diff_stats(ticket.id, base)

        return get_review_prompt(
            title=ticket.title,
            ticket_id=ticket.id,
            description=ticket.description or "",
            commits="\n".join(f"- {c}" for c in commits) if commits else "No commits",
            diff_summary=diff_summary or "No changes",
        )

    async def _auto_merge(self, ticket: Ticket) -> None:
        """Auto-merge ticket to main and move to DONE."""
        base = self._config.general.default_base_branch
        success, message = await self._worktrees.merge_to_main(ticket.id, base_branch=base)

        if success:
            await self._worktrees.delete(ticket.id, delete_branch=True)
            if self._sessions is not None:
                await self._sessions.kill_session(ticket.id)
            await self._update_ticket_status(ticket.id, TicketStatus.DONE)
            log.info(f"Auto-merged ticket {ticket.id}: {ticket.title}")
        else:
            log.warning(f"Auto-merge failed for {ticket.id}: {message}")

        self._notify_ticket_changed()

    async def _handle_blocked(self, ticket: Ticket, reason: str) -> None:
        """Handle blocked ticket - move back to BACKLOG with reason."""
        scratchpad = await self._state.get_scratchpad(ticket.id)
        block_note = f"\n\n--- BLOCKED ---\nReason: {reason}\n"
        await self._state.update_scratchpad(ticket.id, scratchpad + block_note)

        await self._update_ticket_status(ticket.id, TicketStatus.BACKLOG)
        self._notify_ticket_changed()

    async def _handle_max_iterations(self, ticket: Ticket) -> None:
        """Handle ticket that reached max iterations."""
        scratchpad = await self._state.get_scratchpad(ticket.id)
        max_iter_note = (
            f"\n\n--- MAX ITERATIONS ---\n"
            f"Reached {self._config.general.max_iterations} iterations without completion.\n"
        )
        await self._state.update_scratchpad(ticket.id, scratchpad + max_iter_note)

        await self._update_ticket_status(ticket.id, TicketStatus.BACKLOG)
        self._notify_ticket_changed()

    async def _update_ticket_status(self, ticket_id: str, status: TicketStatus) -> None:
        """Update ticket status."""
        await self._state.update_ticket(ticket_id, status=status)
