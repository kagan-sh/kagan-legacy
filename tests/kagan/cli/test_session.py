"""Session navigator routing + the detached-run spawn (DESIGN 3.5).

These guard the blocker the adversarial review caught: re-run and intake-run
must spawn the detached ``kagan _run`` runner, NOT call ``start_task`` inline —
the inline path orphaned the agent (and lost the harvest -> gate -> REVIEW
chain) the moment the user quit the session.
"""

import subprocess
import sys

import pytest

from kagan.cli import _interactive
from kagan.cli._bootstrap import run_async
from kagan.cli.session import Session
from kagan.core import TaskState
from kagan.core.models import NeedsYou, Task

# A fully-answered medium-tier comprehension set (both prompts substantively answered).
_FULL_MEDIUM = {
    "postcondition": "Rounds half-up so the total never drifts on retries.",
    "what_breaks": "Could break on overflow with very large invoice totals.",
}


class _FakeCore:
    """Minimal stand-in for Harness covering only what these paths touch."""

    def __init__(self, task: Task, *, data_dir, repo_root) -> None:
        self._task = task
        self.data_dir = data_dir
        self.repo_root = repo_root
        self.viewed: list[str] = []
        self.start_task_calls: list[str] = []
        self.transitions: list = []
        self.answered_decisions: list = []

    def touch_viewed(self, task_id: str) -> None:
        self.viewed.append(task_id)

    def get_task(self, task_id: str) -> Task | None:
        return self._task if task_id == self._task.id else None

    async def start_task(self, task_id: str) -> None:  # must NEVER be called by re-run
        self.start_task_calls.append(task_id)

    # -- review-path stubs (lever 1) --------------------------------------

    async def gate_is_stale(self, task_id: str) -> bool:
        return False

    def can_approve(self, task_id: str) -> bool:
        # Mirrors the real gate: refused until every required risk-scaled prompt
        # carries a substantive answer.
        from kagan.core.comprehension import required_keys
        from kagan.core.tasks import _is_substantive

        return all(
            _is_substantive(self._task.comprehension.get(k)) for k in required_keys(self._task.risk)
        )

    # -- lever 5 stubs ----------------------------------------------------

    def can_start_agent(self, exclude: str | None = None) -> bool:
        return True  # default: cap not hit; the cap-specific tests override this

    def reconcile_in_flight(self) -> list[str]:
        return []  # rule 12: called once on session launch; no-op for the fake

    def read_events(self, task_id: str) -> list:
        return []  # workspaces "started" elapsed reads transitions; none for the fake

    def running_count(self, exclude: str | None = None) -> int:
        return 0

    def approve_cooldown_remaining(self, task_id: str, now=None) -> int:
        return 0  # default: cooldown elapsed; the cooldown test overrides this

    def record_comprehension(self, task_id: str, key: str, answer: str) -> Task:
        self._task.comprehension[key] = answer
        return self._task

    def transition_task(self, task_id: str, new_state) -> Task:
        self.transitions.append(new_state)
        self._task.state = new_state
        return self._task

    # -- lever 6 stubs ----------------------------------------------------

    def high_risk_approvers(self) -> int:
        return 2

    def approve_task(self, task_id: str, approver: str | None = None) -> Task:
        # Mirror the real chokepoint: record then gate. The fake tasks are medium
        # risk, so one approver meets the bar; READY only when can_approve holds.
        if approver and approver not in self._task.approvers:
            self._task.approvers.append(approver)
        if not self.can_approve(task_id):
            return self._task
        bar = self.high_risk_approvers() if self._task.risk == "high" else 1
        if len(set(self._task.approvers)) < bar:
            return self._task
        return self.transition_task(task_id, TaskState.READY)

    def set_verdict(self, task_id: str, finding_id: str, *, verdict: str, reply: str = ""):
        for f in self._task.findings:
            if f.id == finding_id:
                f.verdict = verdict
                f.reply = reply or None
                return self._task
        return self._task

    def verify_smoke_test(self, task_id: str, smoke_id: str) -> Task:
        for s in self._task.smoke_tests:
            if s.id == smoke_id:
                s.verified = True
                return self._task
        return self._task

    def inbox_tasks(self):
        return []

    def list_tasks(self) -> list[Task]:
        return [self._task]

    # -- lever 8 stubs ----------------------------------------------------

    def propose_retro(self, task_id: str) -> str | None:
        return getattr(self, "retro_suggestion", None)

    def confirm_retro(self, task_id: str, line: str):
        self.retro_appended = line

    # -- ship-view stubs --------------------------------------------------

    def get_push_command(self, task_id: str) -> str:
        return "git push -u origin kagan/t"

    def get_pr_command(self, task_id: str) -> str:
        return "gh pr create --fill"

    def render_pr_body(self, task_id: str) -> str:
        return "# receipt body"

    async def branch_on_origin(self, task_id: str) -> bool | None:
        return getattr(self, "branch_present", True)

    async def mark_task_pushed(self, task_id: str):
        self.marked_pushed = task_id
        return self._task

    # -- sub-frame view stubs (stats / workspaces / new-task) -------------

    def outcome_scorecard(self):
        from kagan.core.stats import Scorecard

        return Scorecard(
            shipped=0,
            cycle_seconds_by_risk={},
            cfr_failed=None,
            cfr_total=None,
            comprehension_first_try=0,
            comprehension_asked=0,
            review_caught=0,
        )

    async def durability_estimate(self, now=None) -> tuple[int, int]:
        return (0, 0)

    def preview_risk(self, scope: list[str]) -> str:
        return "medium"

    def reviewer_configured(self, cli: str) -> bool:
        return getattr(self, "_reviewer_configured", False)

    def available_clis(self) -> list[str]:
        return ["codex"]

    def create_task(self, title: str) -> Task:
        self._task.title = title
        return self._task

    def configure_task(self, task_id: str, *, agent_cli=None, scope=None) -> Task:
        self._task.agent_cli = agent_cli
        self._task.scope = scope or []
        return self._task

    async def run_intake(self, task_id: str) -> None:
        if hasattr(self, "intake_error"):
            raise self.intake_error

    def answer_needs_you(self, task_id: str, answer: str) -> None:
        self.answered = answer

    async def aclose(self) -> None:
        self.closed = True

    # -- intake stubs -----------------------------------------------------

    def can_run(self, task_id: str) -> bool:
        return getattr(self, "_can_run", False)

    def answer_decision(
        self, task_id: str, decision_id: str, *, answer: str, approved: bool = False
    ):
        self.answered_decisions.append((decision_id, answer, approved))


def _session(task: Task, tmp_path) -> tuple[Session, _FakeCore]:
    core = _FakeCore(task, data_dir=tmp_path / "state", repo_root=tmp_path)
    return Session(core), core  # type: ignore[arg-type]


