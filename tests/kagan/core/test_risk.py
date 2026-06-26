"""Risk routing (lever 4) + the risk-routed confidence gate (DESIGN 3.8).

classify() turns a task's scope into a tier; the rules encode WHY each tier is
chosen (Rule 9): HIGH if ANY path is high (one auth file taints the task), LOW
only if EVERY path is low (a mixed scope is never fast-tracked), MEDIUM as the
default so unconfigured repos behave like today. downgrade_low_confidence keeps
the finding visible but flips it advisory below the tier's confidence bar.
"""

from kagan.core.models import Finding
from kagan.core.risk import DEFAULT_TIER, classify, downgrade_low_confidence

_TIERS = {"high": ["src/auth/**", "migrations/**"], "low": ["docs/**"]}


def test_high_if_any_scope_path_matches_a_high_glob():
    # One high-risk path taints the whole task even when the rest is low — the
    # autonomy ladder routes by the worst thing touched, not the average.
    assert classify(["docs/x.md", "src/auth/login.py"], _TIERS) == "high"
    assert classify(["migrations/0007.py"], _TIERS) == "high"


def test_low_only_when_every_scope_path_matches_a_low_glob():
    # Fast-approve is earned only if EVERY path is low; a single non-low path
    # drops it to medium so a docs+code mix never skips the gate.
    assert classify(["docs/a.md", "docs/b.md"], _TIERS) == "low"
    assert classify(["docs/a.md", "src/util.py"], _TIERS) == "medium"


def test_medium_for_unmatched_scope():
    # A path under neither high nor low globs is medium (the default ceremony).
    assert classify(["src/util.py"], _TIERS) == "medium"


def test_unconfigured_repo_is_medium():
    # No risk_tiers declared -> every task is medium, i.e. today's behaviour.
    assert classify(["src/auth/login.py"], {}) == DEFAULT_TIER
    assert classify([], _TIERS) == DEFAULT_TIER


def test_empty_scope_strings_are_ignored():
    # A bare "" scope entry (the gate's catch-all) is not a real path and must
    # not be mistaken for a low-glob match.
    assert classify([""], _TIERS) == DEFAULT_TIER


def _finding(severity: str, *, source: str, confidence: int | None) -> Finding:
    return Finding(
        id="f", severity=severity, location=".", message="m", source=source, confidence=confidence
    )


def test_low_confidence_finding_downgraded_on_low_risk_but_kept():
    # DESIGN 3.8: low risk demands high confidence (>=8). A confidence-5 ai-review
    # finding is below the bar -> downgraded to advisory, but still present (signal
    # kept, not dropped) so the human can still see and adjudicate it.
    findings = [_finding("blocking", source="ai-review", confidence=5)]
    downgrade_low_confidence(findings, "low")
    assert len(findings) == 1
    assert findings[0].severity == "question"


def test_same_finding_stays_blocking_on_high_risk():
    # DESIGN 3.8: high risk surfaces even tentative findings (bar 2), so the same
    # confidence-5 finding stays blocking — the business rule flips with the tier.
    findings = [_finding("blocking", source="ai-review", confidence=5)]
    downgrade_low_confidence(findings, "high")
    assert findings[0].severity == "blocking"


def test_none_confidence_is_never_downgraded():
    # A finding with no self-rating (None) is left alone — treating None as 0 would
    # silently downgrade every machine/security finding regardless of tier.
    findings = [_finding("blocking", source="security", confidence=None)]
    downgrade_low_confidence(findings, "low")
    assert findings[0].severity == "blocking"


def test_machine_findings_are_not_downgraded():
    # Only ai-review/security findings carry a confidence to gate on; a machine
    # scope/secret finding is never relaxed by the confidence pass.
    findings = [_finding("blocking", source="machine", confidence=1)]
    downgrade_low_confidence(findings, "low")
    assert findings[0].severity == "blocking"
