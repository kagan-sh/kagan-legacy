"""Prompt refinement service using a dedicated ACP agent.

This module provides the PromptRefiner class which enhances user prompts
before they are sent to the planner agent for ticket creation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import log

from kagan.acp.agent import Agent
from kagan.agents.refinement_rules import build_refinement_prompt
from kagan.limits import AGENT_TIMEOUT

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.config import AgentConfig


class PromptRefiner:
    """Service for refining user prompts via a dedicated ACP agent.

    The refiner uses a separate agent instance to enhance user prompts
    before they are submitted to the planner. This ensures refinement
    happens pre-send and the user can review/edit before final submission.

    Example:
        refiner = PromptRefiner(Path.cwd(), agent_config)
        refined = await refiner.refine("fix login bug")
        # refined = "Analyze the authentication bug in the login module..."
        await refiner.stop()
    """

    def __init__(self, project_root: Path, agent_config: AgentConfig) -> None:
        """Initialize the prompt refiner.

        Args:
            project_root: The project root directory.
            agent_config: Configuration for the ACP agent to use.
        """
        self._project_root = project_root
        self._agent_config = agent_config
        self._agent: Agent | None = None

    async def refine(self, user_input: str) -> str:
        """Refine user input using ACP agent.

        The agent is lazily initialized on first call and reused for
        subsequent refinements.

        Args:
            user_input: The original user prompt to refine.

        Returns:
            Refined prompt text, or original input if refinement fails
            or returns empty response.

        Raises:
            RuntimeError: If agent fails to start or times out.
        """
        if not self._agent:
            log.info("[PromptRefiner] Initializing refiner agent...")
            self._agent = Agent(self._project_root, self._agent_config, read_only=True)
            self._agent.set_auto_approve(True)  # No permission dialogs
            self._agent.start(message_target=None)  # No UI messages
            await self._agent.wait_ready(timeout=AGENT_TIMEOUT)
            log.info("[PromptRefiner] Refiner agent ready")

        prompt = build_refinement_prompt(user_input)
        log.debug(f"[PromptRefiner] Sending refinement request (input_len={len(user_input)})")

        await self._agent.send_prompt(prompt)

        response = self._agent.get_response_text().strip()
        log.debug(f"[PromptRefiner] Received response (len={len(response)})")

        # Return original if response is empty or very short
        if not response or len(response) < len(user_input) // 2:
            log.warning("[PromptRefiner] Empty or too-short response, returning original")
            return user_input

        return response

    async def stop(self) -> None:
        """Stop the refiner agent and clean up resources."""
        if self._agent:
            log.info("[PromptRefiner] Stopping refiner agent...")
            await self._agent.stop()
            self._agent = None