async def _press_enter(_render, handlers, **_kwargs):
    class _Event:
        class _App:
            @staticmethod
            def exit():
                return None

        app = _App()

    handlers["enter"](_Event())


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (TaskState.INTAKE, "view_intake"),
        (TaskState.READY, "view_ship"),
        (TaskState.REVIEW, "view_review"),
        (TaskState.RUNNING, "view_workspaces"),
        (TaskState.VALIDATING, "view_workspaces"),
        (TaskState.PR_OPEN, "view_workspaces"),
    ],
)
def test_open_task_routes_by_state(tmp_path, monkeypatch, state, expected):
    task = Task(id="task-1", title="t", state=state)
    session, core = _session(task, tmp_path)
    called: list[str] = []

    for name in ("view_intake", "view_ship", "view_review", "view_workspaces"):

        async def _rec(*_a, _n=name, **_k) -> None:
            called.append(_n)

        monkeypatch.setattr(session, name, _rec)

    async def _needs_you(*_a, **_k) -> None:
        called.append("view_needs_you")

    monkeypatch.setattr(session, "view_needs_you", _needs_you)

    run_async(session.open_task("task-1"))

    assert called == [expected]
    assert core.viewed == ["task-1"]  # the task is stamped viewed on open


def test_needs_you_outranks_state(tmp_path, monkeypatch):
    task = Task(
        id="task-1",
        title="t",
        state=TaskState.REVIEW,
        needs_you=NeedsYou(reason="r", question="q?"),
    )
    session, _ = _session(task, tmp_path)
    called: list[str] = []

    async def _review(*_a, **_k) -> None:
        called.append("review")

    monkeypatch.setattr(session, "view_review", _review)

    async def _needs_you(*_a, **_k) -> None:
        called.append("needs_you")

    monkeypatch.setattr(session, "view_needs_you", _needs_you)

    run_async(session.open_task("task-1"))

    assert called == ["needs_you"]  # a mid-run question wins over the state (A11)


def test_spawn_run_is_detached_and_well_formed(tmp_path, monkeypatch):
    task = Task(id="task-9", title="t")
    session, core = _session(task, tmp_path)
    captured: dict = {}

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    session._spawn_run("task-9")

    assert captured["cmd"] == [
        sys.executable,
        "-m",
        "kagan",
        "_run",
        "task-9",
        "--data-dir",
        str(core.data_dir),
    ]
    assert captured["kwargs"]["start_new_session"] is True  # detached — survives session quit
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL
    assert captured["kwargs"]["stdout"] == subprocess.DEVNULL
    assert captured["kwargs"]["stderr"] == subprocess.DEVNULL


def test_review_c_records_comprehension_and_gates_approve(tmp_path, monkeypatch):
    # Lever 1: 'a' is refused while no note exists; 'c' records the note through the
    # core; only then does 'a' approve and transition to READY. Proves the gate the
    # user sees can fail, and that the recorded note is what unlocks it.
    task = Task(id="task-7", title="t", state=TaskState.REVIEW)
    session, core = _session(task, tmp_path)

    verbs = iter(["approve", "comprehension", "approve"])

    async def _frame(*_a, **_k):
        return next(verbs)

    monkeypatch.setattr(session, "_review_frame", _frame)
    note = "Rounds half-up so the total never drifts; could break on overflow inputs."

    async def _note(*_a, **_k):
        return note

    monkeypatch.setattr(_interactive, "prompt_in_frame", _note)

    run_async(session.view_review("task-7"))

    # 'c' walked both medium prompts; each was answered through the core.
    assert core._task.comprehension == {"postcondition": note, "what_breaks": note}
    # The first 'a' was refused (no answers); the second 'a' approved exactly once.
    assert core.transitions == [TaskState.READY]


def test_comprehension_walk_resumes_with_prior_answers(tmp_path, monkeypatch):
    # Rule 12 (resume-from-partial-state): re-entering the walk after answering some
    # prompts prefills each prompt with its recorded answer — a re-run never re-demands
    # an answered prompt from scratch. Fails if _walk_comprehension drops default=existing.
    task = Task(
        id="task-rp",
        title="t",
        state=TaskState.REVIEW,
        comprehension={"postcondition": "Rounds half-up so totals never drift on retries."},
    )
    session, _ = _session(task, tmp_path)

    seen: list[str] = []

    async def _capture(render, *, default="", **_k):
        seen.append(default)  # the question is drawn by `render`; we pin the prefill order
        return default  # leave the answers untouched

    monkeypatch.setattr(_interactive, "prompt_in_frame", _capture)

    run_async(session._walk_comprehension(task))

    # Prompt 1 (postcondition) opens prefilled with its recorded answer; prompt 2
    # (what_breaks) opens empty.
    assert seen == ["Rounds half-up so totals never drift on retries.", ""]


def test_comprehension_walk_uses_generated_prompts_at_floor(tmp_path, monkeypatch):
    generated = [
        ("postcondition", "How does billing retry after this diff?"),
        ("what_breaks", "What race could still lose a charge?"),
    ]
    task = Task(
        id="task-gen",
        title="t",
        state=TaskState.REVIEW,
        risk="medium",
        comprehension_prompts=generated,
    )
    session, core = _session(task, tmp_path)
    note = "Retries are idempotent; a race on the webhook could still double-charge."

    async def _note(render, **_k):
        return note

    monkeypatch.setattr(_interactive, "prompt_in_frame", _note)

    run_async(session._walk_comprehension(task))

    assert core._task.comprehension == {"postcondition": note, "what_breaks": note}


def test_comprehension_walk_rejects_trivial_answer_with_feedback(tmp_path, monkeypatch, capsys):
    # B9: a trivial/templated answer is not silently swallowed — the human is told WHY
    # and the junk is never persisted (it cannot ride into the receipt). The same prompt
    # is re-asked until a substantive answer lands.
    task = Task(id="task-tr", title="t", state=TaskState.REVIEW, risk="medium")
    session, core = _session(task, tmp_path)
    good = "Adds a recursive descent parser; deep input could overflow the stack."
    # postcondition: a placeholder (rejected) then a real answer; what_breaks: real.
    replies = iter(["stuff", good, good])

    async def _reply(_render, *, default="", **_k):
        return next(replies)

    monkeypatch.setattr(_interactive, "prompt_in_frame", _reply)

    run_async(session._walk_comprehension(task))

    # The trivial "stuff" was never persisted; both prompts hold their substantive answer.
    assert core._task.comprehension == {"postcondition": good, "what_breaks": good}
    assert "placeholder" in capsys.readouterr().out


def test_review_approve_does_not_offer_retro_at_approve_time(tmp_path, monkeypatch):
    # Phase 12c ship §1: the retro NO LONGER fires at approve-time (the transient
    # prompt the user blew past) — it lives on the ship screen now. Approving still
    # reaches READY, but no AGENTS.md edit is prompted here.
    task = Task(id="task-10", title="t", state=TaskState.REVIEW, comprehension=_FULL_MEDIUM)
    session, core = _session(task, tmp_path)
    core.retro_suggestion = "expr eval lives in src/eval.rs; bad input -> Error"

    async def _frame(*_a, **_k):
        return "approve"

    monkeypatch.setattr(session, "_review_frame", _frame)

    run_async(session.view_review("task-10"))

    assert core.transitions == [TaskState.READY]
    assert not hasattr(core, "retro_appended")


