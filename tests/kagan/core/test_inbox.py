from datetime import UTC, datetime, timedelta

from kagan.core.enums import TaskState
from kagan.core.inbox import (
    after_hours_note,
    build_item,
    coach_hint,
    recent_approval_count,
    sort_items,
    throughput_note,
)
from kagan.core.models import NeedsYou, Task


def _task(**kw) -> Task:
    kw.setdefault("last_activity_at", datetime.now(UTC))
    return Task(id=kw.pop("id"), title=kw.pop("title", "t"), **kw)


def test_precedence_order():
    # TUI-INBOX-01: who-needs-a-human-most sorts first, regardless of state order.
    tasks = [
        _task(id="running", state=TaskState.RUNNING),
        _task(id="intake", state=TaskState.INTAKE),
        _task(
            id="needs-you",
            state=TaskState.RUNNING,
            needs_you=NeedsYou(reason="ambiguous", question="which API?"),
        ),
        _task(id="drift", state=TaskState.RUNNING, drift=True),
    ]
    items = sort_items([build_item(t) for t in tasks])
    assert [i.task_id for i in items] == ["drift", "needs-you", "intake", "running"]


def test_needs_you_is_presence_not_bool():
    # TUI-INBOX-01: needs_you is NeedsYou | None — a populated object means "needs you".
    item = build_item(
        _task(id="t", state=TaskState.RUNNING, needs_you=NeedsYou(reason="x", question="y"))
    )
    assert item.signal == "needs-you"
    assert build_item(_task(id="t2", state=TaskState.RUNNING)).signal == "running"


def test_ci_failed_derived_from_remote_status():
    # TUI-INBOX-01: ci-failed is derived from remote_ci_status, not stored as a flag.
    item = build_item(_task(id="t", state=TaskState.RUNNING, remote_ci_status="fail"))
    assert item.signal == "ci-failed"
    assert (
        build_item(_task(id="ok", state=TaskState.RUNNING, remote_ci_status="pass")).signal
        == "running"
    )


def test_running_collapses_to_eta():
    # TUI-INBOX-03: a running task collapses to a single heartbeat+ETA cell derived
    # from the median finished-task duration minus elapsed (430s median, ~100s in
    # => ~330s remaining = ~5m; offset from a minute boundary so sub-second drift
    # can't flip the floor).
    started = datetime.now(UTC) - timedelta(seconds=100)
    item = build_item(
        _task(id="t", state=TaskState.RUNNING, created_at=started, last_activity_at=started),
        median_seconds=430.0,
    )
    assert item.eta == "~5m"


