"""Review (gate) view renderer — checks, decisions, findings, smoke, readiness.

Pure Rich: no prompt-toolkit, no Harness. The session passes a fresh Task plus
the precomputed ``stale`` / ``locked`` bools (from ``gate_is_stale`` /
``can_approve``) so this file stays pure. Ports the GatePane render verbatim and
adds DESIGN section 5's readiness-checklist framing over the same data.
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.core.api import humanize_task_state
from kagan.core.comprehension import prompts_for_risk
from kagan.core.tasks import _is_substantive
from kagan.format import _symbols as sym
from kagan.format._risk import risk_label, risk_style

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import CheckResult, Decision, Finding, SmokeTest, Task


def render_checks_strip(checks: list[CheckResult]) -> Text:
    """Ports GatePane._checks_text: '✓/✗ name' joined by '  ·  '."""
    if not checks:
        return Text("No checks recorded.", style="secondary")
    out = Text()
    for i, c in enumerate(checks):
        if i:
            out.append("  ·  ", style="secondary")
        glyph, style = (sym.DONE, "done") if c.passed else (sym.BLOCKER, "blocker")
        out.append(f"{glyph} ", style=style)
        out.append(c.name)
    return out


def render_decisions(decisions: list[Decision]) -> RenderableType:
    """Ports GatePane._decisions_text under the pinned-at-intake heading."""
    heading = Text("Pinned at intake  ·  decided, not inferred", style="bold")
    if not decisions:
        return Group(heading, Text("No pinned decisions.", style="secondary"))
    lines: list[RenderableType] = [heading]
    for d in decisions:
        # "accepted as-is" is the surface word for the internal blessed flag (DESIGN §5).
        status = (
            "accepted as-is" if d.blessed else (f"answer: {d.answer}" if d.answer else "unresolved")
        )
        lines.append(Text(f"{d.question}  →  {status}"))
    return Group(*lines)


def _finding_line(f: Finding, *, focused: bool) -> Text:
    """One finding row with the shared cursor glyph on the first line only."""
    cursor_prefix = f"{sym.CURSOR} " if focused else "  "
    indent = "    "
    line = Text(cursor_prefix, style="bold" if focused else "")
    # Severity once, then location + provenance (lever 2).
    tag = f"{f.severity}  ·  {f.location}  ·  [{f.source}]"
    line.append(tag, style="bold" if focused else "")
    line.append(f"\n{indent}{f.message}", style="")
    verdict = f.verdict or "open"
    footer_text = verdict if not f.reply else f"{verdict} — {f.reply}"
    line.append(f"\n{indent}({footer_text})", style="secondary")
    if f.hunk:
        line.append(f"\n{indent}{f.hunk}", style="secondary")
    return line


def render_findings(findings: list[Finding], *, cursor: int = 0) -> RenderableType:
    """The focused-walk findings list. ``cursor`` marks the focused open finding
    with the cursor glyph; only open findings are focusable, but resolved findings
    are shown below for context."""
    heading = Text("Findings", style="bold")
    if not findings:
        return Group(heading, Text("No findings.", style="secondary"))

    open_ = [f for f in findings if f.verdict is None]
    resolved = [f for f in findings if f.verdict is not None]
    cursor = max(0, min(cursor, len(open_) - 1)) if open_ else 0

    cards: list[RenderableType] = [heading]
    for i, f in enumerate(open_):
        cards.append(_finding_line(f, focused=i == cursor))
    if resolved:
        cards.append(Text(""))
        cards.append(Text("Resolved", style="secondary"))
        for f in resolved:
            cards.append(_finding_line(f, focused=False))
    return Group(*cards)


def render_smoke(
    smoke: list[SmokeTest], ports: dict[str, int], *, cursor: int = 0
) -> RenderableType:
    """Per smoke test: ✓ verified / ○ unverified (the palette set, never a sixth
    glyph). ``cursor`` marks the focused unverified test."""
    heading = Text("Smoke tests", style="bold")
    if not smoke:
        return Group(heading, Text("No smoke tests.", style="secondary"))
    lines: list[RenderableType] = [heading]
    todo = [s for s in smoke if not s.verified]
    done = [s for s in smoke if s.verified]
    cursor = max(0, min(cursor, len(todo) - 1)) if todo else 0
    for i, s in enumerate(todo):
        prefix = f"{sym.CURSOR} " if i == cursor else "  "
        label = s.behaviour
        if s.service:
            label += f"  (:{ports.get(s.service, '')})"
        lines.append(Text(f"{prefix}{sym.OPTIONAL} {label}", style="secondary"))
    if done:
        lines.append(Text(""))
        lines.append(Text("Verified", style="secondary"))
        for s in done:
            label = s.behaviour
            if s.service:
                label += f"  (:{ports.get(s.service, '')})"
            lines.append(Text(f"  {sym.DONE} {label}", style="done"))
    return Group(*lines)


def _unanswered_keys(task: Task) -> list[str]:
    """Required prompt keys still missing a substantive answer (reuses the core
    per-answer check — never a duplicate of the substantive logic)."""
    return [
        key
        for key, _ in prompts_for_risk(task.risk)
        if not _is_substantive(task.comprehension.get(key))
    ]


def render_comprehension(task: Task) -> RenderableType:
    """Lever 1: the risk-scaled prompt set — each prompt's question and the recorded
    answer, or 'pending' when unanswered. Low risk requires no prompts.

    Pure — ``task.comprehension`` is the recorded fact; the lock decision is the
    caller's (``can_approve``)."""
    heading = Text("Comprehension", style="bold")
    prompts = prompts_for_risk(task.risk)
    if not prompts:
        return Group(heading, Text("Not required at low risk.", style="secondary"))
    rows: list[RenderableType] = [heading]
    for key, question in prompts:
        rows.append(Text(question, style="secondary"))
        answer = (task.comprehension.get(key) or "").strip()
        rows.append(Text(answer) if answer else Text("pending", style="secondary"))
    return Group(*rows)


