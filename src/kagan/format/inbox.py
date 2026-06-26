"""Inbox view renderer — the urgency-ranked supervision queue (the default view).

Pure Rich: no I/O, no prompt-toolkit, no Harness. The session passes in the
already-ranked ``inbox_tasks()`` feed, the folded ``attention_counts()`` and the
repo name; this file only renders. Grouping is a pure pass over core's
``_PRECEDENCE`` (no re-rank, no second sort) — the same contract the old
``inbox_list.group_items`` held.

Glyphs follow DESIGN section 5's 5-symbol set, NOT the old TUI's 10-glyph palette
(the inbox_list ``_GLYPH`` table is superseded — flag for deletion on cutover).
"""

from typing import TYPE_CHECKING

from rich.align import Align
from rich.console import Group
from rich.table import Table
from rich.text import Text

from kagan.core import InboxItem  # noqa: TC001 — used at runtime in selectable_rows
from kagan.core.inbox import _PRECEDENCE
from kagan.format import _symbols as sym
from kagan.format._risk import risk_label, risk_style

if TYPE_CHECKING:
    from rich.console import RenderableType

# Section-header wording per signal (carried over from inbox_list._LABEL).
_LABEL: dict[str, str] = {
    "interrupted": "interrupted · runner died · re-run",
    "drift": "drift · edited outside scope",
    "ci-failed": "ci failed · back to you",
    "needs-you": "needs you",
    "intake": "intake · pin decisions",
    "review": "review",
    "ready": "ready · your push",
    "validating": "validating",
    "pr-open": "in review · on github",
    "running": "running",
    "done": "done today",
}

# Signal -> the 5-symbol set (DESIGN section 5 / Appendix A). Replaces the TUI's
# 10-glyph palette: drift/ci use the blocker/note symbols, in-flight states use
# the working/reviewing symbols, done/ready use the pass check.
_GLYPH: dict[str, str] = {
    "interrupted": sym.BLOCKER,
    "drift": sym.NOTE,
    "ci-failed": sym.BLOCKER,
    "needs-you": sym.NEEDS_YOU,
    "intake": sym.NEEDS_YOU,
    "review": sym.IN_REVIEW,
    "ready": sym.DONE,
    "validating": sym.REVIEWING,
    "pr-open": sym.IN_REVIEW,
    "running": sym.WORKING,
    "done": sym.DONE,
}

# Per-signal semantic style names (resolved by KAGAN_THEME, not raw color literals).
_COLOR: dict[str, str] = {
    "interrupted": "blocker",
    "drift": "blocker",
    "ci-failed": "blocker",
    "needs-you": "needs-you",
    "intake": "needs-you",
    "review": "in-review",
    "ready": "done",
    "validating": "reviewing",
    "pr-open": "in-review",
    "running": "running",
    "done": "secondary",
}

# The next-action line per signal, shown indented + dim under the row (DESIGN §5:
# "enter → review"). The action is its OWN line, never crammed into the inline meta.
_ROW_ACTION: dict[str, str] = {
    "interrupted": "r re-run · same worktree",
    "drift": "s send back · a allow scope",
    "ci-failed": "r re-run · same worktree",
    "needs-you": "enter → answer",
    "intake": "enter → pin decisions",
    "review": "enter → review",
    "ready": "p copy push",
}

# Header buckets — every glyph from the one palette, one meaning each: need-you is
# the ● the rows also use; live is ◷ working (NOT ● — that stays needs-you only).
_HEADER_LABELS: tuple[tuple[str, str, str], ...] = (
    ("drift", sym.NOTE, "drift"),
    ("needs_you", sym.NEEDS_YOU, "need you"),
    ("review", sym.IN_REVIEW, "review"),
    ("ready", sym.DONE, "ready"),
    ("live", sym.WORKING, "live"),
)

_FULL_LOGO = """\
█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █
█▀▄  █▀█  █▄█  █▀█  █ ▀▄█"""


def _group_items(items: list[InboxItem]) -> list[tuple[str, list[InboxItem]]]:
    """Group already-ranked items by signal in precedence order (no re-sort)."""
    groups: list[tuple[str, list[InboxItem]]] = []
    for signal in _PRECEDENCE:
        members = [item for item in items if item.signal == signal]
        if members:
            groups.append((signal, members))
    return groups


def selectable_rows(items: list[InboxItem]) -> list[InboxItem]:
    """Flat list of rows in render order — the navigator maps a cursor index to a
    task id through this, so render order and selection order can never drift."""
    rows: list[InboxItem] = []
    for _signal, members in _group_items(items):
        rows.extend(members)
    return rows


def _meta(item: InboxItem) -> str:
    """ONE signal-specific detail for the inline row tail (the action moves to its
    own line — see ``_ROW_ACTION``). The running heartbeat is the running detail."""
    detail = _row_detail(item)
    return f"  · {detail}" if detail else ""


