"""Width-aware layout helpers — never hardcoded spacing (DESIGN §5 deference).

Right-aligned metadata and label columns must hold from 80 to 120 cols. These helpers
right-align from the real console width (a 2-col ``Table(box=None)`` that expands to
the printing width — never a literal-space string) and pad label columns by *display*
width (``rich.cells.cell_len`` accounts for wide glyphs like ``↑↓`` / ``✋``, which
``len()`` undercounts).
"""

from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.console import RenderableType


def header_with_rail(left: str, right: str, *, left_style: str = "bold") -> Table:
    """A header line whose ``right`` rail is flush to the real width (no space literal).

    A borderless 2-column table that expands to the console width; the second column
    is right-justified, so ``right`` tracks 80 or 120 cols identically.
    """
    table = Table(box=None, show_header=False, show_edge=False, expand=True, pad_edge=False)
    table.add_column(justify="left", no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    table.add_row(Text(left, style=left_style), Text(right, style="secondary"))
    return table


def label_value_rows(
    rows: Sequence[tuple[str, str]],
    *,
    label_style: str = "secondary",
    value_style: str = "",
) -> RenderableType:
    """Dim-label / value rows aligned by display width — the calm hairline list.

    The label column is padded to the widest *display* width (``cell_len``), so wide
    glyphs in a label do not shove the value column out of alignment.
    """
    table = Table(
        box=None, show_header=False, show_edge=False, pad_edge=False, padding=(0, 2, 0, 0)
    )
    table.add_column(justify="left", no_wrap=True)
    table.add_column(justify="left")
    for label, value in rows:
        table.add_row(Text(label, style=label_style), Text(value, style=value_style))
    return table


def pad_display(text: str, width: int) -> str:
    """Right-pad ``text`` with spaces to ``width`` *display* columns (wide-glyph safe)."""
    deficit = width - cell_len(text)
    return text + (" " * deficit if deficit > 0 else "")


def max_display_width(labels: Sequence[str]) -> int:
    """The widest display width across ``labels`` (for a single label-column constant)."""
    return max((cell_len(label) for label in labels), default=0)


__all__ = ["header_with_rail", "label_value_rows", "max_display_width", "pad_display"]
