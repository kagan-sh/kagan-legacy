"""ChatEngine — the single chat conversation loop for all surfaces.

Owns the per-turn lifecycle:

1. Persist the user message via :class:`ChatSessions`.
2. Hand the prompt to an :class:`ACPSessionFactory` and fan ACP updates back
   out as :class:`ChatEvent` instances.
3. Buffer assistant text chunks. On normal completion, persist the full
   response. On cancellation, persist the partial buffer with
   ``terminated_at_user_request=True`` — this matches the server's behaviour
   (NOT the CLI's drop-on-cancel) and is a deliberate convergence so that
   /watch subscribers and reconnect endpoints see consistent history.
4. If a ``title_generator`` is configured and this was the session's first
   turn, kick off an out-of-band title rename without blocking the stream.

Per-session in-flight state is held on the engine instance (NOT module-level
dicts) so multiple ``ChatEngine`` instances — e.g. one per server worker —
don't share state across processes.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from kagan.core.chat.acp import (
    ACPSessionFactory,
    ACPTurnResult,
    acp_update_to_chat_event,
)
from kagan.core.chat.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    ChatEvent,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnStarted,
)
from kagan.core.errors import KaganError

if TYPE_CHECKING:
    import builtins
    from collections.abc import AsyncIterator, Awaitable, Callable

    from kagan.core.chat.sessions import ChatSessions
    from kagan.core.models import ChatMessage


class TurnInProgressError(KaganError):
    """Raised when a second ``stream_assistant`` is requested while one is active."""


@dataclass(frozen=True, slots=True)
class CancelResult:
    """Outcome of :meth:`ChatEngine.cancel`."""

    was_running: bool
    partial_chars: int


@dataclass(frozen=True, slots=True)
class TurnStatus:
    """Read-only snapshot of per-session turn state."""

    active: bool
    started_at: datetime | None
    partial_chars: int


@dataclass(slots=True)
class _TurnState:
    """In-flight state for a single chat session.

    ``task`` may be either:
      * ``None`` — no turn ever ran for this session,
      * a sentinel ``Future`` — claimed but not yet started (mirrors server's
        409-guard pattern in ``server/_chat_routes._claim_turn_slot``),
      * an ``asyncio.Task`` — the running turn coroutine.
    """

    task: asyncio.Future[Any] | None = None
    started_at: datetime | None = None
    partial: list[str] = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class ChatEngine:
    """The single chat conversation loop. Wired into :class:`KaganCore`.

    See module docstring for the lifecycle contract.
    """

    def __init__(
        self,
        *,
        sessions: ChatSessions,
        acp_factory: ACPSessionFactory,
        title_generator: Callable[[str, str], Awaitable[str | None]] | None = None,
    ) -> None:
        self._sessions = sessions
        self._acp = acp_factory
        self._title_generator = title_generator
        self._states: dict[str, _TurnState] = {}

    # ------------------------------------------------------------------ history

    async def history(
        self,
        session_id: str,
        *,
        after_id: int | None = None,
        limit: int | None = None,
    ) -> builtins.list[ChatMessage]:
        """Return messages for a session.

        ``after_id`` switches to the cursor-tail query used by /watch
        reconnect; ``limit`` is honoured only when ``after_id`` is set.
        """
        if after_id is not None:
            return await self._sessions.messages_after(
                session_id,
                after_id=after_id,
                limit=limit if limit is not None else 200,
            )
        return await self._sessions.history(session_id)

    # ------------------------------------------------------------------ user

    async def push_user(
        self,
        session_id: str,
        text: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """Persist a user message via :class:`ChatSessions`. Returns the persisted row.

        ``attachments`` is currently unused by the persistence layer (chat
        messages are plain text rows). The parameter exists so the engine API
        can carry attachments through to ``stream_assistant`` without callers
        needing two parallel paths. Phase 3+ will route them properly.
        """
        del attachments  # threaded into stream_assistant by callers
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("user message text is required")
        return await self._sessions.append_message(session_id, "user", cleaned)

    # ------------------------------------------------------------------ stream

    async def stream_assistant(
        self,
        session_id: str,
        *,
        prompt_blocks: list[Any],
        agent_backend: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Run a single assistant turn and yield :class:`ChatEvent` items.

        Raises :class:`TurnInProgressError` if a turn is already in flight for
        ``session_id``.
        """
        state = self._claim_slot(session_id)

        # First turn = "no assistant has replied yet". The user row is already
        # persisted by ``push_user`` before this method is called, so checking
        # ``len(prior) == 0`` would never fire title generation.
        prior = await self._sessions.history(session_id)
        is_first_turn = not any(m.role == "assistant" for m in prior)

        async for event in self._run_stream(
            session_id, state, prompt_blocks, is_first_turn, agent_backend
        ):
            yield event

    # ------------------------------------------------------------------ cancel

    async def cancel(self, session_id: str, *, reason: str = "user") -> CancelResult:
        """Cancel any in-flight turn for ``session_id``.

        The persist-partial-on-cancel write is performed by the streaming
        coroutine itself when it observes ``cancel_event``, not by this method.
        """
        del reason  # broadcast happens at the transport layer
        state = self._states.get(session_id)
        if state is None:
            return CancelResult(was_running=False, partial_chars=0)
        partial_chars = sum(len(chunk) for chunk in state.partial)
        if state.task is None or state.task.done():
            return CancelResult(was_running=False, partial_chars=partial_chars)
        state.cancel_event.set()
        if isinstance(state.task, asyncio.Task):
            state.task.cancel()
        return CancelResult(was_running=True, partial_chars=partial_chars)

    # ------------------------------------------------------------------ detach

    async def detach(self, session_id: str) -> None:
        """Drop per-session in-flight state. Cancel any running turn first."""
        state = self._states.pop(session_id, None)
        if state is None:
            return
        if state.task is not None and not state.task.done():
            state.cancel_event.set()
            if isinstance(state.task, asyncio.Task):
                state.task.cancel()

    # ------------------------------------------------------------------ status

    def turn_status(self, session_id: str) -> TurnStatus:
        state = self._states.get(session_id)
        if state is None or state.task is None or state.task.done():
            return TurnStatus(active=False, started_at=None, partial_chars=0)
        return TurnStatus(
            active=True,
            started_at=state.started_at,
            partial_chars=sum(len(chunk) for chunk in state.partial),
        )

    # ------------------------------------------------------------------ internals

    def _claim_slot(self, session_id: str) -> _TurnState:
        existing = self._states.get(session_id)
        if existing is not None and existing.task is not None and not existing.task.done():
            raise TurnInProgressError(f"Chat turn already running for session {session_id}")

        # Mirror server's 409-guard: install a sentinel Future *before* any
        # await so a concurrent ``stream_assistant`` cannot slip past the
        # in-progress check while we set up the real task.
        sentinel: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        state = _TurnState(
            task=sentinel,
            started_at=datetime.now(UTC),
            partial=[],
            cancel_event=asyncio.Event(),
        )
        self._states[session_id] = state
        return state

    async def _run_stream(
        self,
        session_id: str,
        state: _TurnState,
        prompt_blocks: list[Any],
        is_first_turn: bool,
        agent_backend: str | None,
    ) -> AsyncIterator[ChatEvent]:
        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()

        async def _on_update(update: Any) -> None:
            event = acp_update_to_chat_event(update)
            if event is None:
                return
            if isinstance(event, AssistantChunk) and not event.thought:
                state.partial.append(event.text)
            await queue.put(event)

        # Create the actual running task and replace the sentinel.
        run_task: asyncio.Task[ACPTurnResult] = asyncio.create_task(
            self._acp.prompt(
                session_id=session_id,
                prompt_blocks=prompt_blocks,
                on_update=_on_update,
                cancel_event=state.cancel_event,
                agent_backend=agent_backend,
            )
        )
        state.task = run_task

        async def _drain_to_queue() -> None:
            # The drain task's only job is to wait for the run to finish (or
            # be cancelled) and then close the queue. Lifecycle / error
            # reporting is owned by the outer engine coroutine — emitting a
            # ``TurnError`` from here would race with the outer ``except`` and
            # produce duplicate events.
            try:
                await run_task
            except asyncio.CancelledError:
                pass
            except Exception:
                # Outer coroutine reports the error via ``run_task.result()``.
                pass
            finally:
                await queue.put(None)

        drain_task = asyncio.create_task(_drain_to_queue())

        yield TurnStarted(at=state.started_at or datetime.now(UTC))

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        except (GeneratorExit, asyncio.CancelledError):
            state.cancel_event.set()
            if not run_task.done():
                run_task.cancel()
            await asyncio.gather(drain_task, return_exceptions=True)
            raise

        # Join the drain task — it already swallows its own exceptions.
        with contextlib.suppress(BaseException):
            await drain_task

        # Decide outcome from run_task.
        try:
            result = run_task.result()
        except asyncio.CancelledError:
            partial_text = "".join(state.partial)
            if partial_text:
                msg = await self._sessions.append_message(
                    session_id, "assistant", partial_text, terminated=True
                )
                yield AssistantMessagePersisted(
                    message_id=int(msg.id or 0),
                    content=partial_text,
                    terminated=True,
                )
            yield TurnCancelled(reason="user")
            self._teardown(session_id)
            return
        except Exception as exc:
            yield TurnError(message=str(exc))
            self._teardown(session_id)
            return

        if result.cancelled:
            partial_text = "".join(state.partial)
            if partial_text:
                msg = await self._sessions.append_message(
                    session_id, "assistant", partial_text, terminated=True
                )
                yield AssistantMessagePersisted(
                    message_id=int(msg.id or 0),
                    content=partial_text,
                    terminated=True,
                )
            yield TurnCancelled(reason="user")
            self._teardown(session_id)
            return

        full_response = result.full_response or "".join(state.partial)
        if full_response:
            msg = await self._sessions.append_message(
                session_id, "assistant", full_response, terminated=False
            )
            yield AssistantMessagePersisted(
                message_id=int(msg.id or 0),
                content=full_response,
                terminated=False,
            )

        if is_first_turn and full_response and self._title_generator is not None:
            first_user_text = _last_user_text(prompt_blocks)
            if first_user_text is not None:
                # Fire-and-forget — title generation must not block the stream.
                asyncio.create_task(self._maybe_rename(session_id, first_user_text, full_response))

        yield TurnDone(full_response=full_response)
        self._teardown(session_id)

    async def _maybe_rename(self, session_id: str, user_text: str, reply: str) -> None:
        if self._title_generator is None:
            return
        try:
            title = await self._title_generator(user_text, reply)
        except Exception:
            logger.debug("Chat title generation failed for session {}", session_id)
            return
        if not title:
            return
        try:
            await self._sessions.update(session_id, label=title)
        except Exception:
            logger.debug("Chat title update failed for session {}", session_id)

    def _teardown(self, session_id: str) -> None:
        self._states.pop(session_id, None)


def _last_user_text(prompt_blocks: list[Any]) -> str | None:
    """Pull the most recent user text out of a list of ACP prompt blocks."""
    for block in reversed(prompt_blocks):
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


__all__ = [
    "CancelResult",
    "ChatEngine",
    "TurnInProgressError",
    "TurnStatus",
]
