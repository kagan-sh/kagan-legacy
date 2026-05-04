"""Contract tests for kagan.server.mcp.toolsets._edit_diff helpers.

Covers:
- detect_bom: UTF-8-BOM, UTF-16-LE/BE, UTF-32-LE/BE, no-BOM.
- normalize_line_endings: LF, CRLF, mixed, no-newlines.
- reapply_line_endings: LF and CRLF round-trip.
- apply_edits_to_normalized_content: basic replace, fuzzy match, empty
  old_text error, not-found error, duplicate error, overlap error,
  no-change error, multi-edit, reverse-order safety.
- merge_overlapping_edits: non-overlapping, overlapping merge, exact-
  duplicate collapse, conflict raises EditConflict.

All tests are pure unit tests — no I/O, no DB, no subprocess.
"""

from __future__ import annotations

import pytest

from kagan.server.mcp.toolsets._edit_diff import (
    Edit,
    EditConflict,
    LineEdit,
    apply_edits_to_normalized_content,
    detect_bom,
    merge_overlapping_edits,
    normalize_line_endings,
    reapply_line_endings,
)

pytestmark = [pytest.mark.contract]


# ---------------------------------------------------------------------------
# detect_bom
# ---------------------------------------------------------------------------


class TestDetectBom:
    def test_no_bom_returns_none_utf8(self) -> None:
        bom, enc = detect_bom(b"hello world")
        assert bom is None
        assert enc == "utf-8"

    def test_utf8_sig(self) -> None:
        bom, enc = detect_bom(b"\xef\xbb\xbfhello")
        assert bom == b"\xef\xbb\xbf"
        assert enc == "utf-8-sig"

    def test_utf16_le(self) -> None:
        bom, enc = detect_bom(b"\xff\xfe" + "hi".encode("utf-16-le"))
        assert bom == b"\xff\xfe"
        assert enc == "utf-16-le"

    def test_utf16_be(self) -> None:
        bom, enc = detect_bom(b"\xfe\xff" + "hi".encode("utf-16-be"))
        assert bom == b"\xfe\xff"
        assert enc == "utf-16-be"

    def test_utf32_le(self) -> None:
        # UTF-32-LE BOM must take priority over UTF-16-LE BOM (FF FE prefix)
        bom, enc = detect_bom(b"\xff\xfe\x00\x00rest")
        assert bom == b"\xff\xfe\x00\x00"
        assert enc == "utf-32-le"

    def test_utf32_be(self) -> None:
        bom, enc = detect_bom(b"\x00\x00\xfe\xffrest")
        assert bom == b"\x00\x00\xfe\xff"
        assert enc == "utf-32-be"

    def test_empty_bytes(self) -> None:
        bom, enc = detect_bom(b"")
        assert bom is None
        assert enc == "utf-8"


# ---------------------------------------------------------------------------
# normalize_line_endings
# ---------------------------------------------------------------------------


class TestNormalizeLineEndings:
    def test_lf_file_unchanged(self) -> None:
        text = "line1\nline2\nline3"
        normalized, eol = normalize_line_endings(text)
        assert eol == "lf"
        assert normalized == text

    def test_crlf_file_normalized(self) -> None:
        text = "line1\r\nline2\r\nline3"
        normalized, eol = normalize_line_endings(text)
        assert eol == "crlf"
        assert normalized == "line1\nline2\nline3"

    def test_mixed_eol_treated_as_lf(self) -> None:
        # First LF comes before first CRLF → detected as "lf"
        text = "line1\nline2\r\nline3"
        normalized, eol = normalize_line_endings(text)
        assert eol == "lf"
        assert "\r" not in normalized

    def test_no_newlines(self) -> None:
        text = "no newlines here"
        normalized, eol = normalize_line_endings(text)
        assert eol == "lf"
        assert normalized == text

    def test_trailing_newline_preserved(self) -> None:
        text = "line1\r\nline2\r\n"
        normalized, eol = normalize_line_endings(text)
        assert eol == "crlf"
        assert normalized == "line1\nline2\n"

    def test_bare_cr_normalized(self) -> None:
        text = "line1\rline2"
        normalized, _eol = normalize_line_endings(text)
        assert "\r" not in normalized

    def test_crlf_detected_when_first(self) -> None:
        # CRLF appears first → detected as CRLF even though bare LF follows
        text = "line1\r\nline2\nline3"
        _, eol = normalize_line_endings(text)
        assert eol == "crlf"


