"""Test helpers for ``kagan.core.chat.engine.ChatEngine`` unit tests.

Provides synthetic ``ACPSessionFactory`` implementations and a boot helper
that wires a temporary :class:`KaganCore` together with a :class:`ChatEngine`.

Kept here (rather than inline in test files) per CLAUDE.md: "DO NOT put test
fixtures in test files — use tests/helpers/".
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kagan.core import KaganCore
from kagan.core.chat.acp import ACPTurnResult
from kagan.core.chat.engine import ChatEngine

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from kagan.core.chat.acp import ACPSessionFactory


def text_chunk(text: str) -> Any:
    """Build an ACP ``AgentMessageChunk`` with a plain text content block."""
    from acp.schema import AgentMessageChunk, TextContentBlock

    return AgentMessageChunk(
        content=TextContentBlock(type="text", text=text),
        session_update="agent_message_chunk",
    )


@dataclass
class ScriptedFactory:
    """ACPSessionFactory that emits a scripted list of ACP updates."""

    chunks: list[str]

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Any = None,
    ) -> ACPTurnResult:
        del session_id, prompt_blocks, agent_backend, permission_resolver
        for chunk in self.chunks:
            if cancel_event.is_set():
                return ACPTurnResult(full_response="", cancelled=True)
            await on_update(text_chunk(chunk))
            await asyncio.sleep(0)
        return ACPTurnResult(full_response="".join(self.chunks), cancelled=False)


@dataclass
class SuspendingFactory:
    """ACPSessionFactory that emits one chunk then suspends until cancelled."""

    first_chunk: str
    started: asyncio.Event

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Any = None,
    ) -> ACPTurnResult:
        del session_id, prompt_blocks, agent_backend, permission_resolver
        await on_update(text_chunk(self.first_chunk))
        self.started.set()
        await cancel_event.wait()
        return ACPTurnResult(full_response="", cancelled=True)


@dataclass
class PermissionFactory:
    """ACPSessionFactory that drives the permission seam.

    On ``prompt`` it invokes ``permission_resolver`` once, stores the
    resulting :class:`PermissionDecision` on ``self.decision``, and returns
    a successful turn carrying the decision's outcome as text. Raises if no
    resolver was passed (the seam is broken).
    """

    tool_call: dict[str, Any]
    options: list[dict[str, Any]]
    decision: Any = None
    resolver_started: asyncio.Event | None = None

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Any = None,
    ) -> ACPTurnResult:
        del session_id, prompt_blocks, on_update, cancel_event, agent_backend
        if permission_resolver is None:
            raise AssertionError("permission_resolver was not threaded through")
        from kagan.core.chat.acp import PermissionRequestPayload

        payload = PermissionRequestPayload(
            tool_call=self.tool_call,
            options=self.options,
        )
        if self.resolver_started is not None:
            self.resolver_started.set()
        self.decision = await permission_resolver(payload)
        return ACPTurnResult(
            full_response=f"resolved:{self.decision.outcome}",
            cancelled=False,
        )


@dataclass
class RaisingFactory:
    """ACPSessionFactory whose ``prompt`` raises immediately.

    Used to verify that ``ChatEngine`` emits exactly one ``TurnError`` event
    when the underlying agent run blows up.
    """

    exc: BaseException

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Any = None,
    ) -> ACPTurnResult:
        del session_id, prompt_blocks, on_update, cancel_event, agent_backend, permission_resolver
        raise self.exc


async def boot_engine(
    tmp_path: Path,
    factory: ACPSessionFactory,
    *,
    title_generator: Callable[[str, str], Awaitable[str | None]] | None = None,
) -> tuple[KaganCore, ChatEngine, str]:
    """Build a ``KaganCore`` + ``ChatEngine`` against a fresh sqlite DB.

    Returns the core (so the caller can ``close()`` it), the engine, and a
    fresh chat session id.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    await core.reset()
    engine = ChatEngine(
        sessions=core.chat_sessions,
        acp_factory=factory,
        title_generator=title_generator,
    )
    session = await core.chat_sessions.create(source="test", label="Engine test")
    return core, engine, session.id


__all__ = [
    "PermissionFactory",
    "RaisingFactory",
    "ScriptedFactory",
    "SuspendingFactory",
    "boot_engine",
    "text_chunk",
]
