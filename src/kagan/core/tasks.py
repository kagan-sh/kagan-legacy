"""Domain operations over the ledger. Records an event for every mutation.

ID format `<prefix>-<8 hex>` satisfies the ledger's P3 id regex.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from kagan.core import git
from kagan.core.comprehension import prompts_for_risk, required_keys_for_task
from kagan.core.config import load_repo_config
from kagan.core.errors import ConfigurationError, NotFoundError, ValidationError
from kagan.core.models import Decision, DriftConcern, Finding, NeedsYou, SmokeTest, Task
from kagan.core.paths import ensure_gitignore_line

if TYPE_CHECKING:
    from pathlib import Path

if TYPE_CHECKING:
    from kagan.core.enums import TaskState
    from kagan.core.ledger import Ledger


def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# Lever 1: the comprehension note must be the human's own words, not a rubber-stamp.
# The gate must be able to fail — empty, placeholder, or trivial filler stays locked.
_MIN_COMPREHENSION_WORDS = 5
_PLACEHOLDER_NOTES = frozenset(
    {
        "n/a",
        "na",
        "none",
        "tbd",
        "todo",
        "ok",
        "okay",
        "lgtm",
        "fine",
        "done",
        "looks good",
        "looks good to me",
    }
)


def _is_substantive(text: str | None) -> bool:
    """A comprehension note clears the gate only if it is the author's own words.

    The gate must be *able* to fail (mutation-probe philosophy): None, empty,
    whitespace, a known placeholder, too few words, or trivial filler with no
    real words ("a a a a a", ". . . . .") keeps approve locked. It cannot detect
    a determined rubber-stamp of real words — that is what the receipt's
    provenance is for — but it rejects the obvious non-answers.
    """
    if not text:
        return False
    normalized = " ".join(text.split()).casefold()
    if not normalized or normalized in _PLACEHOLDER_NOTES:
        return False
    words = normalized.split()
    if len(words) < _MIN_COMPREHENSION_WORDS:
        return False
    real_words = {w for w in words if sum(c.isalpha() for c in w) >= 3}
    return len(real_words) >= 3


def _event_summary(event: dict) -> str:
    # One-line resume point from the last event. A transition names its target,
    # an update names the fields it touched; else the type with spaces.
    kind = str(event.get("type", "updated"))
    if kind == "transition":
        return f"now {event.get('to', '')}".strip()
    if kind == "updated":
        fields = event.get("fields") or []
        return f"updated {', '.join(fields)}" if fields else "updated"
    return kind.replace("_", " ")


class TaskService:
    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger
        self._needs_you_waiters: dict[str, asyncio.Future[str]] = {}

    def _load(self, task_id: str) -> Task:
        task = self._ledger.load_task(task_id)
        if task is None:
            raise NotFoundError("task", task_id)
        return task

    def _commit(self, task: Task, event: dict) -> None:
        # Single chokepoint: every mutation stamps activity + a one-line resume point
        # so the Inbox heartbeat is live (TUI-INBOX-03/05).
        task.updated_at = task.last_activity_at = datetime.now(UTC)
        task.resume_point = _event_summary(event)
        self._ledger.save_task(task)
        self._ledger.append_event(task.id, event)

    def create(self, title: str, base_branch: str = "main") -> Task:
        task = Task(id=_make_id("task"), title=title, base_branch=base_branch)
        self._commit(task, {"type": "created", "title": title})
        return task

    def transition(self, task_id: str, new_state: TaskState) -> Task:
        task = self._load(task_id)
        before = task.state
        task.state = new_state
        self._commit(task, {"type": "transition", "from": before.value, "to": new_state.value})
        return task

    def touch_viewed(self, task_id: str) -> Task:
        # Stamps last_viewed_at so the "since you left" delta can be derived.
        task = self._load(task_id)
        task.last_viewed_at = datetime.now(UTC)
        self._commit(task, {"type": "viewed"})
        return task

    def update_task(self, task_id: str, **fields) -> Task:
        # Generic setter for the plain scalar fields other plans write
        # (understanding, branch, worktree_path, drift, remote_ci_status, ...).
        unknown = set(fields) - set(Task.model_fields)
        if unknown:
            raise ValidationError("fields", f"unknown task field(s): {', '.join(sorted(unknown))}")
        task = self._load(task_id)
        # model_validate (not model_copy) so a bad value fails here, never on reload.
        updated = Task.model_validate(task.model_dump() | fields)
        self._commit(updated, {"type": "updated", "fields": sorted(fields)})
        return updated

    def add_decision(
        self, task_id: str, *, question: str, severity: str, options: list[str] | None = None
    ) -> Task:
        task = self._load(task_id)
        decision = Decision(
            id=_make_id("dec"), question=question, severity=severity, options=options or []
        )
        task.decisions.append(decision)
        self._commit(task, {"type": "decision_added", "decision_id": decision.id})
        return task

    def answer_decision(
        self, task_id: str, decision_id: str, *, answer: str, blessed: bool = False
    ) -> Task:
        task = self._load(task_id)
        decision = next((d for d in task.decisions if d.id == decision_id), None)
        if decision is None:
            raise NotFoundError("decision", decision_id)
        decision.answer = answer
        decision.blessed = blessed
        self._commit(task, {"type": "decision_answered", "decision_id": decision_id})
        return task

    def can_run(self, task_id: str) -> bool:
        task = self._load(task_id)
        return not any(
            d.severity == "blocking" and d.answer is None and not d.blessed for d in task.decisions
        )

    def add_finding(
        self,
        task_id: str,
        *,
        severity: str,
        location: str,
        message: str,
        source: str = "machine",
        confidence: int | None = None,
        status: str | None = None,
    ) -> Task:
        task = self._load(task_id)
        finding = Finding(
            id=_make_id("find"),
            severity=severity,
            location=location,
            message=message,
            source=source,
            confidence=confidence,
            status=status,
        )
        task.findings.append(finding)
        self._commit(task, {"type": "finding_added", "finding_id": finding.id})
        return task

    def set_verdict(
        self, task_id: str, finding_id: str, *, verdict: str, reply: str | None = None
    ) -> Task:
        if verdict == "disagree" and not reply:
            raise ValueError("a disagree verdict must carry a reply (TUI-GATE-05)")
        task = self._load(task_id)
        finding = next((f for f in task.findings if f.id == finding_id), None)
        if finding is None:
            raise NotFoundError("finding", finding_id)
        finding.verdict = verdict
        finding.reply = reply
        self._commit(task, {"type": "verdict_set", "finding_id": finding_id, "verdict": verdict})
        return task

    def record_comprehension(self, task_id: str, key: str, answer: str) -> Task:
        # Lever 1: record ONE prompt's own-words answer into the dict. Partial
        # answers persist (rule 12) — answering 1 of N records that 1.
        task = self._load(task_id)
        task.comprehension[key] = answer
        self._commit(task, {"type": "comprehension_recorded", "key": key})
        return task

    def record_comprehension_prompts(
        self, task_id: str, prompts: list[tuple[str, str]] | list[dict[str, Any]]
    ) -> Task:
        task = self._load(task_id)
        floor = len(prompts_for_risk(task.risk))
        if floor == 0:
            return task
        normalized: list[tuple[str, str]] = []
        for item in prompts:
            if isinstance(item, dict):
                key = item.get("key")
                question = item.get("question")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                key, question = item[0], item[1]
            else:
                logger.warning("dropping malformed comprehension prompt for task {}", task_id)
                continue
            if not key or not question:
                logger.warning("dropping malformed comprehension prompt for task {}", task_id)
                continue
            normalized.append((str(key), str(question)))
        if len(normalized) < floor:
            return task
        stored = normalized[:floor]
        task.comprehension_prompts = stored
        self._commit(task, {"type": "comprehension_prompts_recorded", "count": len(stored)})
        return task

    def record_approver(self, task_id: str, approver: str) -> Task:
        # Lever 6: append a distinct approver identity. Idempotent per identity so
        # one human pressing approve twice never counts twice toward the high-risk bar.
        task = self._load(task_id)
        if approver not in task.approvers:
            task.approvers.append(approver)
        self._commit(task, {"type": "approved", "approver": approver})
        return task

    def can_approve(self, task_id: str) -> bool:
        # Every tier needs blocking findings adjudicated (TUI-GATE-05). The
        # comprehension lock (lever 1) is risk-scaled (lever 4): low = fast approve
        # (no note); medium/high require the substantive own-words note. The
        # high-risk second-approver bar (lever 6) is a SEPARATE gate in
        # Harness.approve_task, kept out of here so this stays a pure
        # findings+comprehension lock the surface reads for rendering.
        task = self._load(task_id)
        findings_clear = not any(
            f.severity == "blocking" and f.verdict is None for f in task.findings
        )
        if not findings_clear:
            return False
        if task.risk == "low":
            return True
        return all(
            _is_substantive(task.comprehension.get(key)) for key in required_keys_for_task(task)
        )

    def add_smoke_test(self, task_id: str, *, behaviour: str, service: str | None = None) -> Task:
        task = self._load(task_id)
        item = SmokeTest(id=_make_id("smoke"), behaviour=behaviour, service=service)
        task.smoke_tests.append(item)
        self._commit(task, {"type": "smoke_added", "smoke_id": item.id})
        return task

    def verify_smoke_test(self, task_id: str, smoke_id: str) -> Task:
        task = self._load(task_id)
        item = next((s for s in task.smoke_tests if s.id == smoke_id), None)
        if item is None:
            raise NotFoundError("smoke_test", smoke_id)
        item.verified = True
        self._commit(task, {"type": "smoke_verified", "smoke_id": smoke_id})
        return task

    def record_intake_decisions(
        self, task_id: str, *, understanding: str, decisions: list[dict[str, Any]]
    ) -> Task:
        task = self._load(task_id)
        task.understanding = understanding
        task.decisions = [
            Decision(
                id=_make_id("dec"),
                question=d["question"],
                severity=d.get("severity", "question"),
                options=d.get("options", []),
            )
            for d in decisions
        ]
        self._commit(task, {"type": "intake_decisions_recorded", "count": len(task.decisions)})
        return task

    def record_smoke_tests(self, task_id: str, *, tests: list[dict[str, Any]]) -> Task:
        task = self._load(task_id)
        task.smoke_tests = [
            SmokeTest(id=_make_id("smoke"), behaviour=t["behaviour"], service=t.get("service"))
            for t in tests
        ]
        self._commit(task, {"type": "smoke_tests_recorded", "count": len(task.smoke_tests)})
        return task

    def record_drift(self, task_id: str, *, message: str, location: str | None = None) -> Task:
        task = self._load(task_id)
        concern = DriftConcern(id=_make_id("drift"), message=message, location=location)
        task.drift_concerns.append(concern)
        self._commit(task, {"type": "drift_recorded", "concern_id": concern.id})
        return task

    def record_done(self, task_id: str) -> Task:
        task = self._load(task_id)
        task.done_reported = True
        self._commit(task, {"type": "done_reported"})
        return task

    async def record_needs_you(
        self, task_id: str, *, reason: str, question: str, context: str = ""
    ) -> str:
        # P9: persist BEFORE blocking so the pending question survives a crash.
        task = self._load(task_id)
        task.needs_you = NeedsYou(reason=reason, question=question, context=context)
        self._commit(task, {"type": "needs_you_recorded", "reason": reason})
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._needs_you_waiters[task_id] = future
        try:
            return await future
        finally:
            self._needs_you_waiters.pop(task_id, None)

    def answer_needs_you(self, task_id: str, answer: str) -> Task:
        task = self._load(task_id)
        task.needs_you = None
        self._commit(task, {"type": "needs_you_answered"})
        waiter = self._needs_you_waiters.get(task_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(answer)
        return task

    async def prepare_worktree(self, task: Task, repo_root: Path) -> Task:
        # Idempotent: send-back reuses an existing worktree (TUI-GATE-07).
        if task.worktree_path is not None and task.worktree_path.exists():
            return task
        branch = f"kagan/{task.id}"
        # TUI-WS-05: never check out a pinned branch (off-limits to agents). A repo
        # with no manifest pins nothing, so a missing config is not an error here.
        try:
            pinned = set(load_repo_config(repo_root).pinned)
        except ConfigurationError:
            pinned = set()
        if branch in pinned:
            raise ConfigurationError(
                "workspace", f"branch {branch} is pinned (off-limits to agents)"
            )
        wt_path = repo_root / ".kagan_worktrees" / task.id
        # Keep per-task worktree checkouts out of commits: idempotently ensure the
        # repo-root .gitignore covers .kagan_worktrees/. Never clobbers a hand-
        # written .gitignore; a second worktree is a no-op (DESIGN §3.6).
        ensure_gitignore_line(repo_root / ".gitignore", ".kagan_worktrees/")
        await git.worktree_add(repo_root, wt_path, branch=branch, base=task.base_branch)
        task.branch = branch
        task.worktree_path = wt_path
        self._commit(task, {"type": "worktree_prepared", "path": str(wt_path)})
        return task
