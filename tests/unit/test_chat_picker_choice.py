"""Unit tests for _resolve_picker_choice — pure function, no UI.

Tests verify index → AgentPickerRow mapping including boundary and
out-of-range safety, and the orchestrator slot (idx 0 → session_id=None).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kagan.cli.chat._agents_rail import (
    AgentPickerRow,
    _resolve_picker_choice,
    build_picker_rows,
)
from kagan.core._sessions_query import ActiveAgentRow

pytestmark = [pytest.mark.unit]


def _make_agent_row(
    *,
    session_id: str = "sess-abc",
    task_id: str = "task-1",
    task_title: str = "Do something",
    agent_role: str = "worker",
    input_tokens: int = 50_000,
    output_tokens: int = 32_000,
) -> ActiveAgentRow:
    return ActiveAgentRow(
        task_id=task_id,
        task_title=task_title,
        task_status="IN_PROGRESS",
        session_id=session_id,
        agent_role=agent_role,
        agent_backend="claude-code",
        session_status="RUNNING",
        started_at=datetime.now(UTC) - timedelta(minutes=3),
        last_event_at=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _make_picker_rows(n: int) -> list[AgentPickerRow]:
    active = [
        _make_agent_row(
            session_id=f"sess-{i}",
            task_id=f"task-{i}",
            task_title=f"Task {i}",
            agent_role="worker",
        )
        for i in range(n)
    ]
    return build_picker_rows(active)


# ---------------------------------------------------------------------------
# Orchestrator slot (index 0)
# ---------------------------------------------------------------------------


def test_resolve_picker_choice_idx_zero_returns_orchestrator_slot() -> None:
    """Index 0 is always the orchestrator/detach row (session_id=None)."""
    rows = _make_picker_rows(2)
    result = _resolve_picker_choice(rows, 0)
    assert result is not None
    assert result.session_id is None
    assert result.label == "main"


# ---------------------------------------------------------------------------
# Agent slots (index 1..N)
# ---------------------------------------------------------------------------


def test_resolve_picker_choice_idx_one_returns_first_agent() -> None:
    rows = _make_picker_rows(3)
    result = _resolve_picker_choice(rows, 1)
    assert result is not None
    assert result.session_id == "sess-0"


def test_resolve_picker_choice_idx_n_returns_last_agent() -> None:
    rows = _make_picker_rows(3)
    # rows = [main, sess-0, sess-1, sess-2]  → idx 3 → sess-2
    result = _resolve_picker_choice(rows, 3)
    assert result is not None
    assert result.session_id == "sess-2"


def test_resolve_picker_choice_single_agent_idx_one() -> None:
    rows = _make_picker_rows(1)
    result = _resolve_picker_choice(rows, 1)
    assert result is not None
    assert result.session_id == "sess-0"


# ---------------------------------------------------------------------------
# Out-of-range safety
# ---------------------------------------------------------------------------


def test_resolve_picker_choice_out_of_range_returns_none() -> None:
    rows = _make_picker_rows(2)
    assert _resolve_picker_choice(rows, 99) is None


def test_resolve_picker_choice_negative_index_returns_none() -> None:
    rows = _make_picker_rows(2)
    assert _resolve_picker_choice(rows, -1) is None


def test_resolve_picker_choice_empty_rows_returns_none() -> None:
    assert _resolve_picker_choice([], 0) is None


# ---------------------------------------------------------------------------
# build_picker_rows produces correctly structured list
# ---------------------------------------------------------------------------


def test_build_picker_rows_first_row_is_orchestrator() -> None:
    rows = _make_picker_rows(2)
    assert rows[0].label == "main"
    assert rows[0].session_id is None
    assert rows[0].agent_role is None


def test_build_picker_rows_length_is_n_plus_one() -> None:
    rows = _make_picker_rows(3)
    assert len(rows) == 4  # 1 orchestrator + 3 agents


def test_build_picker_rows_token_count_summed() -> None:
    active = [_make_agent_row(input_tokens=80_000, output_tokens=2_000)]
    rows = build_picker_rows(active)
    assert rows[1].context_tokens == 82_000


def test_build_picker_rows_zero_tokens_gives_none() -> None:
    active = [_make_agent_row(input_tokens=0, output_tokens=0)]
    rows = build_picker_rows(active)
    assert rows[1].context_tokens is None
