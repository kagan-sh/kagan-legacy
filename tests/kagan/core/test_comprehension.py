"""Lever 1: the risk-scaled comprehension prompt set (pure lookups)."""

from kagan.core.comprehension import (
    COMPREHENSION_PROMPTS,
    prompts_for_risk,
    required_keys,
)


def test_low_risk_has_no_prompts():
    # Low auto-satisfies the comprehension lock (lever-4 invariant; DESIGN §8).
    assert prompts_for_risk("low") == []
    assert required_keys("low") == []


def test_medium_and_high_prompt_counts():
    assert required_keys("medium") == ["postcondition", "what_breaks"]
    assert required_keys("high") == [
        "postcondition",
        "delta",
        "dependencies",
        "security",
        "gotchas",
    ]


def test_unknown_tier_falls_back_to_medium():
    assert prompts_for_risk("nonsense") == COMPREHENSION_PROMPTS["medium"]
    assert required_keys("nonsense") == ["postcondition", "what_breaks"]
