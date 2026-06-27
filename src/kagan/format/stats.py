"""Stats view renderer — the in-session `stats` action (lever 7).

Pure Rich. ``render_scorecard`` IS the stats screen: the calm PRIVATE outcome mirror
(DESIGN §stats) — durability / clean-merges / comprehension / review-caught /
cycle-time as plain sentences, "just for you", never anxious bars and never a team
metric. (The old operational tally ``render_stats`` was dropped from this view in
Phase 12c — a cockpit reading, not the calm mirror; not relocated, YAGNI.)

The Scorecard is computed in ``kagan.core.stats``; this file only renders. None /
empty metrics render as "—" or N/A (never a fabricated 0).
"""

from typing import TYPE_CHECKING

from rich.console import Group
from rich.text import Text

from kagan.format._layout import header_with_rail, label_value_rows

if TYPE_CHECKING:
    from rich.console import RenderableType

    from kagan.core.api import Scorecard

# Cycle-time tiers in display order, with the DESIGN-mockup short labels.
_CYCLE_TIERS: tuple[tuple[str, str], ...] = (("low", "low"), ("medium", "med"), ("high", "high"))


def _human_duration(seconds: float) -> str:
    minutes = seconds / 60
    if minutes < 60:
        return f"{round(minutes)}m"
    hours = minutes / 60
    if hours < 24:
        return f"{round(hours)}h"
    return f"{round(hours / 24)}d"


# Each metric is a (label, value) pair so the value column aligns by display width
# (DESIGN §3.3) — no embedded space runs to hand-pad the label column.
def _durability_value(durability: tuple[int, int] | None) -> str:
    if durability is None or durability[1] == 0:
        return "too new to tell — kagan never merges, so this is best-effort"
    untouched, observed = durability
    return f"{untouched} of {observed} still untouched after two weeks (best-effort)"


def _clean_merges_value(card: Scorecard) -> str:
    if card.cfr_total is None or card.cfr_total == 0:
        return "N/A — no PR CI seen yet (needs gh + an open PR)"
    passed = card.cfr_total - (card.cfr_failed or 0)
    return f"{passed} of {card.cfr_total} passed CI after opening"


def _comprehension_value(card: Scorecard) -> str:
    if card.comprehension_asked == 0:
        return "N/A — no notes asked yet (low-risk skips the note)"
    thin = card.comprehension_asked - card.comprehension_first_try
    first = card.comprehension_first_try
    base = f"{first} of {card.comprehension_asked} answered first try"
    return base + (f" · {thin} were re-recorded" if thin else "")


def _review_caught_value(card: Scorecard) -> str:
    n = card.review_caught
    if n == 0:
        return "none yet — no validator bugs upheld"
    bugs = "bug" if n == 1 else "bugs"
    # Not "before they shipped" — an agreed blocker may ship as a known issue (F20/F26).
    # This counts real bugs the validator surfaced and the human upheld, fixed or not.
    return f"{n} real {bugs} surfaced and upheld"


def _debt_value(card: Scorecard) -> str:
    # Lever 9 (PRIVATE): the rotting-area trend. Names the scopes most rewritten
    # across tasks so the human sees where heavier review is auto-routing. Never a
    # block, never a team metric — an observational nudge "just for you".
    debt = card.debt_by_scope
    if not debt:
        return "— (no scope rewritten enough to track yet)"
    top = sorted(debt.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    parts = [f"{scope} x{n}" for scope, n in top]
    return "   ·   ".join(parts) + " rewritten (observational)"


def _cycle_value(card: Scorecard) -> str:
    cycle = card.cycle_seconds_by_risk
    if not cycle:
        return "— (no tasks have reached ready yet)"
    parts = [
        f"{label} {_human_duration(cycle[tier])}" for tier, label in _CYCLE_TIERS if tier in cycle
    ]
    return "   ·   ".join(parts)


# The closing reflection that ends the private mirror (DESIGN §stats) — the read,
# not the longest day, is what the research finds durable. Always shown.
_DURABLE_WORK_LINE = (
    "The most durable work wasn't the longest day — it was the read-before-approve."
)


def render_scorecard(
    card: Scorecard,
    repo: str,
    durability: tuple[int, int] | None = None,
    *,
    reflection: str | None = None,
) -> RenderableType:
    """The calm private outcome mirror — sentences, not bars (DESIGN §stats).

    The "just for you" rail is flush to the real width via ``header_with_rail`` (a
    2-col borderless table) — never a literal 54-space string that drifts off-100.
    A brand-new repo (nothing shipped, no signals) shows a single calm line instead
    of five dashes. ``reflection`` is the private supervision-hours line the session
    derives from the coach data; the durable-work close always trails it.
    """
    if _is_too_new(card, durability):
        empty = header_with_rail(f"{repo}", "just for you")
        return Group(
            empty,
            Text(""),
            Text(
                "Too new to mirror yet — ship a few tasks and this fills in.",
                style="secondary",
            ),
        )

    header = header_with_rail(f"{repo} · {card.shipped} shipped in 30 days", "just for you")

    metrics = label_value_rows(
        [
            ("durability", _durability_value(durability)),
            ("clean merges", _clean_merges_value(card)),
            ("comprehension", _comprehension_value(card)),
            ("review caught", _review_caught_value(card)),
            ("debt trend", _debt_value(card)),
        ]
    )
    cycle = label_value_rows([("cycle time", _cycle_value(card))])

    close: list[RenderableType] = []
    if reflection:
        close.append(Text(reflection, style="secondary"))
    close.append(Text(_DURABLE_WORK_LINE, style="secondary"))

    return Group(header, Text(""), metrics, Text(""), cycle, Text(""), *close)


def _is_too_new(card: Scorecard, durability: tuple[int, int] | None) -> bool:
    """A brand-new repo: nothing shipped, no comprehension asked, no review caught,
    no cycle data, no observed durability — five dashes would read as 0/vanity."""
    return (
        card.shipped == 0
        and card.comprehension_asked == 0
        and card.review_caught == 0
        and not card.cycle_seconds_by_risk
        and (durability is None or durability[1] == 0)
    )


__all__ = ["render_scorecard"]
