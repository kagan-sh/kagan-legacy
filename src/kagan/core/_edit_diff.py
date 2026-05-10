"""kagan.core._edit_diff -- CRLF/BOM/overlap edit helpers.

Pure helper module -- no MCP coupling.

Provides normalize_line_endings, detect_bom, reapply_line_endings,
merge_overlapping_edits, the Edit dataclass and EditConflict exception.
Handles Unicode BOM detection (UTF-8/16/32 variants), EOL normalization
(CRLF/LF/CR), and fuzzy-match overlap detection for concurrent edit merging.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Edit:
    """A single text replacement expressed as (old_text, new_text) pair.

    Both fields use LF line endings.  The fs toolset normalizes CRLF to LF
    before constructing Edit instances and reapplies the original EOL style
    after applying edits.
    """

    old_text: str
    new_text: str


class EditConflict(Exception):
    """Raised when two edits target the same region with different content."""


# ---------------------------------------------------------------------------
# BOM detection
# ---------------------------------------------------------------------------

_BOMS: list[tuple[bytes, str]] = [
    (b"\xff\xfe\x00\x00", "utf-32-le"),  # UTF-32-LE (must precede UTF-16-LE)
    (b"\x00\x00\xfe\xff", "utf-32-be"),  # UTF-32-BE
    (b"\xff\xfe", "utf-16-le"),  # UTF-16-LE
    (b"\xfe\xff", "utf-16-be"),  # UTF-16-BE
    (b"\xef\xbb\xbf", "utf-8-sig"),  # UTF-8-with-BOM
]


def detect_bom(raw_bytes: bytes) -> tuple[bytes | None, str]:
    """Return (bom_bytes_or_None, encoding_name).

    Checks the four BOM patterns documented by Unicode (section 2.13):
    UTF-32-LE/BE, UTF-16-LE/BE, UTF-8-with-BOM.
    UTF-32 variants must be tested before UTF-16-LE because the byte
    sequence FF FE 00 00 shares a prefix with FF FE (UTF-16-LE BOM).

    Returns (None, "utf-8") when no BOM is found.
    """
    for bom, encoding in _BOMS:
        if raw_bytes.startswith(bom):
            return bom, encoding
    return None, "utf-8"


# ---------------------------------------------------------------------------
# EOL helpers
# ---------------------------------------------------------------------------


def normalize_line_endings(content: str) -> tuple[str, str]:
    """Detect EOL style and return (lf_normalized_text, original_eol).

    Detection rule:
    - If the first CRLF appears before the first bare LF -> CRLF file.
    - Otherwise -> LF file.
    - A file with no line endings at all -> "lf" (no-op for reapply).

    Mixed-EOL files are treated as "lf" in the canonical form; reapply
    will not convert them back to a consistent style (they were already
    inconsistent).
    """
    crlf_idx = content.find("\r\n")
    lf_idx = content.find("\n")

    if lf_idx == -1:
        # No LF at all -- either pure CR (very rare) or no line endings.
        original_eol = "lf"
    elif crlf_idx == -1:
        original_eol = "lf"
    elif crlf_idx < lf_idx:
        original_eol = "crlf"
    else:
        # First LF comes before first CRLF -> mixed or LF-primary.
        original_eol = "lf"

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, original_eol


def reapply_line_endings(text: str, original_eol: str) -> str:
    """Convert LF-normalized text back to the original EOL style.

    When original_eol is "lf" (or anything other than "crlf"), this is
    a no-op.  Only "crlf" triggers replacement to avoid producing
    double-CRLF on a file that is already CRLF-clean.
    """
    if original_eol == "crlf":
        return text.replace("\n", "\r\n")
    return text


# ---------------------------------------------------------------------------
# Fuzzy normalization (ported from normalizeForFuzzyMatch in edit-diff.ts)
# ---------------------------------------------------------------------------
#
# Regex patterns are built from explicit code-point lists rather than from
# string literals containing the ambiguous characters themselves.  This keeps
# the source file free of non-ASCII literals that ruff RUF001 would flag.
#
# Smart single quotes: U+2018 U+2019 U+201A U+201B


def _char_class(codepoints: list[int]) -> re.Pattern[str]:
    """Build a regex [char-class] pattern from a list of Unicode codepoints."""
    chars = "".join(chr(cp) for cp in codepoints)
    return re.compile("[" + re.escape(chars) + "]")


# Smart single quotes (U+2018 U+2019 U+201A U+201B)
_RE_SMART_SINGLE: re.Pattern[str] = _char_class([0x2018, 0x2019, 0x201A, 0x201B])

# Smart double quotes (U+201C U+201D U+201E U+201F)
_RE_SMART_DOUBLE: re.Pattern[str] = _char_class([0x201C, 0x201D, 0x201E, 0x201F])

# Unicode dashes/hyphens: U+2010 hyphen, U+2011 NB-hyphen, U+2012 figure dash,
# U+2013 en-dash, U+2014 em-dash, U+2015 horizontal bar, U+2212 minus sign
_RE_DASHES: re.Pattern[str] = _char_class([0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212])

# Special Unicode spaces: U+00A0 NBSP, U+2002-U+200A various spaces,
# U+202F narrow NBSP, U+205F medium math space, U+3000 ideographic space
_RE_SPECIAL_SPACES: re.Pattern[str] = _char_class(
    [
        0x00A0,  # NO-BREAK SPACE
        0x2002,
        0x2003,
        0x2004,
        0x2005,
        0x2006,  # EN/EM/3-PER-EM/4-PER-EM/6-PER-EM SPACE
        0x2007,
        0x2008,
        0x2009,
        0x200A,  # FIGURE/PUNCTUATION/THIN/HAIR SPACE
        0x202F,  # NARROW NO-BREAK SPACE
        0x205F,  # MEDIUM MATHEMATICAL SPACE
        0x3000,  # IDEOGRAPHIC SPACE
    ]
)


def _normalize_for_fuzzy(text: str) -> str:
    """Normalize text for fuzzy matching.

    Applies progressive transformations:
    - NFKC Unicode normalisation.
    - Strip trailing whitespace from each line.
    - Smart quotes -> ASCII equivalents.
    - Unicode dashes/hyphens -> ASCII hyphen.
    - Special Unicode spaces -> regular space.
    """
    normalized = unicodedata.normalize("NFKC", text)
    # Strip trailing whitespace per line
    lines = normalized.split("\n")
    lines = [line.rstrip() for line in lines]
    normalized = "\n".join(lines)

    normalized = _RE_SMART_SINGLE.sub("'", normalized)
    normalized = _RE_SMART_DOUBLE.sub('"', normalized)
    normalized = _RE_DASHES.sub("-", normalized)
    normalized = _RE_SPECIAL_SPACES.sub(" ", normalized)

    return normalized


# ---------------------------------------------------------------------------
# Fuzzy find
# ---------------------------------------------------------------------------


@dataclass
class _FuzzyMatch:
    found: bool
    index: int
    match_length: int
    used_fuzzy: bool
    content_for_replacement: str


def _fuzzy_find(content: str, old_text: str) -> _FuzzyMatch:
    """Find old_text in content, exact-first then fuzzy."""
    exact_idx = content.find(old_text)
    if exact_idx != -1:
        return _FuzzyMatch(
            found=True,
            index=exact_idx,
            match_length=len(old_text),
            used_fuzzy=False,
            content_for_replacement=content,
        )

    fuzzy_content = _normalize_for_fuzzy(content)
    fuzzy_old = _normalize_for_fuzzy(old_text)
    fuzzy_idx = fuzzy_content.find(fuzzy_old)
    if fuzzy_idx == -1:
        return _FuzzyMatch(
            found=False,
            index=-1,
            match_length=0,
            used_fuzzy=False,
            content_for_replacement=content,
        )

    return _FuzzyMatch(
        found=True,
        index=fuzzy_idx,
        match_length=len(fuzzy_old),
        used_fuzzy=True,
        content_for_replacement=fuzzy_content,
    )


def _count_occurrences(content: str, old_text: str) -> int:
    fuzzy_content = _normalize_for_fuzzy(content)
    fuzzy_old = _normalize_for_fuzzy(old_text)
    return fuzzy_content.count(fuzzy_old)


# ---------------------------------------------------------------------------
# Overlap resolution for line-range edits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineEdit:
    """A line-range edit (1-indexed inclusive bounds).

    Used by merge_overlapping_edits when the caller thinks in terms of
    line numbers rather than text hunks.
    """

    start_line: int
    end_line: int
    replacement: str


def merge_overlapping_edits(edits: list[LineEdit]) -> list[LineEdit]:
    """Sort edits by line range and merge overlapping ones into single hunks.

    Raises EditConflict if two non-overlapping edits target the same line
    range but carry different replacement text.

    Algorithm:
    1. Sort by start_line, then end_line.
    2. Walk sequentially; if current edit starts within the previous edit's
       range, merge by extending end_line and concatenating replacements
       (separated by a newline if neither side ends/starts with one).
    3. Identical-range duplicates with same replacement are collapsed.
    4. Identical-range duplicates with different replacements raise EditConflict.
    """
    if not edits:
        return []

    sorted_edits = sorted(edits, key=lambda e: (e.start_line, e.end_line))
    merged: list[LineEdit] = [sorted_edits[0]]

    for current in sorted_edits[1:]:
        last = merged[-1]

        # Exact same range -- identical is fine, different is a conflict.
        if current.start_line == last.start_line and current.end_line == last.end_line:
            if current.replacement != last.replacement:
                raise EditConflict(
                    f"Conflicting edits on lines {last.start_line}-{last.end_line}: "
                    "two different replacements for the same range."
                )
            # Identical duplicate -- skip.
            continue

        # Overlap check: current starts inside last's range.
        if current.start_line <= last.end_line:
            # Merge: extend to whichever end_line is larger.
            new_end = max(last.end_line, current.end_line)
            # Join replacements; ensure a single newline between them.
            needs_sep = not last.replacement.endswith("\n") and not current.replacement.startswith(
                "\n"
            )
            sep = "\n" if needs_sep else ""
            new_replacement = last.replacement + sep + current.replacement
            merged[-1] = LineEdit(
                start_line=last.start_line,
                end_line=new_end,
                replacement=new_replacement,
            )
        else:
            merged.append(current)

    return merged


# ---------------------------------------------------------------------------
# Core apply logic (text-hunk edits, not line-range)
# ---------------------------------------------------------------------------


@dataclass
class _MatchedEdit:
    edit_index: int
    match_index: int
    match_length: int
    new_text: str


def apply_edits_to_normalized_content(
    normalized_content: str,
    edits: list[Edit],
    path: str,
) -> tuple[str, str]:
    """Apply one or more old->new text replacements to LF-normalized content.

    Returns (base_content, new_content) where base_content is either the
    original normalized_content or the fuzzy-normalized version (when any
    edit required fuzzy matching).

    Raises ValueError for: empty old_text, not-found, duplicate matches,
    overlapping edits, no-change result.

    All edits are matched against the same original content.  Replacements
    are applied in reverse order so earlier offsets remain stable.
    """
    n = len(edits)

    # Normalize EOL in edit texts
    normed_edits = [
        Edit(
            old_text=e.old_text.replace("\r\n", "\n").replace("\r", "\n"),
            new_text=e.new_text.replace("\r\n", "\n").replace("\r", "\n"),
        )
        for e in edits
    ]

    # Validate non-empty old_text
    for i, edit in enumerate(normed_edits):
        if not edit.old_text:
            label = f"edits[{i}].old_text" if n > 1 else "old_text"
            raise ValueError(f"{label} must not be empty in {path}.")

    # Determine whether fuzzy matching is needed for any edit
    initial_matches = [_fuzzy_find(normalized_content, e.old_text) for e in normed_edits]
    needs_fuzzy = any(m.used_fuzzy for m in initial_matches)
    base_content = _normalize_for_fuzzy(normalized_content) if needs_fuzzy else normalized_content

    # Match each edit against base_content
    matched: list[_MatchedEdit] = []
    for i, edit in enumerate(normed_edits):
        result = _fuzzy_find(base_content, edit.old_text)
        if not result.found:
            if n == 1:
                raise ValueError(
                    f"Could not find the exact text in {path}. "
                    "The old text must match exactly including all whitespace and newlines."
                )
            raise ValueError(
                f"Could not find edits[{i}] in {path}. "
                "The oldText must match exactly including all whitespace and newlines."
            )

        occurrences = _count_occurrences(base_content, edit.old_text)
        if occurrences > 1:
            if n == 1:
                raise ValueError(
                    f"Found {occurrences} occurrences of the text in {path}. "
                    "The text must be unique. Please provide more context to make it unique."
                )
            raise ValueError(
                f"Found {occurrences} occurrences of edits[{i}] in {path}. "
                "Each oldText must be unique. Please provide more context to make it unique."
            )

        matched.append(
            _MatchedEdit(
                edit_index=i,
                match_index=result.index,
                match_length=result.match_length,
                new_text=edit.new_text,
            )
        )

    # Sort by position and check for overlaps
    matched.sort(key=lambda m: m.match_index)
    for j in range(1, len(matched)):
        prev = matched[j - 1]
        curr = matched[j]
        if prev.match_index + prev.match_length > curr.match_index:
            raise ValueError(
                f"edits[{prev.edit_index}] and edits[{curr.edit_index}] overlap in {path}. "
                "Merge them into one edit or target disjoint regions."
            )

    # Apply in reverse order to keep earlier offsets valid
    new_content = base_content
    for m in reversed(matched):
        end = m.match_index + m.match_length
        new_content = new_content[: m.match_index] + m.new_text + new_content[end:]

    if new_content == base_content:
        if n == 1:
            raise ValueError(
                f"No changes made to {path}. The replacement produced identical content. "
                "This might indicate an issue with special characters or "
                "the text not existing as expected."
            )
        raise ValueError(f"No changes made to {path}. The replacements produced identical content.")

    return base_content, new_content
