"""The DESIGN section 5 five-symbol set, shared by every format renderer.

One palette so the inbox, gate, ship, workspaces, and intake views never drift.
``●`` needs you · ``▸`` in review · ``✓`` done/passed · ``✗`` blocker · ``○`` optional;
Appendix A adds ``◷`` working · ``⟳`` reviewing/re-run · ``⚠`` note.

``CURSOR`` is the ONE selection cursor (every focusable list — inbox / intake /
new-task / picker — uses it; never ``▸``, which is reserved for the in-review state).
Smoke verification reuses ``✓`` / ``○`` from the set, not a sixth ``☑`` glyph. Service
health is plain text, not a palette glyph, so the reserved ``●`` keeps one meaning.
"""

NEEDS_YOU = "●"
IN_REVIEW = "▸"
DONE = "✓"
BLOCKER = "✗"
OPTIONAL = "○"
WORKING = "◷"
REVIEWING = "⟳"
NOTE = "⚠"
CURSOR = "›"  # noqa: RUF001 — the single selection cursor (DESIGN §5)

__all__ = [
    "BLOCKER",
    "CURSOR",
    "DONE",
    "IN_REVIEW",
    "NEEDS_YOU",
    "NOTE",
    "OPTIONAL",
    "REVIEWING",
    "WORKING",
]
