"""Diff renderer — line numbers, headers, and huge-file fallback."""

import asyncio

from kagan.format.diff import (
    DiffDisplayBlock,
    compute_file_diff,
    render_diff_panel,
    render_diff_panel_slice,
    render_diff_summary_panel,
)
from tests.kagan.format._render import to_str


def test_render_diff_panel_shows_line_numbers_and_stats_header():
    diff = asyncio.run(compute_file_diff("src/widget.py", "alpha\nbeta\n", "alpha\ngamma\n"))
    assert diff is not None
    out = to_str(
        render_diff_panel("src/widget.py", diff.hunks, diff.added, diff.removed), width=100
    )
    assert "+1" in out
    assert "-1" in out
    assert "src/widget.py" in out
    assert "gamma" in out


def test_render_diff_panel_handles_new_file():
    diff = asyncio.run(compute_file_diff("new_file.py", "", "hello\nworld\n"))
    assert diff is not None
    out = to_str(render_diff_panel("new_file.py", diff.hunks, diff.added, diff.removed), width=100)
    assert "+2" in out
    assert "new_file.py" in out
    assert diff.removed == 0


def test_huge_file_renders_summary_panel():
    huge = "\n".join(f"line {i}" for i in range(10001))
    diff = asyncio.run(compute_file_diff("big.py", "", huge))
    assert diff is not None
    assert diff.is_summary
    assert diff.summary is not None
    out = to_str(render_diff_summary_panel("big.py", [diff.summary]), width=100)
    assert "File too large for inline diff" in out
    assert "big.py" in out
    assert "10001" in out


def test_build_diff_blocks_sync_summary_shape():
    block = DiffDisplayBlock(
        path="x.py",
        old_text="(0 lines)",
        new_text="(42 lines)",
        is_summary=True,
    )
    out = to_str(render_diff_summary_panel("x.py", [block]), width=80)
    assert "New file with 42 lines" in out


def test_virtualized_slice_highlights_only_visible_rows():
    body = "\n".join(f"line {i}" for i in range(200))
    diff = asyncio.run(compute_file_diff("big.py", body, body + "\nline 200"))
    assert diff is not None
    full = render_diff_panel_slice(diff, width=80)
    partial = render_diff_panel_slice(diff, width=80, table_row_start=50, table_row_end=60)
    assert len(partial) < len(full)
