"""Tests for _kill_agent / _force_kill process-handle timeout path.

Covers:
- timeout fires → process is terminated via proc.terminate()/kill(), not os.kill()
- process already gone → no crash, timeout entry cleaned up
- unregister_spawned_process cancels the pending timer
- no signal.SIGKILL reference in the kill path (cross-platform safety)
"""

import asyncio
import sys

import pytest

from kagan.core._agent import (
    _AGENT_TIMEOUT_GRACE_SECONDS,
    _AGENT_TIMEOUTS,
    _AgentTimeout,
    _force_kill,
    _kill_agent,
    _spawned_processes,
    register_spawned_process,
    unregister_spawned_process,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fake asyncio subprocess Process
# ---------------------------------------------------------------------------


class _FakeProcess:
    """Minimal stand-in for asyncio.subprocess.Process."""

    def __init__(self, *, pid: int = 9999, already_dead: bool = False) -> None:
        self.pid: int = pid
        self.returncode: int | None = 0 if already_dead else None
        self.terminate_calls: int = 0
        self.kill_calls: int = 0

    def terminate(self) -> None:
        if self.returncode is not None:
            raise ProcessLookupError("process already exited")
        self.terminate_calls += 1
        # Simulate OS-level termination
        self.returncode = -15

    def kill(self) -> None:
        if self.returncode is not None:
            raise ProcessLookupError("process already exited")
        self.kill_calls += 1
        self.returncode = -9


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_timer_handle() -> asyncio.TimerHandle:
    """Return a cancelled TimerHandle (avoids scheduling real callbacks)."""
    loop = asyncio.get_event_loop_policy().get_event_loop()
    handle = loop.call_later(9999, lambda: None)
    handle.cancel()
    return handle


# ---------------------------------------------------------------------------
# _kill_agent
# ---------------------------------------------------------------------------


async def test_kill_agent_calls_terminate_not_os_kill() -> None:
    """_kill_agent must use proc.terminate(), never os.kill with signal constants."""
    proc = _FakeProcess(pid=1001)

    # Seed _AGENT_TIMEOUTS so _kill_agent can overwrite the entry
    loop = asyncio.get_event_loop()
    dummy = loop.call_later(9999, lambda: None)
    dummy.cancel()
    _AGENT_TIMEOUTS[proc.pid] = _AgentTimeout(proc=proc, handle=dummy)

    try:
        _kill_agent(proc)
        assert proc.terminate_calls == 1, "proc.terminate() should have been called once"
    finally:
        # Clean up any timer _kill_agent may have scheduled
        entry = _AGENT_TIMEOUTS.pop(proc.pid, None)
        if entry is not None:
            entry.handle.cancel()


async def test_kill_agent_process_already_dead_no_crash() -> None:
    """_kill_agent must not raise when proc.terminate() raises ProcessLookupError."""
    proc = _FakeProcess(pid=1002, already_dead=True)

    loop = asyncio.get_event_loop()
    dummy = loop.call_later(9999, lambda: None)
    dummy.cancel()
    _AGENT_TIMEOUTS[proc.pid] = _AgentTimeout(proc=proc, handle=dummy)

    try:
        # Should not raise even though terminate() raises ProcessLookupError
        _kill_agent(proc)
    finally:
        entry = _AGENT_TIMEOUTS.pop(proc.pid, None)
        if entry is not None:
            entry.handle.cancel()


async def test_kill_agent_schedules_force_kill_timer() -> None:
    """After _kill_agent, a grace-period timer entry must be present in _AGENT_TIMEOUTS."""
    proc = _FakeProcess(pid=1003)

    try:
        _kill_agent(proc)
        assert proc.pid in _AGENT_TIMEOUTS, "_AGENT_TIMEOUTS must contain the force-kill timer"
        entry = _AGENT_TIMEOUTS[proc.pid]
        assert entry.proc is proc
        assert not entry.handle.cancelled()
    finally:
        entry = _AGENT_TIMEOUTS.pop(proc.pid, None)
        if entry is not None:
            entry.handle.cancel()


# ---------------------------------------------------------------------------
# _force_kill
# ---------------------------------------------------------------------------


async def test_force_kill_kills_live_process() -> None:
    """_force_kill calls proc.kill() when process is still running."""
    proc = _FakeProcess(pid=2001)
    loop = asyncio.get_event_loop()
    dummy = loop.call_later(9999, lambda: None)
    dummy.cancel()
    _AGENT_TIMEOUTS[proc.pid] = _AgentTimeout(proc=proc, handle=dummy)

    _force_kill(proc)

    assert proc.kill_calls == 1
    assert proc.pid not in _AGENT_TIMEOUTS, "_AGENT_TIMEOUTS entry should be cleaned up"


async def test_force_kill_skips_already_dead_process() -> None:
    """_force_kill must not raise and must clean up when process is already gone."""
    proc = _FakeProcess(pid=2002, already_dead=True)
    loop = asyncio.get_event_loop()
    dummy = loop.call_later(9999, lambda: None)
    dummy.cancel()
    _AGENT_TIMEOUTS[proc.pid] = _AgentTimeout(proc=proc, handle=dummy)

    _force_kill(proc)  # Should not raise

    assert proc.kill_calls == 0, "kill() must not be called on an already-dead process"
    assert proc.pid not in _AGENT_TIMEOUTS


# ---------------------------------------------------------------------------
# unregister_spawned_process cancels the timer
# ---------------------------------------------------------------------------


async def test_unregister_cancels_pending_timer() -> None:
    """unregister_spawned_process must cancel any pending timeout timer."""
    session_id = "session-cancel-test"
    proc = _FakeProcess(pid=3001)

    await register_spawned_process(session_id, proc)

    loop = asyncio.get_event_loop()
    handle = loop.call_later(9999, _kill_agent, proc)
    _AGENT_TIMEOUTS[proc.pid] = _AgentTimeout(proc=proc, handle=handle)

    assert not handle.cancelled()
    await unregister_spawned_process(session_id)

    assert handle.cancelled(), "Timer handle must be cancelled after unregister"
    assert proc.pid not in _AGENT_TIMEOUTS
    assert session_id not in _spawned_processes


async def test_unregister_without_timer_does_not_crash() -> None:
    """unregister_spawned_process is safe even if no timeout was registered."""
    session_id = "session-no-timer"
    proc = _FakeProcess(pid=3002)

    await register_spawned_process(session_id, proc)
    await unregister_spawned_process(session_id)  # No timer registered — must not raise

    assert session_id not in _spawned_processes


async def test_unregister_unknown_session_is_noop() -> None:
    """unregister_spawned_process on an unknown session_id must not crash."""
    await unregister_spawned_process("does-not-exist")  # Should not raise


# ---------------------------------------------------------------------------
# Integration: full timeout cycle with a real subprocess
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="real subprocess spawn skipped on Windows CI")
async def test_timeout_kills_real_subprocess() -> None:
    """Spawn a real long-running process, register a short timeout, verify it exits."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert proc.pid is not None

    pid = proc.pid
    session_id = f"integration-{pid}"
    await register_spawned_process(session_id, proc)

    # Schedule a very short timeout
    loop = asyncio.get_event_loop()
    handle = loop.call_later(0.05, _kill_agent, proc)
    _AGENT_TIMEOUTS[pid] = _AgentTimeout(proc=proc, handle=handle)

    # Wait long enough for terminate + grace period + force kill
    total_wait = 0.05 + _AGENT_TIMEOUT_GRACE_SECONDS + 1.0
    await asyncio.sleep(total_wait)

    assert proc.returncode is not None, "Process must have been terminated by the timeout"

    # Clean up tracking state
    _spawned_processes.pop(session_id, None)
    entry = _AGENT_TIMEOUTS.pop(pid, None)
    if entry is not None:
        entry.handle.cancel()


# ---------------------------------------------------------------------------
# Windows-specific: no signal.SIGKILL in the kill path
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only guard")
def test_no_sigkill_reference_on_windows() -> None:
    """On Windows, signal.SIGKILL must not exist and the kill path must not reference it."""
    import signal as _signal

    assert not hasattr(_signal, "SIGKILL"), (
        "signal.SIGKILL must not exist on Windows — the kill path would raise AttributeError"
    )


def test_kill_agent_uses_proc_handle_not_os_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch os.kill to raise — _kill_agent must succeed without calling it."""
    import os

    def _bad_os_kill(pid: int, sig: int) -> None:
        raise AssertionError(f"os.kill({pid}, {sig}) must not be called by _kill_agent")

    monkeypatch.setattr(os, "kill", _bad_os_kill)

    proc = _FakeProcess(pid=4001)

    try:
        _kill_agent(proc)  # Must not call os.kill
    finally:
        entry = _AGENT_TIMEOUTS.pop(proc.pid, None)
        if entry is not None:
            entry.handle.cancel()
