"""New-task form renderer — the `n new` in-session confirm frame.

Pure Rich, stateless: the session collects the fields sequentially, then renders
this frame ONCE as the confirm gate before creating the task (DESIGN §5). Risk is
the tier computed from the entered scope; the reviewer line is future-gated
(lever 2 in core) and renders only when its optional arg is passed (the
gap-guard).
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.core.ceremony import banner_suffix, gates_clause, validator_status
from kagan.format import _symbols as sym
from kagan.format._layout import max_display_width, pad_display
from kagan.format._risk import risk_label

if TYPE_CHECKING:
    from rich.console import RenderableType

_NO_AGENT = "✋ I'll drive"

# One label column for the form so values + continuation lines align by display width.
_LABEL_WIDTH = max_display_width(["Title", "Scope", "Agent"])


def _risk_sentence(risk: str, reviewer_configured: bool) -> str:
    # The EFFECTIVE ceremony, not the tier label (B10): if no reviewer is configured the
    # validator will not run, so the line says "validator disabled — no reviewer
    # configured" rather than promising "validator + comprehension" it can't deliver.
    status = validator_status(risk, reviewer_configured=reviewer_configured)
    return f"{risk_label(risk)} — {gates_clause(risk, status)}{banner_suffix(status)}."


def _indent(text: str, label_width: int) -> str:
    """Hang a continuation line under the value column (label_width + the 2-space gap)."""
    return " " * (label_width + 2) + text


def render_new_task_form(
    *,
    title: str,
    scope: list[str],
    clis: list[str],
    selected: str | None,
    recipe_command: list[str] | None,
    risk: str | None = None,
    reviewer_configured: bool = False,
    reviewer_note: str | None = None,
    queue_note: str | None = None,
) -> RenderableType:
    """The new-task form: title, scope (+ optional risk), agent picker, launch line."""
    # The field labels share one display-width column so values line up and the
    # risk/reviewer continuation lines indent under the value, not a fixed guess.
    label_w = _LABEL_WIDTH
    blocks: list[RenderableType] = [Text("New task", style="bold"), Text("")]

    title_line = Text(pad_display("Title", label_w) + "  ", style="secondary")
    title_line.append(title if title else "…", style="" if title else "secondary")
    blocks.append(title_line)

    scope_line = Text(pad_display("Scope", label_w) + "  ", style="secondary")
    scope_line.append("  ".join(scope) if scope else "…", style="" if scope else "secondary")
    blocks.append(scope_line)
    if risk is not None:
        blocks.append(
            Text(_indent(_risk_sentence(risk, reviewer_configured), label_w), style="secondary")
        )

    agent_line = Text(pad_display("Agent", label_w) + "  ", style="secondary")
    tokens = [*clis, _NO_AGENT]
    selected_token = selected if selected is not None else _NO_AGENT
    for i, tok in enumerate(tokens):
        if i:
            agent_line.append("   ")
        if tok == selected_token:
            agent_line.append(f"{sym.CURSOR} ", style="bold")
            agent_line.append(tok, style="bold")
        else:
            agent_line.append(tok)
    blocks.append(agent_line)
    if reviewer_note is not None:
        blocks.append(
            Text(
                _indent(f"reviewed by {reviewer_note} (a different model)", label_w),
                style="secondary",
            )
        )

    if recipe_command is None:
        blocks.append(Text("launch: you drive — no agent CLI", style="secondary"))
    else:
        blocks.append(Text(f"launch: {' '.join(recipe_command)} …", style="secondary"))

    blocks.append(Rule(style="secondary"))
    footer = Text("enter create & plan · q cancel", style="secondary")
    if queue_note is not None:
        footer.append(f"   ({queue_note})", style="secondary")
    blocks.append(footer)
    return Group(*blocks)


__all__ = ["render_new_task_form"]
