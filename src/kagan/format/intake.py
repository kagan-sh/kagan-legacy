"""Intake view renderer — the decision walk.

Pure Rich. The session passes a fresh Task plus the precomputed ``can_run``
bool (from ``core.can_run``) so this file never calls Harness. Ports the
IntakeScreen render: understanding block, blocking + optional decisions, a
resolved section, the scope footer, and the run lock phrasing.

NOTE (Rule 7): DESIGN renames ``Decision.blessed`` → ``approved`` with an
explicit reject path. Core still has ``answer`` + ``blessed`` only, so this
renderer reads ``blessed``/``answer`` (today's model). The rename is core work
(Phase 1/3) — flagged, not blended.
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.core.api import humanize_task_state
from kagan.format import _symbols as sym
from kagan.format._risk import risk_label, risk_style

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Decision, Task


def _option_chips(options: list[str]) -> str:
    return " · ".join(opt for opt in options)


def _is_blocking(d: Decision) -> bool:
    return d.severity == "blocking"


def _is_resolved(d: Decision) -> bool:
    return d.answer is not None or d.blessed


def _decision_line(d: Decision, *, focused: bool) -> Text:
    glyph = sym.NEEDS_YOU if _is_blocking(d) else sym.OPTIONAL
    prefix = f"{sym.CURSOR} " if focused else "  "
    line = Text(prefix, style="bold" if focused else "")
    line.append(f"{glyph} ", style="needs-you" if _is_blocking(d) else "secondary")
    line.append(d.question, style="bold" if focused else "")
    if d.options:
        line.append(f"   {_option_chips(d.options)}", style="secondary")
    if not _is_blocking(d):
        line.append("   (optional)", style="secondary")
    return line


def _resolved_line(d: Decision) -> Text:
    line = Text(f"{sym.DONE} ", style="done")
    line.append(d.question)
    answer = d.answer or ""
    annotation = "(accepted as-is)" if d.blessed and not answer else ""
    if answer:
        line.append(f" → {answer}")
        if not d.blessed:
            annotation = "(rejected — overridden)"
    if annotation:
        line.append(f" {annotation}", style="secondary")
    return line


def render_intake(
    task: Task, *, can_run: bool, risk: str | None = None, cursor: int = 0
) -> RenderableType:
    """The intake content panel (the key-bar is printed by the session, not here)."""
    header = Text(f"{task.title} · {humanize_task_state(task.state)}", style="bold")
    if risk:
        header.append(f"   {risk_label(risk)}", style=risk_style(risk))

    blocks: list[RenderableType] = [header, Text("")]

    blocks.append(Text("What the agent understood", style="bold"))
    if task.understanding:
        blocks.append(Text(task.understanding))
    else:
        blocks.append(Text("no understanding recorded", style="secondary"))
    blocks.append(Text(""))

    open_decisions = [d for d in task.decisions if not _is_resolved(d)]
    blocking = [d for d in open_decisions if _is_blocking(d)]
    optional = [d for d in open_decisions if not _is_blocking(d)]
    resolved = [d for d in task.decisions if _is_resolved(d)]

    if open_decisions:
        blocks.append(
            Text("Answer before it runs   ·   Approve = take assumption · Reject = override")
        )
        for focus_index, d in enumerate(blocking):
            blocks.append(_decision_line(d, focused=focus_index == cursor))
        for d in optional:
            blocks.append(_decision_line(d, focused=False))
        blocks.append(Text(""))

    if resolved:
        blocks.append(Text("Resolved", style="secondary"))
        for d in resolved:
            blocks.append(_resolved_line(d))
        blocks.append(Text(""))

    if task.scope:
        scope = "  ".join(s for s in task.scope)
        blocks.append(Text(f"Scope  {scope}", style="secondary"))

    blocks.append(Rule(style="secondary"))
    if can_run:
        blocks.append(Text("Run unlocked — r to start", style="done"))
    else:
        blocks.append(
            Text(f"Run locked: {len(blocking)} blocking decision(s) open", style="secondary")
        )
    return Group(*blocks)


__all__ = ["render_intake"]
