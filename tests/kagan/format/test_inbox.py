"""Inbox renderer — replaces the OptionList prompt-text assertions in the TUI."""

from datetime import UTC, datetime

from kagan.core.enums import TaskState
from kagan.core.inbox import build_item, sort_items
from kagan.core.models import NeedsYou, Task
from kagan.format import inbox
from tests.kagan.format._render import to_str


def _task(**kw) -> Task:
    kw.setdefault("last_activity_at", datetime.now(UTC))
    return Task(id=kw.pop("id"), title=kw.pop("title", "t"), **kw)


def _items(tasks: list[Task]):
    return sort_items([build_item(t) for t in tasks])


def test_renders_a_section_header_with_count_per_nonempty_state():
    items = _items(
        [
            _task(id="r1", title="run-1", state=TaskState.REVIEW),
            _task(id="r2", title="run-2", state=TaskState.REVIEW),
            _task(id="d1", title="ready-1", state=TaskState.READY),
        ]
    )
    out = to_str(inbox.render_inbox(items, {}, "myrepo", coach="c"))
    assert "review ──── 2" in out
    assert "ready · your push ──── 1" in out


def test_running_row_shows_a_liveness_heartbeat():
    items = _items([_task(id="t", title="task", state=TaskState.RUNNING)])
    out = to_str(inbox.render_inbox(items, {}, "myrepo", coach="c"))
    assert "♥ alive" in out


def test_drift_row_shows_its_drift_note():
    from kagan.core.models import Finding

    task = _task(
        id="t",
        title="oauth",
        state=TaskState.RUNNING,
        drift=True,
        findings=[
            Finding(id="drift-0", severity="blocking", location="x.py", message="edited foo")
        ],
    )
    out = to_str(inbox.render_inbox(_items([task]), {}, "myrepo", coach="c"))
    assert "edited foo" in out


def test_ci_failed_row_shows_remote_ci_detail():
    from kagan.core.models import CheckResult

    task = _task(
        id="t",
        title="task",
        state=TaskState.RUNNING,
        remote_ci_status="fail",
        checks=[CheckResult(name="tests", passed=False)],
    )
    out = to_str(inbox.render_inbox(_items([task]), {}, "myrepo", coach="c"))
    assert "remote CI failed: tests" in out


def test_needs_you_row_shows_the_question_inline():
    task = _task(
        id="t",
        title="bill",
        state=TaskState.RUNNING,
        needs_you=NeedsYou(reason="ambiguous", question="which rounding?"),
    )
    out = to_str(inbox.render_inbox(_items([task]), {}, "myrepo", coach="c"))
    assert "which rounding?" in out


def test_inbox_empty_state_shows_new_task_cta():
    out = to_str(inbox.render_inbox([], {}, "myrepo", coach="c", standing="2 agents working"))
    assert "Nothing needs you right now." in out
    assert "2 agents working" in out
    assert "all quiet" in out
    assert "█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █" in out
    assert "ᘚᘛ kagan" not in out


def test_compact_empty_state_uses_small_brand_and_omits_large_logo():
    out = to_str(
        inbox.render_inbox([], {}, "myrepo", coach="c", standing="0 agents working", compact=True)
    )

    assert "ᘚᘛ kagan · myrepo" in out
    assert "█▄▀" not in out


def test_populated_inbox_uses_compact_branding():
    task = _task(id="t", title="task", state=TaskState.REVIEW)
    out = to_str(inbox.render_inbox(_items([task]), {"review": 1}, "myrepo", coach="c"))

    assert "ᘚᘛ kagan · myrepo" in out
    assert "█▄▀" not in out


def test_brand_does_not_repeat_when_repository_is_named_kagan():
    task = _task(id="t", title="task", state=TaskState.REVIEW)
    out = to_str(inbox.render_inbox(_items([task]), {"review": 1}, "kagan", coach="c"))

    assert "ᘚᘛ kagan · kagan" not in out
    assert out.count("kagan") == 1


def test_header_shows_repo_and_live_counts():
    counts = {"drift": 2, "needs_you": 0, "review": 3, "ready": 0, "live": 0}
    out = to_str(inbox.render_header(counts, "myrepo"))
    assert "myrepo" in out
    assert "2 drift" in out
    assert "3 review" in out
    assert "ready" not in out  # zero buckets are dropped


def test_coach_line_is_passed_through_not_recomputed():
    out = to_str(inbox.render_coach("export-csv — ship it"))
    assert "export-csv — ship it" in out


def test_titles_are_markup_escaped():
    # The TUI did not escape; a title with Rich markup must render literally.
    task = _task(id="t", title="add [bold]injection[/]", state=TaskState.REVIEW)
    out = to_str(inbox.render_inbox(_items([task]), {}, "repo", coach="c"))
    assert "[bold]injection[/]" in out


def test_row_action_is_on_its_own_indented_line_not_the_meta_tail():
    # Phase 12c inbox §2: the next action ("enter → review") moves to its own indented
    # dim line below the row — it must NOT be crammed into the inline meta tail.
    items = _items([_task(id="r", title="refactor-parser", state=TaskState.REVIEW)])
    out = to_str(inbox.render_inbox(items, {}, "repo", coach="c"))
    lines = out.splitlines()
    row_line = next(line for line in lines if "refactor-parser" in line)
    assert "enter → review" not in row_line  # the action is NOT on the packed row line
    action_line = next(line for line in lines if "enter → review" in line)
    assert action_line.startswith("     ")  # indented under the row


def test_row_meta_caps_to_one_signal_specific_detail():
    # Phase 12c inbox §2: a running row's inline tail carries ONE detail (the
    # heartbeat), not a packed chain of eta · resume · since-you-left + action.
    items = _items([_task(id="t", title="task", state=TaskState.RUNNING, resume_point="step 3")])
    out = to_str(inbox.render_inbox(items, {}, "repo", coach="c"))
    row_line = next(line for line in out.splitlines() if "task" in line and "♥ alive" in line)
    assert row_line.count(" · ") <= 1  # at most one inline detail separator


def test_empty_state_shows_last_shipped_and_no_poll_timer():
    # Phase 12c inbox §3: the empty-state standing line carries "last shipped" but
    # NEVER a "next check ~5m" poll clause (invoke-and-exit, no timer).
    out = to_str(
        inbox.render_inbox(
            [], {}, "myrepo", coach="c", standing="2 agents working · last shipped 1h ago"
        )
    )
    assert "last shipped 1h ago" in out
    assert "next check" not in out


def test_empty_state_does_not_duplicate_the_session_footer():
    # The responsive shell adds the one registry-backed footer; the empty renderer
    # must not embed a second stale copy inside its body.
    out = to_str(inbox.render_inbox([], {}, "myrepo", coach="c"))
    assert "n new" not in out
    assert "? help" not in out


def test_selectable_rows_match_render_order_no_resort():
    items = _items(
        [
            _task(id="a", title="a", state=TaskState.REVIEW),
            _task(id="b", title="b", state=TaskState.READY),
        ]
    )
    rows = inbox.selectable_rows(items)
    # review outranks ready in precedence — order must follow it, not re-sort.
    assert [r.task_id for r in rows] == ["a", "b"]