def test_retro_prompt_header_matches_prefilled_submit_model(tmp_path, monkeypatch):
    # B21: the learning field is PREFILLED, so the header must read enter=append /
    # esc=skip — not the contradictory "(enter to skip)" that fought the "enter submit"
    # footer with a non-empty field.
    task = Task(id="task-l", title="t", state=TaskState.READY)
    session, core = _session(task, tmp_path)
    core.retro_suggestion = "openapi.json is the source of truth — never hand-edit api.md"
    seen: dict[str, str] = {}

    async def _capture(label, *, default="", **_k):
        seen["label"] = label
        seen["default"] = default
        return None  # esc — skip

    monkeypatch.setattr(session, "_prompt_in_frame", _capture)
    run_async(session._offer_retro("task-l"))

    assert "enter to skip" not in seen["label"]
    assert "esc to skip" in seen["label"]
    assert seen["default"] == core.retro_suggestion  # the suggestion prefills the field


def test_inbox_body_reprobes_ledger_so_it_never_lags_the_header(tmp_path, monkeypatch):
    # B14: the inbox body must derive from the SAME ledger read as its header on every
    # frame. A task advancing running->review while the inbox is parked open must show
    # the new state in the body, not a stale "running ♥ alive" captured at loop entry.
    from kagan.core import Harness, git
    from kagan.format import inbox as fmt_inbox
    from kagan.format.shell import frame_geometry

    repo = tmp_path / "repo"
    run_async(git.init_repo(repo, initial_branch="main", create_initial_commit=True))
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add-calculator")
    core.transition_task(task.id, TaskState.RUNNING)
    session = Session(core)

    captured: dict[str, str] = {}

    async def _navigate(render, _handlers, **_kw):
        # a detached runner advances the task while the inbox frame is parked open
        core.transition_task(task.id, TaskState.REVIEW)
        captured["text"] = render(frame_geometry(120, 40)).text

    monkeypatch.setattr(_interactive, "navigate", _navigate)

    rows = fmt_inbox.selectable_rows(core.inbox_tasks())  # built while still RUNNING
    run_async(session._inbox_loop(rows))

    assert "alive" not in captured["text"]  # body re-read shows review, not stale running
    # The blocker regression guard: re-run must spawn _run, NOT run start_task in
    # the session loop (which orphans the agent on quit).
    task = Task(id="task-2", title="t", state=TaskState.RUNNING)
    session, core = _session(task, tmp_path)
    spawned: list[str] = []
    monkeypatch.setattr(session, "_spawn_run", lambda tid: spawned.append(tid))

    run_async(session.action_rerun("task-2"))

    assert spawned == ["task-2"]
    assert core.start_task_calls == []  # inline start_task is the bug — must not fire


def test_review_approve_refused_while_cooldown_remains(tmp_path, monkeypatch):
    # Lever 5: even with the gate fully clear (can_approve True), the approve key is
    # refused while the gen->approve cooldown is still running — forcing a real read.
    # Once the window elapses (remaining 0) the same key approves. Proves the surface
    # checks BOTH locks, not just can_approve.
    task = Task(id="task-8", title="t", state=TaskState.REVIEW, comprehension=_FULL_MEDIUM)
    session, core = _session(task, tmp_path)

    # First 'a' lands mid-cooldown (20s left => refused); second 'a' lands after the
    # window (0 => approves). The two presses see the two cooldown readings in order.
    cooldowns = iter([20, 0])
    monkeypatch.setattr(core, "approve_cooldown_remaining", lambda *_a, **_k: next(cooldowns))
    verbs = iter(["approve", "approve"])

    async def _frame(*_a, **_k):
        return next(verbs)

    monkeypatch.setattr(session, "_review_frame", _frame)

    run_async(session.view_review("task-8"))

    assert core.transitions == [TaskState.READY]  # exactly one approve, only after the window


def test_rerun_refused_at_agent_cap_before_spawning(tmp_path, monkeypatch):
    # Lever 5: at the cap the surface refuses the run and never spawns the detached
    # runner — otherwise start_task's AgentCapError would fire invisibly in the
    # detached process and the user would think the run started.
    task = Task(id="task-3", title="t", state=TaskState.RUNNING)
    session, core = _session(task, tmp_path)
    monkeypatch.setattr(core, "can_start_agent", lambda exclude=None: False)
    monkeypatch.setattr(core, "running_count", lambda exclude=None: 2)
    spawned: list[str] = []
    monkeypatch.setattr(session, "_spawn_run", lambda tid: spawned.append(tid))

    run_async(session.action_rerun("task-3"))

    assert spawned == []  # refused at the cap — nothing spawned


# -- Phase 12d-2: review focused-walk acts on the focused item -----------------


def test_findings_g_d_acts_on_focused_finding_not_first(tmp_path, monkeypatch):
    # Phase 12d-2: j/k move the finding cursor and g/d act on the FOCUSED finding,
    # not always open_findings[0]. Fails if _adjudicate_finding still hard-codes index 0.
    from kagan.core.models import Finding

    findings = [
        Finding(id="f0", severity="blocking", location="a.py:1", message="m0"),
        Finding(id="f1", severity="blocking", location="b.py:2", message="m1"),
    ]
    task = Task(id="task-fw", title="t", state=TaskState.REVIEW, findings=findings)
    session, core = _session(task, tmp_path)

    # Step into findings, move cursor to f1, disagree, then back out.
    review_verbs = iter(["findings", "back"])

    async def _review_frame(*_a, **_k):
        return next(review_verbs)

    monkeypatch.setattr(session, "_review_frame", _review_frame)

    calls = {"n": 0}

    async def _findings_frame(_task, open_findings, cursor):
        calls["n"] += 1
        if calls["n"] == 1:
            cursor["i"] = 1  # supervisor walked down to the second finding
            return "disagree"
        return "back"

    monkeypatch.setattr(session, "_findings_frame", _findings_frame)

    reasons = iter(["not a bug"])

    async def _reason(*_a, **_k):
        return next(reasons)

    monkeypatch.setattr(_interactive, "prompt_in_frame", _reason)

    run_async(session.view_review("task-fw"))

    assert core._task.findings[1].verdict == "disagree"
    assert core._task.findings[1].reply == "not a bug"
    assert core._task.findings[0].verdict is None  # untouched


