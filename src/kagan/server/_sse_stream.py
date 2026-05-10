"""kagan.server._sse_stream — Shared SSE turn producer for chat sessions.

Both ``_chat_routes`` (orchestrator-only legacy endpoint) and
``_session_routes`` (unified session overlay) drive the same lifecycle:

  claim turn → push_user → broadcast CHAT_USER_MESSAGE →
  broadcast CHAT_TURN_STARTED → stream_assistant events →
  broadcast CHAT_SESSION_UPDATED (post-turn)

The only runtime axis is ``is_orchestrator``:
- True:  build an orchestrator prompt via ``build_orchestrator_prompt``
         and pass ``raw=False`` to the ACP factory.
- False: forward the user text directly and pass ``raw=True`` so the
         spawn-per-turn ACP helper does not inject Kagan MCP tooling.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import acp
from loguru import logger

from kagan.core.chat import TurnInProgressError, make_spawn_per_turn_acp_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from kagan.server.mcp.server import ServerContext


async def _unified_sse_stream(
    ctx: ServerContext,
    session_id: str,
    session: Any,
    text: str,
    backend: str,
    attachments: list[Any] | None,
    *,
    is_orchestrator: bool,
    broadcast: Any,
    emit: Any,
    chat_event_to_sse_frame: Any,
    session_summary: Any,
) -> AsyncIterator[str]:
    """Drive one chat turn through ``ChatEngine`` and yield SSE frames.

    Parameters
    ----------
    ctx:
        Server context carrying ``ctx.client.chat`` (the ``ChatEngine``).
    session_id:
        Raw (un-prefixed) chat session ID.
    session:
        ``ChatSessionView`` for the session.
    text:
        User message text.
    backend:
        Agent backend identifier already resolved by the caller.
    attachments:
        Optional list of typed attachment dicts.
    is_orchestrator:
        When ``True`` the prompt is built via ``build_orchestrator_prompt``
        and the ACP factory is invoked without ``raw=True``.
    broadcast:
        The ``_broadcast`` callable from ``_chat_routes``.
    emit:
        The ``_emit`` callable from ``_chat_routes``.
    chat_event_to_sse_frame:
        The ``_chat_event_to_sse_frame`` callable from ``_chat_routes``.
    session_summary:
        The ``_session_summary`` callable from ``_chat_routes``.
    """
    engine = ctx.client.chat

    # Claim the engine slot BEFORE any side effects. The claim is synchronous
    # so it is atomic w.r.t. the asyncio scheduler; without it a concurrent
    # request on the same session could slip past the preflight turn_status
    # check, persist a user row, and then trip TurnInProgressError inside
    # stream_assistant — leaving an orphan user row and /watch subscribers
    # stuck without a recovery frame.
    try:
        engine.try_claim_turn(session_id)
    except TurnInProgressError:
        err = {"t": "CHAT_ERROR", "error": "Turn already in progress for this session"}
        broadcast(session_id, err)
        yield emit(err)
        return

    stream_entered = False
    turn_done = False
    try:
        await ctx.client.chat_sessions.update(session_id, agent_backend=backend)

        attachment_dicts: list[dict[str, str]] | None = (
            [a.model_dump() for a in attachments] if attachments else None
        )

        user_msg = await engine.push_user(session_id, text, attachments=attachment_dicts)
        user_msg_id = getattr(user_msg, "id", None)

        attachment_count = len(attachments) if attachments else 0
        user_event: dict[str, Any] = {
            "t": "CHAT_USER_MESSAGE",
            "message_id": user_msg_id,
            "content": text or "",
            **({"attachment_count": attachment_count} if attachment_count > 0 else {}),
        }
        broadcast(session_id, user_event)
        yield emit(user_event)

        started_event: dict[str, Any] = {
            "t": "CHAT_TURN_STARTED",
            "at": datetime.now(UTC).isoformat(),
            "by_source": session.source,
        }
        broadcast(session_id, started_event)
        yield emit(started_event)

        settings = await ctx.client.settings.get()
        project_cwd = await ctx.client.projects.resolve_repo_path(settings=settings)
        factory = make_spawn_per_turn_acp_factory(
            client=ctx.client,
            default_agent_backend=backend,
            cwd=project_cwd,
            attachments=attachment_dicts,
            raw=not is_orchestrator,
        )

        if is_orchestrator:
            from kagan.cli.chat.prompt import build_orchestrator_prompt

            prior_history: list[tuple[str, str]] = [
                (str(item[0]), str(item[1]))
                for item in session.orchestrator_history
                if isinstance(item, list | tuple) and len(item) == 2
            ]
            prompt_text = build_orchestrator_prompt(prior_history, text)
            prompt_blocks = [acp.text_block(prompt_text)]
        else:
            prompt_blocks = [acp.text_block(text)]

        stream_entered = True
        async for event in engine.stream_assistant(
            session_id,
            prompt_blocks=prompt_blocks,
            agent_backend=backend,
            acp_factory=factory,
        ):
            frame = chat_event_to_sse_frame(event)
            if frame is None:
                continue
            broadcast(session_id, frame)
            yield emit(frame)
            if frame.get("t") == "CHAT_DONE":
                turn_done = True
    except TurnInProgressError:
        raise
    except (asyncio.CancelledError, GeneratorExit, ConnectionError):
        logger.debug("Client disconnected during chat stream for session {}", session_id)
        # Starlette throws CancelledError at the active yield when the client
        # drops. detach() is idempotent so this is safe even when
        # stream_assistant cleaned up itself.
        await engine.detach(session_id)
        return
    except Exception as exc:
        logger.exception("Chat stream failed for session {}", session_id)
        err = {"t": "CHAT_ERROR", "error": str(exc)}
        broadcast(session_id, err)
        yield emit(err)
    finally:
        if not stream_entered:
            await engine.detach(session_id)

    # Post-turn metadata refresh — outside the error handler so a DB hiccup
    # does not emit a spurious CHAT_ERROR after a successful CHAT_DONE.
    if turn_done:
        try:
            refreshed_pair = await ctx.client.chat_sessions.get_with_history(session_id)
        except Exception:
            logger.exception("Post-turn session refresh failed for {}", session_id)
        else:
            if refreshed_pair is not None:
                from kagan.core.chat.sessions import chat_session_to_view

                refreshed = chat_session_to_view(*refreshed_pair)
                broadcast(
                    session_id,
                    {"t": "CHAT_SESSION_UPDATED", "session": session_summary(refreshed)},
                )
