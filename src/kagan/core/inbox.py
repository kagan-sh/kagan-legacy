"""Inbox urgency ranking (TUI-INBOX-01). Pure read over canonical Task fields."""

from datetime import UTC, datetime
from statistics import median

from pydantic import BaseModel

from kagan.core.enums import TaskState
from kagan.core.models import Task  # noqa: TC001 — used at runtime in build_item

# TUI-INBOX-01 precedence: who needs a human most, first. Index = rank.
_PRECEDENCE: tuple[str, ...] = (
    "interrupted",
    "drift",
    "ci-failed",
    "needs-you",
    "intake",
    "review",
    "ready",
    "validating",
    "pr-open",
    "running",
    "done",
)


class InboxItem(BaseModel):
    task_id: str
    title: str
    state: TaskState
    signal: str
    rank: int
    risk: str = "medium"
    eta: str | None = None
    resume_point: str | None = None
    since_you_left: str | None = None
    last_activity_at: datetime | None = None
    drift_note: str | None = None
    remote_ci_detail: str | None = None
    needs_you_question: str | None = None


def _signal(task: Task) -> str:
    if task.interrupted:  # rule 12: a hard-killed runner — re-runnable (outranks all)
        return "interrupted"
    if task.drift:
        return "drift"
    if task.remote_ci_status == "fail":  # ci-failed is derived, not stored
        return "ci-failed"
    if task.needs_you is not None:  # NeedsYou | None — presence, not a bool
        return "needs-you"
    return task.state.value.replace("_", "-")  # pr_open -> pr-open


def _eta_seconds(task: Task, median_seconds: float | None) -> int | None:
    # Rough estimate (TUI-INBOX-03): median finished-task duration minus elapsed.
    # No history => None (the surface shows "running", never an invented number).
    if median_seconds is None or task.last_activity_at is None:
        return None
    elapsed = (datetime.now(UTC) - task.created_at).total_seconds()
    return max(int(median_seconds - elapsed), 0)


def _eta(task: Task, median_seconds: float | None) -> str | None:
    if task.state is not TaskState.RUNNING:
        return None
    seconds = _eta_seconds(task, median_seconds)
    if seconds is None:
        return "running"
    if seconds < 60:
        return f"{seconds}s"
    return f"~{seconds // 60}m"


# Event types grouped into the named buckets the "since you left" delta reports
# (TUI-INBOX-04: what changed / what was decided / what is now blocked).
_DELTA_BUCKETS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("finding", "findings", frozenset({"finding_added", "verdict_set"})),
    (
        "decision",
        "decisions",
        frozenset({"decision_added", "decision_answered", "intake_decisions_recorded"}),
    ),
    ("drift note", "drift notes", frozenset({"drift_recorded"})),
    ("step", "steps", frozenset({"transition", "worktree_prepared"})),
)


