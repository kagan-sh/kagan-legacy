"""Domain models for the file ledger (TUI-LEDGER-01/04).

Single source of truth for Task and its parts. Severity and verdict are plain
str (validated at the surfaces); the ledger only persists. State is JSON via
model_dump(mode="json") — see _patterns.md P1.
"""

from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — pydantic resolves Path at class body time

from pydantic import BaseModel, Field

from kagan.core.enums import TaskState


def _now() -> datetime:
    return datetime.now(UTC)


class Decision(BaseModel):
    id: str
    question: str
    severity: str  # "blocking" | "question"
    options: list[str] = Field(default_factory=list)  # MCP-INTAKE-02 candidates
    answer: str | None = None
    # True = the human accepted the agent's assumption as-is (DESIGN §5 "Approve");
    # False with an answer = they overrode it. Replaces kagan's old "bless". The
    # accepted assumption itself is recorded in `answer` (the option taken), so the
    # receipt reads WHAT was decided, never the bare verb.
    approved: bool = False


class Finding(BaseModel):
    id: str
    severity: str  # "blocking" | "question" | "nit"
    location: str
    message: str
    verdict: str | None = None  # "agree" | "disagree"
    reply: str | None = None  # required when verdict == "disagree" (TUI-GATE-05)
    resolution_note: str | None = None  # author's own-words note for the receipt (lever 1)
    # ponytail: field + renderer ship now; the gate engine's findings are file-level,
    # so anchoring a real diff hunk per finding is left as later best-effort work.
    hunk: str | None = None
    # Who raised it: "machine" | "ai-review" | "security" (lever 2 provenance).
    source: str = "machine"
    # kipp finding schema (lever 2): the validator's self-rated confidence 0-10.
    confidence: int | None = None
    # kipp finding schema (lever 2): "VERIFIED" | "UNVERIFIED" | "TENTATIVE".
    status: str | None = None


class SmokeTest(BaseModel):
    id: str
    behaviour: str
    service: str | None = None  # MCP-SMOKE-02: reference a service "where applicable"
    verified: bool = False


class NeedsYou(BaseModel):
    reason: str
    question: str
    context: str = ""


class DriftConcern(BaseModel):
    id: str
    message: str
    location: str | None = None
    acknowledged: bool = False


class ReportMessage(BaseModel):
    type: str
    payload: dict = Field(default_factory=dict)


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    scope: list[str] = Field(default_factory=list)
    state: TaskState = TaskState.INTAKE
    branch: str | None = None
    worktree_path: Path | None = None
    base_branch: str = "main"
    agent_cli: str | None = None
    # PID of the detached `kagan _run` child that owns the RUNNING transition. Set
    # by the child as it takes ownership; probed by Harness.reconcile_in_flight to
    # detect a hard-killed runner (rule 12). None while no runner owns the task.
    runner_pid: int | None = None
    # Set when reconcile_in_flight finds the runner_pid dead: the task is excluded
    # from the lever-5 cap, surfaces in the inbox as re-runnable, and is cleared on
    # the next start_task. A RUNNING/VALIDATING task with a live pid stays clear.
    interrupted: bool = False
    decisions: list[Decision] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    smoke_tests: list[SmokeTest] = Field(default_factory=list)
    ports: dict[str, int] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    understanding: str | None = None
    base_commit: str | None = None
    drift: bool = False
    needs_you: NeedsYou | None = None
    last_activity_at: datetime | None = None
    last_viewed_at: datetime | None = None
    resume_point: str | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    not_covered: list[str] = Field(default_factory=list)
    remote_ci_status: str | None = None
    remote_pr_url: str | None = None
    drift_concerns: list[DriftConcern] = Field(default_factory=list)
    done_reported: bool = False
    # Author's own-words answers to the risk-scaled comprehension prompt set
    # (lever 1): prompt-key → answer. Empty until the human answers any prompt.
    comprehension: dict[str, str] = Field(default_factory=dict)
    # Validator-generated (key, question) prompts for this diff (lever 2). Empty
    # means use the static risk-tier set; a short generated set falls back to static
    # so med/high never drop below the tier floor (rule 8).
    comprehension_prompts: list[tuple[str, str]] = Field(default_factory=list)
    # Risk tier classified at intake from scope vs config.risk_tiers (lever 4
    # spine). Default medium so unconfigured repos behave like today. Scales
    # ceremony: low skips the validator + comprehension lock; high keeps both.
    risk: str = "medium"
    # Distinct git identities that approved (lever 6). High risk needs >=2; the
    # approver bar lives in Harness.approve_task, not can_approve.
    approvers: list[str] = Field(default_factory=list)
    # Outcome of the lever-2 validator stage (F2): None = not applicable (low risk,
    # no reviewer model, or no worktree), "ran" = the validator completed, "failed"
    # = it crashed/timed out and the diff was reviewed unaided. The receipt's
    # ceremony banner consults this so a failed validator never reads as one that ran
    # (false provenance is worse than an honest gap — the trust-incompetence spiral).
    validator_outcome: str | None = None
    # The human's most recent send-back directive (DESIGN-SHARE-08), NOT a finding. It
    # feeds the re-run prompt's _sendback_section and is cleared once the re-run harvests.
    # Modelling it as a Finding (the old approach) gave it a null title, a pre-set
    # disagree verdict, and a phantom "open" state that gated approve and polluted the
    # receipt's disputed-findings list with a circular reason (B12/B13/B17).
    sendback_note: str | None = None
    # Lever 8: True once a learning from this task was appended to AGENTS.md. The ship
    # view re-reads this each frame so the retro offer disappears after it is taken,
    # instead of re-offering the same (now stale) templated learning (B22).
    retro_appended: bool = False
    # Path to the prior .kagan/reviews record this one replaces (§3.7 link-not-delete).
    supersedes: str | None = None
    # Files this task's diff rewrote (harvested, run-artifacts stripped; capped). The
    # real churn signal lever 9 escalates on — replaces the old finding-location proxy
    # that read zero for a churning scope with no findings (turkey problem). Empty for
    # tasks harvested before this field existed; debt falls back to finding locations.
    changed_files: list[str] = Field(default_factory=list)