def test_smoke_v_verifies_focused_test_not_bulk(tmp_path, monkeypatch):
    # Phase 12d-2: j/k move the smoke cursor and v verifies the FOCUSED test only,
    # not every unverified test in a bulk loop. Fails if view_review still loops over
    # task.smoke_tests on 'v'.
    from kagan.core.models import SmokeTest

    smoke = [
        SmokeTest(id="s0", behaviour="login works"),
        SmokeTest(id="s1", behaviour="api up", service="api"),
    ]
    task = Task(id="task-sw", title="t", state=TaskState.REVIEW, smoke_tests=smoke)
    session, core = _session(task, tmp_path)

    review_verbs = iter(["smoke", "back"])

    async def _review_frame(*_a, **_k):
        return next(review_verbs)

    monkeypatch.setattr(session, "_review_frame", _review_frame)

    calls = {"n": 0}

    async def _smoke_frame(_task, smoke_todo, cursor):
        calls["n"] += 1
        if calls["n"] == 1:
            cursor["i"] = 1  # supervisor focused the second smoke test
            return "verify"
        return "back"

    monkeypatch.setattr(session, "_smoke_frame", _smoke_frame)

    run_async(session.view_review("task-sw"))

    assert core._task.smoke_tests[1].verified is True
    assert core._task.smoke_tests[0].verified is False  # untouched


# -- F1 regression: the REAL prompt-toolkit loop, not a stub ------------------
# Every test above stubs the input layer (`_read_key`, `_interactive.text`), so
# none ever runs prompt_toolkit's `app.run_async()`. That is exactly how F1 hid:
# the sync helpers called `app.run()` -> `asyncio.run()` from inside the already
# running session loop and crashed with "asyncio.run() cannot be called from a
# running event loop". These tests drive the live loop headlessly via a pipe
# input + DummyOutput, so a regression to a blocking helper re-raises that crash.


def _headless_session(task: Task, tmp_path, pipe):
    from prompt_toolkit.output import DummyOutput

    core = _FakeCore(task, data_dir=tmp_path / "state", repo_root=tmp_path)
    return Session(core, input=pipe, output=DummyOutput()), core  # type: ignore[arg-type]


def test_review_real_loop_records_note_then_approves(tmp_path):
    # Drives the REAL loop: 'c' walks the two medium prompts (each a single-line answer
    # submitted with Enter), then 'a' approves -> READY. Asserts no nested-loop
    # crash AND the routing/state effect (both answers recorded, transition to READY).
    from prompt_toolkit.input import create_pipe_input

    task = Task(id="task-real-1", title="t", state=TaskState.REVIEW)
    note = "Rounds half-up; could overflow on huge inputs."
    with create_pipe_input() as pipe:
        session, core = _headless_session(task, tmp_path, pipe)
        pipe.send_text("c")  # comprehension key -> walks the prompt set
        pipe.send_text(f"{note}\r")  # prompt 1 answer + submit (single-line: Enter submits)
        pipe.send_text(f"{note}\r")  # prompt 2 answer + submit, loop advances
        pipe.send_text("a")  # approve

        run_async(session.view_review("task-real-1"))  # must NOT raise RuntimeError

    assert core._task.comprehension == {"postcondition": note, "what_breaks": note}
    assert core.transitions == [TaskState.READY]


def test_intake_real_loop_run_key_spawns_detached(tmp_path, monkeypatch):
    # Drives the REAL read_key loop in the intake view: pressing 'r' on a runnable
    # task spawns the detached runner. Proves read_key works under the live loop
    # (the F1 crash site) — not via a monkeypatched _read_key.
    from prompt_toolkit.input import create_pipe_input

    task = Task(id="task-real-2", title="t", state=TaskState.INTAKE)
    spawned: list[str] = []
    with create_pipe_input() as pipe:
        session, core = _headless_session(task, tmp_path, pipe)
        # view_intake reads can_run / can_start_agent off the core; stub them True.
        monkeypatch.setattr(core, "can_run", lambda tid: True, raising=False)
        monkeypatch.setattr(session, "_spawn_run", lambda tid: spawned.append(tid))
        pipe.send_text("r")  # run key

        run_async(session.view_intake("task-real-2"))  # must NOT raise RuntimeError

    assert spawned == ["task-real-2"]


# -- §1.2 keystone: stats / help / bare-workspaces HOLD a frame until dismissed --
# Before the fix these were one-shot _print()s the navigator's next full_screen
# repaint painted over — they flashed and vanished (view_help was even sync, so
# `await view_help()` would TypeError). These drive the REAL loop: the view must
# run a held full-screen frame that ignores non-dismiss keys and exits only on
# 'q'. A regression to a print-and-return never reads the queued keys and the
# spy assertion fails (it didn't route through the held-frame helper at all).


def _spy_real(monkeypatch, name: str) -> list[bool]:
    """Wrap the held-frame helper so we record entry yet still run the REAL loop."""
    seen: list[bool] = []
    real = getattr(_interactive, name)

    async def _wrapped(*args, **kwargs):
        seen.append(True)
        return await real(*args, **kwargs)

    monkeypatch.setattr(_interactive, name, _wrapped)
    return seen


def test_stats_real_loop_holds_frame_and_dismisses_on_q(tmp_path, monkeypatch):
    from prompt_toolkit.input import create_pipe_input

    seen = _spy_real(monkeypatch, "show_until_dismiss")
    task = Task(id="task-st", title="t", state=TaskState.REVIEW)
    with create_pipe_input() as pipe:
        session, _ = _headless_session(task, tmp_path, pipe)
        pipe.send_text("x")  # a non-dismiss key the held frame must ignore
        pipe.send_text("q")  # then dismiss
        run_async(session.view_stats())  # must NOT flash past; holds until 'q'
    assert seen == [True]  # routed through the held-frame helper


def test_help_real_loop_holds_frame_and_dismisses_on_q(tmp_path, monkeypatch):
    from prompt_toolkit.input import create_pipe_input

    seen = _spy_real(monkeypatch, "show_until_dismiss")
    task = Task(id="task-hp", title="t", state=TaskState.REVIEW)
    with create_pipe_input() as pipe:
        session, _ = _headless_session(task, tmp_path, pipe)
        pipe.send_text("x")
        pipe.send_text("q")
        run_async(session.view_help())  # was sync before — await would TypeError
    assert seen == [True]


def test_workspaces_real_loop_holds_frame_and_dismisses_on_q(tmp_path, monkeypatch):
    from prompt_toolkit.input import create_pipe_input

    seen = _spy_real(monkeypatch, "navigate")
    task = Task(id="task-ws", title="t", state=TaskState.RUNNING)
    with create_pipe_input() as pipe:
        session, _ = _headless_session(task, tmp_path, pipe)
        pipe.send_text("x")  # non-dismiss key the bare frame must ignore
        pipe.send_text("q")
        run_async(session.view_workspaces())  # bare workspaces (§1.2/§1.3 frame loop)
    assert seen == [True]


def test_full_screen_loop_uses_live_output_geometry():
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from kagan.format.shell import RenderedFrame

    class _LargeOutput(DummyOutput):
        def get_size(self):
            return Size(rows=50, columns=140)

    seen = []

    def _render(geometry):
        seen.append(geometry)
        return RenderedFrame("frame", width=geometry.width, height=12)

    def _quit(event):
        event.app.exit()

    with create_pipe_input() as pipe:
        pipe.send_text("q")
        run_async(
            _interactive.navigate(
                _render,
                {"q": _quit},
                input=pipe,
                output=_LargeOutput(),
            )
        )

    assert seen
    assert seen[-1].terminal_columns == 140
    assert seen[-1].terminal_rows == 50
    assert seen[-1].width == 100
    assert seen[-1].height == 41


