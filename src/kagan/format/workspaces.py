"""Workspaces view renderer — the live map of active worktrees.

Pure Rich (the log file read lives in the session, not here). Active =
RUNNING / VALIDATING / PR_OPEN. Health is derived from a leased port (a leased
port means the service started — the ledger is the source, there is no process
supervisor); the renderer never probes a PID.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.core.api import TaskState
from kagan.format._layout import label_value_rows

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Task

_ACTIVE = (TaskState.RUNNING, TaskState.VALIDATING, TaskState.PR_OPEN)

# View-specific status copy (DESIGN section 5 / Appendix A ⑪) — not humanize_task_state.
_STATUS_WORD: dict[TaskState, str] = {
    TaskState.RUNNING: "working",
    TaskState.VALIDATING: "reviewing…",
    TaskState.PR_OPEN: "PR open · watching CI…",
}


def _elapsed(created_at: datetime, now: datetime) -> str:
    seconds = max(int((now - created_at).total_seconds()), 0)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def _active(tasks: list[Task]) -> list[Task]:
    return [t for t in tasks if t.state in _ACTIVE]


def render_workspaces(
    tasks: list[Task], *, repo_name: str, now: datetime | None = None
) -> RenderableType:
    """Header + one row per active task; calm one-liner when nothing is running."""
    now = now or datetime.now(UTC)
    active = _active(tasks)
    working = sum(1 for t in tasks if t.state in (TaskState.RUNNING, TaskState.VALIDATING))

    header = Text()
    header.append(f"kagan · {repo_name}", style="bold")
    header.append(f"   {working} agents working", style="secondary")

    if not active:
        return Group(header, Text(""), Text("No agents are working right now.", style="secondary"))

    # Two display-width-aligned columns (title | status·ports·started) — no fixed gaps.
    rows = label_value_rows([(t.title, _row_meta(t, now)) for t in active], label_style="bold")
    return Group(header, Text(""), Rule(style="secondary"), rows)


def _row_meta(task: Task, now: datetime) -> str:
    status = _STATUS_WORD.get(task.state, task.state.value)
    bits = [status]
    if task.ports:
        bits.append(" ".join(f"{name} :{port}" for name, port in task.ports.items()))
    bits.append(f"started {_elapsed(task.created_at, now)} ago")
    return "  ·  ".join(bits)


# The log is a dim teaser, not a 200-line dump: a raw dump pushes the take-over line
# off-screen. The full log stays a separate step (the take-over cd). DESIGN §5 density.
_LOG_TEASER_LINES = 4


def render_workspace_detail(
    task: Task, *, log_tail: str | None = None, cooldown_note: str | None = None
) -> RenderableType:
    """Per-service status, a dim log teaser, and the take-over cd hand-off."""
    now = datetime.now(UTC)
    blocks: list[RenderableType] = [Text(task.title, style="bold")]

    if task.ports:
        elapsed = _elapsed(task.created_at, now)
        # Health is plain dim text, not a palette glyph — ● stays needs-you only (DESIGN §5).
        svc_rows = [(name, f":{port}  healthy {elapsed}") for name, port in task.ports.items()]
        blocks.append(label_value_rows(svc_rows, label_style=""))
    else:
        blocks.append(Text("no services", style="secondary"))

    if log_tail:
        blocks.append(Text("log", style="secondary"))
        blocks.extend(_log_teaser(log_tail))

    if task.worktree_path is not None:
        handoff = Text("take over →  ", style="secondary")
        handoff.append(f"cd {task.worktree_path}")
        handoff.append(f"    (kagan takeover {task.title})", style="secondary")
        blocks.append(handoff)

    if cooldown_note:
        blocks.append(Text(cooldown_note, style="secondary"))

    return Group(*blocks)


def _log_teaser(log_tail: str) -> list[RenderableType]:
    """The last few log lines as a dim teaser — raw output, never Rich markup
    (LogView parity), and capped so the take-over line never scrolls off-screen."""
    lines = log_tail.splitlines()[-_LOG_TEASER_LINES:]
    # ``no_wrap`` + ellipsis truncation keeps each line one row at any width, so the
    # teaser height is bounded — width-aware, not a hardcoded character count.
    return [Text(line, style="secondary", no_wrap=True, overflow="ellipsis") for line in lines]


__all__ = ["render_workspace_detail", "render_workspaces"]
