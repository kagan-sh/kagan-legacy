"""Lever 1: the risk-scaled comprehension prompt set (pure lookups)."""

from kagan.core.comprehension import (
    COMPREHENSION_PROMPTS,
    prompts_for_risk,
    prompts_for_task,
    required_keys,
    required_keys_for_task,
)
from kagan.core.models import Task

_GENERATED_MEDIUM = [
    ("postcondition", "How does the billing retry path behave after this diff?"),
    ("what_breaks", "What race could still lose a charge?"),
]

_GENERATED_HIGH = [
    ("postcondition", "Generated postcondition question?"),
    ("delta", "Generated delta question?"),
    ("dependencies", "Generated dependencies question?"),
    ("security", "Generated security question?"),
    ("gotchas", "Generated gotchas question?"),
]


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


def test_prompts_for_task_uses_generated_when_at_floor():
    task = Task(id="t", title="t", risk="medium", comprehension_prompts=_GENERATED_MEDIUM)
    assert prompts_for_task(task) == _GENERATED_MEDIUM
    assert required_keys_for_task(task) == ["postcondition", "what_breaks"]


def test_prompts_for_task_falls_back_when_generated_too_short():
    # Rule 8: a degraded generated set must never shrink the tier floor.
    short = [("postcondition", "Only one generated prompt?")]
    task = Task(id="t", title="t", risk="high", comprehension_prompts=short)
    assert prompts_for_task(task) == prompts_for_risk("high")
    assert required_keys_for_task(task) == required_keys("high")


def test_prompts_for_task_empty_generated_uses_static():
    task = Task(id="t", title="t", risk="medium")
    assert prompts_for_task(task) == prompts_for_risk("medium")


def test_prompts_for_task_low_risk_stays_empty_even_with_generated():
    task = Task(id="t", title="t", risk="low", comprehension_prompts=_GENERATED_MEDIUM)
    assert prompts_for_task(task) == []


def test_prompts_for_task_high_generated_at_floor():
    task = Task(id="t", title="t", risk="high", comprehension_prompts=_GENERATED_HIGH)
    assert prompts_for_task(task) == _GENERATED_HIGH