def _row_detail(item: InboxItem) -> str | None:
    """The single most signal-specific clause for the inline tail (DESIGN §5: cap
    inline meta to one detail). Drift/ci/needs-you carry their own note; a running
    row carries the liveness heartbeat; otherwise the freshest progress clause."""
    if item.signal == "running":
        return "♥ alive"
    for detail in (item.drift_note, item.remote_ci_detail, item.needs_you_question):
        if detail:
            return detail
    for clause in (item.eta, item.resume_point, item.since_you_left):
        if clause:
            return clause
    return None


def render_header(
    counts: dict[str, int],
    repo: str,
    *,
    quiet: bool = False,
    branded: bool = False,
) -> RenderableType:
    """Repository identity on the left and the live state summary on the right."""
    parts = [
        f"{glyph}{counts[key]} {label}" for key, glyph, label in _HEADER_LABELS if counts.get(key)
    ]
    left = Text()
    if branded:
        left.append("ᘚᘛ kagan", style="brand")
    show_repo = repo.casefold() != "kagan" or not branded
    if quiet and repo.casefold() == "kagan":
        show_repo = False
    if show_repo:
        if branded:
            left.append(" · ", style="secondary")
        left.append(repo, style="bold")
    right = Text("all quiet" if quiet else " · ".join(parts), style="header-status")
    header = Table.grid(expand=True, padding=0)
    header.add_column()
    header.add_column(justify="right")
    header.add_row(left, right)
    return header


def render_coach(coach: str) -> Text:
    """Wrap the precomputed coach_hint(items) line; never recompute the top item."""
    return Text(coach, style="secondary")


def render_inbox(
    items: list[InboxItem],
    counts: dict[str, int],
    repo: str,
    *,
    coach: str,
    cursor: int | None = None,
    standing: str | None = None,
    compact: bool = False,
) -> RenderableType:
    """The whole view: header + coach + grouped sections (or the empty state).

    ``cursor`` indexes into ``selectable_rows`` (headers are not selectable);
    ``standing`` is the empty-state stats sentence shown when there are no items.
    """
    header = render_header(
        counts,
        repo,
        quiet=not items,
        branded=bool(items) or compact,
    )
    body = render_inbox_body(
        items,
        coach=coach,
        cursor=cursor,
        standing=standing,
        compact=compact,
    )
    return Group(header, body)


def render_inbox_body(
    items: list[InboxItem],
    *,
    coach: str,
    cursor: int | None = None,
    standing: str | None = None,
    compact: bool = False,
) -> RenderableType:
    """Inbox content without shell chrome, so the session can pin header/footer."""
    if not items:
        return _render_empty_body(standing, compact=compact)

    blocks: list[RenderableType] = [render_coach(coach), Text("")]
    flat_index = 0
    for signal, members in _group_items(items):
        label = _LABEL.get(signal, signal)
        blocks.append(Text(f"{label} ──── {len(members)}", style="secondary"))
        glyph = _GLYPH.get(signal, "·")
        color = _COLOR.get(signal, "secondary")
        for item in members:
            focused = cursor is not None and cursor == flat_index
            blocks.extend(_render_row(item, glyph, color, focused=focused))
            flat_index += 1
        blocks.append(Text(""))
    return Group(*blocks)


def _render_row(item: InboxItem, glyph: str, color: str, *, focused: bool) -> list[RenderableType]:
    """The row line + (when the signal has one) its next action on an indented dim
    line below — DESIGN §5 keeps the action off the packed meta tail."""
    prefix = f"{sym.CURSOR} " if focused else "  "
    line = Text(prefix, style="bold" if focused else "")
    line.append(f"{glyph} ", style=color)
    line.append(item.title, style="bold" if focused else "")
    line.append(f"  {item.task_id}", style="secondary")
    # Lever 4: surface the tier on the row; high reads red (DESIGN section 5).
    if item.risk != "medium":
        line.append(f"  {risk_label(item.risk)}", style=risk_style(item.risk))
    meta = _meta(item)
    if meta:
        line.append(meta, style="secondary")
    rendered: list[RenderableType] = [line]
    action = _ROW_ACTION.get(item.signal)
    if action:
        rendered.append(Text(f"     {action}", style="secondary"))
    return rendered


def _render_empty_body(
    standing: str | None,
    *,
    compact: bool,
) -> RenderableType:
    blocks: list[RenderableType] = []
    if not compact:
        blocks.extend((Align.center(Text(_FULL_LOGO, style="brand")), Text("")))
    blocks.extend(
        (
            Align.center(Text("Nothing needs you right now.", style="bold")),
            Text(""),
        )
    )
    if standing:
        blocks.append(Align.center(Text(standing, style="secondary")))
    return Group(*blocks)


__all__ = [
    "render_coach",
    "render_header",
    "render_inbox",
    "render_inbox_body",
    "selectable_rows",
]
