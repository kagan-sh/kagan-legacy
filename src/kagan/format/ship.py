"""Ship view renderer — next-step-first push/PR commands + a receipt digest.

Pure Rich. The push/pr command strings and the full receipt markdown are
resolved by the caller via Harness and passed in, so this file never imports
Harness (matching format/doctor.py). Renders what core returns — it does NOT
hardcode a divergent pr command (the `--fill` vs long-form gap is core's call,
flagged for the receipt/ship phase).
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.format.receipt import render_receipt_digest

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Task


def render_ship(
    task: Task,
    push_cmd: str,
    pr_cmd: str,
    receipt: str,
    *,
    retro: str | None = None,
    copied: str | None = None,
) -> RenderableType:
    """The full ship view: header, "Do this next" commands, receipt digest, footer.

    ``receipt`` (the full markdown body) is accepted for parity with the copy
    action even though the panel renders the digest derived from the Task.
    ``retro`` is the lever-8 learning candidate (rendered with an ``l`` affordance
    when present — this is where the loop closes, DESIGN §5). ``copied`` is the key
    whose copy just succeeded, persisted as ``[c ✓ copied]`` so the feedback does not
    scroll off on the next redraw.
    """
    _ = receipt  # the copy action carries the full body; the panel shows the digest
    header = Text()
    header.append(f"{task.title} · ready", style="bold")
    branch = task.branch or "(no branch set)"
    header.append(f"   {branch} → {task.base_branch}", style="secondary")

    do_next = Group(
        Text("Do this next", style="bold"),
        _command_line(push_cmd, "c", copied=copied == "c"),
        _command_line(pr_cmd, "p", copied=copied == "p"),
    )

    receipt_block = _receipt_block(task, copied=copied == "r")

    blocks: list[RenderableType] = [header, Text(""), do_next, Text(""), receipt_block]
    if retro:
        blocks.append(Text(""))
        blocks.append(_retro_block(retro))
    blocks.append(Text(""))
    blocks.append(Rule(style="secondary"))
    blocks.append(_footer(retro is not None))
    return Group(*blocks)


def _receipt_block(task: Task, *, copied: bool) -> RenderableType:
    """The receipt digest under its header; a thin (machine-unverified) digest gets a
    dim honesty line so the near-blank digest is not read as a confident receipt."""
    head = Text("Receipt → paste in the PR body  ", style="bold")
    head.append("[r ✓ copied]" if copied else "[r]", style="secondary")
    rows: list[RenderableType] = [head, render_receipt_digest(task)]
    if _receipt_is_thin(task):
        rows.append(
            Text(
                "This receipt is thin — nothing was machine-verified or adjudicated.",
                style="secondary",
            )
        )
    return Group(*rows)


def _receipt_is_thin(task: Task) -> bool:
    """A hollow digest: no passing checks, no adjudicated findings, no verified smoke,
    no pinned decisions — the human is the only thing standing behind it."""
    checks_executed = bool(task.checks)
    adjudicated = any(f.verdict for f in task.findings)
    verified_smoke = any(s.verified for s in task.smoke_tests)
    pinned = any(d.answer or d.approved for d in task.decisions)
    return not (checks_executed or adjudicated or verified_smoke or pinned)


def _retro_block(retro: str) -> RenderableType:
    action = Text("   ")
    action.append("l", style="shortcut-key")
    action.append(" append to AGENTS.md", style="secondary")
    return Group(
        Text("One learning for next time?", style="bold"),
        Text(f'   "{retro}"', style="secondary"),
        action,
    )


def _footer(has_retro: bool) -> Text:
    hints = [("c", "push"), ("p", "pr"), ("r", "receipt")]
    if has_retro:
        hints.append(("l", "learning"))
    hints.extend((("⏎", "I pushed & opened PR"), ("q", "quit")))
    line = Text()
    for index, (key, description) in enumerate(hints):
        if index:
            line.append("   ", style="secondary")
        line.append(key, style="shortcut-key")
        line.append(f" {description}", style="secondary")
    line.append("    kagan never pushes", style="secondary")
    return line


def _command_line(cmd: str, key: str, *, copied: bool) -> Text:
    line = Text("  $ ", style="secondary")
    line.append(cmd)
    line.append(f"  [{key} ✓ copied]" if copied else f"  [{key}]", style="secondary")
    return line


__all__ = ["render_ship"]
