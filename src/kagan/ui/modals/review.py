"""Modal for reviewing ticket changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, RichLog, Rule, Static

from kagan.acp import messages
from kagan.acp.agent import Agent
from kagan.constants import DIFF_MAX_LENGTH, MODAL_TITLE_MAX_LENGTH
from kagan.limits import AGENT_TIMEOUT
from kagan.ui.widgets import StreamingOutput

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.agents.worktree import WorktreeManager
    from kagan.config import AgentConfig
    from kagan.database.models import Ticket


class ReviewModal(ModalScreen[str | None]):
    """Modal for reviewing ticket changes."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("a", "approve", "Approve"),
        Binding("r", "reject", "Reject"),
        Binding("g", "generate_review", "Generate AI Review"),
    ]

    def __init__(
        self,
        ticket: Ticket,
        worktree_manager: WorktreeManager,
        agent_config: AgentConfig,
        base_branch: str = "main",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.ticket = ticket
        self._worktree = worktree_manager
        self._agent_config = agent_config
        self._base_branch = base_branch
        self._agent: Agent | None = None
        self._review_started = False

    def compose(self) -> ComposeResult:
        with Vertical(id="review-modal-container"):
            yield Label(
                f"Review: {self.ticket.title[:MODAL_TITLE_MAX_LENGTH]}", classes="modal-title"
            )
            yield Rule()

            # Commits section
            with Vertical(id="commits-section"):
                yield Label("Commits", classes="section-title")
                yield RichLog(id="commits-log", wrap=True, markup=True)

            # Diff stats section
            with Vertical(id="diff-section"):
                yield Label("Changes", classes="section-title")
                yield Static(id="diff-stats")

            yield Rule()

            # AI Review section (opt-in, expandable)
            with Vertical(id="ai-review-section"):
                yield Label("AI Review", classes="section-title")
                yield Button("Generate AI Review", id="generate-btn", variant="default")
                yield StreamingOutput(id="ai-review-output", classes="hidden")

            yield Rule()

            # Action bar
            with Horizontal(classes="button-row"):
                yield Button("Approve", variant="success", id="approve-btn")
                yield Button("Reject", variant="error", id="reject-btn")

        yield Footer()

    async def on_mount(self) -> None:
        """Load commits and diff immediately (fast operations)."""
        commits = await self._worktree.get_commit_log(self.ticket.id, self._base_branch)
        diff_stats = await self._worktree.get_diff_stats(self.ticket.id, self._base_branch)

        log = self.query_one("#commits-log", RichLog)
        for commit in commits or ["[dim]No commits found[/dim]"]:
            log.write(f"  {commit}")

        self.query_one("#diff-stats", Static).update(diff_stats or "[dim](No changes)[/dim]")

    @on(Button.Pressed, "#generate-btn")
    async def on_generate_btn(self) -> None:
        """Generate AI review on demand."""
        await self.action_generate_review()

    @on(Button.Pressed, "#approve-btn")
    def on_approve_btn(self) -> None:
        self.action_approve()

    @on(Button.Pressed, "#reject-btn")
    def on_reject_btn(self) -> None:
        self.action_reject()

    async def action_generate_review(self) -> None:
        """Generate AI review on demand."""
        if self._review_started:
            return

        self._review_started = True
        btn = self.query_one("#generate-btn", Button)
        btn.disabled = True
        btn.label = "Generating..."

        output = self.query_one("#ai-review-output", StreamingOutput)
        output.remove_class("hidden")

        # Spawn agent and stream review
        await self._generate_ai_review(output)

    async def _generate_ai_review(self, output: StreamingOutput) -> None:
        """Spawn agent to generate code review."""
        wt_path = await self._worktree.get_path(self.ticket.id)
        if not wt_path:
            await output.write("**Error:** Worktree not found\n")
            return

        diff = await self._worktree.get_diff(self.ticket.id, self._base_branch)
        if not diff:
            await output.write("*No diff to review*\n")
            return

        # Create agent in worktree directory
        self._agent = Agent(wt_path, self._agent_config)
        self._agent.start(self)

        await output.write("*Starting AI review...*\n\n")

        try:
            await self._agent.wait_ready(timeout=AGENT_TIMEOUT)

            review_prompt = f"""Review the following code changes for ticket: {self.ticket.title}

Focus on:
1. Code quality and best practices
2. Potential bugs or issues
3. Test coverage considerations
4. Suggestions for improvement

Be concise - keep your review brief and actionable.

Diff:
```diff
{diff[:DIFF_MAX_LENGTH]}
```"""

            await self._agent.send_prompt(review_prompt)
        except Exception as e:
            await output.write(f"\n**Review failed:** {e}\n")
        finally:
            btn = self.query_one("#generate-btn", Button)
            btn.label = "Review Complete"

    # ACP Message handlers

    @on(messages.AgentUpdate)
    async def on_agent_update(self, message: messages.AgentUpdate) -> None:
        """Handle agent text output."""
        output = self.query_one("#ai-review-output", StreamingOutput)
        await output.write(message.text)

    @on(messages.Thinking)
    async def on_agent_thinking(self, message: messages.Thinking) -> None:
        """Handle agent thinking."""
        output = self.query_one("#ai-review-output", StreamingOutput)
        await output.write(f"*{message.text}*")

    @on(messages.AgentFail)
    async def on_agent_fail(self, message: messages.AgentFail) -> None:
        """Handle agent failure."""
        output = self.query_one("#ai-review-output", StreamingOutput)
        await output.write(f"\n**Error:** {message.message}\n")

    def action_approve(self) -> None:
        """Approve the review."""
        self.dismiss("approve")

    def action_reject(self) -> None:
        """Reject the review."""
        self.dismiss("reject")

    def action_close(self) -> None:
        """Close without action."""
        self.dismiss(None)

    async def on_unmount(self) -> None:
        """Cleanup agent on close."""
        if self._agent:
            await self._agent.stop()
