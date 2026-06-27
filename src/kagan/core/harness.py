"""Harness — file-ledger engine seam.

Owns the on-disk ledger root (per-task state files + event logs). The v2 ledger
read/write API is grown here during the rebuild. No relational database — the
data is small, per-task, and single-writer (TUI-LEDGER-04).
"""

import asyncio
import json
import os
import shutil
from contextlib import suppress
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from kagan.core import git, mirror, workspace
from kagan.core.agent import launch_intake, launch_run, launch_validate, terminate, wait_bounded
from kagan.core.config import RepoConfig, load_repo_config
from kagan.core.debt import cumulative_scope_debt, escalate_tier
from kagan.core.enums import TaskState
from kagan.core.errors import (
    AgentCapError,
    ConfigurationError,
    InvalidTransitionError,
    NotFoundError,
)
from kagan.core.gate import GateEngine
from kagan.core.inbox import InboxItem, build_item, median_run_seconds, sort_items
from kagan.core.ledger import Ledger
from kagan.core.models import CheckResult, Decision, Finding, NeedsYou, ReportMessage, Task
from kagan.core.notifications import NotificationEvent, Notifier
from kagan.core.paths import ensure_gitignore_line, is_run_artifact
from kagan.core.receipt import render_pr_body, render_receipt
from kagan.core.recipes import available_clis, recipe_for
from kagan.core.remote_ci import RemoteCi
from kagan.core.reports import detect_drift, read_ask, summarize_learnings
from kagan.core.retro import append_learning
from kagan.core.risk import classify, downgrade_low_confidence
from kagan.core.ship import ShipService
from kagan.core.stats import Scorecard, compute_scorecard
from kagan.core.stats import durability as stats_durability
from kagan.core.tasks import TaskService

if TYPE_CHECKING:
    from kagan.core.workspace import RunningService


def default_data_dir(repo_root: Path | None = None) -> Path:
    """The one ledger-root resolver (DESIGN §3.6). KAGAN_DATA_DIR wins, else
    <git-toplevel>/.kagan/state, else cwd/.kagan/state. Every entrypoint
    (tui, new, mcp, reset, Harness) routes through here so they never disagree."""
    override = os.environ.get("KAGAN_DATA_DIR")
    if override:
        return Path(override)
    root = repo_root or git.repo_root(Path.cwd()) or Path.cwd()
    return root / ".kagan" / "state"


def _scaffold_kagan_gitignore(repo_root: Path) -> None:
    """Write <repo>/.kagan/.gitignore ignoring the operational state/ dir, so the
    committable subset (.kagan/repo.yaml, .kagan/reviews/) is trackable out of the
    box while .kagan/state never enters commits (§3.6). Idempotent and never
    clobbering — a hand-edited .gitignore is appended to, not overwritten."""
    ensure_gitignore_line(repo_root / ".kagan" / ".gitignore", "state/")


