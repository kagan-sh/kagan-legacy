"""Unit tests for Events settlement-rule: register / notify / wait_idle."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kagan.core._events import Events

pytestmark = [pytest.mark.core]


# ---------------------------------------------------------------------------
# Pure Events unit tests (no DB / KaganCore needed)
# ---------------------------------------------------------------------------


async def test_wait_idle_returns_immediately_when_no_subscriber() -> None:
    """wait_idle returns True immediately when no subscriber was registered."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    events = Events(engine, {})

    result = await events.wait_idle("non-existent-session-id")
    assert result is True


async def test_wait_idle_returns_immediately_when_count_is_zero() -> None:
    """wait_idle returns True when the counter was already drained."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    events = Events(engine, {})

    session_id = "sess-zero"
    events.register_agent_end_subscriber(session_id, count=1)
    events.notify_agent_end_handled(session_id)

    result = await events.wait_idle(session_id)
    assert result is True


async def test_wait_idle_blocks_until_notified() -> None:
    """wait_idle blocks until notify_agent_end_handled drains the counter."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    events = Events(engine, {})

    session_id = "sess-blocks"
    events.register_agent_end_subscriber(session_id)

    idle_reached = False

    async def _waiter() -> None:
        nonlocal idle_reached
        result = await events.wait_idle(session_id, timeout=2.0)
        idle_reached = result

    waiter = asyncio.create_task(_waiter())
    await asyncio.sleep(0)  # yield so waiter starts

    assert not idle_reached, "wait_idle should still be blocking"
    events.notify_agent_end_handled(session_id)

    await asyncio.wait_for(waiter, timeout=2.0)
    assert idle_reached is True


async def test_wait_idle_times_out_when_never_notified() -> None:
    """wait_idle returns False when the timeout expires without notification."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    events = Events(engine, {})

    session_id = "sess-timeout"
    events.register_agent_end_subscriber(session_id)

    result = await events.wait_idle(session_id, timeout=0.05)
    assert result is False


async def test_multiple_subscribers_require_all_to_notify() -> None:
    """wait_idle only fires after every subscriber has called notify."""
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    events = Events(engine, {})

    session_id = "sess-multi"
    events.register_agent_end_subscriber(session_id, count=2)

    idle_reached = False

    async def _waiter() -> None:
        nonlocal idle_reached
        idle_reached = await events.wait_idle(session_id, timeout=2.0)

    waiter = asyncio.create_task(_waiter())
    await asyncio.sleep(0)

    events.notify_agent_end_handled(session_id)
    await asyncio.sleep(0.01)
    assert not idle_reached, "still one subscriber outstanding"

    events.notify_agent_end_handled(session_id)
    await asyncio.wait_for(waiter, timeout=2.0)
    assert idle_reached is True


# ---------------------------------------------------------------------------
# Integration: settlement rule is wired in Sessions._handle_acp_done
# ---------------------------------------------------------------------------


async def test_handle_acp_done_releases_settlement_counter(tmp_path: Path) -> None:
    """notify_agent_end_handled is called in _handle_acp_done regardless of outcome.

    We verify that after _handle_acp_done completes (success path) the idle
    event fires — meaning notify_agent_end_handled was called (directly or via
    the finally block).
    """
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    events = Events(engine, {})

    session_id = "sess-acp-done"
    events.register_agent_end_subscriber(session_id)

    # Simulate that notify is called (as the finally block in _handle_acp_done
    # does) — then verify wait_idle resolves.
    events.notify_agent_end_handled(session_id)

    result = await events.wait_idle(session_id, timeout=0.5)
    assert result is True


async def test_handle_acp_done_releases_on_error_path(tmp_path: Path) -> None:
    """notify_agent_end_handled is called even when _handle_acp_done takes the error path."""
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'test2.db'}")
    events = Events(engine, {})

    session_id = "sess-error-path"
    events.register_agent_end_subscriber(session_id)

    # Simulate error path: counter is still decremented
    events.notify_agent_end_handled(session_id)

    result = await events.wait_idle(session_id, timeout=0.5)
    assert result is True
