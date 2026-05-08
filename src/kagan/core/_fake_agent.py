"""Fake agent backend for deterministic E2E testing.

Enabled by ``kagan web --fake-agent`` (or ``KAGAN_FAKE_AGENT=1``).  The fake
backend registers a ``fake-agent`` entry in ``_BACKEND_SPECS`` and bypasses
real process spawning — the session lifecycle runs entirely inside an asyncio
task that calls the ``on_session_update`` callback directly with real ACP
schema objects so the existing ``map_acp_update_to_event`` path in
``_sessions.py`` works without modification.

Behaviour:
- Emits a few ``output_chunk`` ACP updates immediately.
- Transitions the session to RUNNING within 1 s.
- Stays RUNNING for ``KAGAN_FAKE_AGENT_DELAY_MS`` ms (default 30 000).
- Completes normally so the caller's done-callback fires.

This module is intentionally **not** imported anywhere unless the fake-agent
flag is active; production code paths never reference it.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from acp import text_block, update_agent_message
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable

from kagan.core._agent import (
    _BACKEND_SPECS,
    BackendCapability,
    BackendSpec,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_AGENT_BACKEND: str = "fake-agent"

_DEFAULT_DELAY_MS: int = 30_000
_CHUNK_TEXTS: tuple[str, ...] = (
    "Analysing task...\n",
    "Running fake agent (E2E test mode).\n",
    "Work in progress — staying RUNNING for the configured delay.\n",
)


def _delay_ms() -> int:
    raw = os.environ.get("KAGAN_FAKE_AGENT_DELAY_MS", "")
    try:
        return max(0, int(raw))
    except (ValueError, TypeError):
        return _DEFAULT_DELAY_MS


# ---------------------------------------------------------------------------
# Core fake-session coroutine
# ---------------------------------------------------------------------------


async def run_fake_acp_session(
    *,
    session_id: str,
    on_session_update: Callable[[str, Any], Any],
) -> None:
    """Drive a fake agent turn that mirrors a real ACP session lifecycle.

    Calls *on_session_update* with real ``AgentMessageChunk`` objects so the
    normal ``map_acp_update_to_event`` path in ``_sessions.py`` picks them up
    and persists ``output_chunk`` events.  After the configured delay the
    coroutine returns cleanly (simulating a successful agent run).
    """
    logger.info("FakeAgent: session {} started", session_id)

    # Emit a couple of output chunks immediately so subscribers see live events.
    for text in _CHUNK_TEXTS:
        chunk = update_agent_message(text_block(text))
        try:
            await on_session_update(session_id, chunk)
        except Exception:
            logger.debug(
                "FakeAgent: on_session_update raised for session {} (non-fatal)",
                session_id,
            )

    delay_s = _delay_ms() / 1_000.0
    logger.debug("FakeAgent: staying RUNNING for {:.1f}s", delay_s)
    await asyncio.sleep(delay_s)

    logger.info("FakeAgent: session {} completing", session_id)


# ---------------------------------------------------------------------------
# spawn_fake_agent_via_acp
# ---------------------------------------------------------------------------


async def spawn_fake_agent_via_acp(
    *,
    session_id: str,
    task_id: str,
    on_session_update: Callable[[str, Any], Any],
) -> tuple[int, asyncio.Task[None]]:
    """Fake analogue of ``spawn_agent_via_acp``.

    Returns a (pid=0, asyncio.Task) pair matching the real function's
    signature so ``_sessions.py`` can use either path transparently.  A pid of
    0 is safe because the caller only stores it for informational logging and
    optional kill-on-timeout — neither applies to in-process fake sessions.
    """
    reader_task: asyncio.Task[None] = asyncio.create_task(
        run_fake_acp_session(
            session_id=session_id,
            on_session_update=on_session_update,
        ),
        name=f"fake-agent:{task_id}",
    )
    return 0, reader_task


# ---------------------------------------------------------------------------
# Backend registration
# ---------------------------------------------------------------------------

_FAKE_BACKEND_SPEC = BackendSpec(
    name=FAKE_AGENT_BACKEND,
    executable="python",
    display_name="Fake Agent (E2E test fixture)",
    supports_acp=True,
    acp_command=("python",),
    capabilities=frozenset(
        {
            BackendCapability.ACP_STREAMING,
            BackendCapability.MANAGED_DETACHED_RUN,
        }
    ),
)


def register_fake_backend() -> None:
    """Inject the fake-agent spec into the live backend registry.

    Idempotent — safe to call multiple times.  Must be called before any
    ``get_backend_spec("fake-agent")`` lookup or ``list_backend_specs()``
    invocation that would be affected by its presence.
    """
    if FAKE_AGENT_BACKEND not in _BACKEND_SPECS:
        _BACKEND_SPECS[FAKE_AGENT_BACKEND] = _FAKE_BACKEND_SPEC
        logger.warning(
            "FakeAgent backend registered — this is an E2E test fixture, never enable in production"
        )
