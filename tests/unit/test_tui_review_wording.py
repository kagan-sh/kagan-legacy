from types import SimpleNamespace

import pytest

from kagan.core.enums import TaskStatus
from kagan.tui.widgets.task_review_helpers import build_merge_readiness_text

pytestmark = [pytest.mark.unit]


def test_ai_criteria_pass_does_not_mark_human_approved() -> None:
    task = SimpleNamespace(
        status=TaskStatus.REVIEW,
        criteria=[
            SimpleNamespace(ordinal=0, verdicts=[SimpleNamespace(verdict="pass")]),
            SimpleNamespace(ordinal=1, verdicts=[SimpleNamespace(verdict="pass")]),
        ],
    )

    text = build_merge_readiness_text(task, human_approved=False, last_merge_blocker=None)

    assert "Human approval pending" in text
    assert "AI review: all 2 criteria passed" in text
    assert "✓ Approved" not in text


def test_human_approval_is_separate_review_gate() -> None:
    task = SimpleNamespace(
        status=TaskStatus.REVIEW,
        criteria=[SimpleNamespace(ordinal=0, verdicts=[SimpleNamespace(verdict="pass")])],
    )

    text = build_merge_readiness_text(task, human_approved=True, last_merge_blocker=None)

    assert "Human approved" in text
    assert "AI review: all 1 criteria passed" in text


def test_merge_readiness_is_empty_without_task() -> None:
    assert build_merge_readiness_text(None, last_merge_blocker=None) == ""


def test_merged_task_shows_review_summary() -> None:
    task = SimpleNamespace(
        status=TaskStatus.DONE,
        criteria=[
            SimpleNamespace(ordinal=0, verdicts=[SimpleNamespace(verdict="pass")]),
            SimpleNamespace(ordinal=1, verdicts=[SimpleNamespace(verdict="fail")]),
        ],
    )

    text = build_merge_readiness_text(task, last_merge_blocker=None)

    assert "Review Summary (merged)" in text
    assert "1/2 criteria passed" in text


def test_merge_blocker_is_shown_with_failed_ai_review() -> None:
    task = SimpleNamespace(
        status=TaskStatus.REVIEW,
        criteria=[
            SimpleNamespace(ordinal=0, verdicts=[SimpleNamespace(verdict="pass")]),
            SimpleNamespace(ordinal=1, verdicts=[SimpleNamespace(verdict="fail")]),
        ],
    )

    text = build_merge_readiness_text(
        task,
        human_approved=True,
        last_merge_blocker="Working tree has conflicts",
    )

    assert "Human approved" in text
    assert "Working tree has conflicts" in text
    assert "AI review: 1/2 criteria failed" in text


def test_partial_ai_review_is_reported_as_processed() -> None:
    task = SimpleNamespace(
        status=TaskStatus.REVIEW,
        criteria=[
            SimpleNamespace(ordinal=0, verdicts=[SimpleNamespace(verdict="pass")]),
            SimpleNamespace(ordinal=1, verdicts=[]),
        ],
    )

    text = build_merge_readiness_text(task, last_merge_blocker=None)

    assert "No merge blockers" in text
    assert "AI review: 1/2 criteria processed" in text


def test_review_without_criteria_points_to_approval_options() -> None:
    task = SimpleNamespace(status=TaskStatus.REVIEW, criteria=[])

    text = build_merge_readiness_text(task, last_merge_blocker=None)

    assert "Human approval pending (no criteria)" in text
    assert "AI review: not run yet" in text
