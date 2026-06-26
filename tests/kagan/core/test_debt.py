"""Structural debt budget (lever 9): a best-effort, language-agnostic signal that
routes a rotting scope into heavier review WITHOUT ever blocking generation.

These encode WHY the signal is shaped this way (Rule 9), not just the arithmetic:
  - debt counts DUPLICATION + CHURN and has NO novelty term: boilerplate/copy-paste
    RAISES debt while a small unique change stays cheap. A novelty term would invert
    this and reward boilerplate (the GitClear pathology DESIGN lever 9 forbids);
  - escalation is ONE-DIRECTIONAL up (low->medium->high), never down, and a None
    threshold disables it so an unconfigured repo is unchanged;
  - cumulative scope debt is derived from ledger history, no DB.
"""

from kagan.core.debt import (
    ChangesetDebt,
    changeset_debt,
    cumulative_scope_debt,
    escalate_tier,
)
from kagan.core.models import Finding, Task


def _diff(*added_lines: str) -> str:
    # A minimal unified diff: a +++ header (which must be ignored) plus added lines.
    return "+++ b/x.py\n" + "".join(f"+{ln}\n" for ln in added_lines)


def test_duplication_raises_debt_more_than_an_equal_count_of_unique_lines():
    # WHY: the signal must penalize copy-paste, not raw line count. A block repeated
    # verbatim (a copy-pasted unit) scores higher than the same number of distinct
    # lines, so consolidating the copy would lower the score — the inverse of a
    # novelty term, which is what keeps it un-gameable by writing boilerplate.
    block = ["a = 1", "b = 2", "c = 3", "d = 4", "e = 5"]
    duplicated = changeset_debt(_diff(*block, *block))  # the block copy-pasted once
    unique = changeset_debt(_diff(*[f"u{i} = {i}" for i in range(10)]))  # 10 distinct lines
    assert duplicated.churn == unique.churn == 10  # same raw churn
    assert duplicated.duplicated > 0  # the repeated window is flagged
    assert unique.duplicated == 0  # nothing repeats
    assert duplicated.score > unique.score  # duplication is the differentiator


def test_small_unique_change_has_no_duplication_and_low_score():
    # WHY: a short, novel change must be debt-cheap — the lever escalates ROT, not
    # ordinary small work. Below the shingle size there is no window to repeat.
    d = changeset_debt(_diff("def add(a, b):", "    return a + b"))
    assert d.duplicated == 0
    assert d.score == d.churn == 2


def test_there_is_no_novelty_term():
    # WHY (the load-bearing anti-gaming property): writing MORE distinct boilerplate
    # never lowers the score. A novelty term would reward "different" code; here a
    # change can only lower its score by REMOVING duplication, not by being novel.
    few_unique = changeset_debt(_diff("x = 1", "y = 2"))
    more_unique = changeset_debt(_diff(*[f"v{i} = {i}" for i in range(20)]))
    assert more_unique.score >= few_unique.score  # novelty never discounts debt


def test_added_file_header_and_blank_lines_are_not_counted():
    # WHY: +++ is a diff header, not real added code, and blank lines are spacing —
    # counting either would inflate churn and let formatting masquerade as work.
    d = changeset_debt("+++ b/x.py\n+real = 1\n+\n+   \n")
    assert d.churn == 1


def _task(scope: list[str], *locations: str) -> Task:
    return Task(
        id=f"t{hash(tuple(locations)) & 0xFFFF}",
        title="t",
        scope=scope,
        findings=[Finding(id=loc, severity="nit", location=loc, message="m") for loc in locations],
    )


def test_cumulative_scope_debt_counts_prior_tasks_touching_the_scope():
    # WHY: the cross-diff blind spot is "this area keeps getting rewritten". We count
    # prior tasks whose touched files (finding locations, the best-effort set) fall
    # under the scope glob — a file under no overlapping scope does not count.
    tasks = [
        _task(["src/auth/**"], "src/auth/login.py"),
        _task(["src/auth/**"], "src/auth/session.py"),
        _task(["docs/**"], "docs/readme.md"),  # different area -> not counted
    ]
    assert cumulative_scope_debt(["src/auth/**"], tasks) == 2
    assert cumulative_scope_debt(["docs/**"], tasks) == 1
    assert cumulative_scope_debt([], tasks) == 0  # no scope -> no signal

    # exclude_id drops the task being classified so it never counts itself.
    target = _task(["src/auth/**"], "src/auth/a.py")
    pool = [target, _task(["src/auth/**"], "src/auth/b.py")]
    assert cumulative_scope_debt(["src/auth/**"], pool) == 2
    assert cumulative_scope_debt(["src/auth/**"], pool, exclude_id=target.id) == 1


def test_escalate_bumps_up_one_level_when_over_threshold():
    # WHY (the teeth): a rotting scope routes itself into heavier ceremony. The bump
    # is exactly one tier so a hot area gets the next ladder rung, not max ceremony.
    assert escalate_tier("low", cumulative=3, threshold=2) == "medium"
    assert escalate_tier("medium", cumulative=3, threshold=2) == "high"


def test_escalate_never_bumps_down_and_high_is_terminal():
    # WHY: escalation is one-directional. Debt may RAISE risk but a high scope a glob
    # already matched stays high — debt can never relax the autonomy ladder.
    assert escalate_tier("high", cumulative=999, threshold=0) == "high"


def test_escalate_is_a_noop_under_threshold_or_when_disabled():
    # WHY: below the budget nothing changes, and threshold=None disables the lever so
    # an unconfigured repo behaves exactly like today (the additive-by-default rule).
    assert escalate_tier("low", cumulative=1, threshold=2) == "low"
    assert escalate_tier("low", cumulative=999, threshold=None) == "low"


def test_changeset_debt_is_a_pure_model():
    # WHY: the signal is data, not a side effect — it can be surfaced in the private
    # scorecard without any I/O. Guards against someone making score recompute live.
    d = changeset_debt(_diff("a = 1"))
    assert isinstance(d, ChangesetDebt)
    assert d.score == d.churn + d.duplicated


def test_scope_debt_counts_real_changed_files_without_findings():
    # M1: a churning scope with NO findings must register. The old finding-location
    # proxy read zero here (turkey problem — absence of findings != absence of churn);
    # real changed_files is the actual exposure the escalation routes on.
    clean = Task(id="task-1", title="x", changed_files=["src/auth/login.py"])
    assert cumulative_scope_debt(["src/auth/**"], [clean]) == 1


def test_scope_debt_falls_back_to_finding_locations_for_legacy_tasks():
    # M1 migration: a task harvested before changed_files existed (empty list) still
    # contributes via its finding locations — graceful, no zeroing of old history.
    legacy = Task(
        id="task-2",
        title="x",
        findings=[Finding(id="f1", severity="blocking", location="src/auth/x.py", message="m")],
    )
    assert cumulative_scope_debt(["src/auth/**"], [legacy]) == 1
