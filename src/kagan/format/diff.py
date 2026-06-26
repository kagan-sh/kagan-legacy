"""Unified diff rendering for in-session review."""

import asyncio
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum, auto
from typing import TYPE_CHECKING, Literal

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kagan.format._console import get_diff_colors, render_to_str
from kagan.format._syntax import KimiSyntax

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from rich.console import RenderableType

_INLINE_DIFF_MIN_RATIO = 0.5
N_CONTEXT_LINES = 3
_HUGE_FILE_THRESHOLD = 10000
_PANEL_OVERHEAD = 3


@dataclass(slots=True)
class DiffDisplayBlock:
    path: str
    old_text: str
    new_text: str
    old_start: int = 1
    new_start: int = 1
    is_summary: bool = False


class DiffLineKind(Enum):
    CONTEXT = auto()
    ADD = auto()
    DELETE = auto()


@dataclass(slots=True)
class DiffLine:
    kind: DiffLineKind
    old_num: int
    new_num: int
    code: str
    content: Text | None = None
    is_inline_paired: bool = False


@dataclass(slots=True)
class FileDiff:
    path: str
    is_summary: bool = False
    summary: DiffDisplayBlock | None = None
    hunks: list[list[DiffLine]] = field(default_factory=list)
    added: int = 0
    removed: int = 0


@dataclass(slots=True)
class _FlatRow:
    kind: Literal["sep", "line"]
    line: DiffLine | None = None


def _append_opcode_lines(
    hunk: list[DiffLine],
    tag: str,
    old_lines: list[str],
    new_lines: list[str],
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    old_start: int,
    new_start: int,
) -> None:
    if tag == "equal":
        for k in range(i2 - i1):
            hunk.append(
                DiffLine(
                    kind=DiffLineKind.CONTEXT,
                    old_num=old_start + i1 + k,
                    new_num=new_start + j1 + k,
                    code=old_lines[i1 + k],
                )
            )
    elif tag == "delete":
        for k in range(i2 - i1):
            hunk.append(
                DiffLine(
                    kind=DiffLineKind.DELETE,
                    old_num=old_start + i1 + k,
                    new_num=0,
                    code=old_lines[i1 + k],
                )
            )
    elif tag == "insert":
        for k in range(j2 - j1):
            hunk.append(
                DiffLine(
                    kind=DiffLineKind.ADD,
                    old_num=0,
                    new_num=new_start + j1 + k,
                    code=new_lines[j1 + k],
                )
            )
    elif tag == "replace":
        for k in range(i2 - i1):
            hunk.append(
                DiffLine(
                    kind=DiffLineKind.DELETE,
                    old_num=old_start + i1 + k,
                    new_num=0,
                    code=old_lines[i1 + k],
                )
            )
        for k in range(j2 - j1):
            hunk.append(
                DiffLine(
                    kind=DiffLineKind.ADD,
                    old_num=0,
                    new_num=new_start + j1 + k,
                    code=new_lines[j1 + k],
                )
            )


def _hunks_from_lines(
    old_lines: list[str],
    new_lines: list[str],
    *,
    n_context: int = N_CONTEXT_LINES,
) -> tuple[list[list[DiffLine]], int, int]:
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    hunks: list[list[DiffLine]] = []
    added = 0
    removed = 0
    for group in matcher.get_grouped_opcodes(n=n_context):
        hunk: list[DiffLine] = []
        for tag, i1, i2, j1, j2 in group:
            _append_opcode_lines(hunk, tag, old_lines, new_lines, i1, i2, j1, j2, 1, 1)
        if not hunk:
            continue
        for dl in hunk:
            if dl.kind == DiffLineKind.ADD:
                added += 1
            elif dl.kind == DiffLineKind.DELETE:
                removed += 1
        hunks.append(hunk)
    return hunks, added, removed


def compute_file_diff_sync(path: str, old_text: str, new_text: str) -> FileDiff | None:
    if old_text == new_text:
        return None

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    max_lines = max(len(old_lines), len(new_lines))

    if max_lines > _HUGE_FILE_THRESHOLD:
        old_desc = f"({len(old_lines)} lines)"
        if len(old_lines) == len(new_lines):
            new_desc = f"({len(new_lines)} lines, modified)"
        else:
            new_desc = f"({len(new_lines)} lines)"
        return FileDiff(
            path=path,
            is_summary=True,
            summary=DiffDisplayBlock(
                path=path,
                old_text=old_desc,
                new_text=new_desc,
                is_summary=True,
            ),
        )

    hunks, added, removed = _hunks_from_lines(old_lines, new_lines)
    if not hunks:
        return None
    return FileDiff(path=path, hunks=hunks, added=added, removed=removed)


