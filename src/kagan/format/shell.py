"""Responsive full-screen shell shared by every held session view."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich import box
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from kagan.format._console import render_to_str

if TYPE_CHECKING:
    from rich.console import RenderableType


@dataclass(frozen=True, slots=True)
class FrameGeometry:
    """Maximum frame dimensions derived from the live terminal size."""

    terminal_columns: int
    terminal_rows: int
    width: int
    height: int
    padding_x: int
    padding_y: int
    compact: bool

    @property
    def content_width(self) -> int:
        chrome = 0 if self.compact else 2 + (self.padding_x * 2)
        return max(1, self.width - chrome)

    @property
    def content_height(self) -> int:
        chrome = 0 if self.compact else 2 + (self.padding_y * 2)
        return max(1, self.height - chrome)


@dataclass(frozen=True, slots=True)
class RenderedFrame:
    """ANSI frame plus the exact dimensions prompt-toolkit should center."""

    text: str
    width: int
    height: int


def frame_geometry(columns: int, rows: int) -> FrameGeometry:
    """Fill constrained terminals; center a capped proportional panel otherwise."""
    columns = max(1, columns)
    rows = max(1, rows)
    compact = columns < 96 or rows < 30
    if compact:
        return FrameGeometry(columns, rows, columns, rows, 1, 0, True)
    return FrameGeometry(
        columns,
        rows,
        min(100, max(72, round(columns * 0.72))),
        min(rows - 2, max(24, round(rows * 0.82))),
        2,
        1,
        False,
    )


def render_frame(
    body: RenderableType,
    geometry: FrameGeometry,
    *,
    minimum_height: int = 12,
    header: RenderableType | None = None,
    footer: RenderableType | None = None,
) -> RenderedFrame:
    """Fit short content, clamp long content, and remove chrome when constrained."""
    surface = Padding(body, (0, 0), expand=True)
    measured = render_to_str(surface, width=geometry.content_width, no_color=True)
    body_height = max(1, len(measured.splitlines()))
    header_height = _measure_height(header, geometry.content_width)
    footer_height = _measure_height(footer, geometry.content_width)
    rail_height = int(header is not None) + int(footer is not None)
    required_height = body_height + header_height + footer_height + rail_height

    if geometry.compact:
        content = _compose_regions(
            surface,
            body_height=body_height,
            height=geometry.height,
            width=geometry.content_width,
            header=header,
            header_height=header_height,
            footer=footer,
            footer_height=footer_height,
        )
        return RenderedFrame(
            render_to_str(content, width=geometry.width, no_color=False),
            geometry.width,
            geometry.height,
        )

    chrome_height = 2 + (geometry.padding_y * 2)
    height = min(
        geometry.height,
        max(minimum_height, required_height + chrome_height),
    )
    content = _compose_regions(
        surface,
        body_height=body_height,
        height=max(1, height - chrome_height),
        width=geometry.content_width,
        header=header,
        header_height=header_height,
        footer=footer,
        footer_height=footer_height,
    )
    panel = Panel(
        content,
        box=box.ROUNDED,
        border_style="frame-border",
        width=geometry.width,
        height=height,
        padding=(geometry.padding_y, geometry.padding_x),
    )
    return RenderedFrame(
        render_to_str(panel, width=geometry.width, no_color=False),
        geometry.width,
        height,
    )


def render_input_line(
    label: str,
    text: str,
    *,
    placeholder: str = "",
    hint: str | None = None,
) -> RenderableType:
    """A prompt line drawn INSIDE the frame: the label, then the live input text with
    a cursor glyph (the real terminal cursor is hidden by the frame). Shows a dim
    placeholder when empty, and an optional dim hint line below."""
    blocks: list[RenderableType] = [Text(label)]
    line = Text("  ")
    if text:
        line.append(text)
    elif placeholder:
        line.append(placeholder, style="secondary")
    line.append("▏", style="secondary")  # cursor glyph; pt hides the real one
    blocks.append(line)
    if hint:
        blocks.append(Text(hint, style="secondary"))
    return Group(*blocks)


def _measure_height(renderable: RenderableType | None, width: int) -> int:
    if renderable is None:
        return 0
    rendered = render_to_str(renderable, width=width, no_color=True)
    return max(1, len(rendered.splitlines()))


def _compose_regions(
    body: RenderableType,
    *,
    body_height: int,
    height: int,
    width: int,
    header: RenderableType | None,
    header_height: int,
    footer: RenderableType | None,
    footer_height: int,
) -> RenderableType:
    """Pin optional chrome to the edges and center (or clip) only the flexible body."""
    rails = int(header is not None) + int(footer is not None)
    body_area = max(1, height - header_height - footer_height - rails)
    blocks: list[RenderableType] = []
    if header is not None:
        blocks.extend((header, Rule(style="frame-border")))
    blocks.append(_fit_content(body, body_height=body_height, height=body_area, width=width))
    if footer is not None:
        blocks.extend((Rule(style="frame-border"), footer))
    return Padding(Group(*blocks), (0, 0), expand=True)


def _fit_content(
    body: RenderableType, *, body_height: int, height: int, width: int
) -> RenderableType:
    """Center short content; CLIP content taller than its area so pinned header/footer
    are never pushed off the frame (B5 — the intake decision walk's controls vanished
    when the decisions overflowed). Clipping is top-anchored; the caller windows the
    body around its cursor so the focused row stays inside the kept region."""
    if body_height > height:
        rendered = render_to_str(body, width=width, no_color=False)
        return Text.from_ansi("\n".join(rendered.splitlines()[:height]))
    top = (height - body_height) // 2
    bottom = height - body_height - top
    blocks: list[RenderableType] = [
        *(Text("") for _ in range(top)),
        body,
        *(Text("") for _ in range(bottom)),
    ]
    return Padding(Group(*blocks), (0, 0), expand=True)


__all__ = [
    "FrameGeometry",
    "RenderedFrame",
    "frame_geometry",
    "render_frame",
    "render_input_line",
]
