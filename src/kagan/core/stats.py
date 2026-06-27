"""Outcome scorecard (lever 7) — a PRIVATE self-calibration mirror.

Read-only over the ledger (Task state + events.jsonl) and read-only ``git log``;
no DB, no new git verbs, no schema change (DESIGN lever 7). The five outcome
metrics are the ones the research says actually matter — cycle-time, change-
failure-rate, comprehension-first-try, review-caught, and a best-effort
durability — NOT commits or LOC.

This is a self-mirror only: it is never written to the committable ``.kagan/``
and is never a team productivity metric (DESIGN §3.6 — l7 stats are private).

Metrics 1-4 are pure (``compute_scorecard``) so they unit-test like inbox.py.
Metric 5 (``durability``) is async + git-backed and best-effort, so it is kept
apart (kagan never merges, so durability can only ever be observational).
"""

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

from kagan.core.comprehension import required_keys_for_task
from kagan.core.debt import cumulative_scope_debt
from kagan.core.enums import TaskState
from kagan.core.models import Task  # noqa: TC001 — used at runtime in compute_scorecard

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from pathlib import Path


class Scorecard(BaseModel):
    """The computed outcome metrics. None / empty == "no signal yet" (render "—"),
    never a fabricated zero (inbox.py None-on-empty precedent)."""

    shipped: int  # tasks that ever reached READY (the headline count)
    cycle_seconds_by_risk: dict[str, float]  # median intake->READY seconds per tier
    cfr_failed: int | None  # PR_OPEN tasks with remote CI fail
    cfr_total: int | None  # PR_OPEN tasks with a known (pass|fail) CI verdict
    comprehension_first_try: (
        int  # tasks whose full risk-scaled prompt set was answered once each (no re-records)
    )
    comprehension_asked: int  # tasks asked to comprehend at all (denominator)
    review_caught: int  # agreed blocking ai-review/security findings
    # lever 9: cross-diff debt per touched scope (private). Default empty so the
    # field is additive — an old caller that omits it renders the "no trend" line.
    debt_by_scope: dict[str, int] = Field(default_factory=dict)


def _reached_ready_at(events: list[dict]) -> datetime | None:
    """Timestamp of the first REVIEW -> READY transition (the canonical approval
    signal the inbox already keys on, NOT the ambiguous double-emitted
    "approved" event)."""
    for e in events:
        if (
            e.get("type") == "transition"
            and e.get("to") == TaskState.READY.value
            and e.get("from") == TaskState.REVIEW.value
        ):
            ts = e.get("ts")
            if ts:
                return datetime.fromisoformat(str(ts))
    return None


def _created_at(task: Task, events: list[dict]) -> datetime:
    for e in events:
        if e.get("type") == "created":
            ts = e.get("ts")
            if ts:
                return datetime.fromisoformat(str(ts))
    return task.created_at  # equivalent fallback


def _cycle_seconds_by_risk(
    tasks: list[Task], events_by_task: dict[str, list[dict]]
) -> dict[str, float]:
    # Cycle time = first event (intake) -> first REVIEW->READY transition, median
    # per risk tier. Tasks that never reached READY have no t1 and are excluded.
    # Bucketed by the LIVE risk tier (re-derivable from scope, may have changed).
    by_tier: dict[str, list[float]] = {}
    for task in tasks:
        events = events_by_task.get(task.id, [])
        ready_at = _reached_ready_at(events)
        if ready_at is None:
            continue
        seconds = (ready_at - _created_at(task, events)).total_seconds()
        if seconds < 0:
            continue
        by_tier.setdefault(task.risk, []).append(seconds)
    return {tier: median(vals) for tier, vals in by_tier.items() if vals}


def _cfr(tasks: list[Task]) -> tuple[int | None, int | None]:
    # Change-failure-rate over tasks open as a PR. Denominator = PR_OPEN tasks with
    # a settled CI verdict (pass|fail); pending/unknown are excluded so a pending
    # check is not silently counted as a pass (which would understate CFR). No
    # qualifying tasks => (None, None) so the surface renders N/A, not 0%.
    settled = [
        t for t in tasks if t.state is TaskState.PR_OPEN and t.remote_ci_status in {"pass", "fail"}
    ]
    if not settled:
        return None, None
    failed = sum(1 for t in settled if t.remote_ci_status == "fail")
    return failed, len(settled)


def _comprehension(tasks: list[Task], events_by_task: dict[str, list[dict]]) -> tuple[int, int]:
    # First-try = the author answered the full risk-scaled prompt set right once:
    # the distinct answered keys cover the tier's required keys AND no key was
    # re-recorded (total comprehension_recorded events == distinct keys == required
    # count). A re-answered prompt => not first-try. Denominator = tasks (risk != low)
    # that recorded >=1 answer (low skips the lock and emits no events).
    first_try = 0
    asked = 0
    for task in tasks:
        if task.risk == "low":
            continue
        events = [
            e for e in events_by_task.get(task.id, []) if e.get("type") == "comprehension_recorded"
        ]
        if not events:
            continue
        asked += 1
        keys = [e.get("key") for e in events]
        distinct = set(keys)
        required = set(required_keys_for_task(task))
        if required <= distinct and len(events) == len(distinct) == len(required):
            first_try += 1
    return first_try, asked