# ---------------------------------------------------------------------------
# reapply_line_endings
# ---------------------------------------------------------------------------


class TestReapplyLineEndings:
    def test_lf_is_noop(self) -> None:
        text = "a\nb\nc"
        assert reapply_line_endings(text, "lf") == text

    def test_crlf_converts(self) -> None:
        text = "a\nb\nc"
        assert reapply_line_endings(text, "crlf") == "a\r\nb\r\nc"

    def test_unknown_eol_is_noop(self) -> None:
        text = "a\nb"
        assert reapply_line_endings(text, "unknown") == text

    def test_round_trip_crlf(self) -> None:
        original = "hello\r\nworld\r\n"
        lf, eol = normalize_line_endings(original)
        restored = reapply_line_endings(lf, eol)
        assert restored == original

    def test_round_trip_lf(self) -> None:
        original = "hello\nworld\n"
        lf, eol = normalize_line_endings(original)
        restored = reapply_line_endings(lf, eol)
        assert restored == original


# ---------------------------------------------------------------------------
# apply_edits_to_normalized_content
# ---------------------------------------------------------------------------


class TestApplyEditsToNormalizedContent:
    def test_basic_replacement(self) -> None:
        content = "foo bar baz"
        edits = [Edit(old_text="bar", new_text="qux")]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert new == "foo qux baz"

    def test_multiline_replacement(self) -> None:
        content = "line1\nold line\nline3"
        edits = [Edit(old_text="old line", new_text="new line")]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert new == "line1\nnew line\nline3"

    def test_empty_old_text_raises(self) -> None:
        content = "foo"
        edits = [Edit(old_text="", new_text="bar")]
        with pytest.raises(ValueError, match="must not be empty"):
            apply_edits_to_normalized_content(content, edits, "test.txt")

    def test_empty_old_text_multi_raises(self) -> None:
        content = "foo"
        edits = [Edit(old_text="foo", new_text="x"), Edit(old_text="", new_text="y")]
        with pytest.raises(ValueError, match=r"edits\[1\]\.old_text must not be empty"):
            apply_edits_to_normalized_content(content, edits, "test.txt")

    def test_not_found_raises(self) -> None:
        content = "foo bar"
        edits = [Edit(old_text="missing", new_text="x")]
        with pytest.raises(ValueError, match="Could not find"):
            apply_edits_to_normalized_content(content, edits, "test.txt")

    def test_duplicate_raises(self) -> None:
        content = "foo foo foo"
        edits = [Edit(old_text="foo", new_text="bar")]
        with pytest.raises(ValueError, match="occurrences"):
            apply_edits_to_normalized_content(content, edits, "test.txt")

    def test_no_change_raises(self) -> None:
        content = "foo"
        edits = [Edit(old_text="foo", new_text="foo")]
        with pytest.raises(ValueError, match="No changes"):
            apply_edits_to_normalized_content(content, edits, "test.txt")

    def test_overlapping_edits_raise(self) -> None:
        content = "abcdefgh"
        # Both edits target overlapping substrings
        edits = [
            Edit(old_text="abcde", new_text="X"),
            Edit(old_text="cdefgh", new_text="Y"),
        ]
        with pytest.raises(ValueError, match="overlap"):
            apply_edits_to_normalized_content(content, edits, "test.txt")

    def test_multiple_disjoint_edits(self) -> None:
        content = "alpha beta gamma"
        edits = [
            Edit(old_text="alpha", new_text="ONE"),
            Edit(old_text="gamma", new_text="THREE"),
        ]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert new == "ONE beta THREE"

    def test_edits_applied_in_stable_order(self) -> None:
        # Provide edits in reverse positional order; result should still be correct.
        content = "AAA BBB CCC"
        edits = [
            Edit(old_text="CCC", new_text="3"),
            Edit(old_text="AAA", new_text="1"),
        ]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert new == "1 BBB 3"

    def test_file_without_trailing_newline(self) -> None:
        content = "line1\nline2"  # no trailing newline
        edits = [Edit(old_text="line2", new_text="line2_edited")]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert new == "line1\nline2_edited"

    def test_whitespace_only_edit(self) -> None:
        content = "foo  bar"
        edits = [Edit(old_text="foo  bar", new_text="foo bar")]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert new == "foo bar"

    def test_fuzzy_match_smart_quotes(self) -> None:
        # Content has curly quotes; old_text uses straight quotes — fuzzy should match.
        content = "He said “hello” to everyone"
        edits = [Edit(old_text='He said "hello" to everyone', new_text="He said hi to everyone")]
        _, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert "hi" in new

    def test_base_content_returned(self) -> None:
        content = "hello world"
        edits = [Edit(old_text="hello", new_text="hi")]
        base, new = apply_edits_to_normalized_content(content, edits, "test.txt")
        assert "hello" in base
        assert "hi" in new


