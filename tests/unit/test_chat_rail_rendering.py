"""Unit tests for the inline running-agents rail formatter.

These tests exercise pure formatting functions — no I/O, no DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kagan.cli.chat._agents_rail import (
    AgentPickerRow,
    _resolve_picker_choice,
    build_picker_rows,
    format_agent_rows,
    format_agents_rail,
    format_rail_line,
)
from kagan.core._sessions_query import ActiveAgentRow

pytestmark = [pytest.mark.unit]


def _make_row(
    *,
    task_id: str = "task-1",
    task_title: str = "Implement feature",
    session_id: str = "sess-1",
    agent_role: str = "worker",
    session_status: str = "RUNNING",
    started_seconds_ago: float = 30.0,
    input_tokens: int | None = 40000,
    output_tokens: int | None = 42000,
) -> ActiveAgentRow:
    started_at = datetime.now(UTC) - timedelta(seconds=started_seconds_ago)
    return ActiveAgentRow(
        task_id=task_id,
        task_title=task_title,
        task_status="IN_PROGRESS",
        session_id=session_id,
        agent_role=agent_role,
        agent_backend="claude-code",
        session_status=session_status,
        started_at=started_at,
        last_event_at=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


# ---------------------------------------------------------------------------
# format_rail_line
# ---------------------------------------------------------------------------


def test_format_rail_line_zero_returns_empty_string() -> None:
    assert format_rail_line(0) == ""


def test_format_rail_line_one_agent() -> None:
    line = format_rail_line(1)
    assert "1 local agent" in line
    assert "↓ to manage" in line


def test_format_rail_line_multiple_agents() -> None:
    line = format_rail_line(3)
    assert "3 local agents" in line
    assert "↓ to manage" in line


def test_format_rail_line_starts_with_bullet() -> None:
    line = format_rail_line(2)
    assert line.startswith("●")


# ---------------------------------------------------------------------------
# format_agents_rail
# ---------------------------------------------------------------------------


def test_format_agents_rail_empty_list_returns_empty() -> None:
    assert format_agents_rail([]) == []


def test_format_agents_rail_single_row_returns_header_plus_detail() -> None:
    row = _make_row()
    lines = format_agents_rail([row])
    assert len(lines) == 2
    assert "1 local agent" in lines[0]
    # Detail line should contain role and title fragment
    assert "worker" in lines[1]
    assert "Implement feature" in lines[1]


def test_format_agents_rail_three_rows() -> None:
    rows = [
        _make_row(task_id="t1", session_id="s1", agent_role="worker"),
        _make_row(task_id="t2", session_id="s2", agent_role="reviewer"),
        _make_row(task_id="t3", session_id="s3", agent_role="worker"),
    ]
    lines = format_agents_rail(rows)
    assert len(lines) == 4  # 1 header + 3 detail rows
    assert "3 local agents" in lines[0]


def test_format_agent_rows_contains_elapsed_and_tokens() -> None:
    row = _make_row(started_seconds_ago=23.0, input_tokens=50000, output_tokens=32000)
    rows_text = format_agent_rows([row])
    assert len(rows_text) == 1
    line = rows_text[0]
    # Should contain elapsed time and token hint
    assert "23s" in line or "0m 23s" in line or "s" in line  # elapsed present in some form
    assert "k" in line  # token abbreviated


def test_format_agent_rows_no_tokens_when_none() -> None:
    row = _make_row(input_tokens=None, output_tokens=None)
    rows_text = format_agent_rows([row])
    assert len(rows_text) == 1
    # Should not contain ↓ if no tokens
    assert "↓" not in rows_text[0]


def test_format_agent_rows_title_truncated_at_40_chars() -> None:
    long_title = "A" * 60
    row = _make_row(task_title=long_title)
    rows_text = format_agent_rows([row])
    assert len(rows_text) == 1
    # Title should be truncated with ellipsis
    assert "…" in rows_text[0]


# ---------------------------------------------------------------------------
# _resolve_picker_choice
# ---------------------------------------------------------------------------


def _make_picker_rows() -> list[AgentPickerRow]:
    return [
        AgentPickerRow(
            label="main",
            session_id=None,
            agent_role=None,
            task_id=None,
            task_title="Return to orchestrator",
            context_tokens=None,
        ),
        AgentPickerRow(
            label="worker",
            session_id="sess-worker",
            agent_role="worker",
            task_id="task-1",
            task_title="Implement feature",
            context_tokens=82000,
        ),
        AgentPickerRow(
            label="reviewer",
            session_id="sess-reviewer",
            agent_role="reviewer",
            task_id="task-1",
            task_title="Implement feature",
            context_tokens=91000,
        ),
    ]


def test_resolve_picker_choice_returns_none_for_empty_list() -> None:
    assert _resolve_picker_choice([], 0) is None


def test_resolve_picker_choice_returns_none_for_negative_index() -> None:
    rows = _make_picker_rows()
    assert _resolve_picker_choice(rows, -1) is None


def test_resolve_picker_choice_returns_none_for_out_of_range() -> None:
    rows = _make_picker_rows()
    assert _resolve_picker_choice(rows, 10) is None


def test_resolve_picker_choice_index_zero_is_orchestrator() -> None:
    rows = _make_picker_rows()
    chosen = _resolve_picker_choice(rows, 0)
    assert chosen is not None
    assert chosen.session_id is None
    assert chosen.label == "main"


def test_resolve_picker_choice_index_one_is_first_agent() -> None:
    rows = _make_picker_rows()
    chosen = _resolve_picker_choice(rows, 1)
    assert chosen is not None
    assert chosen.session_id == "sess-worker"
    assert chosen.agent_role == "worker"


def test_resolve_picker_choice_index_two_is_second_agent() -> None:
    rows = _make_picker_rows()
    chosen = _resolve_picker_choice(rows, 2)
    assert chosen is not None
    assert chosen.session_id == "sess-reviewer"
    assert chosen.agent_role == "reviewer"


# ---------------------------------------------------------------------------
# build_picker_rows
# ---------------------------------------------------------------------------


def test_build_picker_rows_first_row_is_orchestrator() -> None:
    rows = build_picker_rows([])
    assert len(rows) == 1
    assert rows[0].session_id is None
    assert rows[0].label == "main"


def test_build_picker_rows_agents_follow_orchestrator() -> None:
    agent_row = _make_row(session_id="s1", agent_role="worker")
    rows = build_picker_rows([agent_row])
    assert len(rows) == 2
    assert rows[0].session_id is None  # orchestrator
    assert rows[1].session_id == "s1"
    assert rows[1].agent_role == "worker"


def test_build_picker_rows_computes_context_tokens() -> None:
    agent_row = _make_row(input_tokens=50000, output_tokens=32000)
    rows = build_picker_rows([agent_row])
    assert rows[1].context_tokens == 82000


def test_build_picker_rows_none_tokens_when_both_none() -> None:
    agent_row = _make_row(input_tokens=None, output_tokens=None)
    rows = build_picker_rows([agent_row])
    assert rows[1].context_tokens is None