def _review_caught(tasks: list[Task]) -> int:
    # Real bugs the validator surfaced and the human upheld: blocking findings from
    # an adversarial source (ai-review|security) the human marked "agree". A
    # "disagree" means the human overruled the machine, so it is excluded.
    return sum(
        1
        for task in tasks
        for f in task.findings
        if f.severity == "blocking"
        and f.source in {"ai-review", "security"}
        and f.verdict == "agree"
    )


def _debt_by_scope(tasks: list[Task]) -> dict[str, int]:
    # Lever 9 (PRIVATE): cross-diff structural debt per scope the tasks declare —
    # how many tasks rewrote files under each distinct scope glob. A rising number
    # is what escalates that scope's tier; surfaced here so the human sees WHICH
    # area is rotting. Pure read over the ledger (cumulative_scope_debt is pure),
    # so it stays in the sync scorecard, never a subprocess. Only scopes touched by
    # >= 2 tasks are kept (a scope seen once is not yet a trend).
    scopes = {s for t in tasks for s in t.scope if s}
    out = {s: cumulative_scope_debt([s], tasks) for s in scopes}
    return {s: n for s, n in out.items() if n >= 2}


def compute_scorecard(tasks: list[Task], events_by_task: dict[str, list[dict]]) -> Scorecard:
    """Pure compute of outcome metrics 1-4 + the lever-9 debt trend (DESIGN levers
    7+9). Read-only; no I/O."""
    shipped = sum(1 for t in tasks if _reached_ready_at(events_by_task.get(t.id, [])) is not None)
    cfr_failed, cfr_total = _cfr(tasks)
    first_try, asked = _comprehension(tasks, events_by_task)
    return Scorecard(
        shipped=shipped,
        cycle_seconds_by_risk=_cycle_seconds_by_risk(tasks, events_by_task),
        cfr_failed=cfr_failed,
        cfr_total=cfr_total,
        comprehension_first_try=first_try,
        comprehension_asked=asked,
        review_caught=_review_caught(tasks),
        debt_by_scope=_debt_by_scope(tasks),
    )


class _GitRunner(Protocol):
    def __call__(self, args: list[str], *, cwd: Path, check: bool) -> Awaitable[str]: ...


_DURABILITY_WINDOW_DAYS = 14


async def durability(
    tasks: list[Task],
    *,
    repo_root: Path,
    git_runner: _GitRunner,
    events_by_task: dict[str, list[dict]],
    now: datetime | None = None,
    window_days: int = _DURABILITY_WINDOW_DAYS,
) -> tuple[int, int]:
    """Best-effort durability (lever 7): of approved tasks, how many had their
    changed files left untouched on the base branch within ``window_days``.

    FUNDAMENTAL LIMIT (DESIGN lever 7 / TUI-SHIP-05): kagan NEVER merges — approve
    only marks READY and the human runs the push/PR themselves. So the harness
    cannot know which approved tasks actually landed, nor when. ``base_commit`` is
    the worktree's HEAD at prep time, not a merge commit. The read-only ``git log``
    below can only observe the base branch when the user later merged AND kept
    working in the same clone. Frame this as observational, never a hard
    reliability number. Returns (untouched, observed) over tasks we could check;
    (0, 0) when nothing is observable (the surface renders that as "too new").
    """
    now = now or datetime.now(UTC)
    window_start = now - timedelta(days=window_days)
    cutoff = window_start.date().isoformat()
    observed = 0
    untouched = 0
    for task in tasks:
        ready_at = _reached_ready_at(events_by_task.get(task.id, []))
        if ready_at is None or task.base_commit is None:
            continue
        # F26: a two-week-durability metric cannot be computed on a fresh task. Only count
        # a task once it has had the full window to survive — otherwise "0 of 1 untouched
        # after two weeks" is a nonsense data point on a task that shipped minutes ago. Too
        # young → not observed (the surface renders observed==0 as "too new").
        ready_at = ready_at if ready_at.tzinfo else ready_at.replace(tzinfo=UTC)
        if ready_at > window_start:
            continue
        files = _changed_files(task)
        if not files:
            continue
        observed += 1
        if not await _files_touched_since(git_runner, repo_root, task, files, cutoff):
            untouched += 1
    return untouched, observed


def _changed_files(task: Task) -> list[str]:
    # M1: prefer the real harvested changed-file set; fall back to finding locations
    # for tasks harvested before changed_files existed. The proxy under-observed —
    # a task with no findings was skipped entirely (durability never saw it).
    if task.changed_files:
        return list(task.changed_files)
    seen: dict[str, None] = {}
    for f in task.findings:
        if f.location:
            seen.setdefault(f.location, None)
    return list(seen)


async def _files_touched_since(
    git_runner: _GitRunner, repo_root: Path, task: Task, files: list[str], cutoff: str
) -> bool:
    # Read-only `git log` over the base branch since the cutoff for the task's
    # files. Any commit touching them after approval == re-edited/reverted. Degrades
    # to "untouched" (False) on any git error — best-effort, never crashes stats.
    try:
        out = await git_runner(
            ["log", "--oneline", f"--since={cutoff}", task.base_branch, "--", *files],
            cwd=repo_root,
            check=False,
        )
    except Exception:
        return False
    return bool(out.strip())


__all__ = ["Scorecard", "compute_scorecard", "durability"]
