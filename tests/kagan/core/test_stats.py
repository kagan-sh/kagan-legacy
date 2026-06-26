"""Lever 7 outcome scorecard: cycle-time / CFR / comprehension-first-try /
review-caught / best-effort durability, computed read-only from a seeded ledger.

These encode WHY each metric matters (Rule 9), not just the arithmetic:
  - cycle-time keys on the canonical REVIEW->READY transition, never the
    double-emitted "approved" event;
  - CFR excludes pending/unknown so a pending check is never silently a pass;
  - comprehension first-try fails the moment a note is re-recorded;
  - review-caught counts only adversarial blocking findings the human UPHELD
    (a disagree = human overruled, must not count).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kagan.core.enums import TaskState
from kagan.core.models import Finding, Task
from kagan.core.stats import compute_scorecard, durability


def _ready_events(*, created: datetime, ready: datetime) -> list[dict]:
    return [
        {"type": "created", "ts": created.isoformat()},
        {
            "type": "transition",
            "from": TaskState.REVIEW.value,
            "to": TaskState.READY.value,
            "ts": ready.isoformat(),
        },
    ]


def test_cycle_time_medians_by_risk_from_review_to_ready_transition():
    base = datetime(2026, 6, 1, tzinfo=UTC)
    # Two medium tasks: 1h and 3h -> median 2h. One low task: 30m. Both keyed on the
    # REVIEW->READY transition, NOT created_at-to-now.
    tasks = [
        Task(id="m1", title="m1", risk="medium"),
        Task(id="m2", title="m2", risk="medium"),
        Task(id="l1", title="l1", risk="low"),
    ]
    events = {
        "m1": _ready_events(created=base, ready=base + timedelta(hours=1)),
        "m2": _ready_events(created=base, ready=base + timedelta(hours=3)),
        "l1": _ready_events(created=base, ready=base + timedelta(minutes=30)),
    }
    card = compute_scorecard(tasks, events)
    assert card.shipped == 3
    assert card.cycle_seconds_by_risk["medium"] == 7200.0  # median(3600, 10800)
    assert card.cycle_seconds_by_risk["low"] == 1800.0


def test_task_that_never_reached_ready_is_excluded_from_cycle_time():
    # A REVIEW task with no READY transition contributes no t1, so it must not be
    # counted as shipped nor pollute the median (it would otherwise be a fake 0).
    tasks = [Task(id="open", title="open", risk="medium", state=TaskState.REVIEW)]
    events = {"open": [{"type": "created", "ts": datetime(2026, 6, 1, tzinfo=UTC).isoformat()}]}
    card = compute_scorecard(tasks, events)
    assert card.shipped == 0
    assert card.cycle_seconds_by_risk == {}


def test_cfr_counts_only_settled_pr_open_tasks():
    # CFR = failed / (pass|fail) over PR_OPEN tasks. A pending PR must NOT be counted
    # as a pass (which would understate the failure rate).
    tasks = [
        Task(id="a", title="a", state=TaskState.PR_OPEN, remote_ci_status="fail"),
        Task(id="b", title="b", state=TaskState.PR_OPEN, remote_ci_status="pass"),
        Task(id="c", title="c", state=TaskState.PR_OPEN, remote_ci_status="pending"),
        Task(id="d", title="d", state=TaskState.PR_OPEN, remote_ci_status="unknown"),
        Task(id="e", title="e", state=TaskState.READY),  # not a PR -> not counted
    ]
    card = compute_scorecard(tasks, {})
    assert card.cfr_failed == 1
    assert card.cfr_total == 2  # only the fail + the pass; pending/unknown excluded


def test_cfr_is_none_when_no_pr_has_a_verdict():
    # No settled PR CI -> N/A signal, not 0% (don't invent a clean rate).
    tasks = [Task(id="a", title="a", state=TaskState.PR_OPEN, remote_ci_status="pending")]
    card = compute_scorecard(tasks, {})
    assert card.cfr_failed is None
    assert card.cfr_total is None


def test_comprehension_first_try_uses_required_keys_for_task_on_fallback():
    tasks = [
        Task(
            id="t0",
            title="t0",
            risk="high",
            comprehension_prompts=[("postcondition", "Only one?")],
        ),
    ]
    events = {
        "t0": [
            {"type": "comprehension_recorded", "key": "postcondition"},
            {"type": "comprehension_recorded", "key": "delta"},
            {"type": "comprehension_recorded", "key": "dependencies"},
            {"type": "comprehension_recorded", "key": "security"},
            {"type": "comprehension_recorded", "key": "gotchas"},
        ],
    }
    card = compute_scorecard(tasks, events)
    assert card.comprehension_first_try == 1


def test_comprehension_first_try_fails_when_note_was_re_recorded():
    # First-try = the full risk-scaled prompt set answered once each (distinct keys
    # cover the tier's required keys AND no key re-recorded). A re-answered prompt
    # (a thin note rejected then redone) is NOT first-try. Low-risk tasks (no
    # prompts) emit none and are excluded from the denominator entirely.
    tasks = [
        Task(id="t0", title="t0", risk="medium"),
        Task(id="t1", title="t1", risk="medium"),
        Task(id="t2", title="t2", risk="low"),
    ]
    events = {
        # both medium prompts answered once each -> first-try.
        "t0": [
            {"type": "comprehension_recorded", "key": "postcondition"},
            {"type": "comprehension_recorded", "key": "what_breaks"},
        ],
        # postcondition re-answered after a thin first pass -> not first-try.
        "t1": [
            {"type": "comprehension_recorded", "key": "postcondition"},
            {"type": "comprehension_recorded", "key": "what_breaks"},
            {"type": "comprehension_recorded", "key": "postcondition"},
        ],
        "t2": [],  # never asked (low risk) -> not in the denominator
    }
    card = compute_scorecard(tasks, events)
    assert card.comprehension_asked == 2  # t2 excluded
    assert card.comprehension_first_try == 1  # only t0


def test_review_caught_counts_only_upheld_adversarial_blockers():
    # A real bug caught == blocking + ai-review/security + human AGREED. A machine
    # finding, a non-blocking finding, or a DISAGREED finding (human overruled) must
    # not count.
    task = Task(
        id="t",
        title="t",
        findings=[
            Finding(
                id="f1",
                severity="blocking",
                location="a.py",
                message="x",
                source="ai-review",
                verdict="agree",
            ),
            Finding(
                id="f2",
                severity="blocking",
                location="b.py",
                message="y",
                source="security",
                verdict="agree",
            ),
            Finding(
                id="f3",
                severity="blocking",
                location="c.py",
                message="z",
                source="ai-review",
                verdict="disagree",
            ),
            Finding(
                id="f4",
                severity="blocking",
                location="d.py",
                message="w",
                source="machine",
                verdict="agree",
            ),
            Finding(
                id="f5",
                severity="nit",
                location="e.py",
                message="v",
                source="ai-review",
                verdict="agree",
            ),
        ],
    )
    card = compute_scorecard([task], {})
    assert card.review_caught == 2  # f1 + f2 only


@pytest.mark.asyncio
async def test_durability_flags_files_re_edited_on_base_within_window(tmp_path: Path):
    # Best-effort: an approved task whose changed files were touched again on base
    # within the window is NOT durable. The other, untouched, is. Uses a stub git
    # runner so no real repo is needed (durability is observational by design).
    base = datetime(2026, 6, 20, tzinfo=UTC)
    durable = Task(
        id="durable",
        title="durable",
        base_commit="abc",
        findings=[Finding(id="f", severity="blocking", location="kept.py", message="m")],
    )
    reverted = Task(
        id="reverted",
        title="reverted",
        base_commit="def",
        findings=[Finding(id="f", severity="blocking", location="reverted.py", message="m")],
    )
    events = {
        "durable": _ready_events(created=base, ready=base),
        "reverted": _ready_events(created=base, ready=base),
    }

    async def fake_git(args: list[str], *, cwd: Path, check: bool) -> str:
        # The probe greps the base branch for later commits touching the task files.
        return "deadbeef revert it\n" if "reverted.py" in args else ""

    untouched, observed = await durability(
        [durable, reverted],
        repo_root=tmp_path,
        git_runner=fake_git,
        events_by_task=events,
        now=base,
    )
    assert observed == 2
    assert untouched == 1  # only `durable` had no later commit
