"""Unit tests for CLIRenderer.on_agent_lifecycle.

Verifies that AgentLifecycle events produce correctly-formatted dim lines
via print_via_terminal when dispatched through on_event.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from kagan.cli.chat._renderer import CLIRenderer
from kagan.core.events import AgentLifecycle

pytestmark = [pytest.mark.unit]


def _console_and_buf() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None, width=120)
    return console, buf


def _fire(kind: str, *, task_id: str | None = "task-abc123", detail: str | None = None) -> str:
    """Fire an AgentLifecycle event through CLIRenderer and return console output."""
    console, buf = _console_and_buf()
    renderer = CLIRenderer(console)
    event = AgentLifecycle(
        session_id="session-1",
        task_id=task_id,
        kind=kind,  # type: ignore[arg-type]
        detail=detail,
    )
    renderer.on_event(event)
    return buf.getvalue()


def test_finished_kind_prints_checkmark() -> None:
    output = _fire("finished", task_id="abc12345")
    assert "✓" in output
    assert "#abc12345" in output
    assert "finished" in output


def test_failed_kind_prints_cross() -> None:
    output = _fire("failed", task_id="abc12345", detail="exit code 1")
    assert "✗" in output
    assert "failed" in output
    assert "exit code 1" in output


def test_failed_kind_no_detail() -> None:
    output = _fire("failed", task_id="abc12345")
    assert "✗" in output
    assert "failed" in output


def test_stopped_kind_prints_circle() -> None:
    output = _fire("stopped", task_id="abc12345")
    assert "◯" in output
    assert "stopped" in output


def test_started_kind_prints_arrow() -> None:
    output = _fire("started", task_id="abc12345")
    assert "▸" in output
    assert "started" in output


def test_task_id_is_truncated_to_eight_chars() -> None:
    output = _fire("finished", task_id="abcdef1234567890")
    assert "#abcdef12" in output
    assert "1234567890" not in output


def test_none_task_id_shows_task_label() -> None:
    output = _fire("finished", task_id=None)
    assert "task" in output


def test_on_event_dispatches_agent_lifecycle() -> None:
    """on_event 'agent_lifecycle' arm invokes on_agent_lifecycle."""
    console, buf = _console_and_buf()
    renderer = CLIRenderer(console)
    event = AgentLifecycle(
        session_id="s1",
        task_id="T1abcdef",
        kind="finished",
        detail=None,
    )
    renderer.on_event(event)
    output = buf.getvalue()
    assert "✓" in output
    assert "T1abcdef" in output