def test_full_screen_display_window_always_hides_the_terminal_cursor():
    from prompt_toolkit.data_structures import Point

    from kagan.format.shell import RenderedFrame

    layout = _interactive._centered_frame(
        lambda _geometry: RenderedFrame("frame", width=80, height=12)
    )
    row = layout.children[0]
    frame = row.children[0]

    assert frame.always_hide_cursor()
    assert frame.content.show_cursor is False
    assert frame.content.get_cursor_position() == Point(x=0, y=0)


def test_workspaces_t_copies_the_cd(tmp_path, monkeypatch):
    # §1.3: 't' was advertised in the footer but unwired. The bare workspaces frame
    # must copy `cd <worktree_path>` of a live worktree to the clipboard.
    from pathlib import Path

    from prompt_toolkit.input import create_pipe_input

    task = Task(
        id="task-t",
        title="fix-rate-limit",
        state=TaskState.RUNNING,
        worktree_path=Path("/tmp/wt/task-t"),
    )
    copied: list[str] = []
    monkeypatch.setattr(_interactive, "copy_to_clipboard", lambda v: copied.append(v) or True)
    with create_pipe_input() as pipe:
        session, _ = _headless_session(task, tmp_path, pipe)
        pipe.send_text("t")  # take over -> copy cd
        pipe.send_text("q")  # dismiss
        run_async(session.view_workspaces())

    assert copied == ["cd /tmp/wt/task-t"]


def test_workspaces_reconciles_and_refreshes_while_open(tmp_path, monkeypatch):
    from kagan.format.shell import frame_geometry

    task = Task(id="task-ws2", title="t", state=TaskState.RUNNING)
    session, core = _session(task, tmp_path)
    reconciled: list[str] = []
    core.reconcile_in_flight = lambda: reconciled.append("reconcile") or []  # type: ignore[method-assign]
    refresh: list[float | None] = []

    async def _navigate(render, _handlers, **kwargs):
        refresh.append(kwargs.get("refresh_interval"))
        render(frame_geometry(100, 40))

    monkeypatch.setattr(_interactive, "navigate", _navigate)

    run_async(session.view_workspaces())

    assert reconciled == ["reconcile"]
    # No background poll timer (DESIGN-PLAT-01 / UI-03); reconcile runs on render instead.
    assert refresh == [None]


# -- §1.4: new-task is a real confirm gate; cancel creates no task ------------


def test_new_task_cancel_creates_no_task_and_says_so(tmp_path, monkeypatch, capsys):
    task = Task(id="task-n", title="t", state=TaskState.INTAKE)
    session, core = _session(task, tmp_path)
    created: list[str] = []
    core.create_task = lambda title: created.append(title)  # type: ignore[attr-defined]

    answers = iter(["a new title", ""])  # title, then scope (blank)

    async def _text(*_a, **_k):
        return next(answers)

    monkeypatch.setattr(_interactive, "prompt_in_frame", _text)

    async def _choose(*_a, **_k):
        return 0  # pick the agent

    monkeypatch.setattr(_interactive, "choose_in_frame", _choose)

    async def _decline(*_a, **_k):
        return False  # cancel at the confirm gate

    monkeypatch.setattr(_interactive, "confirm_in_frame", _decline)

    run_async(session.action_new_task())

    assert created == []  # the gate refused before create_task
    assert "Cancelled — no task created." in capsys.readouterr().out


def test_new_task_empty_title_fails_loud(tmp_path, monkeypatch, capsys):
    task = Task(id="task-n2", title="t", state=TaskState.INTAKE)
    session, core = _session(task, tmp_path)
    created: list[str] = []
    core.create_task = lambda title: created.append(title)  # type: ignore[attr-defined]

    async def _blank(*_a, **_k):
        return ""  # empty title

    monkeypatch.setattr(_interactive, "prompt_in_frame", _blank)

    run_async(session.action_new_task())

    assert created == []
    assert "Title is required — task not created." in capsys.readouterr().out


def test_new_task_cancelled_agent_pick_fails_loud(tmp_path, monkeypatch, capsys):
    task = Task(id="task-n3", title="t", state=TaskState.INTAKE)
    session, core = _session(task, tmp_path)
    created: list[str] = []
    core.create_task = lambda title: created.append(title)  # type: ignore[attr-defined]

    answers = iter(["a title", ""])

    async def _text(*_a, **_k):
        return next(answers)

    monkeypatch.setattr(_interactive, "prompt_in_frame", _text)

    async def _cancel_pick(*_a, **_k):
        return None  # cancel the agent picker

    monkeypatch.setattr(_interactive, "choose_in_frame", _cancel_pick)

    run_async(session.action_new_task())

    assert created == []
    assert "Cancelled." in capsys.readouterr().out


def test_new_task_scope_prompt_explains_scope(tmp_path, monkeypatch):
    # Phase 5: "scope" must be self-explanatory in-frame (no docs). The Scope prompt
    # carries an explanatory body; the Title prompt does not.
    task = Task(id="task-n5", title="t", state=TaskState.INTAKE)
    session, _ = _session(task, tmp_path)
    captured: list[tuple[str, object]] = []
    fields = iter(["build login", None])  # title ok, then esc the scope prompt -> bail

    async def _field(label, *, body=None, default="", placeholder=""):
        captured.append((label, body))
        return next(fields)

    monkeypatch.setattr(session, "_prompt_in_frame", _field)

    run_async(session.action_new_task())

    scope_calls = [body for label, body in captured if label == "Scope"]
    title_calls = [body for label, body in captured if label == "Title"]
    assert scope_calls and scope_calls[0] is not None  # scope is explained
    assert title_calls and title_calls[0] is None  # title needs no body


def test_new_task_intake_failure_is_not_reported_as_create_failure(tmp_path, monkeypatch, capsys):
    task = Task(id="task-n6", title="t", state=TaskState.INTAKE)
    session, core = _session(task, tmp_path)
    core.intake_error = RuntimeError("bad report")

    fields = iter(["build login", "src/**"])

    async def _field(*_a, **_k):
        return next(fields)

    async def _choose(*_a, **_k):
        return 0

    async def _confirm(*_a, **_k):
        return True

    monkeypatch.setattr(session, "_prompt_in_frame", _field)
    monkeypatch.setattr(session, "_choose_in_frame", _choose)
    monkeypatch.setattr(session, "_confirm_in_frame", _confirm)

    run_async(session.action_new_task())

    out = capsys.readouterr().out
    assert "Cannot plan task: bad report" in out
    assert "Cannot create task" not in out


