"""Doctor report formatting shared by the CLI surfaces (pure Rich, no boxes)."""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.text import Text

from kagan.format._layout import max_display_width, pad_display

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.doctor_checks import DoctorCheck

# Status → (preflight glyph, semantic theme style). One ramp, shared by both forms.
_STATUS: dict[str, tuple[str, str]] = {
    "pass": ("✓", "done"),
    "warn": ("⚠", "advisory"),
    "fail": ("✗", "blocker"),
}

# Calm sentence labels for the preflight (DESIGN §5 doctor) — the raw check name is
# reserved for `--verbosity technical`. Unknown checks fall back to their raw name.
_CALM_LABEL: dict[str, str] = {
    "git": "git repository",
    "python": "python 3.14",
    "agent CLI": "coding agent",
    "gh": "github cli",
    "repo manifest": "repo config",
}


def _calm_label(name: str) -> str:
    return _CALM_LABEL.get(name, name)


def format_doctor_tldr(checks: list[DoctorCheck]) -> str:
    total = len(checks)
    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    return f"doctor: {total} checks | PASS {passed} | WARN {warned} | FAIL {failed}"


def format_doctor_technical(checks: list[DoctorCheck]) -> str:
    width = max_display_width([c.status.upper() for c in checks])
    lines: list[str] = []
    for check in checks:
        lines.append(f"{pad_display(check.status.upper(), width)} {check.name}")
        lines.append(f"  detail: {check.message}")
        if check.fix_hint:
            lines.append(f"  quick fix: {check.fix_hint}")
        lines.append(f"  verify: {check.verify_hint}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_preflight(checks: list[DoctorCheck]) -> Group:
    """Calm one-shot preflight (DESIGN §5): a glyph + calm label + message line per
    check, the dimmed ``fix_hint`` under each fail/warn (the moment the user needs it),
    then a trailing verdict. The single visual language ``kagan doctor`` also uses."""
    blocks: list[RenderableType] = []
    for check in checks:
        glyph, style = _STATUS.get(check.status, ("·", "secondary"))
        line = Text(f"{glyph} ", style=style)
        line.append(_calm_label(check.name), style="bold")
        line.append(f"  {check.message}", style="secondary")
        blocks.append(line)
        # The fix is shown right under the line that needs it (not buried in a footer).
        if check.status in {"warn", "fail"} and check.fix_hint:
            blocks.append(Text(f"    {check.fix_hint}", style="secondary"))

    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    if failed:
        verdict = Text(f"Needs attention — {failed} must be fixed.", style="bold blocker")
    elif warned:
        verdict = Text(f"Usable — {warned} warning(s).", style="bold advisory")
    else:
        verdict = Text("Ready.", style="bold done")
    return Group(*blocks, Text(""), verdict)
