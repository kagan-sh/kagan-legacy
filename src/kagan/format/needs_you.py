"""needs-you view renderer — the mid-run question that gates a running agent.

Pure Rich. The standard chrome the other views have (the ``●`` needs-you glyph, the
shared header with risk context) — the highest-stakes "unblock the agent" decision
had the least guidance before Phase 12c. The footer (enter/esc/^O) is the session's,
rendered via ``format.help.render_footer``; this file renders the question body.
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.text import Text

from kagan.format import _symbols as sym
from kagan.format._risk import risk_label, risk_style

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Task


def render_needs_you(task: Task) -> RenderableType:
    """Header (title + risk) + the ``●`` needs-you question and its context."""
    ny = task.needs_you
    if ny is None:  # the session only routes here with a live question; guard anyway
        return Text("Nothing is waiting on you.", style="secondary")

    header = Text(task.title, style="bold")
    if task.risk:
        header.append(f"   {risk_label(task.risk)}", style=risk_style(task.risk))

    question = Text(f"{sym.NEEDS_YOU} ", style="needs-you")
    question.append(ny.question, style="bold")

    blocks: list[RenderableType] = [
        header,
        Text(""),
        Text(f"waiting · {ny.reason}", style="secondary"),
        question,
    ]
    if ny.context:
        blocks.append(Text(ny.context, style="secondary"))
    return Group(*blocks)


__all__ = ["render_needs_you"]