def test_new_task_intake_runs_inside_planning_frame(tmp_path, monkeypatch):
    from kagan.format.shell import frame_geometry

    task = Task(id="task-n7", title="t", state=TaskState.INTAKE)
    session, _core = _session(task, tmp_path)

    fields = iter(["build login", "src/**"])

    async def _field(*_a, **_k):
        return next(fields)

    async def _choose(*_a, **_k):
        return 0

    async def _confirm(*_a, **_k):
        return True

    seen_frames: list[str] = []

    async def _wait(render, awaitable, **_kw):
        seen_frames.append(render(frame_geometry(100, 40)).text)
        return await awaitable

    opened: list[str] = []

    async def _open(task_id):
        opened.append(task_id)

    monkeypatch.setattr(session, "_prompt_in_frame", _field)
    monkeypatch.setattr(session, "_choose_in_frame", _choose)
    monkeypatch.setattr(session, "_confirm_in_frame", _confirm)
    monkeypatch.setattr(_interactive, "wait_in_frame", _wait)
    monkeypatch.setattr(session, "open_task", _open)

    run_async(session.action_new_task())

    assert opened == ["task-n7"]
    assert any("build login · planning" in frame for frame in seen_frames)


# -- §1.5: fail-loud sentences on the silent terminal paths -------------------


def test_needs_you_empty_answer_says_still_waiting(tmp_path, monkeypatch, capsys):
    task = Task(
        id="task-ny",
        title="migrate-billing",
        state=TaskState.RUNNING,
        needs_you=NeedsYou(reason="waiting", question="which currency?"),
    )
    session, core = _session(task, tmp_path)

    async def _empty(*_a, **_k):
        return ""  # cancelled / empty answer

    monkeypatch.setattr(_interactive, "navigate", _press_enter)
    monkeypatch.setattr(_interactive, "prompt_in_frame", _empty)

    run_async(session.view_needs_you(task))

    out = capsys.readouterr().out
    assert "No answer sent — migrate-billing is still waiting." in out
    assert getattr(core, "answered", None) is None  # nothing sent


def test_needs_you_success_echoes_answer_and_consequence(tmp_path, monkeypatch, capsys):
    task = Task(
        id="task-ny2",
        title="migrate-billing",
        state=TaskState.RUNNING,
        needs_you=NeedsYou(reason="waiting", question="which currency?"),
    )
    session, core = _session(task, tmp_path)

    async def _answer(*_a, **_k):
        return "banker's rounding"

    monkeypatch.setattr(_interactive, "navigate", _press_enter)
    monkeypatch.setattr(_interactive, "prompt_in_frame", _answer)

    run_async(session.view_needs_you(task))

    out = capsys.readouterr().out
    assert core.answered == "banker's rounding"
    assert "banker's rounding" in out  # echoes the answer
    assert "will continue" in out  # states the consequence


def test_review_revalidate_no_worktree_fails_loud(tmp_path, monkeypatch, capsys):
    # §1.5: 'r' re-validate is a silent no-op when there is no live worktree.
    task = Task(id="task-rv", title="t", state=TaskState.REVIEW, comprehension=_FULL_MEDIUM)
    session, core = _session(task, tmp_path)
    assert task.worktree_path is None  # no live worktree

    verbs = iter(["re-validate", "back"])

    async def _frame(*_a, **_k):
        return next(verbs)

    monkeypatch.setattr(session, "_review_frame", _frame)

    run_async(session.view_review("task-rv"))

    assert "Nothing to re-validate — no live worktree." in capsys.readouterr().out


# -- Phase 12c INTAKE: the decision walk actually walks --------------------------


def _intake_task(decisions) -> Task:
    return Task(id="task-iw", title="migrate-billing", state=TaskState.INTAKE, decisions=decisions)


def test_intake_cursor_walks_and_acts_on_the_focused_decision(tmp_path, monkeypatch):
    # Phase 12c intake §1: j/k move a focus index and `a` acts on the FOCUSED decision,
    # NOT always blocking[0]. Move down once, then approve -> the SECOND decision is hit.
    from kagan.core.models import Decision

    decisions = [
        Decision(id="d0", question="rounding?", severity="blocking"),
        Decision(id="d1", question="backfill?", severity="blocking"),
    ]
    task = _intake_task(decisions)
    session, core = _session(task, tmp_path)

    # First frame: move the cursor to d1, then return "approve". Second frame: "back".
    calls = {"n": 0}

    async def _fake_frame(_task, blocking, cursor):
        calls["n"] += 1
        if calls["n"] == 1:
            cursor["i"] = 1  # the supervisor walked down to the second decision
            return "approve"
        return "back"

    monkeypatch.setattr(session, "_intake_frame", _fake_frame)

    run_async(session.view_intake("task-iw"))

    # exactly one decision approved, and it is the FOCUSED one (d1), not blocking[0] (d0).
    assert core.answered_decisions == [("d1", "", True)]


def test_intake_approve_records_the_accepted_assumption(tmp_path, monkeypatch):
    # B16: approving a decision records WHAT was accepted (the agent's assumption = the
    # first offered option), so the receipt reconstructs the decision, not a bare verb.
    from kagan.core.models import Decision

    decisions = [
        Decision(
            id="d0",
            question="precedence?",
            severity="blocking",
            options=["proper (mul-div before add-sub)", "left-to-right"],
        )
    ]
    task = _intake_task(decisions)
    session, core = _session(task, tmp_path)
    verbs = iter(["approve", "back"])

    async def _frame(_t, _b, _c):
        return next(verbs)

    monkeypatch.setattr(session, "_intake_frame", _frame)
    run_async(session.view_intake("task-iw"))

    assert core.answered_decisions == [("d0", "proper (mul-div before add-sub)", True)]


def test_intake_reject_picks_from_offered_options(tmp_path, monkeypatch):
    # B6: reject/override offers the decision's own options as a picker (no retyping a
    # choice that was right there); free-text remains the fallback.
    from kagan.core.models import Decision

    decisions = [
        Decision(
            id="d0",
            question="precedence?",
            severity="blocking",
            options=["proper", "left-to-right"],
        )
    ]
    task = _intake_task(decisions)
    session, core = _session(task, tmp_path)
    verbs = iter(["reject", "back"])

    async def _frame(_t, _b, _c):
        return next(verbs)

    monkeypatch.setattr(session, "_intake_frame", _frame)
    seen: dict[str, list[str]] = {}

    async def _choose(_label, options, **_kw):
        seen["options"] = options
        return 1  # pick "left-to-right" from the offered options

    monkeypatch.setattr(session, "_choose_in_frame", _choose)
    run_async(session.view_intake("task-iw"))

    assert "proper" in seen["options"] and "left-to-right" in seen["options"]
    assert core.answered_decisions == [("d0", "left-to-right", False)]


