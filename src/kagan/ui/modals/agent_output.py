"""Modal for watching AUTO ticket agent progress."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, Rule

from kagan.acp import messages
from kagan.constants import MODAL_TITLE_MAX_LENGTH
from kagan.ui.widgets import StreamingOutput

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.acp.agent import Agent
    from kagan.database.models import Ticket


class AgentOutputModal(ModalScreen[None]):
    """Modal for watching an AUTO ticket's agent progress in real-time."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("c", "cancel_agent", "Cancel Agent", show=True),
    ]

    def __init__(
        self,
        ticket: Ticket,
        agent: Agent | None,
        iteration: int = 0,
        **kwargs,
    ) -> None:
        """Initialize the modal.

        Args:
            ticket: The ticket being processed.
            agent: The ACP agent instance (may be None if not running).
            iteration: Current iteration number.
        """
        super().__init__(**kwargs)
        self.ticket = ticket
        self._agent = agent
        self._iteration = iteration

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Vertical(id="agent-output-container"):
            yield Label(
                f"AUTO: {self.ticket.title[:MODAL_TITLE_MAX_LENGTH]}",
                classes="modal-title",
            )
            yield Label(
                f"Ticket #{self.ticket.short_id} | Iteration {self._iteration}",
                classes="modal-subtitle",
            )
            yield Rule()
            yield StreamingOutput(id="agent-output")
            yield Rule()
            yield Label(
                "[c] Cancel Agent  [Esc] Close (agent continues)",
                classes="modal-hint",
            )
            with Horizontal(classes="button-row"):
                yield Button("Cancel Agent", variant="error", id="cancel-btn")
                yield Button("Close", id="close-btn")
        yield Footer()

    async def on_mount(self) -> None:
        """Set up agent message target when modal mounts."""
        output = self._get_output()
        if self._agent:
            self._agent.set_message_target(self)
            await output.write("*Connected to agent stream*\n\n")
        else:
            await output.write("*No agent currently running*\n")

    def on_unmount(self) -> None:
        """Remove message target when modal closes."""
        if self._agent:
            self._agent.set_message_target(None)

    def _get_output(self) -> StreamingOutput:
        """Get the streaming output widget."""
        return self.query_one("#agent-output", StreamingOutput)

    async def _write_to_output(self, text: str) -> None:
        """Write text to the output widget."""
        output = self._get_output()
        await output.write(text)

    # ACP Message handlers

    @on(messages.AgentUpdate)
    async def on_agent_update(self, message: messages.AgentUpdate) -> None:
        """Handle agent text output."""
        await self._write_to_output(message.text)

    @on(messages.Thinking)
    async def on_agent_thinking(self, message: messages.Thinking) -> None:
        """Handle agent thinking/reasoning."""
        await self._write_to_output(f"*{message.text}*")

    @on(messages.ToolCall)
    async def on_tool_call(self, message: messages.ToolCall) -> None:
        """Handle tool call start."""
        title = message.tool_call.get("title", "Tool call")
        kind = message.tool_call.get("kind", "")
        tool_text = f"\n\n**> {title}**"
        if kind:
            tool_text += f" *({kind})*"
        await self._write_to_output(tool_text)

    @on(messages.ToolCallUpdate)
    async def on_tool_call_update(self, message: messages.ToolCallUpdate) -> None:
        """Handle tool call update."""
        status = message.update.get("status")
        if status:
            symbol = " ✓" if status == "completed" else " ⋯"
            await self._write_to_output(f"{symbol} {status}\n")

    @on(messages.AgentReady)
    async def on_agent_ready(self, message: messages.AgentReady) -> None:
        """Handle agent ready."""
        await self._write_to_output("**Agent ready** ✓\n\n")

    @on(messages.AgentFail)
    async def on_agent_fail(self, message: messages.AgentFail) -> None:
        """Handle agent failure."""
        await self._write_to_output(f"\n\n**Error:** {message.message}\n")
        if message.details:
            await self._write_to_output(f"\n{message.details}\n")

    # Button handlers

    @on(Button.Pressed, "#cancel-btn")
    async def on_cancel_btn(self) -> None:
        """Cancel the agent."""
        await self.action_cancel_agent()

    @on(Button.Pressed, "#close-btn")
    def on_close_btn(self) -> None:
        """Close the modal."""
        self.action_close()

    # Actions

    async def action_cancel_agent(self) -> None:
        """Send cancel signal to agent."""
        if self._agent:
            await self._agent.cancel()
            await self._write_to_output("\n\n*Cancel signal sent*\n")
            self.notify("Sent cancel request to agent")
        else:
            self.notify("No agent to cancel", severity="warning")

    def action_close(self) -> None:
        """Close the modal (agent continues running in background)."""
        self.dismiss(None)
