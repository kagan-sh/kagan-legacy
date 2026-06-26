"""Risk routing (lever 4) — the spine that keeps levers 1-3 proportionate.

Classifies a task's scope into a tier ("low"/"medium"/"high") from the repo's
declared path globs, and downgrades low-confidence findings to advisory per the
risk-routed confidence gate (DESIGN 3.8). Pure functions over data already on
the Task — no model call, no I/O. Glob matching reuses ``paths.glob_match``
(``fnmatch``), the same idiom scope values are written in.
"""

from kagan.core.models import Finding  # noqa: TC001 — used at runtime in downgrade
from kagan.core.paths import glob_match as _matches

TIERS = ("low", "medium", "high")
DEFAULT_TIER = "medium"

# Risk-routed confidence gate (DESIGN 3.8): a finding stays blocking only if its
# self-rated confidence clears the tier bar. low-risk demands high confidence
# (>=8 stays blocking); high-risk surfaces even tentative findings (>=2 stays).
# A finding with confidence None is never downgraded (no self-rating to judge).
_CONFIDENCE_BAR: dict[str, int] = {"low": 8, "medium": 5, "high": 2}
_DOWNGRADE_SOURCES = frozenset({"ai-review", "security"})


def classify(scope: list[str], tiers: dict[str, list[str]]) -> str:
    """Tier for a task's scope. HIGH if ANY scope path matches a high glob; else
    LOW only if EVERY scope path matches a low glob; else MEDIUM (the default for
    unconfigured repos and mixed scopes — they behave like today)."""
    paths = [s for s in scope if s]
    if not tiers or not paths:
        return DEFAULT_TIER
    high = tiers.get("high") or []
    low = tiers.get("low") or []
    if any(_matches(p, high) for p in paths):
        return "high"
    if low and all(_matches(p, low) for p in paths):
        return "low"
    return DEFAULT_TIER


def downgrade_low_confidence(findings: list[Finding], risk: str) -> None:
    """Downgrade (never drop) ai-review/security findings below the tier's
    confidence bar to advisory ("question"), so the signal stays visible and
    adjudicable but no longer locks approve. Mutates findings in place; only
    ``severity`` changes. ``confidence is None`` findings are left untouched."""
    bar = _CONFIDENCE_BAR.get(risk, _CONFIDENCE_BAR[DEFAULT_TIER])
    for f in findings:
        if (
            f.source in _DOWNGRADE_SOURCES
            and f.severity == "blocking"
            and f.confidence is not None
            and f.confidence < bar
        ):
            f.severity = "question"


__all__ = ["DEFAULT_TIER", "TIERS", "classify", "downgrade_low_confidence"]
