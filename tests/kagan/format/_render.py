"""Render a Rich renderable to a plain string for content assertions.

Goes through the SAME ``make_console`` factory the production ANSI path uses
(``cli/_interactive.render_to_ansi``) — only ``no_color`` differs — so the test
console exercises the prod construction (theme attached, highlight off).
"""

from rich.console import RenderableType

from kagan.format._console import render_to_str


def to_str(renderable: RenderableType, *, width: int = 100) -> str:
    return render_to_str(renderable, width=width, no_color=True)
