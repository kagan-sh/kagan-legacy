"""Receipt digest renderer — a compact readiness checklist over a Task.

Pure Rich. The full reviewed-before-push markdown body still lives in
``kagan.core.receipt.render_receipt`` (that is what the ship view copies); this
file renders the SHORT digest line the ship panel shows. Honesty rule mirrors
core/receipt: a failing check shows ✗, unverified smoke shows ○.
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.text import Text

from kagan.core.ceremony import DISABLED, FAILED, RAN, task_validator_status
from kagan.format import _symbols as sym
from kagan.format.checks import receipt_check_row

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Task


def _ai_review_row(task: Task) -> Text | None:
    """The ai-review digest line, derived from the EFFECTIVE validator outcome (B20).

    Counts ONLY real ai-review/validator findings — never a send-back or any other
    adjudicated finding (the old line bucketed every verdict as ai-review). When the
    validator did not run, it says so honestly instead of implying "an AI reviewed this"."""
    status = task_validator_status(task)
    if status == RAN:
        found = [f for f in task.findings if f.source == "ai-review"]
        # F23: an agreed blocking finding ships unfixed — never a clean green check over it.
        unfixed = [f for f in found if f.severity == "blocking" and f.verdict == "agree"]
        if unfixed:
            return Text(
                f"{sym.NOTE} ai-review ({len(found)} · {len(unfixed)} shipped unfixed)",
                style="note",
            )
        label = f"ai-review ({len(found)})" if found else "ai-review (clean)"
        return Text(f"{sym.DONE} {label}")
    if status == DISABLED:
        return Text(f"{sym.OPTIONAL} ai-review (none — validator disabled)", style="secondary")
    if status == FAILED:
        return Text(f"{sym.OPTIONAL} ai-review (none — validator unavailable)", style="secondary")
    return None  # n/a (low risk) or pending — no ai-review line


def render_receipt_digest(task: Task) -> RenderableType:
    """One-line-per-fact digest: checks (n/n), decisions, ai-review, smoke, not-covered."""
    rows: list[RenderableType] = []

    rows.append(receipt_check_row(task.checks))

    pinned = [d for d in task.decisions if d.answer or d.approved]
    if pinned:
        rows.append(Text(f"{sym.DONE} decisions ({len(pinned)})"))

    ai_row = _ai_review_row(task)
    if ai_row is not None:
        rows.append(ai_row)

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
