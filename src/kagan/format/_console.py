"""One Theme of named semantic styles + one Console factory (DESIGN §5 / Rich idiom).

The palette lives here, once, instead of as raw ``"red"/"yellow"/"green"`` literals
scattered across the renderers (Rich ``style.rst`` Style Themes — a named ``Theme``
makes the code semantic and keeps the colors in a single place to edit).

``make_console`` is the single Console factory used by BOTH the production ANSI path
(``cli/_interactive.render_to_ansi``) and the test render harness, so the test
console exercises the same construction as prod — only ``no_color`` differs, toggled
by a flag rather than a separate Console class.

Theme style names must be lowercase and contain only letters / ``.`` / ``-`` / ``_``
(Rich constraint), so the risk tiers are ``risk.low`` / ``risk.med`` / ``risk.high``.
"""

from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING

from rich.console import Console
from rich.style import Style as RichStyle
from rich.theme import Theme

if TYPE_CHECKING:
    from rich.console import RenderableType


@dataclass(frozen=True, slots=True)
class DiffColors:
    add_bg: RichStyle
    del_bg: RichStyle
    add_hl: RichStyle
    del_hl: RichStyle


_DIFF_COLORS = DiffColors(
    add_bg=RichStyle(bgcolor="#12261e"),
    del_bg=RichStyle(bgcolor="#2d1214"),
    add_hl=RichStyle(bgcolor="#1a4a2e"),
    del_hl=RichStyle(bgcolor="#5c1a1d"),
)


def get_diff_colors() -> DiffColors:
    return _DIFF_COLORS


# The semantic palette: one name per meaning, the gate severity ramp defined once.
KAGAN_THEME = Theme(
    {
        # gate severity ramp
        "blocker": "red",
        "advisory": "yellow",
        "stale": "yellow",
        "done": "green",
        "needs-you": "yellow",
        "note": "yellow",
        "secondary": "dim",
        "brand": "bold cyan",
        "frame-border": "dim cyan",
        "header-status": "dim",
        "shortcut-key": "bold cyan",
        # risk tiers (lever 4) — only high is emphasised (DESIGN §5: "risk is a quiet word")
        "risk.low": "dim",
        "risk.med": "dim",
        "risk.high": "bold red",
        # in-flight states
        "running": "cyan",
        "reviewing": "cyan",
        "in-review": "magenta",
        # the second-approver / drift blockers read as blockers
        "approver-waiting": "red",
        "approver-done": "green",
    }
)


def make_console(width: int, *, no_color: bool = False) -> Console:
    """The single Console factory — prod (no_color=False) and tests (no_color=True).

    ``highlight=False`` is always set so the auto-highlighter never recolors numbers
    / paths in user strings. The theme is attached so ``style="blocker"`` etc. resolve.
    ``color_system`` is explicit so the no_color=False path carries ANSI even when the
    file is a StringIO (the test seam) or NO_COLOR is set in the environment.
    """
    return Console(
        file=StringIO(),
        force_terminal=not no_color,
        color_system=None if no_color else "standard",
        no_color=no_color,
        width=max(20, width),
        highlight=False,
        theme=KAGAN_THEME,
    )


def render_to_str(renderable: RenderableType, *, width: int = 100, no_color: bool = True) -> str:
    """Render a renderable to a string through ``make_console`` (the test/ANSI seam)."""
    console = make_console(width, no_color=no_color)
    console.print(renderable, end="")
    return console.file.getvalue()  # type: ignore[union-attr]


def print_themed(renderable: RenderableType) -> None:
    """Print to real stdout through a themed, non-highlighting Console.

    For the one-shot CLI paths (doctor / preflight) that print directly rather than
    feeding prompt-toolkit — so ``style="blocker"`` etc. resolve there too.
    """
    Console(highlight=False, theme=KAGAN_THEME).print(renderable)


__all__ = [
    "KAGAN_THEME",
    "DiffColors",
    "get_diff_colors",
    "make_console",
    "print_themed",
    "render_to_str",
]
