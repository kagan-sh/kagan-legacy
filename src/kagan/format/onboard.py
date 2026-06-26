"""Onboarding view renderers for `kagan init` (Phase 14).

Pure Rich, no core or prompt-toolkit imports beyond the ManifestDraft dataclass.
Mirrors `format/intake.py`: a focused walk where one proposed check is read at a
time, dangerous shapes carry the note glyph, and provenance (lifted vs invented)
is shown so the human knows what they're trusting.
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.core.onboard import flag_dangerous
from kagan.format import _symbols as sym

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.models import CheckResult
    from kagan.core.onboard import ManifestDraft, ProposedCheck


def _provenance_note(check: ProposedCheck) -> str:
    if check.provenance in ("invented", "edited"):
        return f"{check.provenance} — not declared in the repo"
    src = f" ({check.source})" if check.source else ""
    return f"lifted from {check.provenance}{src}"


def render_check_walk(check: ProposedCheck, index: int, total: int) -> RenderableType:
    """One check in the approve/drop/edit walk — the literal command the human must
    read before it ever runs, plus its provenance and any danger flag."""
    blocks: list[RenderableType] = [
        Text(f"Check {index + 1} of {total}   ·   {check.name}", style="bold"),
        Text(""),
        Text(f"    {check.command}"),
        Text(""),
        Text(f"  {_provenance_note(check)}", style="secondary"),
    ]
    danger = flag_dangerous(check.command)
    if danger:
        note = Text(f"  {sym.NOTE} {danger} — approve only if you mean it.", style="blocker")
        blocks.append(note)
    blocks.append(Rule(style="secondary"))
    return Group(*blocks)


def render_draft_summary(draft: ManifestDraft) -> RenderableType:
    """The overview the agent proposed, before the walk — nothing has run yet."""
    blocks: list[RenderableType] = [
        Text("Draft manifest", style="bold"),
        Text("the agent read your repo — read each command before you approve", style="secondary"),
        Text(""),
    ]
    if draft.checks:
        blocks.append(Text("Checks (run on every review)", style="bold"))
        for c in draft.checks:
            glyph = sym.NOTE if flag_dangerous(c.command) else sym.DONE
            style = "blocker" if flag_dangerous(c.command) else "done"
            line = Text(f"  {glyph} ", style=style)
            line.append(f"{c.name}  ", style="bold")
            line.append(c.command, style="secondary")
            blocks.append(line)
        blocks.append(Text(""))
    if draft.risk_tiers:
        tiers = "  ·  ".join(f"{tier} {globs}" for tier, globs in draft.risk_tiers.items())
        blocks.append(Text(f"Risk    {tiers}", style="secondary"))
    review = f"builder {draft.builder or 'CLI default'} · reviewer {draft.reviewer or 'DISABLED'}"
    blocks.append(Text(f"Review  {review}", style="secondary"))
    return Group(*blocks)


def render_verify_results(results: list[CheckResult]) -> RenderableType:
    """Pass/fail of the human-approved checks, run once. A failed check is the phantom
    caught here rather than silently mid-review later."""
    blocks: list[RenderableType] = [Text("Verifying approved checks", style="bold"), Text("")]
    for r in results:
        glyph = sym.DONE if r.passed else sym.BLOCKER
        style = "done" if r.passed else "blocker"
        line = Text(f"  {glyph} ", style=style)
        line.append(f"{r.name}", style="bold")
        if not r.passed:
            first = r.detail.splitlines()[0] if r.detail else "failed"
            line.append(f"   {first}", style="secondary")
        blocks.append(line)
    return Group(*blocks)


__all__ = ["render_check_walk", "render_draft_summary", "render_verify_results"]
