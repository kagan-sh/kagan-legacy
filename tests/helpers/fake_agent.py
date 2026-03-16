from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentCall:
    task_id: str | None
    prompt: str
    response: str


@dataclass
class FakeAgentFactory:
    _default_response: str = "<complete/>"
    _response_queue: list[str] = field(default_factory=list)
    agents: list[object] = field(default_factory=list)

    def set_next_response(self, response: str) -> None:
        self._response_queue.append(response)

    def set_responses(self, responses: list[str]) -> None:
        self._response_queue.extend(responses)

    def set_default_response(self, response: str) -> None:
        self._default_response = response

    @property
    def last_agent(self) -> object | None:
        return self.agents[-1] if self.agents else None

    @property
    def all_calls(self) -> list[AgentCall]:
        return []


__all__ = [
    "AgentCall",
    "FakeAgentFactory",
]