def _slugify(title: str) -> str:
    """A filesystem-safe slug for the receipt filename (§3.6 stable per task)."""
    slug = "".join(c if c.isalnum() else "-" for c in title.lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "task"


def _pid_alive(pid: int) -> bool:
    """Liveness probe for a detached runner (rule 12). ``os.kill(pid, 0)`` sends no
    signal: it succeeds for a live owned process, raises PermissionError for a live
    process we don't own (still alive), and ProcessLookupError for a dead pid."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _untracked_as_pseudo_diff(ls_files_out: str) -> str:
    lines = [f"diff --git a/{p} b/{p}" for p in ls_files_out.splitlines() if p.strip()]
    return ("\n".join(lines) + "\n") if lines else ""


class Harness:
    def __init__(
        self,
        data_dir: str | Path | None = None,
        repo_root: str | Path | None = None,
    ) -> None:
        self.repo_root: Path | None = Path(repo_root) if repo_root is not None else None
        self.data_dir: Path = (
            Path(data_dir) if data_dir is not None else default_data_dir(self.repo_root)
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Scaffold .kagan/.gitignore so the committable subset (repo.yaml, reviews/)
        # is trackable while the operational state/ stays ignored (§3.6). Only when
        # the ledger is the in-repo .kagan/state under this repo — never for an
        # arbitrary data_dir (tests, KAGAN_DATA_DIR overrides).
        if self.repo_root is not None and self.data_dir == self.repo_root / ".kagan" / "state":
            _scaffold_kagan_gitignore(self.repo_root)
        self._ledger = Ledger(self.data_dir / "tasks")
        self._tasks = TaskService(self._ledger)
        self._ship = ShipService(self._ledger)
        self._agent_procs: dict[str, asyncio.subprocess.Process] = {}
        self._agent_tasks: dict[str, asyncio.Task] = {}
        self._running: dict[str, list[RunningService]] = {}
        self._remote_ci_obj: RemoteCi | None = None
        self._notifier_obj: Notifier | None = None
        logger.info("Harness initialized (ledger root: {})", self.data_dir)

    @cached_property
    def config(self) -> RepoConfig | None:
        if self.repo_root is None:
            return None
        return load_repo_config(self.repo_root)

    def list_tasks(self) -> list[Task]:
        return [
            t
            for tid in self._ledger.list_task_ids()
            if (t := self._ledger.load_task(tid)) is not None
        ]

    def get_task(self, task_id: str) -> Task | None:
        return self._ledger.load_task(task_id)

    def save_task(self, task: Task) -> None:
        self._ledger.save_task(task)

    def create_task(self, title: str, base_branch: str | None = None) -> Task:
        # Honor the manifest's base_branch: a repo on `master` (or any non-`main`
        # default) would otherwise get a task pinned to `main`, and start_task's
        # `git worktree add … main` fails with "invalid reference" — stranding the
        # task in INTAKE. None means "resolve from the manifest" (falls back to
        # "main" only when there is no config).
        if base_branch is None:
            base_branch = self._manifest_base_branch()
        return self._tasks.create(title, base_branch=base_branch)

    def _manifest_base_branch(self) -> str:
        # load_repo_config raises when there is no manifest (and config caches that);
        # fall back to "main" so task creation never depends on an existing manifest.
        with suppress(ConfigurationError):
            if self.config is not None:
                return self.config.base_branch
        return "main"

    def transition_task(self, task_id: str, new_state: TaskState) -> Task:
        return self._tasks.transition(task_id, new_state)

    def touch_viewed(self, task_id: str) -> Task:
        return self._tasks.touch_viewed(task_id)

    def inbox_tasks(self) -> list[InboxItem]:
        tasks = self.list_tasks()
        median = median_run_seconds(tasks)
        return sort_items(
            [build_item(t, self._ledger.read_events(t.id), median_seconds=median) for t in tasks]
        )

    def read_events(self, task_id: str) -> list[dict[str, Any]]:
        """Read-only event log for a task; the surface uses it for derived,
        never-persisted signals (lever 5 coach lines)."""
        return self._ledger.read_events(task_id)

    def update_task(self, task_id: str, **fields) -> Task:
        return self._tasks.update_task(task_id, **fields)

    def add_decision(
        self, task_id: str, *, question: str, severity: str, options: list[str] | None = None
    ) -> Task:
        return self._tasks.add_decision(
            task_id, question=question, severity=severity, options=options
        )

    def answer_decision(
        self, task_id: str, decision_id: str, *, answer: str, approved: bool = False
    ) -> Task:
        return self._tasks.answer_decision(task_id, decision_id, answer=answer, approved=approved)

    def can_run(self, task_id: str) -> bool:
        return self._tasks.can_run(task_id)

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
        return self._tasks.add_finding(
            task_id,
            severity=severity,
            location=location,
            message=message,
            source=source,
            confidence=confidence,
            status=status,
        )

    def set_verdict(
        self, task_id: str, finding_id: str, *, verdict: str, reply: str | None = None
    ) -> Task:
        return self._tasks.set_verdict(task_id, finding_id, verdict=verdict, reply=reply)

    def record_comprehension(self, task_id: str, key: str, answer: str) -> Task:
        return self._tasks.record_comprehension(task_id, key, answer)

    def record_comprehension_prompts(
        self, task_id: str, prompts: list[tuple[str, str]] | list[dict[str, Any]]
    ) -> Task:
        return self._tasks.record_comprehension_prompts(task_id, prompts)

    def can_approve(self, task_id: str) -> bool:
        return self._tasks.can_approve(task_id)

    def running_count(self, exclude: str | None = None) -> int:
        """Lever 5: agents in flight = tasks in RUNNING or VALIDATING. The surface
        reads this for the inbox standing line; ``start_task`` reads it for the cap.
        ``exclude`` drops a task from the count so a send-back re-running in place
        is not counted against itself. An ``interrupted`` task (dead runner, see
        reconcile_in_flight) no longer occupies a slot (rule 12)."""
        in_flight = {TaskState.RUNNING, TaskState.VALIDATING}
        return sum(
            1
            for t in self.list_tasks()
            if t.state in in_flight and not t.interrupted and t.id != exclude
        )

    def _agent_cap(self) -> int:
        config = self._gate_config()
        return config.max_concurrent_agents if config is not None else 2

    def _agent_timeout(self) -> float:
        """F1: wall-clock cap (seconds) for a single agent run, from repo.yaml. 0
        disables. Default 1800 when no manifest is configured."""
        config = self._gate_config()
        return float(config.agent_timeout_seconds if config is not None else 1800)

    def can_start_agent(self, exclude: str | None = None) -> bool:
        """Lever 5: True while a new run may start (running count below the cap)."""
        return self.running_count(exclude=exclude) < self._agent_cap()

    def reconcile_in_flight(self) -> list[str]:
        """Rule 12: reap tasks whose detached `kagan _run` child was hard-killed.

        Scan RUNNING/VALIDATING tasks; for each with a ``runner_pid``, probe the pid
        with ``os.kill(pid, 0)``. A dead pid (ProcessLookupError) means the runner
        never reached REVIEW — flag the task ``interrupted`` so it stops counting
        toward the lever-5 cap and surfaces in the inbox as re-runnable; a re-run
        (start_task) clears the flag and finishes cleanly. A live pid (PermissionError
        or no error) is left untouched, as is any task with no runner_pid (it never
        owned a detached run). REVIEW/READY are out of scope — they already settled.

        Run on session launch ("reap on every surface"). Returns the reaped task ids.
        pid-reuse residual: liveness is primary — a recycled pid could read as alive
        and leave a genuinely-dead runner stranded until the next launch; accepted.
        """
        in_flight = {TaskState.RUNNING, TaskState.VALIDATING}
        reaped: list[str] = []
        for task in self.list_tasks():
            if task.state not in in_flight or task.interrupted or task.runner_pid is None:
                continue
            if _pid_alive(task.runner_pid):
                continue
            self.update_task(task.id, interrupted=True)
            self._ledger.append_event(
                task.id, {"type": "interrupted", "runner_pid": task.runner_pid}
            )
            reaped.append(task.id)
        return reaped

    def record_run_failed(self, task_id: str, reason: str) -> None:
        """Record that a detached `kagan _run` failed to start the agent (rule 12).

        The detached runner discards its output, so without this a start failure
        (e.g. a base_branch that is not a valid ref) leaves the task silently in
        INTAKE while the session already reported "Agent run started". Append an
        auditable event so the failure is recoverable from the ledger."""
        self._ledger.append_event(task_id, {"type": "run_failed", "reason": reason})

    def approve_cooldown_remaining(self, task_id: str, now: datetime | None = None) -> int:
        """Lever 5: seconds left on the gen->approve cooldown; 0 once elapsed.

        Derived (never stored) from the latest RUNNING/VALIDATING -> REVIEW event
        in the log plus the configured ``approve_cooldown_seconds``. Kept OUT of
        ``can_approve`` (which stays a pure findings+comprehension lock) so the core
        approve tests stay deterministic; the surface checks both. ``now`` is
        injectable for tests."""
        cooldown = self._approve_cooldown_seconds()
        if cooldown <= 0:
            return 0
        landed = self._review_landed_at(task_id)
        if landed is None:
            return 0
        now = now or datetime.now(UTC)
        elapsed = (now - landed).total_seconds()
        return max(int(cooldown - elapsed + 0.999), 0)

    def _approve_cooldown_seconds(self) -> int:
        config = self._gate_config()
        return config.approve_cooldown_seconds if config is not None else 60

    def _review_landed_at(self, task_id: str) -> datetime | None:
        """Timestamp of the most recent RUNNING/VALIDATING -> REVIEW transition."""
        in_flight = {TaskState.RUNNING.value, TaskState.VALIDATING.value}
        landed: datetime | None = None
        for event in self._ledger.read_events(task_id):
            if (
                event.get("type") == "transition"
                and event.get("to") == TaskState.REVIEW.value
                and event.get("from") in in_flight
            ):
                ts = event.get("ts")
                if ts:
                    landed = datetime.fromisoformat(ts)
        return landed

    def add_smoke_test(self, task_id: str, *, behaviour: str, service: str | None = None) -> Task:
        return self._tasks.add_smoke_test(task_id, behaviour=behaviour, service=service)

    def verify_smoke_test(self, task_id: str, smoke_id: str) -> Task:
        return self._tasks.verify_smoke_test(task_id, smoke_id)

    def record_intake_decisions(
        self, task_id: str, *, understanding: str, decisions: list[dict[str, Any]]
    ) -> Task:
        return self._tasks.record_intake_decisions(
            task_id, understanding=understanding, decisions=decisions
        )

    def record_smoke_tests(self, task_id: str, *, tests: list[dict[str, Any]]) -> Task:
        return self._tasks.record_smoke_tests(task_id, tests=tests)

    def record_drift(self, task_id: str, *, message: str, location: str | None = None) -> Task:
        return self._tasks.record_drift(task_id, message=message, location=location)

    def record_done(self, task_id: str) -> Task:
        return self._tasks.record_done(task_id)

    async def record_needs_you(
        self, task_id: str, *, reason: str, question: str, context: str = ""
    ) -> str:
        return await self._tasks.record_needs_you(
            task_id, reason=reason, question=question, context=context
        )

    def answer_needs_you(self, task_id: str, answer: str) -> Task:
        return self._tasks.answer_needs_you(task_id, answer)

    def available_clis(self) -> list[str]:
        return available_clis()

    def approve_task(self, task_id: str, approver: str | None = None) -> Task:
        """Lever 6 chokepoint: record the approver, gate the READY transition on the
        risk-scaled distinct-approver bar, and auto-write the receipt on success.

        Order matters (record THEN check): high risk needs >=2 distinct identities,
        so the first approve records one and stays in REVIEW; a second DISTINCT
        identity flips it to READY. ``can_approve`` (findings+comprehension) is
        re-checked here; the surface gates on it too. The receipt is written only
        AFTER the READY transition, so it is never written for a task still waiting.
        """
        identity = approver or git.user_identity(self.repo_root or Path.cwd())
        if identity:
            self._tasks.record_approver(task_id, identity)
        task = self._require(task_id)
        if task.state not in {TaskState.REVIEW, TaskState.DONE}:
            raise InvalidTransitionError(task.state, TaskState.READY)
        if not self.can_approve(task_id) or not self._approver_bar_met(task):
            return task  # stays in REVIEW — recorded, waiting for the unmet gate
        task = self._tasks.transition(task_id, TaskState.READY)
        self._write_receipt_file(task)
        return task

    def _approver_bar_met(self, task: Task) -> bool:
        """Lever 6: distinct identities must meet the tier's bar (low/med = 1, high = N)."""
        if task.risk != "high":
            return len(set(task.approvers)) >= 1
        return len(set(task.approvers)) >= self.high_risk_approvers()

    def high_risk_approvers(self) -> int:
        """Lever 6: distinct identities a high-risk task needs (config knob, default 2)."""
        config = self._gate_config()
        return config.high_risk_approvers if config is not None else 2

    def _write_receipt_file(self, task: Task) -> Path | None:
        """Auto-write the receipt into the MAIN repo under .kagan/reviews/ (§3.6).

        Committable institutional memory — NOT the worktree (throwaway) and NOT
        data_dir (the external operational ledger). The developer chooses to commit
        it. Skips when there is no repo_root (same guard as run_intake).

        DEFER (§3.7): an abandoned/sent-back task should leave a one-line "productive
        dead end" record here, and an in-flight pause should write a session-boundary
        handoff — both attach at this write seam. ADR supersede-linking (set
        task.supersedes to a prior .kagan/reviews path) is also deferred; the field
        and its Status rendering ship now, the auto-detection does not."""
        if self.repo_root is None:
            return None
        reviews_dir = self.repo_root / ".kagan" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        # B23: the receipt filename is a human-facing date stamp in the committed
        # decision log — use LOCAL date, not UTC (a dev east of UTC saw yesterday).
        date = datetime.now().strftime("%Y-%m-%d")
        path = reviews_dir / f"{date}-{_slugify(task.title)}.md"
        path.write_text(render_receipt(task), encoding="utf-8")
        return path

    async def branch_on_origin(self, task_id: str) -> bool | None:
        """Read-only verification that the task's branch exists on origin (the human
        pushed) before the ship screen flips to PR_OPEN. kagan never pushes — it only
        checks. ``True`` present, ``False`` absent, ``None`` unverifiable (no branch
        set, no repo, or git/network unavailable — the surface softens, not refuses)."""
        task = self._require(task_id)
        if not task.branch or self.repo_root is None:
            return None
        return await git.remote_has_branch(self.repo_root, task.branch)

    async def mark_task_pushed(self, task_id: str) -> Task:
        """Flip READY -> PR_OPEN and best-effort capture the PR URL (lever 7 prereq).

        ShipService.mark_pushed stays sync (no subprocess); the gh read happens
        here. The capture is non-blocking on the flip: gh absent or no PR yet
        (human pushed before `gh pr create`) leaves remote_pr_url None and the
        state flip still proceeds — the tripwire just stays inert until a later
        poll (DESIGN §lever-7: capture opportunity, not a guarantee)."""
        task = self._require(task_id)
        url = await self._remote_ci().pr_url(task.branch)
        if url:
            self.update_task(task_id, remote_pr_url=url)
        return self._ship.mark_pushed(task_id)

    def outcome_scorecard(self) -> Scorecard:
        """Lever 7: the private outcome mirror (cycle-time/CFR/comprehension/
        review-caught). Pure read over the ledger — no git, no I/O, sync."""
        tasks = self.list_tasks()
        events_by_task = {t.id: self._ledger.read_events(t.id) for t in tasks}
        return compute_scorecard(tasks, events_by_task)

    async def durability_estimate(self, now: datetime | None = None) -> tuple[int, int]:
        """Lever 7: best-effort durability (approved files untouched on base within
        the window). Async + read-only git; (0, 0) when nothing is observable.
        Kept separate from outcome_scorecard so the sync metrics never block on
        a subprocess (DESIGN §lever-7 durability is observational only)."""
        tasks = self.list_tasks()
        events_by_task = {t.id: self._ledger.read_events(t.id) for t in tasks}
        return await stats_durability(
            tasks,
            repo_root=self.repo_root or Path.cwd(),
            git_runner=git.run_git,
            events_by_task=events_by_task,
            now=now,
        )

    def propose_retro(self, task_id: str) -> str | None:
        """Lever 8: a candidate AGENTS.md learning for this task, or None. Pure
        read — never writes. The surface offers it; confirm_retro does the append."""
        return summarize_learnings(self._require(task_id))

    def confirm_retro(self, task_id: str, line: str) -> Path | None:
        """Lever 8: append the human-confirmed learning to repo-root AGENTS.md.

        The ONLY AGENTS.md write path, reachable only after the surface's explicit
        confirm. Skips when there is no repo_root (same guard as the receipt write).
        Records ``retro_appended`` so the ship view stops re-offering the same learning
        (B22) — the next render re-reads it and drops the retro affordance."""
        if self.repo_root is None:
            return None
        path = append_learning(self.repo_root, line)
        self.update_task(task_id, retro_appended=True)
        return path

    def get_push_command(self, task_id: str) -> str:
        return self._ship.push_command(self._require(task_id))

    def get_pr_command(self, task_id: str) -> str:
        return self._ship.pr_command(self._require(task_id))

    def render_receipt(self, task_id: str) -> str:
        return render_receipt(self._require(task_id))

    def render_pr_body(self, task_id: str) -> str:
        return render_pr_body(self._require(task_id))

    def _config(self) -> RepoConfig:
        # ponytail: separate from the `config` cached_property so tests can inject
        # `_repo_config`; collapse to one accessor if `config` ever grows injectable.
        cfg = getattr(self, "_repo_config", None)
        if cfg is None:
            cfg = load_repo_config(self.repo_root or Path.cwd())
            self._repo_config = cfg
        return cfg

    def _remote_ci(self) -> RemoteCi:
        if self._remote_ci_obj is None:
            self._remote_ci_obj = RemoteCi(self.repo_root or Path.cwd())
        return self._remote_ci_obj

    def _notifier(self) -> Notifier:
        if self._notifier_obj is None:
            self._notifier_obj = Notifier()
        return self._notifier_obj

    async def run_local_mirror(self, task_id: str) -> Task:
        task = self._require(task_id)
        if task.worktree_path is None:
            raise ValueError(f"task {task_id} has no worktree to run the mirror in")
        checks = await mirror.run_mirror(task.worktree_path, self._config())
        warning = await mirror.base_drift_warning(task.worktree_path, task.base_branch)
        if warning:
            checks.append(CheckResult(name="base-freshness", passed=False, detail=warning))
        return self.update_task(task_id, checks=checks)

    async def run_validation(self, task_id: str) -> Task:
        """Lever 2: the adversarial validator stage. Transition RUNNING -> VALIDATING,
        spawn ONE read-only validator on the reviewer model (a different model is
        recommended, not required; reviewer == builder is allowed — the guarantee is
        the fresh separate spawn, set in
        repo.yaml via reviewer:), and merge its ai-review findings. The human still
        adjudicates every finding — nothing is auto-resolved. The VALIDATING -> REVIEW
        transition is left to run_gate (no double-hop). Skips gracefully when no
        reviewer model is configured or the task has no worktree to read."""
        task = self._require(task_id)
        reviewer = self._reviewer_model(task.agent_cli or "claude")
        # Lever 4 x lever 2: low risk is machine checks only — skip the validator
        # (DESIGN L175); no worktree means nothing to read. Outcome stays None (n/a).
        if task.risk == "low" or task.worktree_path is None:
            return task
        if reviewer is None:
            # Med/high but NO reviewer configured: the validator is genuinely DISABLED,
            # not merely unavailable. Record it so the receipt/ship/digest say so honestly
            # (B18) instead of claiming a review that never ran — and do NOT transition
            # through VALIDATING (nothing ran).
            self.update_task(task_id, validator_outcome="disabled")
            return task
        # The reviewer model lives under `agents.<cli>` so it is already this CLI's own
        # id — no vendor mismatch is representable. A model the CLI can't actually run
        # surfaces below as an honest, receipt-visible "reviewed unaided" (F2), never a
        # silent wrong-vendor run.
        self.transition_task(task_id, TaskState.VALIDATING)
        # F2: the validator is an enhancement, not the floor. If it crashes (raises)
        # OR exits unclean / times out (ok=False), do NOT strand the task in
        # VALIDATING and do NOT let the receipt claim it ran — record a visible
        # (non-blocking) finding, mark the outcome failed, and let _harvest's run_gate
        # carry it to REVIEW for unaided human review (the research baseline). Apply
        # whatever partial reports it did emit either way. Degrade, never block.
        try:
            reports, ok = await launch_validate(task, model=reviewer, timeout=self._agent_timeout())
            for r in reports:
                self._apply_report(task_id, r)
            if ok:
                self.update_task(task_id, validator_outcome="ran")
            else:
                self._degrade_validator(task_id)
        except Exception:
            logger.warning(
                "validator stage crashed for task {}; degrading to unaided review", task_id
            )
            self._degrade_validator(task_id)
        return self._require(task_id)

    def _degrade_validator(self, task_id: str) -> None:
        """F2: mark the validator stage failed and surface it honestly. A failed
        validator must never read as one that ran (the trust-incompetence spiral),
        so this records a non-blocking finding AND sets validator_outcome so the
        receipt banner admits the gap."""
        self.add_finding(
            task_id,
            severity="question",
            location="",
            message=(
                "Validator did not complete (crashed or timed out) — "
                "this diff was reviewed unaided."
            ),
            source="ai-review",
        )
        self.update_task(task_id, validator_outcome="failed")

    def _reviewer_model(self, cli: str) -> str | None:
        """The validator's model, from repo.yaml `agents.<cli>.reviewer`. None disables
        the stage."""
        config = self._gate_config()
        return config.agents.for_cli(cli).reviewer if config is not None else None

    def reviewer_configured(self, cli: str) -> bool:
        """True when repo.yaml configures a reviewer for this CLI, so the validator
        (lever 2) will actually run. The new-task confirm reads this to describe the
        EFFECTIVE ceremony rather than the risk-tier label (WS1/B10)."""
        return self._reviewer_model(cli) is not None

    def _builder_model(self, cli: str) -> str | None:
        """The builder's model, from repo.yaml `agents.<cli>.builder`. None = the CLI
        default.

        Honouring this is what makes the lever-2 'different models' guarantee real:
        the builder runs on `agents.<cli>.builder` and the validator on
        `agents.<cli>.reviewer`."""
        config = self._gate_config()
        return config.agents.for_cli(cli).builder if config is not None else None

    async def run_gate(self, task_id: str) -> Task:
        # Mirror runs build/types/tests; the engine adds the rest (TUI-GATE-01/02).
        # The mirror needs a repo manifest; skip it when none is configured so the
        # engine's universal checks still run.
        config = self._gate_config()
        if config is not None:
            await self.run_local_mirror(task_id)
        task = self._require(task_id)
        engine = GateEngine(repo_root=self.repo_root or Path.cwd(), config=config)
        # Extend so any drift findings already harvested survive (TUI-GATE-03).
        task.findings += await engine.run(task)
        # Risk-routed confidence gate (DESIGN 3.8): low-confidence ai-review/security
        # findings drop to advisory so they stay visible but don't lock approve.
        # Runs after both the validator merge and engine.run, so both are present.
        downgrade_low_confidence(task.findings, task.risk)
        self._ledger.save_task(task)
        return self.transition_task(task_id, TaskState.REVIEW)

    def _gate_config(self) -> RepoConfig | None:
        try:
            return self.config
        except ConfigurationError:
            return None

    async def gate_is_stale(self, task_id: str) -> bool:
        # TUI-GATE-10: results are stale if the base advanced since the run.
        task = self._require(task_id)
        if task.worktree_path is None:
            return False
        moved, _ = await git.base_has_moved(task.worktree_path, task.base_branch)
        return moved

    async def poll_remote_ci(self, task_id: str) -> Task:
        task = self._require(task_id)
        status, ci_checks = await self._remote_ci().fetch(task)
        # ci_failed is DERIVED by the inbox from remote_ci_status; we store the string only.
        return self.update_task(task_id, remote_ci_status=status, checks=ci_checks)

    async def allow_scope(self, task_id: str) -> Task:
        """Record the human's allow-scope choice for a drift alarm (TUI-DRIFT-03)."""
        return self.update_task(task_id, drift=False)

    async def send_back(self, task_id: str, comment: str) -> Task:
        """Clear drift, record the comment as the re-run DIRECTIVE (not a finding), and
        re-run the agent in the SAME worktree (TUI-DRIFT-03 / TUI-GATE-07).

        The note rides in Task.sendback_note → the re-run prompt's _sendback_section,
        alongside the findings the human upheld/overruled (DESIGN-SHARE-08). It is NOT a
        Finding: a send-back is a directive, not something the reviewer disputed."""
        self.update_task(task_id, drift=False, sendback_note=comment)
        return await self.start_task(task_id)  # agent-harness: reuses task.worktree_path

    async def notify(self, event: NotificationEvent, task_id: str) -> None:
        await self._notifier().notify(event, self._require(task_id))

    def _require(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise NotFoundError("task", task_id)
        return task

    def configure_task(
        self, task_id: str, *, agent_cli: str | None = None, scope: list[str] | None = None
    ) -> Task:
        task = self._require(task_id)
        if agent_cli is not None:
            task.agent_cli = agent_cli
        if scope is not None:
            task.scope = scope
            task.risk = self._classify_risk(task.scope, exclude_id=task.id)
        self._ledger.save_task(task)
        return task

    def _classify_risk(self, scope: list[str], *, exclude_id: str | None = None) -> str:
        """Lever 4: tier from scope vs config.risk_tiers, then a one-directional
        lever-9 debt escalation. Re-derivable (scope can change via configure_task
        or intake), so it stays a pure read of scope. The debt bump never blocks:
        any read error degrades to the un-escalated base tier (Rule 12 best-effort,
        like stats)."""
        config = self._gate_config()
        tiers = config.risk_tiers if config is not None else {}
        base = classify(scope, tiers)
        threshold = config.debt_threshold if config is not None else None
        if threshold is None:
            return base
        try:
            cumulative = cumulative_scope_debt(scope, self.list_tasks(), exclude_id=exclude_id)
        except Exception:  # never let a debt read stall intake (DESIGN lever 9)
            return base
        return escalate_tier(base, cumulative, threshold)

    def preview_risk(self, scope: list[str]) -> str:
        """The base risk tier a scope would classify into, with no task created
        (the new-task confirm gate surfaces this before commit). Skips the lever-9
        debt escalation, which needs a persisted task; the gate re-derives the full
        tier at configure/intake."""
        config = self._gate_config()
        tiers = config.risk_tiers if config is not None else {}
        return classify(scope, tiers)

    async def run_intake(self, task_id: str) -> Task:
        if self.repo_root is None:
            raise ValueError("kagan must run inside a git repository (none found here)")
        task = self._require(task_id)
        reports, ok = await launch_intake(task, self.repo_root, timeout=self._agent_timeout())
        for r in reports:
            self._apply_report(task_id, r)
        task = self._require(task_id)
        # Lever 4: classify the risk tier from the task's scope now that intake has
        # run; persists it so the gate/approve/validator all read one tier.
        risk = self._classify_risk(task.scope, exclude_id=task.id)
        if risk != task.risk:
            task = self.update_task(task_id, risk=risk)
        # Distinguish a fully-specified ticket (intake ran, no unknowns) from a
        # crashed/silent intake (no reports or non-zero exit). The first is the calm
        # TUI-INTAKE-07 signal; the second must be LOUD, never recorded as clean.
        if not reports or not ok:
            logger.warning(
                "Intake produced no usable reports for task {} (ok={}, reports={})",
                task_id,
                ok,
                len(reports),
            )
            self._ledger.append_event(
                task_id, {"type": "intake_no_output", "ok": ok, "reports": len(reports)}
            )
            task = self._require(task_id)
            if not any(d.id == "intake-no-output" for d in task.decisions):
                task.decisions.append(
                    Decision(
                        id="intake-no-output",
                        question="agent reported nothing — proceed unaided?",
                        severity="blocking",
                        options=["proceed unaided", "retry intake"],
                    )
                )
                self.save_task(task)
        elif not task.decisions:
            # TUI-INTAKE-07: a fully-specified ticket surfaces no decisions; record
            # that intake produced no unknowns so the empty intake is auditable.
            self._ledger.append_event(task_id, {"type": "intake_no_unknowns"})
        return task

    async def start_task(self, task_id: str) -> Task:
        if self.repo_root is None:
            raise ValueError("kagan must run inside a git repository (none found here)")
        # Lever 5: refuse the run at the cap BEFORE any worktree/launch side effect.
        # Exclude this task so a send-back re-running in place is not counted twice.
        if not self.can_start_agent(exclude=task_id):
            raise AgentCapError(self.running_count(exclude=task_id), self._agent_cap())
        task = self._require(task_id)
        cli = task.agent_cli or "claude"
        # Replace-by-source (B11): a run starts a fresh review cycle, so drop the prior
        # cycle's auto-generated findings here — N re-runs then leave ONE set, not N+1
        # stacked copies. Done at run START (not harvest) so findings the agent reports
        # DURING the run survive to the gate. Upheld/overruled verdicts travel into the
        # re-run prompt via _sendback_section, not as persisted findings.
        task.findings = [
            f for f in task.findings if f.source not in self._REGENERATED_FINDING_SOURCES
        ]
        # Idempotent: send-back reuses the existing worktree (TUI-GATE-07).
        task = await self._tasks.prepare_worktree(task, self.repo_root)
        assert task.worktree_path is not None
        wt = task.worktree_path
        task.base_commit = await git.run_git(["rev-parse", "HEAD"], cwd=wt, check=True)
        # Rule 12: whoever owns the RUNNING transition stamps its own pid here — the
        # detached `kagan _run` child for an initial run, the live session for a
        # send-back re-run. Either way it's the process that also watches the agent, so a
        # dead pid = a genuinely stranded run. reconcile_in_flight probes it on launch.
        # Clear any prior interrupted flag — this fresh run supersedes the dead one.
        task.runner_pid = os.getpid()
        task.interrupted = False
        self._ledger.save_task(task)
        task = self._tasks.transition(task_id, TaskState.RUNNING)
        # Services need the worktree; start them once the task is running
        # (TUI-WS-02/07). Skip when the repo declares none.
        with suppress(ConfigurationError):
            await self.start_services(task_id)
        self._write_mcp_config(task)
        proc = await launch_run(task, model=self._builder_model(cli))
        self._agent_procs[task_id] = proc
        self._agent_tasks[task_id] = asyncio.create_task(self._watch_agent(task_id, proc))
        return task

    def _write_mcp_config(self, task: Task) -> None:
        """Point the agent at the report tools by writing its MCP client config into
        the worktree (MCP-AGENT-01). The harness runs NO server: the config tells the
        agent's own MCP client to start `kagan mcp --task-id <id>` over stdio."""
        recipe = recipe_for(task.agent_cli or "claude")
        if recipe.mcp_config_path is None:
            return
        assert task.worktree_path is not None
        config = {
            "mcpServers": {
                "kagan": {
                    "command": "kagan",
                    # --data-dir is load-bearing: the worktree's git root is the worktree
                    # itself, so the server can't re-derive the main repo's ledger — it
                    # must be told (else every report hits an empty ledger). See B-1.
                    "args": ["mcp", "--task-id", task.id, "--data-dir", str(self.data_dir)],
                }
            }
        }
        path = task.worktree_path / recipe.mcp_config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2))

    async def await_agent(self, task_id: str) -> None:
        """Test hook: await the background watcher for this task."""
        t = self._agent_tasks.get(task_id)
        if t is not None:
            await t

    async def cancel_task(self, task_id: str) -> None:
        proc = self._agent_procs.get(task_id)
        if proc is not None:
            await terminate(proc)

    async def _watch_agent(self, task_id: str, proc: asyncio.subprocess.Process) -> None:
        task = self._require(task_id)
        assert task.worktree_path is not None
        wt = task.worktree_path
        cursor = 0

        def apply_one(report: ReportMessage) -> None:
            # Rule 12: isolate a poison report to itself. A malformed envelope must
            # not kill the poll task (its exception would re-raise at `await ask` and
            # strand the run); log it and move on — the cursor advances regardless so
            # it is skipped once, not re-read forever.
            try:
                self._apply_report(task_id, report)
            except Exception:
                logger.warning("dropping unapplyable report ({}) for task {}", report.type, task_id)

        async def poll_ask() -> None:
            nonlocal cursor
            while True:
                for report in read_ask(wt, offset=cursor):
                    apply_one(report)
                    cursor += 1
                await asyncio.sleep(0.05)

        ask = asyncio.create_task(poll_ask())
        # MCP-AGENT-03: completion via process exit, NOT stream parsing. F1: bound it —
        # a timeout kills the process group (its pid dies, so reconcile can reap a
        # stranded task), but the partial diff is still harvested below and the task
        # lands in REVIEW. Downside capped, work never discarded.
        timed_out = not await wait_bounded(proc, self._agent_timeout())
        ask.cancel()
        with suppress(asyncio.CancelledError):
            await ask
        for report in read_ask(wt, offset=cursor):
            apply_one(report)
            cursor += 1
        # The timeout finding is added INSIDE _harvest (this run's by-source purge already
        # happened at start_task), so a re-run clears it cleanly without stripping the
        # finding describing the run that just timed out.
        await self._harvest(task_id, timed_out=timed_out)

    # Findings the harness/gate regenerate every harvest. Replaced by source on each run
    # (B11): re-running a task must not multiply rubric/security/ai-review/machine
    # findings. Human-authored verdicts on the prior set are stale on a re-run anyway —
    # the upheld/overruled ones travel into the re-run prompt via _sendback_section, not
    # as persisted findings.
    _REGENERATED_FINDING_SOURCES = frozenset({"machine", "security", "rubric", "ai-review"})

    async def _harvest(self, task_id: str, *, timed_out: bool = False) -> Task:
        task = self._require(task_id)
        assert task.worktree_path is not None
        wt = task.worktree_path
        # The send-back directive was consumed by this run's prompt at launch; clear it so
        # it can't re-feed an unrelated later re-run or surface in the receipt (B17). The
        # by-source finding purge happens at run START (start_task), not here, so findings
        # the agent reports DURING this run (.kagan/ask ai-review) survive to the gate.
        task.sendback_note = None
        if timed_out:
            mins = max(1, int(self._agent_timeout() // 60))
            task.findings.append(
                Finding(
                    id="agent-timeout",
                    severity="blocking",
                    location="",
                    message=(
                        f"Agent exceeded {mins}m and was stopped — review the partial diff, "
                        "then re-run to continue in the same worktree."
                    ),
                    source="machine",
                )
            )
        # P5: diff harvest = tracked (git diff HEAD) + untracked (ls-files --others).
        tracked = await git.run_git(["diff", "HEAD"], cwd=wt, check=False)
        untracked = await git.run_git(
            ["ls-files", "--others", "--exclude-standard"], cwd=wt, check=False
        )
        diff_text = tracked + _untracked_as_pseudo_diff(untracked)
        # Strip kagan's own run-artifacts (.mcp.json, .kagan/ask, .kagan/prompt*,
        # .kagan/agent.log) from the changed-file set BEFORE drift detection, not
        # after. Stripping before means detect_drift still SEES — and flags — an
        # agent edit to a PROTECTED path (.kagan/repo.yaml, .kagan/decisions*),
        # which a post-filter on .kagan/* would have swallowed. Same RUN_ARTIFACTS
        # set the gate strips (core/paths.is_run_artifact).
        changed = [f for f in git.parse_diff_changed_files(diff_text) if not is_run_artifact(f)]
        findings = detect_drift(task, _untracked_as_pseudo_diff("\n".join(changed)))
        task.findings.extend(findings)
        task.drift = bool(findings)
        # M1: persist the real changed-file set so lever-9 scope debt measures actual
        # churn, not the finding-location proxy. Cap so a huge generated diff can't
        # bloat the gitignored ledger.
        task.changed_files = changed[:500]
        self._ledger.save_task(task)
        # Lever 2: between harvest and the human gate, run the adversarial validator
        # (RUNNING -> VALIDATING, merge ai-review findings). It leaves the
        # VALIDATING -> REVIEW transition to run_gate below (no double-hop).
        await self.run_validation(task_id)
        # Run the gate engine (mirror checks + rubric) and land in REVIEW — the
        # gate does the transition, so do NOT transition here (no double-hop).
        return await self.run_gate(task_id)

    def _apply_report(self, task_id: str, report: ReportMessage) -> None:
        """Apply a `.kagan/ask` report through the SAME single-writer methods the
        MCP tools use — one apply path, both transports converge (no divergence)."""
        p = report.payload
        if report.type == "intake_decisions":
            self.record_intake_decisions(
                task_id, understanding=p.get("understanding", ""), decisions=p.get("decisions", [])
            )
        elif report.type == "needs_you":
            # Persist only — a mid-run question is NOT a PR_OPEN; the human answers
            # it from the Inbox. (The MCP path blocks; the file path can't.)
            task = self._require(task_id)
            task.needs_you = NeedsYou(
                reason=p.get("reason", ""),
                question=p.get("question", ""),
                context=p.get("context", ""),
            )
            self._ledger.save_task(task)
        elif report.type == "smoke_tests":
            items = p.get("items") or p.get("tests") or []
            self.record_smoke_tests(
                task_id,
                tests=[{"behaviour": i.get("text") or i.get("behaviour", "")} for i in items],
            )
        elif report.type == "drift":
            # Agent-self-reported drift is advisory (MCP-DRIFT-02) — a DriftConcern,
            # not a blocking Finding. The harness's own diff-drift (MCP-DRIFT-01) blocks.
            self.record_drift(
                task_id,
                message=p.get("reason") or p.get("message", "agent reported drift"),
                location=p.get("location"),
            )
        elif report.type == "findings":
            # Lever 2: validator findings. Source-stamped ai-review so the receipt/gate
            # distinguish them from machine findings; the human still adjudicates each.
            for f in p.get("findings", []):
                # Isolate per-finding (rule 12): one malformed finding must not drop
                # the rest of a valid validator report.
                try:
                    self.add_finding(
                        task_id,
                        severity=f.get("severity", "question"),
                        location=f.get("location", ""),
                        message=f.get("message", ""),
                        source="ai-review",
                        confidence=f.get("confidence"),
                        status=f.get("status"),
                    )
                except Exception:
                    logger.warning("dropping malformed validator finding for task {}", task_id)
        elif report.type == "comprehension_prompts":
            items = p.get("prompts") or []
            self.record_comprehension_prompts(task_id, prompts=items)
        elif report.type == "done":
            self.record_done(task_id)
        # "raw"/"unknown" ignored; MCP-AGENT-03 governs completion via process exit.

    async def destroy_workspace(self, task_id: str, *, force: bool = False) -> Task:
        if self.repo_root is None:
            raise ValueError("repo_root required to destroy a workspace")
        return await workspace.destroy_workspace(
            self._ledger, self.repo_root, task_id, running=self._running, force=force
        )

    async def start_services(self, task_id: str) -> list[RunningService]:
        if self.repo_root is None:
            raise ValueError("repo_root required to start services")
        return await workspace.start_services(self._ledger, self.repo_root, task_id, self._running)

    async def stop_services(self, task_id: str) -> list[RunningService]:
        if self.repo_root is None:
            raise ValueError("repo_root required to stop services")
        return await workspace.stop_services(self.repo_root, task_id, self._running)

    def workspace_map(self) -> list[Task]:
        return [t for t in self.list_tasks() if t.worktree_path is not None]

    def close(self) -> None:
        """No persistent handles to release; present for API symmetry with aclose()."""

    async def aclose(self) -> None:
        """Async counterpart to close(); the file ledger holds nothing to await."""

    async def __aenter__(self) -> Harness:
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        await self.aclose()

    async def reset(self) -> None:
        await asyncio.to_thread(self._wipe)
        logger.info("Ledger reset complete")

    def _wipe(self) -> None:
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir, ignore_errors=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)


__all__ = ["Harness", "default_data_dir"]
