"""Help renderer — the keymap and the per-view footer hint line.

Pure Rich, no core imports. Both functions are dumb formatters over ``KeyHint``
tuples; the single registry of keys lives in ``cli/session.py`` so the footer
hints and the `?` keymap can't drift (the single-source rule that replaced the
TUI's reflection over *_BINDINGS).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from kagan.format._layout import max_display_width, pad_display

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.console import RenderableType


@dataclass(frozen=True, slots=True)
class KeyHint:
    key: str
    description: str


def render_keymap(
    groups: Sequence[tuple[str, Sequence[KeyHint]]], *, primary_count: int | None = None
) -> RenderableType:
    """The `?` keymap: a section per group, dim secondary text, no boxes.

    The key column is padded by *display* width (so wide ``↑↓`` / ``✋`` keys don't
    shove the description column out of alignment), one constant across all groups.
    When ``primary_count`` is set the first N groups are the active view (bold
    titles); the remainder is demoted under a dim "Other views" divider with dim
    titles, so help is scoped to context rather than a flat dump of every group.
    """
    key_width = max_display_width([h.key for _title, hints in groups for h in hints])
    blocks: list[RenderableType] = [
        Text("Keyboard shortcuts", style="bold"),
        Text("press q to return", style="secondary"),
        Text(""),
    ]
    for index, (title, hints) in enumerate(groups):
        if primary_count is not None and index == primary_count:
            blocks.append(Text("Other views", style="secondary"))
            blocks.append(Text(""))
        secondary = primary_count is not None and index >= primary_count
        blocks.append(Text(title, style="secondary" if secondary else "bold"))
        for h in hints:
            row = Text(f"  {pad_display(h.key, key_width)}  ", style="reviewing")
            row.append(h.description, style="secondary")
            blocks.append(row)
        blocks.append(Text(""))
    return Group(*blocks)


def render_footer_hint(hints: Sequence[KeyHint]) -> Text:
    """The per-view footer line: ' · '-joined 'key action' segments under a rule."""
    line = Text()
    for i, h in enumerate(hints):
        if i:
            line.append("   ", style="secondary")
        line.append(h.key, style="shortcut-key")
        line.append(f" {h.description}", style="secondary")
    return line


def render_footer(hints: Sequence[KeyHint]) -> RenderableType:
    """A hairline rule above the footer hint (the calm DESIGN-section-5 footer)."""
    return Group(Rule(style="frame-border"), render_footer_hint(hints))


__all__ = ["KeyHint", "render_footer", "render_footer_hint", "render_keymap"]
