"""Reviewed-before-push receipt — a copyable light decision record (ADR spine).

Lever 6 / DESIGN §3.7: the receipt is the cross-team trust artifact written into
`.kagan/reviews/` on approve. It is framed as a light ADR — Context / Decision /
Consequences / Status — carries finding provenance (source/confidence/status)
and the author's comprehension note, and always renders a Pushback section so
"no dissent" is greppable, not silent.

It states honestly what was NOT verified (TUI/CLI-RECEIPT-01/02): failing checks
show as fail, unverified smoke tests show unchecked, unresolved decisions and
unadjudicated findings are omitted, and the empty-placeholder per section keeps
"absent" from reading as "done". Plain string assembly — no templating engine.
"""

from typing import TYPE_CHECKING

from kagan.core.ceremony import banner_suffix, gates_clause, task_validator_status
from kagan.core.comprehension import prompts_for_task
from kagan.core.hygiene import display_location, distill_check_detail
from kagan.core.tasks import shipped_blockers

if TYPE_CHECKING:
    from kagan.core.models import CheckResult, Decision, Finding, SmokeTest, Task

# ADR Status spine: task state maps to a decision-record lifecycle (§3.7).
_STATUS: dict[str, str] = {
    "review": "Proposed",
    "ready": "Accepted",
    "pr_open": "Accepted",
    "done": "Accepted",
}


def _check(c: CheckResult) -> str:
    line = f"- [{'pass' if c.passed else 'fail'}] {c.name}"
    detail = distill_check_detail(c.detail)
    return f"{line}: {detail}" if detail else line


def _decision(d: Decision) -> str:
    # Record WHAT was decided (the accepted assumption or the override), never the bare
    # verb — the receipt is the cross-team trust artifact (lever 6, B16). The accept vs
    # override provenance rides alongside.
    answer = d.answer or "(no answer recorded)"
    how = "accepted" if d.approved else "overrode"
    return f"- {d.question} -> **{answer}** ({how}, severity: {d.severity})"


def _provenance(f: Finding) -> str:
    """The verifier's own provenance, shown literally so low confidence isn't hidden."""
    bits = [f"source: {f.source}"]
    if f.confidence is not None:
        bits.append(f"confidence {f.confidence}/10")
    if f.status:
        bits.append(f.status)
    return f" [{', '.join(bits)}]"


def _finding(f: Finding) -> str:
    line = (
        f"- `{display_location(f.location)}`: "
        f"{f.message}{_provenance(f)} -- verdict: **{f.verdict}**"
    )
    return f"{line} (reply: {f.reply})" if f.reply else line


def _pushback(f: Finding) -> str:
    # A disagree always carries a reply (TUI-GATE-05), so the one-line reason is present.
    return f"- `{display_location(f.location)}`: {f.message}{_provenance(f)} -- reason: {f.reply}"


def _smoke(s: SmokeTest) -> str:
    line = f"- [{'x' if s.verified else ' '}] {s.behaviour}"
    return f"{line} (service: {s.service})" if s.service else line


def _section(title: str, lines: list[str], empty: str) -> list[str]:
    return ["", f"## {title}", *(lines or [empty])]


def _ceremony(task: Task) -> str:
    # The banner states the EFFECTIVE ceremony, not the tier label (WS1): if no reviewer
    # was configured the validator did not run, and the banner says so — disabled (never
    # configured) and unavailable (ran and failed) are distinguished (B18/DESIGN-LVR2-06).
    status = task_validator_status(task)
    return (
        f"reviewed at: {task.risk}-risk — {gates_clause(task.risk, status)}{banner_suffix(status)}"
    )


def _comprehension_lines(task: Task) -> list[str]:
    # Lever 1: the author's own-words rationale travels in the receipt as Q/A pairs,
    # in prompt order for the task's risk tier. Stay honest (TUI/CLI-RECEIPT) — an
    # absent answer set is not dressed up as done.
    lines: list[str] = []
    for key, question in prompts_for_task(task):
        answer = task.comprehension.get(key, "").strip()
        if answer:
            lines.append(f"**{question}**")
            lines.append(answer)
    return lines


def _not_covered_lines(task: Task) -> list[str]:
    # F20: an agreed blocking finding ships a known, conceded defect — it MUST surface here,
    # never silently behind a green check. The resolution note explains the disposition
    # (fixed / accepted-because / deferred-to-#X) so a teammate trusts the receipt.
    lines = list(task.not_covered)
    for f in shipped_blockers(task):
        note = (f.resolution_note or "").strip() or "no resolution note recorded"
        lines.append(f"known issue · `{display_location(f.location)}`: {f.message} — {note}")
    return lines


