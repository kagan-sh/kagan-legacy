"""Fake agent backend for deterministic E2E testing.

Enabled by ``kagan web --fake-agent`` (or ``KAGAN_FAKE_AGENT=1``).  The fake
backend registers a ``fake-agent`` entry in ``_BACKEND_SPECS`` and bypasses
real process spawning — the session lifecycle runs entirely inside an asyncio
task that calls the ``on_session_update`` callback directly with real ACP
schema objects so the existing ``map_acp_update_to_event`` path in
``_sessions.py`` works without modification.

This module is intentionally **not** imported anywhere unless the fake-agent
flag is active; production code paths never reference it.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from acp import start_tool_call, text_block, update_agent_message, update_tool_call
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


# ---------------------------------------------------------------------------
# Script format — declarative agent behaviour
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeCue:
    """A single instruction in a fake-agent script.

    Scripts are JSON-serializable arrays of cues.  Each cue waits *wait*
    seconds (relative to the previous cue) then performs its action.
    """

    wait: float = 0.0
    emit: dict[str, Any] | None = None
    workspace: dict[str, Any] | None = None
    done: bool = False
    error: str | None = None


@dataclass
class FakeScript:
    """A complete fake-agent run definition."""

    cues: list[FakeCue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Director — per-task / per-session script registry
# ---------------------------------------------------------------------------


class FakeAgentDirector:
    """Thread-safe / asyncio-safe registry of fake-agent scripts.

    Tests schedule scripts via the internal REST API; the fake-agent coroutine
    looks up its script here at runtime.  If no script is found, the built-in
    default behaviour is used.
    """

    def __init__(self) -> None:
        self._scripts: dict[str, FakeScript] = {}
        self._lock = asyncio.Lock()

    async def schedule(self, target_id: str, script: FakeScript) -> None:
        async with self._lock:
            self._scripts[target_id] = script

    async def get(self, target_id: str) -> FakeScript | None:
        async with self._lock:
            return self._scripts.get(target_id)

    async def clear(self, target_id: str) -> None:
        async with self._lock:
            self._scripts.pop(target_id, None)


# Global singleton — lives for the server process lifetime.
director = FakeAgentDirector()


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _apply_workspace_action(worktree: Path | None, action: dict[str, Any]) -> None:
    """Execute a workspace mutation inside the task's worktree."""
    if worktree is None:
        logger.debug("FakeAgent: no worktree provided — skipping workspace action")
        return

    if "write_file" in action:
        spec = action["write_file"]
        target = worktree / spec["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(spec["content"], encoding="utf-8")
        logger.debug("FakeAgent: wrote {}", target)

    if "commit" in action:
        spec = action["commit"]
        msg = spec.get("message", "fake-agent: scripted commit")
        import subprocess

        subprocess.run(
            ["git", "add", "-A"],
            cwd=worktree,
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["git", "commit", "-m", msg, "--no-verify"],
            cwd=worktree,
            capture_output=True,
            check=False,
        )
        logger.debug("FakeAgent: committed in {}", worktree)


# ---------------------------------------------------------------------------
# ACP emission helpers
# ---------------------------------------------------------------------------


async def _emit_acp(
    session_id: str,
    on_session_update: Callable[[str, Any], Any],
    spec: dict[str, Any],
) -> None:
    typ = spec.get("type")
    if typ == "chunk":
        chunk = update_agent_message(text_block(spec["text"]))
    elif typ == "tool_use":
        chunk = start_tool_call(
            tool_call_id=spec.get("tool_call_id", "tc-fake-001"),
            title=spec.get("name", "tool"),
            kind=spec.get("kind"),
            status="pending",
            raw_input=spec.get("input", {}),
        )
    elif typ == "tool_result":
        chunk = update_tool_call(
            tool_call_id=spec.get("tool_call_id", "tc-fake-001"),
            status="completed",
            raw_output=spec.get("output", ""),
        )
    elif typ == "status":
        # Status events are emitted as custom ACP updates via the same channel.
        # We wrap them in a minimal envelope that _sessions.py recognises.
        chunk = {"type": "agent_status", **spec.get("usage", {})}
    else:
        logger.warning("FakeAgent: unknown emit type {}", typ)
        return

    try:
        await on_session_update(session_id, chunk)
    except Exception:
        logger.debug("FakeAgent: on_session_update raised for session {} (non-fatal)", session_id)


# ---------------------------------------------------------------------------
# Core fake-session coroutine
# ---------------------------------------------------------------------------


async def run_fake_acp_session(
    *,
    session_id: str,
    task_id: str,
    on_session_update: Callable[[str, Any], Any],
    worktree: Path | None = None,
    script: FakeScript | None = None,
) -> None:
    """Drive a fake agent turn that mirrors a real ACP session lifecycle.

    Calls *on_session_update* with real ``AgentMessageChunk`` objects so the
    normal ``map_acp_update_to_event`` path in ``_sessions.py`` picks them up
    and persists ``output_chunk`` events.  After the configured delay the
    coroutine returns cleanly (simulating a successful agent run).
    """
    logger.info("FakeAgent: session {} started", session_id)

    effective_script = script or FakeScript(
        cues=[FakeCue(emit={"type": "chunk", "text": t}) for t in _CHUNK_TEXTS]
        + [FakeCue(wait=_delay_ms() / 1_000.0, done=True)]
    )

    for cue in effective_script.cues:
        if cue.wait > 0:
            await asyncio.sleep(cue.wait)

        if cue.emit:
            await _emit_acp(session_id, on_session_update, cue.emit)

        if cue.workspace:
            _apply_workspace_action(worktree, cue.workspace)

        if cue.error:
            raise RuntimeError(cue.error)

        if cue.done:
            break

    logger.info("FakeAgent: session {} completing", session_id)


def _delay_ms() -> int:
    raw = os.environ.get("KAGAN_FAKE_AGENT_DELAY_MS", "")
    try:
        return max(0, int(raw))
    except (ValueError, TypeError):
        return _DEFAULT_DELAY_MS


# ---------------------------------------------------------------------------
# spawn_fake_agent_via_acp
# ---------------------------------------------------------------------------


async def spawn_fake_agent_via_acp(
    *,
    session_id: str,
    task_id: str,
    on_session_update: Callable[[str, Any], Any],
    worktree: Path | None = None,
) -> tuple[int, asyncio.Task[None]]:
    """Fake analogue of ``spawn_agent_via_acp``.

    Returns a (pid=0, asyncio.Task) pair matching the real function's
    signature so ``_sessions.py`` can use either path transparently.  A pid of
    0 is safe because the caller only stores it for informational logging and
    optional kill-on-timeout — neither applies to in-process fake sessions.
    """
    script = await director.get(task_id) or await director.get(session_id)

    reader_task: asyncio.Task[None] = asyncio.create_task(
        run_fake_acp_session(
            session_id=session_id,
            task_id=task_id,
            on_session_update=on_session_update,
            worktree=worktree,
            script=script,
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
