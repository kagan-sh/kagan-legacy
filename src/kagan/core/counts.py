"""Attention counts for the shell header (TUI-SHELL-01). Pure read over tasks.

The header shows the same urgency buckets the Inbox sorts by, so the totals match
the list. Buckets are derived from the inbox signal so drift outranks raw state.
"""

from kagan.core.inbox import _signal
from kagan.core.models import Task  # noqa: TC001 — used at runtime over the task list

# Inbox signal -> header bucket. needs-you folds in intake; live folds the
# three in-flight states (running/validating/pr-open). done/ci-failed land in
# no header bucket (ci-failed shows in the inbox row, not the header total).
_BUCKETS: dict[str, str] = {
    "drift": "drift",
    "needs-you": "needs_you",
    "intake": "needs_you",
    "review": "review",
    "ready": "ready",
    "running": "live",
    "validating": "live",
    "pr-open": "live",
}


def attention_counts(tasks: list[Task]) -> dict[str, int]:
    counts = {"drift": 0, "needs_you": 0, "review": 0, "ready": 0, "live": 0}
    for task in tasks:
        bucket = _BUCKETS.get(_signal(task))
        if bucket is not None:
            counts[bucket] += 1
    return counts