def render_approvers(task: Task, required: int) -> RenderableType | None:
    """Lever 6: the high-risk second-approver row — who has signed, how many more.

    Returns None below high risk (the bar is 1, no row needed). ``required`` comes
    from config via the caller so this stays pure."""
    if task.risk != "high":
        return None
    have = sorted(set(task.approvers))
    signed = "  ·  ".join(have) if have else "none yet"
    if len(have) >= required:
        glyph, style = sym.DONE, "done"
        tail = f"approved by {signed}"
    else:
        glyph, style = sym.NEEDS_YOU, "blocker"
        tail = f"approved by {signed} · waiting for one more"
    label = "Second approver — high-risk can't be approved alone"
    return Text(f"{glyph} {label} · {tail}", style=style)


def _focusable_readiness_rows(task: Task) -> list[str]:
    """Ordered kinds of the readiness rows that the cursor may land on."""
    rows: list[str] = []
    if [f for f in task.findings if f.severity == "blocking" and f.verdict != "agree"]:
        rows.append("findings")
    if _unanswered_keys(task):
        rows.append("comprehension")
    if [s for s in task.smoke_tests if not s.verified]:
        rows.append("smoke")
    return rows


def _readiness_row(
    glyph: str, style: str, label: str, *, focused: bool, trailing: str = ""
) -> Text:
    """One checklist row with the shared cursor glyph when focused."""
    prefix = f"{sym.CURSOR} " if focused else "  "
    line = Text(prefix, style="bold" if focused else "")
    line.append(f"{glyph} ", style=style)
    line.append(label, style="bold" if focused else "")
    if trailing:
        line.append(f"   {trailing}", style="secondary")
    return line


def _approver_row(task: Task, required: int, *, focused: bool) -> Text:
    """Lever 6: folded into the readiness checklist as a blocking row until met."""
    have = sorted(set(task.approvers))
    signed = "  ·  ".join(have) if have else "none yet"
    if len(have) >= required:
        return _readiness_row(
            sym.DONE,
            "done",
            "Second approver — high-risk can't be approved alone",
            focused=focused,
            trailing=f"approved by {signed}",
        )
    return _readiness_row(
        sym.NEEDS_YOU,
        "blocker",
        "Second approver — high-risk can't be approved alone",
        focused=focused,
        trailing=f"approved by {signed} · waiting for one more",
    )