# ---------------------------------------------------------------------------
# merge_overlapping_edits
# ---------------------------------------------------------------------------


class TestMergeOverlappingEdits:
    def test_empty_list(self) -> None:
        assert merge_overlapping_edits([]) == []

    def test_single_edit_passthrough(self) -> None:
        edits = [LineEdit(start_line=1, end_line=3, replacement="x")]
        assert merge_overlapping_edits(edits) == edits

    def test_non_overlapping_sorted(self) -> None:
        edits = [
            LineEdit(start_line=5, end_line=7, replacement="b"),
            LineEdit(start_line=1, end_line=3, replacement="a"),
        ]
        result = merge_overlapping_edits(edits)
        assert len(result) == 2
        assert result[0].start_line == 1
        assert result[1].start_line == 5

    def test_overlapping_merged(self) -> None:
        edits = [
            LineEdit(start_line=1, end_line=5, replacement="first"),
            LineEdit(start_line=4, end_line=8, replacement="second"),
        ]
        result = merge_overlapping_edits(edits)
        assert len(result) == 1
        assert result[0].start_line == 1
        assert result[0].end_line == 8
        assert "first" in result[0].replacement
        assert "second" in result[0].replacement

    def test_identical_duplicate_collapsed(self) -> None:
        edits = [
            LineEdit(start_line=2, end_line=4, replacement="same"),
            LineEdit(start_line=2, end_line=4, replacement="same"),
        ]
        result = merge_overlapping_edits(edits)
        assert len(result) == 1

    def test_conflict_raises(self) -> None:
        edits = [
            LineEdit(start_line=2, end_line=4, replacement="version_a"),
            LineEdit(start_line=2, end_line=4, replacement="version_b"),
        ]
        with pytest.raises(EditConflict):
            merge_overlapping_edits(edits)

    def test_adjacent_not_merged(self) -> None:
        # end_line=3, start_line=4 — adjacent but not overlapping
        edits = [
            LineEdit(start_line=1, end_line=3, replacement="a"),
            LineEdit(start_line=4, end_line=6, replacement="b"),
        ]
        result = merge_overlapping_edits(edits)
        assert len(result) == 2

    def test_multiple_overlaps_chained(self) -> None:
        # Three edits that chain-overlap into one
        edits = [
            LineEdit(start_line=1, end_line=4, replacement="A"),
            LineEdit(start_line=3, end_line=7, replacement="B"),
            LineEdit(start_line=6, end_line=10, replacement="C"),
        ]
        result = merge_overlapping_edits(edits)
        assert len(result) == 1
        assert result[0].start_line == 1
        assert result[0].end_line == 10