def test_since_you_left_names_the_kinds_of_change_not_just_a_count():
    # TUI-INBOX-04: the delta names WHAT changed (findings/decisions/progress), not a
    # bare count. Fails if it reverts to "N updates since you left".
    item = build_item(
        _task(
            id="t",
            state=TaskState.RUNNING,
            last_viewed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        events=[
            {"type": "viewed", "ts": "2026-01-01T00:00:00+00:00"},
            {"type": "decision_added", "ts": "2026-06-01T00:00:00+00:00"},
            {"type": "finding_added", "ts": "2026-06-02T00:00:00+00:00"},
            {"type": "finding_added", "ts": "2026-06-03T00:00:00+00:00"},
            {"type": "transition", "ts": "2026-06-04T00:00:00+00:00"},
        ],
    )
    assert item.since_you_left is not None
    assert "2 findings" in item.since_you_left  # the two finding events, named
    assert "1 decision" in item.since_you_left  # the one decision event, named
    assert "since you left" in item.since_you_left


def test_since_you_left_only_counts_events_after_last_viewed():
    # TUI-INBOX-04: events at or before the view boundary are not "since you left".
    # Fails if the cutoff is dropped and pre-view events leak into the delta.
    item = build_item(
        _task(id="t", state=TaskState.RUNNING, last_viewed_at=datetime(2026, 6, 1, tzinfo=UTC)),
        events=[
            {"type": "finding_added", "ts": "2026-05-01T00:00:00+00:00"},  # before view
            {"type": "finding_added", "ts": "2026-06-02T00:00:00+00:00"},  # after view
        ],
    )
    assert item.since_you_left is not None
    assert "1 finding" in item.since_you_left


def test_coach_hint_names_the_top_task_and_its_next_action():
    # TUI-INBOX-06: the coach line names the most-urgent task AND what to do with it,
    # so the next decision is legible at a glance. Fails if it drops the title or the
    # signal-specific verb (e.g. answers a drift task as if it were intake).
    items = sort_items(
        [
            build_item(
                _task(
                    id="ny",
                    title="Pick a library",
                    state=TaskState.RUNNING,
                    needs_you=NeedsYou(reason="dep", question="which lib?"),
                )
            ),
            build_item(_task(id="run", title="Codegen", state=TaskState.RUNNING)),
        ]
    )
    hint = coach_hint(items)
    assert "Pick a library" in hint
    assert "needs you" in hint.lower()


def test_coach_hint_intake_says_open_to_pin_decisions():
    # TUI-INBOX-06: an intake task's coach action is distinct from needs-you.
    items = [build_item(_task(id="i", title="New feature", state=TaskState.INTAKE))]
    hint = coach_hint(items)
    assert "New feature" in hint
    assert "intake" in hint.lower()


def test_coach_hint_quiet_when_nothing_needs_you():
    # TUI-INBOX-02: an empty / all-quiet inbox tells the operator to leave.
    assert coach_hint([]) == "nothing needs you — go do something else"


def test_after_hours_note_appears_evenings_and_weekends_not_work_hours():
    # Lever 5: the private after-hours nudge fires on an evening/night/weekend clock
    # and stays silent during weekday work hours. The clock is injected so the test
    # encodes WHY it fires (off-hours == the slot-machine tell), not the wall time.
    # 2026-06-24 is a Wednesday; 2026-06-27 is a Saturday.
    weekday_evening = datetime(2026, 6, 24, 21, 0)  # 9pm Wed
    weekday_morning = datetime(2026, 6, 24, 7, 0)  # 7am Wed (before 8)
    saturday_noon = datetime(2026, 6, 27, 12, 0)  # weekend, any hour
    weekday_midday = datetime(2026, 6, 24, 11, 0)  # 11am Wed — work hours

    assert after_hours_note(weekday_evening) == "it is after hours — the queue keeps"
    assert after_hours_note(weekday_morning) is not None
    assert after_hours_note(saturday_noon) is not None
    assert after_hours_note(weekday_midday) is None


def test_throughput_note_only_fires_on_a_burst_of_recent_approvals():
    # Lever 5: a gentle nudge when approvals come fast (a real read takes time). The
    # count is derived from REVIEW -> READY transition timestamps within the last
    # hour; older approvals and slower paces stay silent.
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)

    def approval(minutes_ago: float) -> dict:
        ts = (now - timedelta(minutes=minutes_ago)).isoformat()
        return {"type": "transition", "from": "review", "to": "ready", "ts": ts}

    recent = [[approval(m) for m in (1, 5, 10, 20)]]  # 4 within the hour
    assert recent_approval_count(recent, now=now) == 4
    assert throughput_note(recent_approval_count(recent, now=now)) is not None

    stale = [[approval(90), approval(120)]]  # both older than an hour
    assert recent_approval_count(stale, now=now) == 0
    assert throughput_note(0) is None


def test_last_shipped_note_uses_the_most_recent_ship_and_is_none_when_never():
    # Phase 12c inbox §3: the empty-state "last shipped" clause is the most recent
    # REVIEW -> READY transition across all tasks, humanized; None when none exists.
    from kagan.core.inbox import last_shipped_note

    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)

    def ship(hours_ago: float) -> dict:
        ts = (now - timedelta(hours=hours_ago)).isoformat()
        return {"type": "transition", "from": "review", "to": "ready", "ts": ts}

    # two tasks shipped; the note reports the freshest (1h), not the older (5h).
    events = [[ship(5)], [ship(1)]]
    assert last_shipped_note(events, now=now) == "last shipped 1h ago"

    # nothing ever shipped -> None (no fabricated clause)
    assert last_shipped_note([[{"type": "created", "ts": now.isoformat()}]], now=now) is None
    assert last_shipped_note([], now=now) is None


def test_no_delta_when_never_viewed():
    # TUI-INBOX-04: never-viewed task has no "since you left" boundary, so no delta.
    item = build_item(
        _task(id="t", state=TaskState.RUNNING),
        events=[{"type": "decision", "ts": "2026-06-01T00:00:00+00:00"}],
    )
    assert item.since_you_left is None