def test_intake_approve_all_is_gated_by_confirm_and_refused_at_high_risk(tmp_path, monkeypatch):
    # Phase 12c intake §2: `A` approve-all must be gated behind a confirm naming the
    # count + risk, and REFUSED outright at high/irreversible risk (parity with review).
    from kagan.core.models import Decision

    decisions = [Decision(id="d0", question="q", severity="blocking")]

    # High risk: refused, no confirm offered, nothing answered.
    high = _intake_task(decisions)
    high.risk = "high"
    session, core = _session(high, tmp_path)
    verbs = iter(["approve-all", "back"])

    async def _frame(_t, _b, _c):
        return next(verbs)

    monkeypatch.setattr(session, "_intake_frame", _frame)
    confirmed: list[bool] = []

    async def _confirm(*_a, **_k):
        confirmed.append(True)
        return True

    monkeypatch.setattr(_interactive, "confirm_in_frame", _confirm)

    run_async(session.view_intake("task-iw"))
    assert confirmed == []  # high risk refuses before any confirm
    assert core.answered_decisions == []

    # Medium risk: confirm IS offered; declining answers nothing.
    med = _intake_task([Decision(id="d0", question="q", severity="blocking")])
    session2, core2 = _session(med, tmp_path)
    verbs2 = iter(["approve-all", "back"])

    async def _frame2(_t, _b, _c):
        return next(verbs2)

    monkeypatch.setattr(session2, "_intake_frame", _frame2)

    async def _decline(*_a, **_k):
        return False

    monkeypatch.setattr(_interactive, "confirm_in_frame", _decline)

    run_async(session2.view_intake("task-iw"))
    assert core2.answered_decisions == []  # declined the confirm -> nothing approved


# -- Phase 12c SHIP: verify push, retro affordance, copy badge -------------------


def test_ship_enter_refuses_when_branch_absent_on_origin(tmp_path, monkeypatch, capsys):
    # Phase 12c ship §2: before flipping to PR_OPEN, the branch is verified on origin.
    # Absent -> refuse with a clear message; never mark pushed, never auto-push.
    task = Task(id="task-sh", title="t", state=TaskState.READY, branch="kagan/t")
    session, core = _session(task, tmp_path)
    core.branch_present = False

    async def _yes(*_a, **_k):
        return True

    monkeypatch.setattr(_interactive, "confirm_in_frame", _yes)

    handled = run_async(session._verify_and_mark_pushed("task-sh"))

    assert handled is False  # the view stays put
    assert not hasattr(core, "marked_pushed")
    assert "branch not found on origin" in capsys.readouterr().out


def test_ship_enter_softens_when_verification_unavailable(tmp_path, monkeypatch, capsys):
    # Phase 12c ship §2: when gh/network can't verify (None), soften and proceed —
    # do not block the human who really did push.
    task = Task(id="task-sh2", title="t", state=TaskState.READY, branch="kagan/t")
    session, core = _session(task, tmp_path)
    core.branch_present = None  # unverifiable

    async def _yes(*_a, **_k):
        return True

    monkeypatch.setattr(_interactive, "confirm_in_frame", _yes)

    handled = run_async(session._verify_and_mark_pushed("task-sh2"))

    assert handled is True
    assert core.marked_pushed == "task-sh2"
    assert "could not verify" in capsys.readouterr().out


def test_ship_enter_marks_pushed_when_branch_present(tmp_path, monkeypatch):
    task = Task(id="task-sh3", title="t", state=TaskState.READY, branch="kagan/t")
    session, core = _session(task, tmp_path)
    core.branch_present = True

    async def _yes(*_a, **_k):
        return True

    monkeypatch.setattr(_interactive, "confirm_in_frame", _yes)

    assert run_async(session._verify_and_mark_pushed("task-sh3")) is True
    assert core.marked_pushed == "task-sh3"


def test_ship_l_key_appends_retro(tmp_path, monkeypatch):
    # Phase 12c ship §1: `l` on the ship screen offers + appends the lever-8 learning.
    task = Task(id="task-sl", title="t", state=TaskState.READY, branch="kagan/t")
    session, core = _session(task, tmp_path)
    core.retro_suggestion = "docs are generated — never hand-edit"

    keys = iter(["l", "q"])

    async def _next_frame(_body):
        return next(keys)

    monkeypatch.setattr(session, "_ship_frame", _next_frame)

    async def _edited(*_a, **_k):
        return "the confirmed learning"

    monkeypatch.setattr(_interactive, "prompt_in_frame", _edited)

    run_async(session.view_ship("task-sl"))

    assert core.retro_appended == "the confirmed learning"


def test_ship_copy_feedback_only_marks_success(tmp_path, monkeypatch, capsys):
    # #28: the ship controller must not pass `copied="c"` to the renderer when the
    # clipboard backend failed; otherwise the frame lies with "[c ✓ copied]".
    from tests.kagan.format._render import to_str

    task = Task(id="task-cp", title="t", state=TaskState.READY, branch="kagan/t")
    session, _core = _session(task, tmp_path)
    monkeypatch.setattr(_interactive, "copy_to_clipboard", lambda _value: False)

    keys = iter(["c", "q"])
    rendered: list[str] = []

    async def _next_frame(body):
        rendered.append(to_str(body))
        return next(keys)

    monkeypatch.setattr(session, "_ship_frame", _next_frame)

    run_async(session.view_ship("task-cp"))

    assert all("[c ✓ copied]" not in body for body in rendered)
    assert "Push command (copy unavailable" in capsys.readouterr().out


# -- Phase 12c INBOX: the coach aside is a ONE-TIME line, not in the frame -------


def test_coach_aside_is_emitted_once_before_the_navigator(tmp_path, monkeypatch, capsys):
    # Phase 12c inbox §1: the lever-5 coach lines print ONCE before the navigator loop,
    # not inside the repainting inbox frame (so a fatigue nudge isn't an ambient bar).
    task = Task(id="task-c", title="t", state=TaskState.RUNNING)
    session, core = _session(task, tmp_path)
    monkeypatch.setattr(
        session, "_private_coach_lines", lambda: ["it is after hours — the queue keeps"]
    )

    # The navigator loop exits immediately (quit) so we only observe the pre-loop aside.
    async def _inbox_loop(_rows):
        return ("quit", None)

    monkeypatch.setattr(session, "_inbox_loop", _inbox_loop)

    run_async(session.run())

    out = capsys.readouterr().out
    assert out.count("it is after hours — the queue keeps") == 1  # exactly once, not per keystroke


# -- Phase 12c HELP: keymap is the single source; every loop key appears ---------


def test_keymap_covers_every_loop_handled_key():
    # Phase 12c help §1: the `?` keymap and the footers derive from ONE registry
    # (_VIEW_KEYS), so footer and help can't drift apart. This pins the specific
    # regression that motivated the single source — the Review group silently omitted
    # the keys its loop handles — by asserting the main review navigator's keys are
    # all listed. Phase 12d-2 added j/k/enter for the readiness-first cursor.
    from kagan.cli.session import _VIEW_KEYS

    review_hints = _VIEW_KEYS["Review"]
    for key in ("j", "k", "enter", "a", "c", "D", "s", "f", "v", "r", "q"):
        assert any(key in h.key for h in review_hints), (
            f"Review loop handles {key!r} but the keymap omits it"
        )


