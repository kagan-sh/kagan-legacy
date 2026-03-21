from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class AgentCall:
    task_id: str | None
    prompt: str
    response: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class ChunkedResponse:
    """A response that yields chunks on demand."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk


@dataclass
class FakeAgentFactory:
    _default_response: str = "<complete/>"
    _response_queue: list[str | ChunkedResponse] = field(default_factory=list)
    _calls: list[AgentCall] = field(default_factory=list)

    def set_next_response(self, response: str) -> None:
        self._response_queue.append(response)

    def set_next_stream(self, chunks: list[str]) -> None:
        """Queue a chunked streaming response."""
        self._response_queue.append(ChunkedResponse(chunks))

    def record_call(
        self,
        *,
        task_id: str | None = None,
        prompt: str = "",
        response: str = "",
    ) -> None:
        """Record an agent invocation. Called by the agent adapter."""
        self._calls.append(AgentCall(task_id=task_id, prompt=prompt, response=response))

    def next_response(self) -> str | ChunkedResponse:
        """Pop the next queued response, or return the default."""
        if self._response_queue:
            return self._response_queue.pop(0)
        return self._default_response

    @property
    def all_calls(self) -> list[AgentCall]:
        return list(self._calls)

    @property
    def last_call(self) -> AgentCall | None:
        """Most recent agent invocation."""
        return self._calls[-1] if self._calls else None

    @property
    def call_count(self) -> int:
        """Total number of agent invocations."""
        return len(self._calls)

    def assert_called_with(self, *, prompt_contains: str) -> None:
        """Assert that at least one call's prompt contains the given substring."""
        for call in self._calls:
            if prompt_contains in call.prompt:
                return
        prompts = [c.prompt[:80] for c in self._calls]
        raise AssertionError(
            f"No call with prompt containing {prompt_contains!r}. Recorded prompts: {prompts}"
        )

    def reset(self) -> None:
        """Clear all recorded calls and queued responses."""
        self._calls.clear()
        self._response_queue.clear()


__all__ = [
    "AgentCall",
    "ChunkedResponse",
    "FakeAgentFactory",
]