def _pluralize(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _since_you_left(task: Task, events: list[dict]) -> str | None:
    # Derived (P2): name the kinds of change after last_viewed_at. No stored summary.
    # `viewed` events mark the boundary itself, so they are not "updates".
    if task.last_viewed_at is None:
        return None
    cutoff = task.last_viewed_at.isoformat()
    fresh = [e for e in events if e.get("type") != "viewed" and str(e.get("ts", "")) > cutoff]
    if not fresh:
        return None
    parts: list[str] = []
    for one, many, types in _DELTA_BUCKETS:
        n = sum(1 for e in fresh if e.get("type") in types)
        if n:
            parts.append(_pluralize(n, one, many))
    if not parts:  # only event types outside the named buckets
        parts.append(_pluralize(len(fresh), "update", "updates"))
    return f"{' · '.join(parts)} since you left"


def _drift_note(task: Task) -> str | None:
    return next((f.message for f in task.findings if f.id.startswith("drift-")), None)


def _remote_ci_detail(task: Task) -> str | None:
    if task.remote_ci_status != "fail":
        return None
    failed = next((c.name for c in task.checks if not c.passed), None)
    return f"remote CI failed: {failed}" if failed else "remote CI failed"


def build_item(
    task: Task, events: list[dict] | None = None, *, median_seconds: float | None = None
) -> InboxItem:
    signal = _signal(task)
    return InboxItem(
        task_id=task.id,
        title=task.title,
        state=task.state,
        signal=signal,
        rank=_PRECEDENCE.index(signal),
        risk=task.risk,
        eta=_eta(task, median_seconds),
        resume_point=task.resume_point,
        since_you_left=_since_you_left(task, events or []),
        last_activity_at=task.last_activity_at,
        drift_note=_drift_note(task) if signal == "drift" else None,
        remote_ci_detail=_remote_ci_detail(task) if signal == "ci-failed" else None,
        needs_you_question=task.needs_you.question if task.needs_you is not None else None,
    )


def median_run_seconds(tasks: list[Task]) -> float | None:
    # Median run duration over DONE tasks only — the heartbeat ETA's only history.
    # PR_OPEN is excluded: poll_remote_ci keeps bumping its updated_at, which would
    # inflate the median and skew every running task's ETA.
    durations = [
        (t.updated_at - t.created_at).total_seconds()
        for t in tasks
        if t.state is TaskState.DONE and t.updated_at > t.created_at
    ]
    return median(durations) if durations else None


# The "what to do next" verb per signal, keyed by the same signal build_item sets.
# Drives the coach line — no extra ranking, just the next action for the top item.
_COACH_ACTION: dict[str, str] = {
    "interrupted": "run was interrupted — re-run it",
    "drift": "review the drift",
    "ci-failed": "CI failed — take a look",
    "needs-you": "answer what it needs you for",
    "intake": "open intake to pin the decisions",
    "review": "open the review gate",
    "ready": "ship it",
    "validating": "in flight",
    "pr-open": "in flight",
    "running": "in flight",
    "done": "done",
}


def coach_hint(items: list[InboxItem]) -> str:
    # TUI-INBOX-02/06: name the most-urgent task and its next action; quiet when empty.
    if not items:
        return "nothing needs you — go do something else"
    top = items[0]
    return f"{top.title} — {_COACH_ACTION.get(top.signal, 'open it')}"


def _is_after_hours(now: datetime) -> bool:
    # Evening/night (before 8am or 6pm onward) or any weekend day (Sat/Sun).
    return now.weekday() >= 5 or now.hour < 8 or now.hour >= 18


def after_hours_note(now: datetime | None = None) -> str | None:
    """Lever 5: a calm, private after-hours nudge — the slot-machine research finds
    heavy users work nights/weekends 96% of the time (DESIGN L12). Signal, not a
    block; never persisted, never a team metric. ``now`` is the LOCAL clock,
    injectable for tests. Returns None during work hours."""
    now = now or datetime.now()
    return "it is after hours — the queue keeps" if _is_after_hours(now) else None


# Recent-approval window for the throughput nudge (a gentle, derived signal).
_THROUGHPUT_WINDOW_SECONDS = 3600
_THROUGHPUT_THRESHOLD = 4


def recent_approval_count(events_by_task: list[list[dict]], now: datetime | None = None) -> int:
    """Lever 5: approvals (REVIEW -> READY transitions) in the last hour, summed
    across tasks. Derived from event timestamps only — never stored. Feeds the
    optional throughput nudge."""
    now = now or datetime.now(UTC)
    cutoff = now.timestamp() - _THROUGHPUT_WINDOW_SECONDS
    count = 0
    for events in events_by_task:
        for e in events:
            if (
                e.get("type") == "transition"
                and e.get("from") == TaskState.REVIEW.value
                and e.get("to") == TaskState.READY.value
            ):
                ts = e.get("ts")
                if ts and datetime.fromisoformat(str(ts)).timestamp() >= cutoff:
                    count += 1
    return count


def last_shipped_note(events_by_task: list[list[dict]], now: datetime | None = None) -> str | None:
    """Empty-state reassurance: when the most recent REVIEW -> READY transition
    landed, phrased "last shipped Xh ago" (DESIGN §5 inbox empty-state). Derived
    from event timestamps only — never stored. None when nothing has ever shipped."""
    now = now or datetime.now(UTC)
    latest: float | None = None
    for events in events_by_task:
        for e in events:
            if (
                e.get("type") == "transition"
                and e.get("from") == TaskState.REVIEW.value
                and e.get("to") == TaskState.READY.value
            ):
                ts = e.get("ts")
                if ts:
                    seconds = datetime.fromisoformat(str(ts)).timestamp()
                    if latest is None or seconds > latest:
                        latest = seconds
    if latest is None:
        return None
    ago = max(int(now.timestamp() - latest), 0)
    if ago < 60:
        return "last shipped just now"
    if ago < 3600:
        return f"last shipped {ago // 60}m ago"
    if ago < 86400:
        return f"last shipped {ago // 3600}h ago"
    return f"last shipped {ago // 86400}d ago"


def throughput_note(recent_approvals: int) -> str | None:
    """Lever 5: a gentle high-throughput nudge when approvals come fast — a real
    read takes time, so a burst is a slot-machine tell. Private, non-blocking.

    TODO(lever 5): a precise cumulative-session-duration timer ("output dips past
    3-4h") needs a private machine-local session store (DESIGN 3.6 l5 fatigue); it
    is deferred. After-hours + recent-activity stand in until that store exists."""
    if recent_approvals < _THROUGHPUT_THRESHOLD:
        return None
    return f"{recent_approvals} approved this hour — a real read takes a beat"


def sort_items(items: list[InboxItem]) -> list[InboxItem]:
    return sorted(
        items,
        key=lambda i: (i.rank, -(i.last_activity_at.timestamp() if i.last_activity_at else 0.0)),
    )
