"""Receipt digest renderer — a compact readiness checklist over a Task.

Pure Rich. The full reviewed-before-push markdown body still lives in
``kagan.core.receipt.render_receipt`` (that is what the ship view copies); this
file renders the SHORT digest line the ship panel shows. Honesty rule mirrors
core/receipt: a failing check shows ✗, unverified smoke shows ○.
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.text import Text

from kagan.format import _symbols as sym

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Task


def render_receipt_digest(task: Task) -> RenderableType:
    """One-line-per-fact digest: checks (n/n), decisions, ai-review, smoke, not-covered."""
    rows: list[RenderableType] = []

    # Passing rows carry their meaning with the ✓ glyph — not a green wash (DESIGN §5).
    checks_total = len(task.checks)
    checks_passed = sum(1 for c in task.checks if c.passed)
    if checks_total and checks_passed == checks_total:
        rows.append(Text(f"{sym.DONE} checks ({checks_passed}/{checks_total})"))
    elif checks_total:
        rows.append(Text(f"{sym.BLOCKER} checks ({checks_passed}/{checks_total})", style="blocker"))
    else:
        rows.append(Text(f"{sym.OPTIONAL} checks (none recorded)", style="secondary"))

    pinned = [d for d in task.decisions if d.answer or d.blessed]
    if pinned:
        rows.append(Text(f"{sym.DONE} decisions ({len(pinned)})"))

    adjudicated = [f for f in task.findings if f.verdict]
    if adjudicated:
        rows.append(Text(f"{sym.DONE} ai-review ({len(adjudicated)})"))

    if task.smoke_tests:
        verified = sum(1 for s in task.smoke_tests if s.verified)
        all_verified = verified == len(task.smoke_tests)
        glyph = sym.DONE if all_verified else sym.OPTIONAL
        style = "" if all_verified else "secondary"
        rows.append(Text(f"{glyph} smoke ({verified}/{len(task.smoke_tests)})", style=style))

    if task.not_covered:
        covered = ", ".join(n for n in task.not_covered)
        rows.append(Text(f"{sym.NOTE} not covered: {covered}", style="note"))

    return Group(*rows)


__all__ = ["render_receipt_digest"]