def test_no_in_session_prompt_escapes_the_frame():
    # Phase 6: every in-session prompt renders INSIDE the control-plane frame. The raw
    # PromptSession helpers (text/confirm/choose) are reserved for the PREFLIGHT
    # (init/doctor, before the box exists) — they must never appear in session.py.
    import inspect

    from kagan.cli import session as sess

    src = inspect.getsource(sess)
    for pattern in (
        "self._text(",
        "self._multiline(",
        "_interactive.text(",
        "_interactive.multiline(",
        "_interactive.confirm(",
        "_interactive.choose(",
        ".pager(",
    ):
        assert pattern not in src, f"in-session prompt escapes the frame: {pattern}"


def test_review_d_opens_in_frame_diff_viewer(tmp_path, monkeypatch):
    task = Task(
        id="task-diff",
        title="t",
        state=TaskState.REVIEW,
        changed_files=["a.py"],
        worktree_path=str(tmp_path),
    )
    (tmp_path / "a.py").write_text("new\n", encoding="utf-8")
    session, _core = _session(task, tmp_path)
    navigated: list[str] = []

    review_verbs = iter(["diff", "back"])

    async def _review_frame(*_a, **_k):
        return next(review_verbs)

    async def _view_diff(_task):
        navigated.append("diff")

    monkeypatch.setattr(session, "_review_frame", _review_frame)
    monkeypatch.setattr(session, "_view_diff", _view_diff)

    run_async(session.view_review("task-diff"))

    assert navigated == ["diff"]


def test_findings_disagree_d_does_not_collide_with_review_capital_d(tmp_path):
    from kagan.cli.session import _VIEW_KEYS

    review_keys = {hint.key for hint in _VIEW_KEYS["Review"]}
    findings_keys = {hint.key for hint in _VIEW_KEYS["Findings"]}
    assert "D" in review_keys
    assert "d" in findings_keys
    assert "D" not in findings_keys
    assert "d" not in review_keys


def test_view_diff_stays_in_frame_via_navigate(tmp_path, monkeypatch):
    task = Task(
        id="task-diff2",
        title="t",
        state=TaskState.REVIEW,
        changed_files=["a.py"],
        worktree_path=str(tmp_path),
    )
    (tmp_path / "a.py").write_text("line\n", encoding="utf-8")
    session, _core = _session(task, tmp_path)
    calls: list[str] = []

    class _FakeViewport:
        async def window(self, offset: int, height: int, width: int):
            return (["diff body"], offset, 1)

    async def _fake_open(_task):
        return _FakeViewport()

    async def _fake_navigate(_render, _handlers, **_k):
        from prompt_toolkit.key_binding import KeyBindings

        bindings = KeyBindings()
        for key, handler in _handlers.items():
            bindings.add(key)(handler)
        calls.append("navigate")
        geometry = __import__("kagan.format.shell", fromlist=["frame_geometry"]).frame_geometry(
            100, 40
        )
        _render(geometry)

    monkeypatch.setattr("kagan.core.diff.open_diff_viewport", _fake_open)
    monkeypatch.setattr(_interactive, "navigate", _fake_navigate)

    run_async(session._view_diff(task))

    assert calls == ["navigate"]


def test_inbox_footer_only_advertises_actions_available_in_context():
    from kagan.cli.session import _inbox_footer
    from kagan.core.inbox import build_item

    empty = _inbox_footer([], None)
    assert [hint.key for hint in empty] == ["n", "w", "S", "?", "q"]

    drift = Task(id="task-drift", title="drift", state=TaskState.RUNNING, drift=True)
    focused = _inbox_footer([build_item(drift)], 0)
    keys = [hint.key for hint in focused]
    assert keys[:4] == ["↑↓ / j k", "enter", "s", "a"]
    assert "r" not in keys
    assert "p" not in keys


def test_intake_footer_hides_locked_run_and_high_risk_approve_all():
    from kagan.cli.session import _intake_footer

    locked = _intake_footer(2, can_run=False, risk="high")
    assert [hint.key for hint in locked] == ["↑↓ / j k", "a", "x", "q"]

    unlocked = _intake_footer(0, can_run=True, risk="medium")
    assert [hint.key for hint in unlocked] == ["r", "q"]


def test_review_and_workspace_footers_hide_unavailable_actions():
    from kagan.cli.session import _review_footer, _workspace_footer

    task = Task(
        id="task-review",
        title="review",
        state=TaskState.REVIEW,
        comprehension=_FULL_MEDIUM,
    )
    review = _review_footer(
        task,
        locked=True,
        cooldown_remaining=10,
        has_focusable=False,
    )
    review_keys = [hint.key for hint in review]
    assert "a" not in review_keys
    assert "c" not in review_keys
    assert "v" not in review_keys
    assert review_keys == ["s", "D", "r", "q"]

    assert [hint.key for hint in _workspace_footer(False)] == ["w", "q"]
    assert [hint.key for hint in _workspace_footer(True)] == ["t", "w", "q"]


# -- NEEDS-YOU: the answer routes through the in-frame prompt ----------


def test_needs_you_answer_routes_through_in_frame_prompt(tmp_path, monkeypatch):
    # Phase 4: the mid-run answer is captured IN-FRAME (prompt_in_frame, ctrl-o opens
    # $EDITOR for a long one), not a raw line below the box.
    task = Task(
        id="task-nym",
        title="migrate-billing",
        state=TaskState.RUNNING,
        needs_you=NeedsYou(reason="waiting", question="which currency?"),
    )
    session, core = _session(task, tmp_path)
    routed: list[str] = []

    monkeypatch.setattr(_interactive, "navigate", _press_enter)

    async def _in_frame(*_a, **_k):
        routed.append("prompt_in_frame")
        return "banker's rounding"

    monkeypatch.setattr(_interactive, "prompt_in_frame", _in_frame)

    run_async(session.view_needs_you(task))

    assert routed == ["prompt_in_frame"]  # answer captured in-frame, not a raw line
    assert core.answered == "banker's rounding"


# -- Phase 12c WORKSPACES: the cooldown nudge is threaded for a just-landed review --


def test_workspaces_threads_cooldown_for_just_landed_review(tmp_path):
    # Phase 12c workspaces §1: a REVIEW task still in cooldown produces a cooldown note
    # the detail renderer surfaces — the screen's attention-thesis contribution.
    task = Task(id="task-cd", title="export-csv", state=TaskState.REVIEW)
    session, core = _session(task, tmp_path)
    core.approve_cooldown_remaining = lambda *_a, **_k: 20  # 20s left

    note = session._cooldown_note(task)
    assert note is not None
    assert "give it a read before approving" in note
    assert "0:20" in note

    # A non-REVIEW task (or elapsed cooldown) has no note.
    running = Task(id="task-r", title="t", state=TaskState.RUNNING)
    assert session._cooldown_note(running) is None
