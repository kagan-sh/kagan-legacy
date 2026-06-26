"""Lever 1: the risk-scaled comprehension prompt set (DESIGN §4 lever 1, §5).

Pure data + lookup, no I/O. The human answers a set of own-words prompts sized
to the task's risk tier (kipp /build explain 5-section structure, human-authored).
Approve stays locked until every required prompt for the tier has a substantive
answer. Low risk has no prompts — it auto-satisfies the lock (lever-4 invariant:
low/docs skips the comprehension lock; DESIGN §8).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kagan.core.models import Task

COMPREHENSION_PROMPTS: dict[str, list[tuple[str, str]]] = {
    "low": [],
    "medium": [
        ("postcondition", "What does this change do, end to end?"),
        ("what_breaks", "What could still break it?"),
    ],
    "high": [
        ("postcondition", "What does this change do, end to end?"),
        ("delta", "What changed vs before — the precise diff in behavior?"),
        ("dependencies", "What does it now depend on, and what depends on it?"),
        ("security", "What are the security implications — authz, input, secrets?"),
        ("gotchas", "What is non-obvious or easy to get wrong here?"),
    ],
}


def prompts_for_risk(risk: str) -> list[tuple[str, str]]:
    """The (key, question) prompts for a risk tier; an unknown tier maps to medium."""
    return COMPREHENSION_PROMPTS.get(risk, COMPREHENSION_PROMPTS["medium"])


def required_keys(risk: str) -> list[str]:
    """The prompt keys the tier requires answered before approve unlocks."""
    return [key for key, _ in prompts_for_risk(risk)]


def prompts_for_task(task: Task) -> list[tuple[str, str]]:
    """The (key, question) prompts for a task — generated when present and long
    enough for the tier, else the static risk-tier set."""
    static = prompts_for_risk(task.risk)
    generated = task.comprehension_prompts
    if static and generated and len(generated) >= len(static):
        return generated
    return static


def required_keys_for_task(task: Task) -> list[str]:
    """The prompt keys this task requires answered before approve unlocks."""
    return [key for key, _ in prompts_for_task(task)]
