"""Fake agent boundary — stub for acceptance tests.

The new kagan.core architecture spawns agents via _agent.spawn_agent() directly
and does not support AgentFactory injection. FakeAgentFactory is retained as a
lightweight stub so KaganDriver can record agent configuration intent (e.g.
agent_will_complete()) for future use when agent interception is re-introduced.

For now, agent lifecycle tests should use real agent backends or skip agent
execution entirely and test observable state changes through the public API.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Recorded interaction for assertions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentCall:
    """A recorded prompt sent to a fake agent."""

    task_id: str | None
    prompt: str
    response: str


# ---------------------------------------------------------------------------
# FakeAgentFactory — lightweight stub (no injection point in new architecture)
# ---------------------------------------------------------------------------


@dataclass
class FakeAgentFactory:
    """Stub factory — tracks configured responses for future agent interception.

    The new KaganCore does not accept an agent_factory parameter.
    This stub preserves the KaganDriver DSL surface (agent_will_complete etc.)
    so tests can express intent without breaking when agent injection is added.
    """

    _default_response: str = "<complete/>"
    _response_queue: list[str] = field(default_factory=list)

    # Tracking (no real agents created in new architecture)
    agents: list[object] = field(default_factory=list)

    def set_next_response(self, response: str) -> None:
        """Queue a response for the next agent's first prompt."""
        self._response_queue.append(response)

    def set_responses(self, responses: list[str]) -> None:
        """Queue responses for successive prompts."""
        self._response_queue.extend(responses)

    def set_default_response(self, response: str) -> None:
        """Set fallback response for all agents."""
        self._default_response = response

    @property
    def last_agent(self) -> object | None:
        """The most recently created agent (always None in stub)."""
        return self.agents[-1] if self.agents else None

    @property
    def all_calls(self) -> list[AgentCall]:
        """All prompt calls across all agents (always empty in stub)."""
        return []


__all__ = [
    "AgentCall",
    "FakeAgentFactory",
]
