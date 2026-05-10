"""Reusable ``FakeScript`` factories — one per docs/internal flow.

Each factory returns a list of ``FakeCue`` ready to hand to either
``schedule_inproc`` or ``schedule_http``. Keeps the wire shape identical
across Python in-proc tests and Playwright HTTP tests.
"""

from __future__ import annotations

from tests.helpers.fake_agent_backend import FakeCue


def cold_start(reply: str = "hello back") -> list[FakeCue]:
    """Flow A — single-chunk reply, then done."""
    return [
        FakeCue(emit={"type": "chunk", "text": reply}, wait=0.05),
        FakeCue(done=True, wait=0.05),
    ]


def chat_echo(text: str) -> list[FakeCue]:
    """Echo the user input back as one chunk."""
    return cold_start(reply=text)


def streaming(*chunks: str, chunk_delay: float = 0.05) -> list[FakeCue]:
    """Flow D — multiple chunks with a small delay between each."""
    cues = [FakeCue(emit={"type": "chunk", "text": c}, wait=chunk_delay) for c in chunks]
    cues.append(FakeCue(done=True, wait=chunk_delay))
    return cues


def tool_call(
    *,
    tool_name: str = "shell",
    tool_call_id: str = "tc-fake-001",
    tool_input: dict | None = None,
    tool_output: str = "ok",
    final_text: str = "done",
) -> list[FakeCue]:
    """Flow E — emit tool_use, then tool_result, then text + done."""
    return [
        FakeCue(
            emit={
                "type": "tool_use",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "input": tool_input or {},
            },
            wait=0.05,
        ),
        FakeCue(
            emit={
                "type": "tool_result",
                "tool_call_id": tool_call_id,
                "output": tool_output,
            },
            wait=0.1,
        ),
        FakeCue(emit={"type": "chunk", "text": final_text}, wait=0.05),
        FakeCue(done=True, wait=0.05),
    ]


def permission_gate(*, tool_name: str = "shell", final_text: str = "approved") -> list[FakeCue]:
    """Flow C — tool call that triggers a permission prompt; assumes the
    runtime issues the prompt out-of-band, so this script just reflects
    the post-decision flow."""
    return tool_call(tool_name=tool_name, final_text=final_text)


def multiturn_drain(replies: list[str]) -> list[FakeCue]:
    """Flow B — one chunk per scheduled reply, separated by ``done``
    cues so each turn ends cleanly. The director schedules these per
    turn id; consumers slice them per turn."""
    cues: list[FakeCue] = []
    for reply in replies:
        cues.append(FakeCue(emit={"type": "chunk", "text": reply}, wait=0.05))
        cues.append(FakeCue(done=True, wait=0.05))
    return cues


def slow(*, hold_seconds: float = 5.0) -> list[FakeCue]:
    """Flow I — sit idle so the test can issue an interrupt mid-stream."""
    return [
        FakeCue(emit={"type": "chunk", "text": "thinking..."}, wait=0.05),
        FakeCue(wait=hold_seconds),
        FakeCue(emit={"type": "chunk", "text": "should not arrive"}, wait=0.0),
        FakeCue(done=True, wait=0.0),
    ]


def fail(message: str = "agent failed") -> list[FakeCue]:
    return [FakeCue(error=message, wait=0.05)]


__all__ = [
    "chat_echo",
    "cold_start",
    "fail",
    "multiturn_drain",
    "permission_gate",
    "slow",
    "streaming",
    "tool_call",
]
