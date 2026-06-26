"""Workspaces renderer — migrates the four behavioural assertions from the TUI."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from kagan.core.enums import TaskState
from kagan.core.models import Task
from kagan.format import workspaces
from tests.kagan.format._render import to_str


def _task(**kw) -> Task:
    return Task(id=kw.pop("id", "t"), title=kw.pop("title", "task"), **kw)


def test_lists_active_task_with_branch_and_ports():
    now = datetime.now(UTC)
    task = _task(
        title="fix-rate-limit",
        state=TaskState.RUNNING,
        branch="kagan/t-1",
        ports={"api": 51802},
        created_at=now - timedelta(minutes=4),
    )
    out = to_str(workspaces.render_workspaces([task], repo_name="myrepo", now=now))
    assert "fix-rate-limit" in out
    assert "working" in out
    assert "api :51802" in out
    assert "started 4m ago" in out
    assert "1 agents working" in out


def test_pr_open_task_is_active_but_not_counted_as_working():
    now = datetime.now(UTC)
    task = _task(title="export-csv", state=TaskState.PR_OPEN, created_at=now)
    out = to_str(workspaces.render_workspaces([task], repo_name="r", now=now))
    assert "export-csv" in out
    assert "0 agents working" in out  # pr_open watches CI, not "working"


def test_empty_active_list_is_calm_not_a_traceback():
    out = to_str(workspaces.render_workspaces([], repo_name="r"))
    assert "No agents are working right now." in out


def test_detail_health_is_plain_text_not_the_needs_you_dot():
    # §3.1: service health must NOT reuse the reserved ● needs-you glyph — plain text.
    task = _task(
        title="t",
        state=TaskState.RUNNING,
        ports={"api": 51802},
        worktree_path=Path("/wt/task-bb34"),
    )
    out = to_str(workspaces.render_workspace_detail(task, log_tail="worker picked job 9f2"))
    assert "● api" not in out  # the needs-you dot keeps one meaning
    assert "api" in out
    assert "healthy" in out
    assert "worker picked job 9f2" in out
    assert "cd /wt/task-bb34" in out


def test_detail_omits_takeover_when_no_worktree():
    task = _task(title="t", state=TaskState.RUNNING, ports={"api": 1})
    out = to_str(workspaces.render_workspace_detail(task))
    assert "take over" not in out


def test_log_tail_raw_output_is_not_interpreted_as_markup():
    task = _task(title="t", state=TaskState.RUNNING, ports={"api": 1}, worktree_path=Path("/wt"))
    out = to_str(workspaces.render_workspace_detail(task, log_tail="[red]not styled[/]"))
    assert "[red]not styled[/]" in out


def test_log_is_truncated_so_takeover_line_never_scrolls_off():
    # Phase 12c workspaces §3: a long log is a dim teaser (last few lines), not a
    # 200-line dump that pushes the take-over hand-off off-screen.
    task = _task(title="t", state=TaskState.RUNNING, ports={"api": 1}, worktree_path=Path("/wt"))
    log = "\n".join(f"line {i}" for i in range(40))
    out = to_str(workspaces.render_workspace_detail(task, log_tail=log))
    assert "line 39" in out  # the freshest lines are kept
    assert "line 0" not in out  # the oldest are dropped (teaser, not full dump)
    assert "cd /wt" in out  # the take-over line survives below the teaser


def test_cooldown_note_renders_when_threaded():
    # Phase 12c workspaces §1: render_workspace_detail surfaces the cooldown nudge the
    # caller now threads (the screen's attention-thesis contribution, previously dropped).
    task = _task(title="t", state=TaskState.REVIEW, ports={"api": 1}, worktree_path=Path("/wt"))
    out = to_str(
        workspaces.render_workspace_detail(
            task, cooldown_note="export-csv just landed — give it a read (unlocks 0:20)."
        )
    )
    assert "give it a read (unlocks 0:20)." in out