def render_readiness(
    task: Task,
    locked: bool,
    *,
    cursor: int = 0,
    high_risk_approvers: int = 2,
) -> RenderableType:
    """DESIGN section 5 checklist framing over the existing checks/findings/smoke
    data. ``cursor`` marks the focused focusable row (findings / comprehension /
    smoke)."""
    open_blocking = [f for f in task.findings if f.severity == "blocking" and f.verdict != "agree"]
    checks_passed = sum(1 for c in task.checks if c.passed)
    checks_total = len(task.checks)
    smoke_todo = [s for s in task.smoke_tests if not s.verified]
    unanswered = _unanswered_keys(task)
    comprehension_done = not unanswered

    focusable = _focusable_readiness_rows(task)
    cursor = max(0, min(cursor, len(focusable) - 1)) if focusable else 0
    focus_kind = focusable[cursor] if focusable else None

    todo_count = len(open_blocking) + len(unanswered)
    title = (
        Text(f"Almost ready — {todo_count} thing(s) before you approve.")
        if locked
        else Text("All blocking findings adjudicated.", style="done")
    )

    rows: list[RenderableType] = [title, Text("")]
    if open_blocking:
        rows.append(
            _readiness_row(
                sym.NEEDS_YOU,
                "blocker",
                f"Adjudicate {len(open_blocking)} blocking finding(s)",
                focused=focus_kind == "findings",
            )
        )
    if comprehension_done:
        rows.append(
            _readiness_row(
                sym.DONE,
                "done",
                "Comprehension recorded",
                focused=False,
            )
        )
    else:
        rows.append(
            _readiness_row(
                sym.NEEDS_YOU,
                "blocker",
                f"Answer {len(unanswered)} comprehension prompt(s)",
                focused=focus_kind == "comprehension",
            )
        )
    rows.append(
        _readiness_row(
            sym.DONE,
            "done",
            f"Checks passed · {checks_passed} of {checks_total}",
            focused=False,
        )
    )
    if task.risk == "high":
        # ponytail: second-approver row is folded into the checklist (Phase 12d-2);
        # it is not focusable because the human cannot step into it — they add
        # themselves by pressing 'a' once the rest of the checklist is clear.
        rows.append(_approver_row(task, high_risk_approvers, focused=False))
    if smoke_todo:
        rows.append(
            _readiness_row(
                sym.OPTIONAL,
                "secondary",
                f"Smoke tests · {len(smoke_todo)} to verify",
                focused=focus_kind == "smoke",
                trailing="optional" if task.risk != "high" else "",
            )
        )
    return Group(*rows)


def render_lock_block(
    task: Task,
    locked: bool,
    *,
    cooldown_remaining: int = 0,
    high_risk_approvers: int = 2,
) -> RenderableType:
    """Persistent block naming every approve lock still in force — structural
    (findings/comprehension), cooldown, and high-risk second approver."""
    if not locked and cooldown_remaining <= 0:
        return Text("")

    lines: list[RenderableType] = []
    if cooldown_remaining > 0:
        minutes, seconds = divmod(cooldown_remaining, 60)
        lines.append(
            Text(
                f"Give it a read before approving — unlocks in {minutes}:{seconds:02d}.",
                style="secondary",
            )
        )
    if locked:
        if any(f.severity == "blocking" and f.verdict is None for f in task.findings):
            lines.append(Text("Approve is locked: adjudicate the open blocking finding(s) first."))
        unanswered = _unanswered_keys(task)
        if unanswered:
            lines.append(
                Text(
                    f"Approve is locked: answer {len(unanswered)} "
                    "comprehension prompt(s) first (press c)."
                )
            )
        if task.risk == "high":
            have = len(set(task.approvers))
            if have < high_risk_approvers:
                lines.append(
                    Text(
                        f"Approve is locked: high-risk needs {high_risk_approvers} "
                        "distinct approvers."
                    )
                )
    return Group(Rule(style="secondary"), *lines) if lines else Text("")


def render_review(
    task: Task,
    *,
    stale: bool,
    locked: bool,
    cursor: int = 0,
    high_risk_approvers: int = 2,
    cooldown_remaining: int = 0,
) -> RenderableType:
    """The readiness-first review view: header + stale banner + checklist + the
    persistent lock/cooldown block. Findings, smoke, and comprehension are
    step-into sub-views, not dumped inline."""
    header = Text(f"{task.title}  ·  {humanize_task_state(task.state)}", style="bold")
    header.append(f"  ·  {risk_label(task.risk)}", style=risk_style(task.risk))
    blocks: list[RenderableType] = [header]
    if task.branch:
        blocks.append(Text(f"{task.branch} → {task.base_branch}", style="secondary"))
    if stale:
        blocks.append(
            Text(
                "Base moved since the gate ran — results may be stale; re-validate.",
                style="stale",
            )
        )
    blocks.append(Text(""))
    blocks.append(
        render_readiness(task, locked, cursor=cursor, high_risk_approvers=high_risk_approvers)
    )
    blocks.append(
        render_lock_block(
            task,
            locked,
            cooldown_remaining=cooldown_remaining,
            high_risk_approvers=high_risk_approvers,
        )
    )
    return Group(*blocks)


__all__ = [
    "render_approvers",
    "render_checks_strip",
    "render_comprehension",
    "render_decisions",
    "render_findings",
    "render_lock_block",
    "render_readiness",
    "render_review",
    "render_smoke",
]
