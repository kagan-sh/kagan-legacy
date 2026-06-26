"""Structural debt budget (lever 9) — the blind spot across diffs.

kagan's other levers verify *this* diff (correct/secure/understood) but are blind
to the codebase rotting *across* diffs. This computes a best-effort, language-
agnostic structural-debt signal from real signals only — DUPLICATION + CHURN —
with NO hand-rolled "novelty" term: gaming a novelty score pushes the agent
toward boilerplate (the GitClear pathology DESIGN lever 9 names). Both terms here
DECREASE when code is consolidated, so deleting a copy lowers the score; they
cannot be gamed by writing more boilerplate.

Two signals, two homes:
  - ``changeset_debt`` is the per-changeset observational number (duplication +
    churn over a unified diff's ADDED lines). Pure text, no parser. The primitive
    for a future live-diff surface — not yet wired into the scorecard.
  - ``cumulative_scope_debt`` is the cross-diff churn for a scope, derived from
    ledger history (how many prior tasks rewrote files under this scope's globs).
    A rising number routes the rotting area into heavier review by ESCALATING its
    risk tier (lever 4) — never a block, never a self-serve override.

No DB (DESIGN lever 9 / TUI-LEDGER-04): every number is computed over the diff
text or the already-loaded ledger Tasks, never a new persisted store.
"""

from pydantic import BaseModel

from kagan.core.models import Task  # noqa: TC001 — used at runtime in the type hints
from kagan.core.paths import matches_scope
from kagan.core.risk import TIERS

# A duplicate is a window of this many consecutive normalized added lines that
# recurs. 5 is the standard shingle size: long enough that incidental one-liners
# (closing braces, blank lines) do not register, short enough to catch a
# copy-pasted block.
_SHINGLE = 5


class ChangesetDebt(BaseModel):
    """The per-changeset debt signal (observational). ``score`` rises with churn
    and duplication and falls when a change consolidates code."""

    churn: int  # added lines in the diff
    duplicated: int  # added lines that belong to a repeated window
    score: int  # churn + duplicated (duplication weighted by counting twice)


def _added_lines(diff_text: str) -> list[str]:
    # Added lines from a unified diff, normalized (whitespace-trimmed) so that
    # re-indented copies still register as duplicates. Skips the +++ file header
    # and drops blank lines so trivial spacing never inflates the count.
    out: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            text = line[1:].strip()
            if text:
                out.append(text)
    return out


def changeset_debt(diff_text: str) -> ChangesetDebt:
    """Pure duplication + churn over a unified diff's added lines (lever 9). No
    novelty term — deleting a duplicate lowers the score, so it cannot be gamed by
    writing boilerplate."""
    added = _added_lines(diff_text)
    churn = len(added)
    duplicated = _duplicated_line_count(added)
    return ChangesetDebt(churn=churn, duplicated=duplicated, score=churn + duplicated)


def _duplicated_line_count(added: list[str]) -> int:
    # Count added lines that fall inside a repeated k-line window. A window is the
    # tuple of `_SHINGLE` consecutive normalized lines; any window seen >= 2x marks
    # all its lines as duplicated. Short changes (< k lines) have no window and so
    # never register duplication — a small unique change is debt-cheap by design.
    if len(added) < _SHINGLE:
        return 0
    windows: dict[tuple[str, ...], list[int]] = {}
    for i in range(len(added) - _SHINGLE + 1):
        key = tuple(added[i : i + _SHINGLE])
        windows.setdefault(key, []).append(i)
    duplicated: set[int] = set()
    for starts in windows.values():
        if len(starts) >= 2:
            for start in starts:
                duplicated.update(range(start, start + _SHINGLE))
    return len(duplicated)


def _touched_files(task: Task) -> set[str]:
    # M1: prefer the real harvested changed-file set; fall back to finding locations
    # for tasks harvested before changed_files existed (graceful migration). The old
    # proxy under-counted — a churning scope with no findings read as zero (turkey
    # problem); changed_files is the actual churn signal.
    if task.changed_files:
        return set(task.changed_files)
    return {f.location for f in task.findings if f.location}


def _scope_touch_count(scope: list[str], tasks: list[Task]) -> int:
    # Cross-diff churn for a scope: how many prior tasks rewrote a file under this
    # scope's globs. Observational, not authoritative.
    globs = [s for s in scope if s]
    if not globs:
        return 0
    count = 0
    for task in tasks:
        if any(matches_scope(path, globs) for path in _touched_files(task)):
            count += 1
    return count


def cumulative_scope_debt(
    scope: list[str], tasks: list[Task], *, exclude_id: str | None = None
) -> int:
    """Cross-diff structural debt for a scope, derived from ledger history (lever
    9). Returns how many PRIOR tasks rewrote files under this scope — the rotting-
    area signal the per-diff gate is blind to. ``exclude_id`` drops the task being
    classified so it never counts itself. Best-effort and approximate (the ledger
    stores finding locations, not the full changed-file set)."""
    prior = [t for t in tasks if t.id != exclude_id]
    return _scope_touch_count(scope, prior)


def escalate_tier(base: str, cumulative: int, threshold: int | None) -> str:
    """Bump a risk tier UP one level when cumulative scope debt exceeds the
    threshold (lever 4 teeth). ONE-DIRECTIONAL: only ever raises (low->medium->
    high), never lowers. ``threshold is None`` disables escalation entirely, so an
    unconfigured repo behaves exactly like today. Never blocks, never refuses."""
    if threshold is None or cumulative <= threshold or base not in TIERS:
        return base
    idx = TIERS.index(base)
    return TIERS[min(idx + 1, len(TIERS) - 1)]


__all__ = [
    "ChangesetDebt",
    "changeset_debt",
    "cumulative_scope_debt",
    "escalate_tier",
]