async def compute_file_diff(path: str, old_text: str, new_text: str) -> FileDiff | None:
    return await asyncio.to_thread(compute_file_diff_sync, path, old_text, new_text)


def _make_highlighter(path: str) -> KimiSyntax:
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    return KimiSyntax("", ext if ext else "text")


def _highlight(highlighter: KimiSyntax, code: str) -> Text:
    t = highlighter.highlight(code)
    if t.plain.endswith("\n"):
        t.right_crop(1)
    return t


def _build_offset_map(raw: str, rendered: str, tab_size: int) -> list[int]:
    if raw == rendered:
        return list(range(len(raw) + 1))
    offsets: list[int] = []
    col = 0
    for ch in raw:
        offsets.append(col)
        if ch == "\t":
            col += tab_size - (col % tab_size)
        else:
            col += 1
    offsets.append(col)
    if col != len(rendered):
        rendered_len = len(rendered)
        raw_len = len(raw)
        if raw_len == 0:
            return [rendered_len]
        return [(i * rendered_len) // raw_len for i in range(raw_len)] + [rendered_len]
    return offsets


def _apply_inline_diff(
    highlighter: KimiSyntax,
    del_lines: list[DiffLine],
    add_lines: list[DiffLine],
) -> None:
    colors = get_diff_colors()
    tab_size = highlighter.tab_size
    paired = min(len(del_lines), len(add_lines))
    for j in range(paired):
        old_code = del_lines[j].code
        new_code = add_lines[j].code
        old_text = _highlight(highlighter, old_code)
        new_text = _highlight(highlighter, new_code)
        del_lines[j].content = old_text
        add_lines[j].content = new_text
        sm = SequenceMatcher(None, old_code, new_code)
        if sm.ratio() < _INLINE_DIFF_MIN_RATIO:
            continue
        old_map = _build_offset_map(old_code, old_text.plain, tab_size)
        new_map = _build_offset_map(new_code, new_text.plain, tab_size)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op in ("delete", "replace"):
                old_text.stylize(colors.del_hl, old_map[i1], old_map[i2])
            if op in ("insert", "replace"):
                new_text.stylize(colors.add_hl, new_map[j1], new_map[j2])
        del_lines[j].content = old_text
        del_lines[j].is_inline_paired = True
        add_lines[j].content = new_text
        add_lines[j].is_inline_paired = True


def _highlight_hunk(highlighter: KimiSyntax, hunk: list[DiffLine]) -> None:
    i = 0
    while i < len(hunk):
        if hunk[i].kind == DiffLineKind.DELETE:
            del_start = i
            while i < len(hunk) and hunk[i].kind == DiffLineKind.DELETE:
                i += 1
            add_start = i
            while i < len(hunk) and hunk[i].kind == DiffLineKind.ADD:
                i += 1
            _apply_inline_diff(
                highlighter,
                hunk[del_start:add_start],
                hunk[add_start:i],
            )
        else:
            i += 1

    for dl in hunk:
        if dl.content is None:
            dl.content = _highlight(highlighter, dl.code)


def _build_diff_header(path: str, added: int, removed: int) -> Text:
    header = Text()
    if added > 0:
        header.append(f"+{added} ", style="bold green")
    if removed > 0:
        header.append(f"-{removed} ", style="bold red")
    header.append(path)
    return header


def _flatten_hunks(hunks: list[list[DiffLine]]) -> list[_FlatRow]:
    rows: list[_FlatRow] = []
    for hunk_idx, hunk in enumerate(hunks):
        if hunk_idx > 0:
            rows.append(_FlatRow(kind="sep"))
        for dl in hunk:
            rows.append(_FlatRow(kind="line", line=dl))
    return rows


def _table_row_count(hunks: list[list[DiffLine]]) -> int:
    if not hunks:
        return 0
    return sum(len(h) for h in hunks) + max(0, len(hunks) - 1)


def _highlight_hunks_for_rows(
    highlighter: KimiSyntax,
    hunks: list[list[DiffLine]],
    row_start: int,
    row_end: int,
) -> None:
    visible_hunks: set[int] = set()
    row = 0
    for hunk_idx, hunk in enumerate(hunks):
        if hunk_idx > 0:
            if row_start <= row < row_end:
                visible_hunks.add(hunk_idx)
            row += 1
        for _ in hunk:
            if row_start <= row < row_end:
                visible_hunks.add(hunk_idx)
            row += 1
    for hunk_idx in visible_hunks:
        _highlight_hunk(highlighter, hunks[hunk_idx])


def _add_diff_row(table: Table, dl: DiffLine, *, num_width: int, colors) -> None:
    assert dl.content is not None
    if dl.kind == DiffLineKind.ADD:
        table.add_row(
            Text(str(dl.new_num)),
            Text(" + ", style="green"),
            dl.content,
            style=colors.add_bg,
        )
    elif dl.kind == DiffLineKind.DELETE:
        table.add_row(
            Text(str(dl.old_num)),
            Text(" - ", style="red"),
            dl.content,
            style=colors.del_bg,
        )
    else:
        table.add_row(
            Text(str(dl.new_num), style="dim"),
            Text("   "),
            dl.content,
        )


def _panel_for_file_diff(
    file_diff: FileDiff,
    *,
    table_row_start: int = 0,
    table_row_end: int | None = None,
) -> RenderableType:
    if file_diff.is_summary:
        assert file_diff.summary is not None
        return render_diff_summary_panel(file_diff.path, [file_diff.summary])

    hunks = file_diff.hunks
    flat = _flatten_hunks(hunks)
    total_rows = len(flat)
    end = total_rows if table_row_end is None else min(table_row_end, total_rows)
    start = max(0, min(table_row_start, end))

    highlighter = _make_highlighter(file_diff.path)
    if start < end:
        _highlight_hunks_for_rows(highlighter, hunks, start, end)

    max_ln = 0
    for hunk in hunks:
        for dl in hunk:
            max_ln = max(max_ln, dl.old_num, dl.new_num)
    num_width = max(len(str(max_ln)), 2)

    table = Table(
        show_header=False,
        box=None,
        padding=(0, 0),
        show_edge=False,
        expand=True,
    )
    table.add_column(justify="right", width=num_width, no_wrap=True)
    table.add_column(width=3, no_wrap=True)
    table.add_column(ratio=1)

    colors = get_diff_colors()
    for row_idx in range(start, end):
        row = flat[row_idx]
        if row.kind == "sep":
            table.add_row(Text("⋮", style="dim"), Text(""), Text(""))
        else:
            assert row.line is not None
            _add_diff_row(table, row.line, num_width=num_width, colors=colors)

    title = Text()
    title.append(" ")
    title.append_text(_build_diff_header(file_diff.path, file_diff.added, file_diff.removed))
    title.append(" ")

    return Panel(
        table,
        title=title,
        title_align="left",
        border_style="dim",
        padding=(0, 1),
    )


def render_diff_panel_slice(
    file_diff: FileDiff,
    *,
    width: int,
    table_row_start: int = 0,
    table_row_end: int | None = None,
) -> list[str]:
    """Render a file panel; only highlight and emit table rows in [start, end)."""
    panel = _panel_for_file_diff(
        file_diff,
        table_row_start=table_row_start,
        table_row_end=table_row_end,
    )
    return render_to_str(panel, width=width, no_color=False).splitlines()


def render_diff_panel(
    path: str,
    hunks: list[list[DiffLine]],
    added: int,
    removed: int,
) -> RenderableType:
    file_diff = FileDiff(path=path, hunks=hunks, added=added, removed=removed)
    return _panel_for_file_diff(file_diff)


def _summary_description(blocks: list[DiffDisplayBlock]) -> str:
    block = blocks[0]
    if block.old_text == "(0 lines)":
        return f"New file with {block.new_text.strip('()')}"
    if block.old_text == block.new_text:
        return block.old_text.strip("()")
    return f"{block.old_text.strip('()')} \u2192 {block.new_text.strip('()')}"


def render_diff_summary_panel(
    path: str,
    blocks: list[DiffDisplayBlock],
) -> RenderableType:
    title = Text()
    title.append(" ")
    title.append(path)
    title.append(" ")

    body = Text()
    body.append("File too large for inline diff", style="dim italic")
    body.append("\n")
    body.append(_summary_description(blocks), style="dim")

    return Panel(
        body,
        title=title,
        title_align="left",
        border_style="dim",
        padding=(1, 2),
    )


def _estimated_panel_lines(file_diff: FileDiff) -> int:
    if file_diff.is_summary:
        return 6
    return _PANEL_OVERHEAD + _table_row_count(file_diff.hunks)


_VIRT_TABLE_ROWS = 80


@dataclass
class _FileSlot:
    path: str
    diff: FileDiff | None = None
    panel_lines: list[str] | None = None
    panel_width: int | None = None


class DiffViewport:
    """Lazy per-file diff + virtualized scroll across a multi-file change set."""

    def __init__(
        self,
        paths: list[str],
        *,
        loader: Callable[[str], Awaitable[FileDiff | None]],
    ) -> None:
        self._loader = loader
        self._slots = [_FileSlot(path=p) for p in paths]

    @property
    def paths(self) -> list[str]:
        return [slot.path for slot in self._slots]

    async def _load_diff(self, index: int) -> FileDiff | None:
        slot = self._slots[index]
        if slot.diff is not None:
            return slot.diff
        slot.diff = await self._loader(slot.path)
        return slot.diff

    def _span_for(self, index: int, width: int) -> int:
        slot = self._slots[index]
        if slot.panel_lines is not None and slot.panel_width == width:
            return len(slot.panel_lines)
        if slot.diff is None:
            return 0
        return _estimated_panel_lines(slot.diff)

    async def _render_file(self, index: int, width: int) -> list[str]:
        slot = self._slots[index]
        if slot.panel_lines is not None and slot.panel_width == width:
            return slot.panel_lines
        diff = await self._load_diff(index)
        if diff is None:
            slot.panel_lines = []
            slot.panel_width = width
            return []
        slot.panel_lines = render_diff_panel_slice(diff, width=width)
        slot.panel_width = width
        return slot.panel_lines

    async def _lines_for_file_range(
        self,
        index: int,
        width: int,
        line_start: int,
        line_end: int,
    ) -> list[str]:
        diff = await self._load_diff(index)
        if diff is None or line_end <= line_start:
            return []
        if diff.is_summary or _table_row_count(diff.hunks) <= _VIRT_TABLE_ROWS:
            full = await self._render_file(index, width)
            return full[line_start:line_end]
        tbl_start = max(0, line_start - _PANEL_OVERHEAD)
        tbl_end = min(
            _table_row_count(diff.hunks),
            max(tbl_start + 1, line_end - _PANEL_OVERHEAD),
        )
        return render_diff_panel_slice(
            diff,
            width=width,
            table_row_start=tbl_start,
            table_row_end=tbl_end,
        )

    async def total_lines(self, width: int) -> int:
        total = 0
        for index in range(len(self._slots)):
            await self._load_diff(index)
            span = self._span_for(index, width)
            total += span
            if span and index + 1 < len(self._slots):
                total += 1
        return total

    async def window(self, offset: int, height: int, width: int) -> tuple[list[str], int, int]:
        if height < 1:
            height = 1

        total = await self.total_lines(width)
        offset = max(0, min(offset, max(0, total - height)))

        lines: list[str] = []
        pos = 0
        for index in range(len(self._slots)):
            if pos >= offset + height and lines:
                break
            await self._load_diff(index)
            span = self._span_for(index, width)
            if span == 0:
                continue

            file_end = pos + span
            if file_end <= offset:
                pos = file_end
                if index + 1 < len(self._slots):
                    pos += 1
                continue
            if pos >= offset + height:
                break

            local_start = max(0, offset - pos)
            local_end = min(span, offset + height - pos)
            lines.extend(await self._lines_for_file_range(index, width, local_start, local_end))
            pos = file_end
            if index + 1 < len(self._slots) and len(lines) < height and pos <= offset + height:
                lines.append("")
                pos += 1
            if len(lines) >= height:
                break

        return lines[:height], offset, total


__all__ = [
    "DiffDisplayBlock",
    "DiffLine",
    "DiffLineKind",
    "DiffViewport",
    "FileDiff",
    "compute_file_diff",
    "compute_file_diff_sync",
    "render_diff_panel",
    "render_diff_panel_slice",
    "render_diff_summary_panel",
]