def _context_lines(task: Task) -> list[str]:
    lines: list[str] = []
    if task.understanding:
        lines.append(task.understanding.strip())
    if task.scope:
        lines.append(f"- scope: {', '.join(task.scope)}")
    return lines


def _status_lines(task: Task) -> list[str]:
    lines = [f"- {_STATUS.get(task.state.value, 'Proposed')}"]
    if task.approvers:
        lines.append(f"- approvers: {', '.join(task.approvers)}")
    if task.supersedes:
        lines.append(f"- Supersedes: [{task.supersedes}]({task.supersedes})")
    return lines


def _adjudicated(task: Task) -> list[Finding]:
    return [f for f in task.findings if f.verdict]


def _disputed(task: Task) -> list[Finding]:
    return [f for f in task.findings if f.verdict == "disagree"]


def render_receipt(task: Task) -> str:
    """The full reviewed-before-push receipt, framed as a light ADR decision record."""
    decisions = [_decision(d) for d in task.decisions if d.answer or d.approved]
    lines = [
        f"# Reviewed-before-push receipt: {task.title}",
        "",
        f"Task: `{task.id}` · Branch: `{task.branch or 'unknown'}` · Base: `{task.base_branch}`",
        f"_{_ceremony(task)}_",
        # CONTEXT — the intake WHY + WHAT.
        *_section("Context", _context_lines(task), "_No intake understanding recorded._"),
        # DECISION — pinned decisions + the author's rationale (the working solution).
        *_section("Decision · pinned at intake", decisions, "_No decisions pinned._"),
        *_section(
            "Decision · author comprehension",
            _comprehension_lines(task),
            "_No comprehension note recorded._",
        ),
        *_section(
            "Decision · adjudicated findings",
            [_finding(f) for f in _adjudicated(task)],
            "_No findings adjudicated._",
        ),
        # Pushback is ALWAYS rendered (§3.8) — a static greppable trust signal.
        *_section(
            "Pushback · findings disputed",
            [_pushback(f) for f in _disputed(task)],
            "_No findings disputed._",
        ),
        # CONSEQUENCES — what is and isn't guaranteed, honestly.
        *_section(
            "Consequences · machine-verified checks",
            [_check(c) for c in task.checks],
            "_No checks recorded._",
        ),
        *_section(
            "Consequences · hand-verified smoke tests",
            [_smoke(s) for s in task.smoke_tests],
            "_No smoke tests recorded._",
        ),
        *_section(
            "Consequences · not covered",
            _not_covered_lines(task),
            "_Nothing explicitly marked as not covered._",
        ),
        # STATUS — the ADR lifecycle line + approver provenance.
        *_section("Status", _status_lines(task), "_Proposed._"),
        "",
    ]
    return "\n".join(lines)


def render_pr_body(task: Task) -> str:
    """A Markdown block the human pastes into the PR (kagan NEVER pushes; text only).

    Reuses the same section builders and the SAME honesty filters as the receipt
    (an unadjudicated finding or unverified smoke is never shown as resolved), but
    drops the receipt title and is prefixed with a copy marker so a reviewer audits
    the author's adjudication instead of re-deriving trust.
    """
    breadcrumb = f"agent: {task.agent_cli}" if task.agent_cli else "agent: (drove manually)"
    lines = [
        "<!-- kagan reviewed-before-push receipt — paste into the PR body -->",
        f"## Reviewed-before-push: {task.title}",
        "",
        f"_{_ceremony(task)} · {breadcrumb}_",
        *_section("Context", _context_lines(task), "_No intake understanding recorded._"),
        *_section(
            "Decision · pinned at intake",
            [_decision(d) for d in task.decisions if d.answer or d.approved],
            "_No decisions pinned._",
        ),
        *_section(
            "Decision · author comprehension",
            _comprehension_lines(task),
            "_No comprehension note recorded._",
        ),
        *_section(
            "Decision · adjudicated findings",
            [_finding(f) for f in _adjudicated(task)],
            "_No findings adjudicated._",
        ),
        *_section(
            "Pushback · findings disputed",
            [_pushback(f) for f in _disputed(task)],
            "_No findings disputed._",
        ),
        *_section(
            "Consequences · machine-verified checks",
            [_check(c) for c in task.checks],
            "_No checks recorded._",
        ),
        *_section(
            "Consequences · hand-verified smoke tests",
            [_smoke(s) for s in task.smoke_tests],
            "_No smoke tests recorded._",
        ),
        *_section(
            "Consequences · not covered",
            _not_covered_lines(task),
            "_Nothing explicitly marked as not covered._",
        ),
        *_section("Status", _status_lines(task), "_Proposed._"),
        "",
    ]
    return "\n".join(lines)
