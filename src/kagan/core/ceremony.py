"""Effective-ceremony resolver (lever 4 truthfulness — WS1).

ONE source of truth for "what review ceremony actually applies to this task, given
its risk tier, whether a reviewer is configured, and how the validator stage turned
out". The new-task confirm, the ship digest, and the receipt banner all read it, so
none can describe ceremony from the risk TIER while the validator (lever 2) is in
fact OFF because no reviewer is configured — the bug where the UI claimed a review
that never ran (B1/B10/B18/B20).

The validator's recorded outcome (`Task.validator_outcome`) is the single fact the
harness writes; every read surface derives its wording from it, so "disabled"
(never configured) is never confused with "failed" (ran and crashed) or "ran".
"""

# Validator status — the effective state of lever 2 for a task.
NA = "n/a"  # low risk: machine checks only, the validator never applies
DISABLED = "disabled"  # med/high but no reviewer configured — it silently no-ops
PENDING = "pending"  # med/high, reviewer configured, not yet run (new-task confirm)
RAN = "ran"  # completed
FAILED = "failed"  # crashed or timed out — reviewed unaided


def validator_status(
    risk: str, *, reviewer_configured: bool | None = None, validator_outcome: str | None = None
) -> str:
    """The effective validator status from (risk, reviewer config, recorded outcome).

    Post-run surfaces pass ``validator_outcome`` (the harness records ran/failed/disabled);
    planning-time surfaces (new-task confirm, before any run) pass ``reviewer_configured``
    and leave the outcome None. A med/high task with neither signal reads ``disabled`` —
    there is no positive evidence the validator ran, and an honest "off" beats a false
    "validated"."""
    if risk == "low":
        return NA
    if validator_outcome in (RAN, FAILED, DISABLED):
        return validator_outcome
    return PENDING if reviewer_configured else DISABLED


def task_validator_status(task) -> str:
    """The validator status for a persisted task — read from its recorded outcome."""
    return validator_status(task.risk, validator_outcome=task.validator_outcome)


def gates_clause(risk: str, status: str) -> str:
    """The ceremony a task routes into, as a human clause. Reflects EFFECTIVE config:
    "validator" appears only when the validator actually applies (not when disabled)."""
    if risk == "low":
        return "machine checks + fast approve"
    parts: list[str] = []
    if status != DISABLED:
        parts.append("validator")
    if risk == "high":
        parts.append("security")
    parts.append("comprehension")
    if risk == "high":
        parts.append("2nd approver")
    return " + ".join(parts)


def banner_suffix(status: str) -> str:
    """The parenthetical a receipt/digest appends to admit the validator gap honestly:
    DISABLED (never configured) and FAILED (ran and crashed) are distinct (B18)."""
    if status == FAILED:
        return " (validator unavailable — reviewed unaided)"
    if status == DISABLED:
        return " (validator disabled — no reviewer configured)"
    return ""


__all__ = [
    "DISABLED",
    "FAILED",
    "NA",
    "PENDING",
    "RAN",
    "banner_suffix",
    "gates_clause",
    "task_validator_status",
    "validator_status",
]
