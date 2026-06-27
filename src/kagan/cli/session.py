"""The single `kagan` interactive session — the only user entrypoint.

An inbox navigator (a pure read over the ledger) that opens a task into its
state-appropriate view (intake / review / ship / workspaces / answer) and routes
key actions through ``Harness`` (the single writer). new / stats / help are
in-session actions. Invoke-and-exit: no persistent dashboard, no live
agent-output stream, no background poll timer (re-invocation hygiene re-probes
fresh state on every render).

This module owns the keymap registry (the replacement for tui/keybindings.py),
the prompt-toolkit key loops, and the action routing. Rendering is delegated to
``kagan.format.*`` (pure Rich); input to ``kagan.cli._interactive`` (the only
prompt-toolkit importer).
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from kagan.cli import _interactive
from kagan.format import gate as fmt_gate
from kagan.format import inbox as fmt_inbox
from kagan.format import intake as fmt_intake
from kagan.format import needs_you as fmt_needs_you
from kagan.format import new_task as fmt_new_task
from kagan.format import ship as fmt_ship
from kagan.format import stats as fmt_stats
from kagan.format import workspaces as fmt_workspaces
from kagan.format.gate import _focusable_readiness_rows
from kagan.format.help import KeyHint, render_footer, render_footer_hint, render_keymap
from kagan.format.shell import FrameGeometry, RenderedFrame, render_frame, render_input_line

if TYPE_CHECKING:
    from kagan.core import Harness, InboxItem, Task

# The single keymap registry (replaces tui/keybindings.py). It is the ONE source of
# truth: each view's footer line AND the `?` keymap derive from the same tuple, so
# they cannot drift. ``test_keymap_covers_every_loop_handled_key`` asserts every key
# a view-loop actually accepts appears here (the regression that let Review's footer
# omit g/d/v/q while the loop handled them).
_PROMPT_HINT = "enter submit · ctrl-o editor · esc cancel"
_TRIVIAL_COMPREHENSION_HINT = (
    "That reads as a placeholder — restate it in your own words; "
    "the gate needs your understanding, not a stand-in."
)

_VIEW_KEYS: dict[str, tuple[KeyHint, ...]] = {
    "Inbox": (
        KeyHint("↑↓ / j k", "move"),
        KeyHint("enter", "open a task"),
        KeyHint("n", "new task"),
        KeyHint("w", "workspaces"),
        KeyHint("S", "stats"),
        KeyHint("?", "help"),
        KeyHint("q", "quit"),
    ),
    "Inbox row actions": (
        KeyHint("s", "send back (drift)"),
        KeyHint("a", "allow scope (drift)"),
        KeyHint("r", "re-run (ci failed / interrupted)"),
        KeyHint("p", "copy push (ready)"),
    ),
    "Review": (
        KeyHint("↑↓ / j k", "move"),
        KeyHint("enter", "open"),
        KeyHint("a", "approve"),
        KeyHint("c", "comprehension"),
        KeyHint("D", "view diff"),
        KeyHint("s", "send back"),
        KeyHint("f", "findings"),
        KeyHint("v", "smoke"),
        KeyHint("r", "re-validate"),
        KeyHint("q", "back"),
    ),
    "Diff": (
        KeyHint("↑↓ / j k", "scroll"),
        KeyHint("pgup / pgdn", "page"),
        KeyHint("q", "back"),
    ),
    "Findings": (
        KeyHint("↑↓ / j k", "move"),
        KeyHint("g", "agree"),
        KeyHint("d", "disagree"),
        KeyHint("q", "back"),
    ),
    "Smoke": (
        KeyHint("↑↓ / j k", "move"),
        KeyHint("v", "verify"),
        KeyHint("q", "back"),
    ),
    "Intake": (
        KeyHint("↑↓ / j k", "move"),
        KeyHint("a", "approve"),
        KeyHint("x", "reject"),
        KeyHint("A", "approve-all"),
        KeyHint("r", "run"),
        KeyHint("q", "back"),
    ),
    "Ship": (
        KeyHint("c", "copy push"),
        KeyHint("p", "copy pr"),
        KeyHint("r", "copy receipt"),
        KeyHint("l", "learning"),
        KeyHint("enter", "I pushed & opened PR"),
        KeyHint("q", "quit"),
    ),
    "Workspaces": (
        KeyHint("t", "take over (copy cd)"),
        KeyHint("w", "back"),
        KeyHint("q", "quit"),
    ),
    "needs-you": (
        KeyHint("enter", "submit"),
        KeyHint("ctrl-o", "editor"),
        KeyHint("esc", "leave it waiting"),
    ),
}


def _repo_name(core: Harness) -> str:
    return core.repo_root.name if core.repo_root else "kagan"


def _accepted_assumption(decision) -> str:
    """The agent's assumption a human accepts on Approve = the first offered option
    (DESIGN §5 'take the assumption'); empty when the decision carried no options."""
    return decision.options[0] if decision.options else ""


def _print(console_text: str) -> None:
    # One stdout seam; ANSI strings already carry styling.
    print(console_text)


def _dim(line: str):
    from rich.text import Text

    return Text(line, style="secondary")


class Session:
    """The interactive session over a single Harness."""

    def __init__(self, core: Harness, *, input=None, output=None) -> None:
        self.core = core
        # Headless test seam: a prompt-toolkit pipe input + dummy output threaded
        # into every prompt loop. None in production so the real TTY is used.
        self._input = input
        self._output = output

    # -- rendering --------------------------------------------------------

    def _ansi(self, renderable, *, columns: int | None = None) -> str:
        width = columns or shutil.get_terminal_size((80, 24)).columns
        return _interactive.render_to_ansi(renderable, columns=width)

    def _frame(
        self,
        renderable,
        geometry: FrameGeometry,
        *,
        minimum_height: int = 12,
        header=None,
        footer=None,
    ) -> RenderedFrame:
        return render_frame(
            renderable,
            geometry,
            minimum_height=minimum_height,
            header=header,
            footer=footer,
        )

    def _inbox_frame(
        self, items: list[InboxItem], cursor: int | None, geometry: FrameGeometry
    ) -> RenderedFrame:
        from kagan.core import attention_counts, coach_hint

        counts = attention_counts(self.core.list_tasks())
        coach = coach_hint(items)
        standing = self._standing_line(items)
        header = fmt_inbox.render_header(
            counts,
            _repo_name(self.core),
            quiet=not items,
            branded=bool(items) or geometry.compact,
        )
        body = fmt_inbox.render_inbox_body(
            items,
            coach=coach,
            cursor=cursor,
            standing=standing,
            compact=geometry.compact,
        )
        footer = render_footer_hint(_inbox_footer(items, cursor))

        # The lever-5 coach lines are NOT here: a fatigue nudge re-rendered every
        # keystroke becomes an ambient status bar. They are shown ONCE, before the
        # navigator frame (see ``run``), as a deferential aside.
        return self._frame(
            body,
            geometry,
            minimum_height=17 if not items else 12,
            header=header,
            footer=footer,
        )

    def _private_coach_lines(self) -> list[str]:
        from kagan.core import after_hours_note, recent_approval_count, throughput_note

        lines = []
        after = after_hours_note()
        if after is not None:
            lines.append(after)
        events = [self.core.read_events(t.id) for t in self.core.list_tasks()]
        nudge = throughput_note(recent_approval_count(events))
        if nudge is not None:
            lines.append(nudge)
        return lines

    def _emit_coach_aside(self) -> None:
        """Print the lever-5 coach lines ONCE, before the live navigator frame, so a
        fatigue nudge is a deferential aside — never an ambient status bar that
        re-renders on every keystroke (Phase 12c inbox §1)."""
        for line in self._private_coach_lines():
            _print(self._ansi(_dim(line)))

    def _standing_line(self, items: list[InboxItem]) -> str | None:
        if items:
            return None
        live = {"running", "validating"}
        active = sum(1 for t in self.core.list_tasks() if t.state.value in live)
        # DESIGN §5 empty-state: agents working + when the queue last shipped (cheaply
        # derived from the ledger). No "next check ~5m" clause — invoke-and-exit, no poll.
        from kagan.core import last_shipped_note

        events = [self.core.read_events(t.id) for t in self.core.list_tasks()]
        shipped = last_shipped_note(events)
        line = f"{active} agents working"
        return f"{line} · {shipped}" if shipped else line

    # -- navigator --------------------------------------------------------

    async def run(self) -> None:
        """Re-probe the ledger, render the inbox, run the key loop until quit."""
        try:
            # Rule 12 "reap on every surface": before the first render, reap any task
            # whose detached runner was hard-killed so it stops eating a cap slot and
            # surfaces as re-runnable (a live runner is left untouched).
            self.core.reconcile_in_flight()
            self._emit_coach_aside()  # lever 5: a one-time deferential aside, not a status bar
            while True:
                items = self.core.inbox_tasks()
                rows = fmt_inbox.selectable_rows(items)
                action = await self._inbox_loop(rows)
                if action is None or action == ("quit", None):
                    return
                verb, task_id = action
                await self._dispatch(verb, task_id, rows)
        finally:
            await self.core.aclose()

    async def _inbox_loop(self, rows: list[InboxItem]) -> tuple[str, str | None] | None:
        """Render the inbox and capture one navigator action.

        Returns ``(verb, task_id)`` or None to quit. ``verb`` is one of: open,
        send-back, allow-scope, re-run, copy-push, new, workspaces, stats, help.
        """
        cursor: dict[str, int | None] = {"i": 0 if rows else None}
        result: dict[str, tuple[str, str | None] | None] = {"action": None}
        # B14: re-read the ledger on every frame so the body AND the header derive from
        # the SAME snapshot — a detached runner's transition can't leave the row list
        # stale while the badge already moved on. Not a poll timer (DESIGN-UI-03): the
        # read happens only on a keypress repaint, never on a background tick.
        live: dict[str, list[InboxItem]] = {"rows": rows}

        def _focused() -> InboxItem | None:
            i, current = cursor["i"], live["rows"]
            return current[i] if i is not None and 0 <= i < len(current) else None

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            items = self.core.inbox_tasks()
            live["rows"] = fmt_inbox.selectable_rows(items)
            if not live["rows"]:
                cursor["i"] = None
            elif cursor["i"] is None:
                cursor["i"] = 0
            else:
                cursor["i"] = min(cursor["i"], len(live["rows"]) - 1)
            return self._inbox_frame(items, cursor["i"], geometry)

        def _move(step: int):
            def _handler(event) -> None:
                current = live["rows"]
                if current and cursor["i"] is not None:
                    cursor["i"] = (cursor["i"] + step) % len(current)

            return _handler

        def _emit(verb: str, *, task: bool, gate: set[str] | None = None):
            def _handler(event) -> None:
                item = _focused() if task else None
                if task:
                    if item is None or (gate is not None and item.signal not in gate):
                        return
                    result["action"] = (verb, item.task_id)
                else:
                    result["action"] = (verb, None)
                event.app.exit()

            return _handler

        handlers = {
            "down": _move(1),
            "j": _move(1),
            "up": _move(-1),
            "k": _move(-1),
            "enter": _emit("open", task=True),
            "s": _emit("send-back", task=True, gate={"drift"}),
            "a": _emit("allow-scope", task=True, gate={"drift"}),
            "r": _emit("re-run", task=True, gate={"ci-failed", "interrupted"}),
            "p": _emit("copy-push", task=True, gate={"ready"}),
            "n": _emit("new", task=False),
            "w": _emit("workspaces", task=False),
            "S": _emit("stats", task=False),
            "?": _emit("help", task=False),
            "q": _emit("quit", task=False),
            "c-c": _emit("quit", task=False),
        }
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)
        return result["action"]

    async def _dispatch(self, verb: str, task_id: str | None, rows: list[InboxItem]) -> None:
        if verb == "open" and task_id:
            await self.open_task(task_id)
        elif verb == "allow-scope" and task_id:
            await self.action_allow_scope(task_id)
        elif verb == "send-back" and task_id:
            await self.action_send_back(task_id)
        elif verb == "re-run" and task_id:
            await self.action_rerun(task_id)
        elif verb == "copy-push" and task_id:
            self.action_copy_push(task_id)
        elif verb == "new":
            await self.action_new_task()
        elif verb == "workspaces":
            await self.view_workspaces()
        elif verb == "stats":
            await self.view_stats()
        elif verb == "help":
            await self.view_help()

    # -- open routing -----------------------------------------------------

    async def open_task(self, task_id: str) -> None:
        """Stamp viewed, then route to the state view (ports app.open_task)."""
        self.core.touch_viewed(task_id)
        task = self.core.get_task(task_id)  # re-read fresh; never route off the cached row
        if task is None:
            return
        from kagan.core import TaskState

        if task.needs_you is not None:  # a mid-run question outranks the state (A11)
            await self.view_needs_you(task)
        elif task.state is TaskState.INTAKE:
            await self.view_intake(task_id)
        elif task.state is TaskState.READY:
            await self.view_ship(task_id)
        elif task.state in (TaskState.RUNNING, TaskState.VALIDATING, TaskState.PR_OPEN):
            await self.view_workspaces(focus=task_id)
        elif task.state in (TaskState.REVIEW, TaskState.DONE):
            await self.view_review(task_id)

    # -- inbox row actions ------------------------------------------------

    async def action_allow_scope(self, task_id: str) -> None:
        await self.core.allow_scope(task_id)

    async def action_send_back(self, task_id: str) -> None:
        comment = await self._prompt_in_frame(
            "Why send it back?", placeholder="what to fix / why it's not ready"
        )
        if not comment or not comment.strip():
            return
        try:
            await self.core.send_back(task_id, comment.strip())
        except Exception as exc:
            _print(f"Could not send back: {exc}")

    async def action_rerun(self, task_id: str) -> None:
        # DESIGN 3.5: spawn the detached `_run` runner so the agent run + harvest
        # + gate finish headless and the session stays safe to quit.
        if not self._agent_cap_ok(exclude=task_id):
            return
        try:
            self._spawn_run(task_id)
            _print("Re-run started — running in the background.")
        except Exception as exc:
            _print(f"Could not re-run: {exc}")

    def _agent_cap_ok(self, *, exclude: str | None = None) -> bool:
        """Lever 5: the surface refuses a new run at the cap and says why, BEFORE
        spawning the detached runner (where start_task's AgentCapError would be
        invisible). Returns True when a run may start."""
        if self.core.can_start_agent(exclude=exclude):
            return True
        running = self.core.running_count(exclude=exclude)
        _print(f"{running} agents already working (cap) — finish a review first.")
        return False

    def _spawn_run(self, task_id: str) -> None:
        """Spawn ``kagan _run <id>`` detached (DESIGN 3.5).

        The agent run + harvest + gate execute in this child process, not the
        session's event loop, so quitting the session never orphans an in-flight
        run (the inline ``start_task`` it replaces did exactly that).
        """
        cmd = [
            sys.executable,
            "-m",
            "kagan",
            "_run",
            task_id,
            "--data-dir",
            str(self.core.data_dir),
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.core.repo_root) if self.core.repo_root else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # F12: claim RUNNING synchronously (owned by the child's pid) so the frame rendered
        # right after `r` re-probes a running task, never the stale pre-run intake frame.
        self.core.claim_running(task_id, proc.pid)

    def action_copy_push(self, task_id: str) -> None:
        try:
            cmd = self.core.get_push_command(task_id)
        except ValueError:
            _print("No branch set — nothing to push.")
            return
        copied = _interactive.copy_to_clipboard(cmd)
        _print(f"Push command{' copied' if copied else ''}: {cmd}")

    # -- state views ------------------------------------------------------

    async def view_needs_you(self, task: Task) -> None:
        if task.needs_you is None:
            return
        from rich.console import Group

        result: dict[str, bool] = {"submit": False}

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            body = fmt_needs_you.render_needs_you(task)
            footer = render_footer(_NEEDS_YOU_FOOTER)
            return self._frame(Group(body, footer), geometry)

        def _submit(event) -> None:
            result["submit"] = True
            event.app.exit()

        def _leave(event) -> None:
            event.app.exit()

        await _interactive.navigate(
            _render,
            {"enter": _submit, "c-o": _submit, "escape": _leave, "c-c": _leave},
            input=self._input,
            output=self._output,
        )
        if not result["submit"]:
            return
        # The mid-run answer is captured in-frame (ctrl-o opens $EDITOR for a long one),
        # with the question kept on screen above the input line.
        answer = await self._prompt_in_frame(
            "Your answer", body=fmt_needs_you.render_needs_you(task)
        )
        if not answer or not answer.strip():
            _print(f"No answer sent — {task.title} is still waiting.")
            return
        self.core.answer_needs_you(task.id, answer.strip())
        _print(f'Answered "{answer.strip()}" — {task.title} will continue.')

    async def view_intake(self, task_id: str) -> None:
        """The decision walk: j/k/up/down move a focus cursor, a/x act on the FOCUSED
        decision (not always blocking[0]), and the frame updates in place rather than
        stacking a panel per keypress. Async actions exit the frame, run, re-enter."""
        cursor: dict[str, int] = {"i": 0}
        while True:
            task = self.core.get_task(task_id)
            if task is None:
                return
            # The whole walk is adjudicable — blocking first, then optional `○` rows (F11,
            # DESIGN §5 / appendix ③). Only blocking decisions gate the run (can_run); an
            # unanswered optional is still focusable so the human can pin it, not left to
            # the agent's silent assumption. Order matches fmt_intake.render_intake.
            open_decisions = [d for d in task.decisions if not (d.answer or d.approved)]
            pending = [d for d in open_decisions if d.severity == "blocking"] + [
                d for d in open_decisions if d.severity != "blocking"
            ]
            cursor["i"] = min(cursor["i"], max(len(pending) - 1, 0))
            verb = await self._intake_frame(task, pending, cursor)
            if verb in ("back", None):
                return
            focused = pending[cursor["i"]] if pending and cursor["i"] < len(pending) else None
            if verb == "approve" and focused is not None:
                # B16: record WHAT was accepted (the agent's assumption = the first
                # offered option), not a bare verb — the receipt must reconstruct it.
                self.core.answer_decision(
                    task_id, focused.id, answer=_accepted_assumption(focused), approved=True
                )
            elif verb == "reject" and focused is not None:
                override = await self._override_decision(focused)
                if override:
                    self.core.answer_decision(task_id, focused.id, answer=override, approved=False)
            elif verb == "approve-all":
                if not await self._confirm_approve_all(pending, task.risk):
                    continue
                for d in pending:
                    self.core.answer_decision(
                        task_id, d.id, answer=_accepted_assumption(d), approved=True
                    )
            elif verb == "run":
                if not self.core.can_run(task_id):
                    _print("Run is locked: resolve blocking decisions first.")
                    continue
                if not self._agent_cap_ok(exclude=task_id):
                    continue
                try:
                    self._spawn_run(task_id)
                    _print("Agent run started — running in the background.")
                except Exception as exc:
                    _print(f"Cannot start run: {exc}")
                return

    async def _intake_frame(self, task: Task, pending: list, cursor: dict[str, int]) -> str | None:
        """One in-place navigator frame for the decision walk; returns the chosen verb
        (approve / reject / approve-all / run / back) or None to quit. ``pending`` is the
        full focusable set (blocking + optional) so a/x reach optional rows too (F11)."""
        result: dict[str, str | None] = {"verb": None}

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            can_run = self.core.can_run(task.id)
            body = fmt_intake.render_intake(
                task, can_run=can_run, risk=task.risk, cursor=cursor["i"]
            )
            # B5: the footer rides the PINNED region (not inside the body Group) so the
            # decision controls survive even when many decisions overflow the frame —
            # render_frame clips the body, never the pinned footer.
            footer = render_footer(_intake_footer(len(pending), can_run=can_run, risk=task.risk))
            return self._frame(body, geometry, footer=footer)

        def _move(step: int):
            def _handler(event) -> None:
                if pending:
                    cursor["i"] = (cursor["i"] + step) % len(pending)

            return _handler

        def _emit(verb: str):
            def _handler(event) -> None:
                result["verb"] = verb
                event.app.exit()

            return _handler

        handlers = {
            "down": _move(1),
            "j": _move(1),
            "up": _move(-1),
            "k": _move(-1),
            "a": _emit("approve"),
            "x": _emit("reject"),
            "A": _emit("approve-all"),
            "r": _emit("run"),
            "q": _emit("back"),
            "escape": _emit("back"),
            "c-c": _emit("back"),
        }
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)
        return result["verb"]

    async def _override_decision(self, decision) -> str | None:
        """B6: reject/override lets the human PICK from the offered options (the decision
        already carries them) with free-text as the fallback — no retyping an option that
        was right there. Returns the chosen/typed answer, or None if cancelled/empty."""
        from rich.text import Text

        body = Text(decision.question, style="secondary")
        options = list(decision.options)
        if options:
            labels = [*options, "✎ type a different answer"]
            picked = await self._choose_in_frame(
                "Override — pick the correct answer", labels, body=body
            )
            if picked is None:
                return None
            if picked < len(options):
                return options[picked]
        typed = await self._prompt_in_frame("Override answer", body=body)
        return typed.strip() if typed and typed.strip() else None

    async def _confirm_approve_all(self, blocking: list, risk: str) -> bool:
        """`A` approve-all is a one-key gate bypass — gate it behind a confirm naming
        the count + risk, and REFUSE outright at high/irreversible risk (parity with
        review's no-skip). Returns True only when approve-all may proceed."""
        if not blocking:
            return False
        if risk == "high":
            _print("Approve-all is refused at high risk — approve each decision deliberately.")
            return False
        return await self._confirm_in_frame(
            f"Approve all {len(blocking)} {risk}-risk decisions as-is?",
            default=False,
        )

    async def view_review(self, task_id: str) -> None:
        """The readiness-first review walk: j/k move over the checklist, enter steps
        into a sub-view, a/s/r/q act at the top level. Findings and smoke get their
        own focused-walk sub-frames so the human chooses WHICH item to act on."""
        while True:
            task = self._resolve_reviewable(task_id)
            if task is None:
                _print("Nothing to review right now.")
                return
            task_id = task.id
            stale = await self.core.gate_is_stale(task_id)
            locked = not self.core.can_approve(task_id)
            cooldown_remaining = self.core.approve_cooldown_remaining(task_id)
            verb = await self._review_frame(
                task,
                stale=stale,
                locked=locked,
                cooldown_remaining=cooldown_remaining,
            )
            if verb in ("back", None):
                return
            if verb == "approve":
                # B19: low/med approve is deliberately a single keystroke with no extra
                # y/N confirm — DESIGN mandates no-auto-advance only at high/irreversible,
                # and the lever-5 cooldown below already forces a real read before it
                # unlocks. High risk gets its no-bypass friction via the second-approver
                # bar in approve_task, not a confirm prompt here.
                remaining = self.core.approve_cooldown_remaining(task_id)
                if not self.core.can_approve(task_id):  # TUI-GATE-06 structural re-check
                    _print(self._approve_lock_reason(task_id))
                    continue
                if remaining > 0:  # lever 5: force a real read before approve unlocks
                    _print(f"give it a read — approve unlocks in {remaining}s")
                    continue
                from kagan.core import TaskState

                # Lever 6: approve_task records the approver and only flips to READY
                # when the risk-scaled approver bar is met (high needs >=2 distinct).
                approver = self._identity()
                approved = self.core.approve_task(task_id, approver=approver)
                if approved.state is TaskState.READY:
                    return
                _print(self._waiting_for_approver_line(approved))
                continue
            if verb == "send-back":
                comment = await self._prompt_in_frame(
                    "Why send it back?", placeholder="what to fix / why it's not ready"
                )
                if comment and comment.strip():
                    await self.core.send_back(task_id, comment.strip())
                return
            if verb == "re-validate":
                fresh = self.core.get_task(task_id)
                if fresh is not None and fresh.worktree_path is not None:
                    await self.core.run_local_mirror(task_id)
                else:
                    _print("Nothing to re-validate — no live worktree.")
                continue
            if verb == "findings":
                await self._findings_walk(task_id)
            elif verb == "smoke":
                await self._smoke_walk(task_id)
            elif verb == "comprehension":
                await self._walk_comprehension(task)
            elif verb == "diff":
                await self._view_diff(task)

    async def _review_frame(
        self,
        task: Task,
        *,
        stale: bool,
        locked: bool,
        cooldown_remaining: int,
    ) -> str | None:
        """One in-place navigator frame for the readiness checklist."""
        from rich.console import Group

        cursor: dict[str, int] = {"i": 0}
        result: dict[str, str | None] = {"verb": None}

        def _focusable() -> list[str]:
            return _focusable_readiness_rows(task)

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            focusable = _focusable()
            cursor["i"] = min(cursor["i"], max(len(focusable) - 1, 0))
            body = fmt_gate.render_review(
                task,
                stale=stale,
                locked=locked,
                cursor=cursor["i"],
                high_risk_approvers=self.core.high_risk_approvers(),
                cooldown_remaining=cooldown_remaining,
            )
            footer = _review_footer(
                task,
                locked=locked,
                cooldown_remaining=cooldown_remaining,
                has_focusable=bool(focusable),
            )
            return self._frame(Group(body, render_footer(footer)), geometry)

        def _move(step: int):
            def _handler(event) -> None:
                focusable = _focusable()
                if focusable:
                    cursor["i"] = (cursor["i"] + step) % len(focusable)

            return _handler

        def _emit(verb: str):
            def _handler(event) -> None:
                result["verb"] = verb
                event.app.exit()

            return _handler

        def _open_focused(event) -> None:
            focusable = _focusable()
            if not focusable:
                return
            kind = focusable[cursor["i"]]
            if kind == "findings":
                result["verb"] = "findings"
            elif kind == "comprehension":
                result["verb"] = "comprehension"
            elif kind == "smoke":
                result["verb"] = "smoke"
            event.app.exit()

        handlers = {
            "down": _move(1),
            "j": _move(1),
            "up": _move(-1),
            "k": _move(-1),
            "enter": _open_focused,
            "a": _emit("approve"),
            "c": _emit("comprehension"),
            "D": _emit("diff"),
            "s": _emit("send-back"),
            "f": _emit("findings"),
            "v": _emit("smoke"),
            "r": _emit("re-validate"),
            "q": _emit("back"),
            "escape": _emit("back"),
            "c-c": _emit("back"),
        }
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)
        return result["verb"]

    async def _findings_walk(self, task_id: str) -> None:
        """Focused walk over the open findings: j/k move, g/d act on the focused one."""
        cursor: dict[str, int] = {"i": 0}
        while True:
            task = self.core.get_task(task_id)
            if task is None:
                return
            from kagan.core.tasks import is_unresolved_agreed_blocker

            # An agreed blocker still needing a resolution note stays in the walk so the
            # human can re-press g and supply it — never a dead-end behind the lock (F20).
            open_findings = [
                f for f in task.findings if f.verdict is None or is_unresolved_agreed_blocker(f)
            ]
            if not open_findings:
                return
            cursor["i"] = min(cursor["i"], len(open_findings) - 1)
            verb = await self._findings_frame(task, open_findings, cursor)
            if verb in ("back", None):
                return
            focused = open_findings[cursor["i"]]
            if verb in ("agree", "disagree"):
                await self._adjudicate_finding(task_id, focused.id, verb)

    async def _findings_frame(
        self, task: Task, open_findings: list, cursor: dict[str, int]
    ) -> str | None:
        """One in-place navigator frame for the open findings list."""
        from rich.console import Group
        from rich.text import Text

        result: dict[str, str | None] = {"verb": None}

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            body = fmt_gate.render_findings(task.findings, cursor=cursor["i"])
            focused = open_findings[cursor["i"]]
            footer = render_footer(_FINDINGS_FOOTER)
            echo = Text(f"{focused.location} · {focused.severity}", style="secondary")
            return self._frame(Group(body, footer, echo), geometry)

        def _move(step: int):
            def _handler(event) -> None:
                cursor["i"] = (cursor["i"] + step) % len(open_findings)

            return _handler

        def _emit(verb: str):
            def _handler(event) -> None:
                result["verb"] = verb
                event.app.exit()

            return _handler

        handlers = {
            "down": _move(1),
            "j": _move(1),
            "up": _move(-1),
            "k": _move(-1),
            "g": _emit("agree"),
            "d": _emit("disagree"),
            "q": _emit("back"),
            "escape": _emit("back"),
            "c-c": _emit("back"),
        }
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)
        return result["verb"]

    async def _smoke_walk(self, task_id: str) -> None:
        """Focused walk over unverified smoke tests: j/k move, v verifies the focused one."""
        cursor: dict[str, int] = {"i": 0}
        while True:
            task = self.core.get_task(task_id)
            if task is None:
                return
            smoke_todo = [s for s in task.smoke_tests if not s.verified]
            if not smoke_todo:
                return
            cursor["i"] = min(cursor["i"], len(smoke_todo) - 1)
            verb = await self._smoke_frame(task, smoke_todo, cursor)
            if verb in ("back", None):
                return
            if verb == "verify":
                focused = smoke_todo[cursor["i"]]
                self.core.verify_smoke_test(task_id, focused.id)

    async def _smoke_frame(
        self, task: Task, smoke_todo: list, cursor: dict[str, int]
    ) -> str | None:
        """One in-place navigator frame for the unverified smoke tests."""
        from rich.console import Group

        result: dict[str, str | None] = {"verb": None}

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            body = fmt_gate.render_smoke(task.smoke_tests, task.ports, cursor=cursor["i"])
            return self._frame(Group(body, render_footer(_SMOKE_FOOTER)), geometry)

        def _move(step: int):
            def _handler(event) -> None:
                cursor["i"] = (cursor["i"] + step) % len(smoke_todo)

            return _handler

        def _emit(verb: str):
            def _handler(event) -> None:
                result["verb"] = verb
                event.app.exit()

            return _handler

        handlers = {
            "down": _move(1),
            "j": _move(1),
            "up": _move(-1),
            "k": _move(-1),
            "v": _emit("verify"),
            "q": _emit("back"),
            "escape": _emit("back"),
            "c-c": _emit("back"),
        }
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)
        return result["verb"]

    def _identity(self) -> str:
        # Lever 6: the approver string is the user's git identity (the distinct key
        # the high-risk bar counts). With no configured identity, fall back to the OS
        # user so low/medium approve still works; high-risk distinctness then needs a
        # second CONFIGURED git identity (DESIGN §3.7 cross-team caveat).
        import getpass

        from kagan.core import git

        identity = git.user_identity(self.core.repo_root or Path.cwd())
        if identity:
            return identity
        try:
            return getpass.getuser()
        except Exception:
            return "local"

    async def _offer_retro(self, task_id: str) -> None:
        """Lever 8: after a task reaches READY, offer one AGENTS.md learning the
        human edits/confirms or skips. kagan NEVER writes AGENTS.md without the
        keypress: an empty/cancelled edit is a no-op (DESIGN panel ⑨)."""
        suggested = self.core.propose_retro(task_id)
        if not suggested:
            return
        # B21: the field is PREFILLED with the suggestion, so Enter appends the (edited)
        # text and esc skips — the header must say that, not the contradictory "enter to
        # skip" (which read as "Enter does nothing" while the footer said "enter submit").
        edited = await self._prompt_in_frame(
            "One learning for AGENTS.md — edit & enter to append, esc to skip",
            default=suggested,
        )
        if edited and edited.strip():
            self.core.confirm_retro(task_id, edited.strip())
            _print("Appended to AGENTS.md.")

    def _waiting_for_approver_line(self, task: Task) -> str:
        """Lever 6: high-risk needs a second distinct approver; name who has signed."""
        who = ", ".join(task.approvers) if task.approvers else "no one yet"
        return f"approved by {who} — high-risk needs another distinct approver."

    def _approve_lock_reason(self, task_id: str) -> str:
        """Name the actual unmet approve condition (findings / comprehension / approver)."""
        from kagan.core.tasks import is_open_blocker, is_unresolved_agreed_blocker

        task = self.core.get_task(task_id)
        if task is None:
            return "Approve is locked."
        if any(is_open_blocker(f) for f in task.findings):
            return "Approve is locked: adjudicate the open blocking finding(s) first."
        if any(is_unresolved_agreed_blocker(f) for f in task.findings):
            return "Approve is locked: note how each agreed blocking finding ships (press f, g)."
        failed_checks = [c.name for c in task.checks if not c.passed]
        if failed_checks:
            return "Approve is locked: fix failing required check(s) first: " + ", ".join(
                failed_checks
            )
        from kagan.format.gate import _unanswered_keys

        remaining = len(_unanswered_keys(task))
        if remaining:
            return f"Approve is locked: answer {remaining} comprehension prompt(s) first (press c)."
        if task.risk == "high":
            bar = self.core.high_risk_approvers()
            if len(set(task.approvers)) < bar:
                return f"Approve is locked: high-risk needs {bar} distinct approvers."
        return "Approve is locked."

    async def _view_diff(self, task: Task) -> None:
        """Scrollable in-frame diff for the task's harvested changed files."""
        import asyncio

        from prompt_toolkit.application import get_app
        from rich.console import Group
        from rich.text import Text

        from kagan.core.diff import open_diff_viewport
        from kagan.format._console import render_to_str

        viewport = await open_diff_viewport(task)
        if viewport is None:
            _print(self._ansi(_dim("No diff to show.")))
            return

        offset: dict[str, int] = {"line": 0}
        visible_rows = 1
        frame_lines: list[str] = ["Loading diff…"]
        frame_total = 1
        frame_width = 80
        frame_visible = 20
        frame_dirty = True
        frame_inflight = False

        async def _refresh() -> None:
            nonlocal frame_lines, frame_total, frame_dirty, frame_inflight
            lines, off, total = await viewport.window(
                offset["line"],
                frame_visible,
                frame_width,
            )
            offset["line"] = off
            frame_lines = lines
            frame_total = total
            frame_dirty = False
            frame_inflight = False

        async def _refresh_then_repaint() -> None:
            await _refresh()
            get_app().invalidate()

        def _schedule_refresh() -> None:
            nonlocal frame_inflight, frame_dirty
            if frame_inflight:
                return
            frame_inflight = True
            frame_dirty = True
            asyncio.create_task(_refresh_then_repaint())

        await _refresh()

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            nonlocal visible_rows, frame_width, frame_visible, frame_dirty

            footer = render_footer(_DIFF_FOOTER)
            footer_h = len(
                render_to_str(footer, width=geometry.content_width, no_color=True).splitlines()
            )
            visible = max(1, geometry.content_height - footer_h - 2)
            visible_rows = visible
            frame_width = geometry.content_width
            frame_visible = visible
            if frame_dirty:
                _schedule_refresh()

            window = "\n".join(frame_lines)
            end_line = offset["line"] + len(frame_lines)
            position = Text(
                f"{offset['line'] + 1}-{end_line} of {frame_total} lines",
                style="secondary",
            )
            content = Group(Text.from_ansi(window), position)
            return self._frame(content, geometry, footer=footer)

        def _scroll(step: int):
            def _handler(_event) -> None:
                nonlocal frame_dirty
                offset["line"] += step
                frame_dirty = True
                _schedule_refresh()

            return _handler

        def _page(step: int):
            def _handler(_event) -> None:
                nonlocal frame_dirty
                offset["line"] += step * visible_rows
                frame_dirty = True
                _schedule_refresh()

            return _handler

        def _back(event) -> None:
            event.app.exit()

        handlers = {
            "down": _scroll(1),
            "j": _scroll(1),
            "up": _scroll(-1),
            "k": _scroll(-1),
            "pagedown": _page(1),
            "pageup": _page(-1),
            "q": _back,
            "escape": _back,
            "c-c": _back,
        }
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)

    async def _walk_comprehension(self, task: Task) -> None:
        """Lever 1: walk the risk-scaled prompt set one prompt at a time, recording
        each answer as we go (partial-save — quitting mid-walk leaves answered
        prompts recorded). An empty set (low risk) is a no-op with a note.

        A trivial/templated answer is NOT silently swallowed (B9): the gate's own
        substance check rejects it, the human is told WHY, and the junk is never
        persisted — the stored value stays the last ACCEPTED answer, so a placeholder
        can never ride into the receipt."""
        from kagan.core.comprehension import prompts_for_task
        from kagan.core.tasks import _is_substantive

        prompts = prompts_for_task(task)
        if not prompts:
            _print("No comprehension prompts at low risk.")
            return
        # 1b: the changed-file context is drawn IN-FRAME above each question, so "what
        # does this change do" is answerable without leaving the box.
        context = self._comprehension_context(task)
        total = len(prompts)
        for i, (key, question) in enumerate(prompts, start=1):
            label = f"{i} of {total} — {question}"
            # Prefill with the last ACCEPTED answer (trivial attempts are never stored).
            draft = task.comprehension.get(key, "")
            while True:
                answer = await self._prompt_in_frame(label, body=context, default=draft)
                if answer is None:
                    return  # esc leaves the walk; answers so far are already recorded
                stripped = answer.strip()
                if not stripped:
                    break  # blank skips this prompt, keeping any prior accepted answer
                if not _is_substantive(stripped):
                    draft = stripped  # let them edit their attempt; do NOT persist it
                    _print(_TRIVIAL_COMPREHENSION_HINT)
                    continue
                self.core.record_comprehension(task.id, key, stripped)
                break

    def _comprehension_context(self, task: Task):
        """Changed-file context above comprehension questions; D opens the diff viewer."""
        from rich.text import Text

        if not task.changed_files:
            return None
        body = Text("This change touched:\n", style="secondary")
        for f in task.changed_files[:10]:
            body.append(f"  · {f}\n")
        if len(task.changed_files) > 10:
            body.append(f"  … and {len(task.changed_files) - 10} more\n", style="secondary")
        body.append("\nPress D in review to view the full diff.\n", style="secondary")
        return body

    async def _adjudicate_finding(self, task_id: str, finding_id: str, verdict: str) -> None:
        """Set the verdict on a SPECIFIC finding. Disagree needs a reason; agreeing a
        BLOCKING finding needs a resolution note — agreeing concedes a real defect, so
        the human records how it ships (fixed / accepted / deferred) before approve can
        clear (F20, DESIGN-LVR1-01). A question/nit agree stays one keypress."""
        from rich.text import Text

        task = self.core.get_task(task_id)
        finding = next((f for f in task.findings if f.id == finding_id), None) if task else None
        if finding is None:
            return
        body = Text(f"{finding.location or 'finding'}: {finding.message}", style="secondary")
        if verdict == "disagree":
            reply = await self._prompt_in_frame("Why do you disagree?", body=body)
            if reply and reply.strip():
                self.core.set_verdict(task_id, finding_id, verdict="disagree", reply=reply.strip())
        elif finding.severity == "blocking":
            note = await self._prompt_in_frame(
                "Agreeing ships this blocker — how is it resolved? "
                "(fixed / accepted because… / deferred to #…)",
                body=body,
            )
            if note and note.strip():
                self.core.set_verdict(
                    task_id, finding_id, verdict="agree", resolution_note=note.strip()
                )
        else:
            self.core.set_verdict(task_id, finding_id, verdict="agree")

    def _resolve_reviewable(self, task_id: str | None) -> Task | None:
        from kagan.core import TaskState

        reviewable = (TaskState.REVIEW, TaskState.DONE)
        if task_id:
            task = self.core.get_task(task_id)
            if task is not None and task.state in reviewable:
                return task
        for item in self.core.inbox_tasks():
            if item.state in reviewable:
                return self.core.get_task(item.task_id)
        return None

    async def view_ship(self, task_id: str) -> None:
        copied: str | None = None  # the last key whose copy succeeded — persisted in the frame
        while True:
            task = self.core.get_task(task_id)
            if task is None:
                return
            push_cmd = self._safe(lambda: self.core.get_push_command(task_id), "(no branch set)")
            pr_cmd = self._safe(lambda: self.core.get_pr_command(task_id), "(no branch set)")
            # Lever 6: the copyable receipt IS the PR-body decision record the human
            # pastes (the full receipt lives in-repo under .kagan/reviews/).
            receipt = self.core.render_pr_body(task_id)
            # Lever 8: the retro closes the loop on THIS screen (not a transient prompt
            # at approve-time the user blows past).
            retro = self.core.propose_retro(task_id)
            key = await self._ship_frame(
                fmt_ship.render_ship(task, push_cmd, pr_cmd, receipt, retro=retro, copied=copied)
            )
            if key in ("q", None):
                return
            if key == "c":
                copied = "c" if self._copy(push_cmd, "Push command") else None
            elif key == "p":
                copied = "p" if self._copy(pr_cmd, "PR command") else None
            elif key == "r":
                copied = "r" if self._copy(receipt, "Receipt") else None
            elif key == "l" and retro:
                copied = None
                await self._offer_retro(task_id)
            elif key == "enter":
                copied = None
                if await self._verify_and_mark_pushed(task_id):
                    return

    async def _ship_frame(self, body) -> str | None:
        """Hold the ship screen in the shared shell until an action key is pressed."""
        result: dict[str, str | None] = {"key": None}

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            return self._frame(body, geometry)

        def _emit(key: str):
            def _handler(event) -> None:
                result["key"] = key
                event.app.exit()

            return _handler

        handlers = {key: _emit(key) for key in ("c", "p", "r", "l", "enter", "q")}
        handlers["escape"] = _emit("q")
        handlers["c-c"] = _emit("q")
        await _interactive.navigate(_render, handlers, input=self._input, output=self._output)
        return result["key"]

    async def _verify_and_mark_pushed(self, task_id: str) -> bool:
        """Before flipping to PR_OPEN, cheaply VERIFY the branch is actually on origin
        (read-only `git ls-remote`). kagan NEVER pushes — it only checks the human
        did. Branch absent → refuse; verification impossible (no gh/network) → soften
        and proceed. Returns True when the view should exit (marked or absent-confirmed)."""
        if not await self._confirm_in_frame("Mark pushed & PR opened?"):
            return False
        present = await self.core.branch_on_origin(task_id)
        if present is False:
            _print("branch not found on origin — did you push? (kagan never pushes for you)")
            return False
        if present is None:
            _print("marking as pushed (could not verify — gh/network unavailable)")
        try:
            await self.core.mark_task_pushed(task_id)
        except Exception as exc:
            _print(f"Cannot mark pushed: {exc}")
            return False
        return True

    async def view_workspaces(self, *, focus: str | None = None) -> None:
        """Hold a workspaces frame until dismissed (DESIGN §1.2); `t` copies the cd
        of a live worktree, `w`/`q` go back (§1.3 — the advertised keys, now wired)."""
        from datetime import UTC, datetime

        copied_note: dict[str, str | None] = {"line": None}

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            from rich.console import Group

            self.core.reconcile_in_flight()
            tasks = self.core.list_tasks()
            target = focus if focus is not None else self._first_live_worktree()
            blocks: list = [
                fmt_workspaces.render_workspaces(
                    tasks,
                    repo_name=_repo_name(self.core),
                    now=datetime.now(UTC),
                    started_at_by_task=self._running_started_at_map(tasks),
                )
            ]
            if focus is not None:
                task = self.core.get_task(focus)
                if task is not None:
                    log_tail = self._read_log_tail(task)
                    blocks.append(
                        fmt_workspaces.render_workspace_detail(
                            task, log_tail=log_tail, cooldown_note=self._cooldown_note(task)
                        )
                    )
            blocks.append(render_footer(_workspace_footer(target is not None)))
            if copied_note["line"] is not None:
                from rich.text import Text

                blocks.append(Text(copied_note["line"], style="dim"))
            return self._frame(Group(*blocks), geometry)

        def _take_over(event) -> None:
            self.core.reconcile_in_flight()
            target = focus if focus is not None else self._first_live_worktree()
            cmd = self._takeover_cd(target)
            if cmd is None:
                copied_note["line"] = "Nothing to take over — no live worktree."
                return
            copied = _interactive.copy_to_clipboard(cmd)
            copied_note["line"] = f"{cmd}{' (copied)' if copied else ''}"

        def _back(event) -> None:
            event.app.exit()

        handlers = {"t": _take_over, "w": _back, "q": _back, "escape": _back, "c-c": _back}
        # No background refresh timer (DESIGN-PLAT-01 / UI-03: no live-updating panes).
        # _render reconciles on entry and on every keypress repaint — enough to keep a
        # finished run from reading as "working" (#21) without idle-watching.
        await _interactive.navigate(
            _render,
            handlers,
            input=self._input,
            output=self._output,
        )

    def _running_started_at_map(self, tasks: list[Task]):
        from datetime import datetime

        from kagan.core import TaskState

        started: dict[str, datetime] = {}
        for task in tasks:
            if task.state not in (TaskState.RUNNING, TaskState.VALIDATING, TaskState.PR_OPEN):
                continue
            for event in self.core.read_events(task.id):
                if event.get("type") != "transition" or event.get("to") != TaskState.RUNNING.value:
                    continue
                ts = event.get("ts")
                if ts:
                    started[task.id] = datetime.fromisoformat(ts)
        return started

    def _first_live_worktree(self) -> str | None:
        from kagan.core import TaskState

        live = (TaskState.RUNNING, TaskState.VALIDATING, TaskState.PR_OPEN)
        for task in self.core.list_tasks():
            if task.state in live and task.worktree_path is not None:
                return task.id
        return None

    def _takeover_cd(self, task_id: str | None) -> str | None:
        if task_id is None:
            return None
        task = self.core.get_task(task_id)
        if task is None or task.worktree_path is None:
            return None
        return f"cd {task.worktree_path}"

    def _cooldown_note(self, task: Task) -> str | None:
        """Lever 5: a just-landed REVIEW task carries the approve cooldown as a calm
        standing cue ("give it a read before approving — unlocks 0:20"), so pacing is
        visible on the workspaces detail, not a surprise rejection at approve-time."""
        from kagan.core import TaskState

        if task.state is not TaskState.REVIEW:
            return None
        remaining = self.core.approve_cooldown_remaining(task.id)
        if remaining <= 0:
            return None
        return (
            f"{task.title} just landed — give it a read before approving "
            f"(unlocks {remaining // 60}:{remaining % 60:02d})."
        )

    def _read_log_tail(self, task: Task, n: int = 200) -> str | None:
        if not task.ports:
            return None
        service = next(iter(task.ports))  # first port-bearing service (LogView parity)
        path = self.core.data_dir / "tasks" / task.id / "logs" / f"{service}.log"
        if not path.exists():
            return ""
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])

    async def view_stats(self) -> None:
        # Lever 7: the private outcome mirror IS the stats screen — the operational
        # tally (render_stats) is dropped from this view (it is a cockpit reading, not
        # the calm mirror DESIGN §5 specifies). Durability is best-effort git-backed,
        # resolved up front so render() stays sync; the frame holds until dismissed.
        card = self.core.outcome_scorecard()
        durability = await self.core.durability_estimate()
        card_body = fmt_stats.render_scorecard(
            card,
            _repo_name(self.core),
            durability,
            reflection=self._supervision_reflection(),
        )
        await _interactive.show_until_dismiss(
            lambda geometry: self._frame(card_body, geometry),
            input=self._input,
            output=self._output,
        )

    def _supervision_reflection(self) -> str | None:
        """The private supervision-hours reflection (DESIGN §stats). Built from the
        coach data — today the after-hours signal (a precise cumulative-hours timer
        needs the deferred private session store, lever 5 TODO); honest, not fabricated."""
        from kagan.core import after_hours_note

        if after_hours_note() is not None:
            return "You're supervising after hours — the queue keeps."
        return None

    async def view_help(self) -> None:
        # Help is reached from the inbox navigator, so the inbox keys lead; everything
        # else is demoted under a dim "Other views" so the screen is scoped, not a
        # flat dump of all groups (Phase 12c help §2).
        groups, primary = _help_groups(("Inbox", "Inbox row actions"))
        body = render_keymap(groups, primary_count=primary)
        await _interactive.show_until_dismiss(
            lambda geometry: self._frame(body, geometry),
            input=self._input,
            output=self._output,
        )

    # -- new task ---------------------------------------------------------

    async def action_new_task(self) -> None:
        from rich.text import Text

        from kagan.core.recipes import recipe_for

        clis = self.core.available_clis()
        title = await self._prompt_in_frame(
            "Title", placeholder="short imperative, e.g. add-oauth-callback"
        )
        if not title or not title.strip():
            _print("Title is required — task not created.")
            return
        title = title.strip()
        # Scope is the field first-time users find opaque — explain it in-frame so it
        # never needs the docs (DESIGN §5: intuitive at every step).
        scope_help = Text(
            "Scope = the paths the agent may edit (e.g. src/auth/** migrations/**).\n"
            "Edits outside flag as drift, and scope sets the review tier (auth, "
            "migrations,\npayments are higher). Space/comma separated. "
            "Blank = the whole repo, no restriction.",
            style="secondary",
        )
        scope_raw = await self._prompt_in_frame(
            "Scope", body=scope_help, placeholder="blank = whole repo"
        )
        if scope_raw is None:  # esc cancels the wizard (vs. a blank submit = whole repo)
            _print("Cancelled — no task created.")
            return
        scope = [s for s in scope_raw.replace(",", " ").split() if s]

        options = [*clis, "✋ I'll drive"]
        picked = await self._choose_in_frame("Agent", options, default=0)
        if picked is None:
            _print("Cancelled.")
            return
        selected = clis[picked] if picked < len(clis) else None
        recipe_cmd = recipe_for(selected).command if selected else None

        # 1.4: a real confirm gate BEFORE create_task — surface the computed
        # risk-from-scope (lever 4 thesis on this screen) IN-FRAME, then commit on yes.
        queue_note = None
        if not self.core.can_start_agent():
            queue_note = f"{self.core.running_count()} agents running — this one will queue"
        form = fmt_new_task.render_new_task_form(
            title=title,
            scope=scope,
            clis=clis,
            selected=selected,
            recipe_command=recipe_cmd,
            risk=self.core.preview_risk(scope),
            reviewer_configured=selected is not None and self.core.reviewer_configured(selected),
            reviewer_note=self.core.reviewer_model(selected) if selected is not None else None,
            queue_note=queue_note,
        )
        if not await self._confirm_in_frame("Create & plan this task?", body=form):
            _print("Cancelled — no task created.")
            return

        try:
            task = self.core.create_task(title)
            if selected is not None or scope:
                self.core.configure_task(task.id, agent_cli=selected, scope=scope or None)
        except Exception as exc:
            _print(f"Cannot create task: {exc}")
            return
        try:
            await self._run_intake_with_status(task.id, title)
        except Exception as exc:
            _print(f"Cannot plan task: {exc}")
            return
        # Lever 5: intake plans read-only (no agent in flight), so creation is never
        # blocked — but warn the cap is hit (no auto-queue; re-run from intake later).
        if not self.core.can_start_agent(exclude=task.id):
            running = self.core.running_count(exclude=task.id)
            _print(
                f"{running} agents already working (cap) — run it from intake once a slot frees."
            )
        await self.open_task(task.id)

    async def _run_intake_with_status(self, task_id: str, title: str) -> None:
        from rich.console import Group
        from rich.text import Text

        def _render(geometry: FrameGeometry) -> RenderedFrame:
            return self._frame(
                Group(
                    Text(f"{title} · planning…", style="bold"),
                    Text("asking the agent to report what it understood", style="secondary"),
                ),
                geometry,
            )

        await _interactive.wait_in_frame(
            _render,
            self.core.run_intake(task_id),
            input=self._input,
            output=self._output,
        )

    # -- helpers ----------------------------------------------------------

    def _copy(self, value: str, label: str) -> bool:
        copied = _interactive.copy_to_clipboard(value)
        _print(f"{label}{' copied' if copied else ' (copy unavailable — select the text)'}.")
        return copied

    @staticmethod
    def _safe(fn, fallback: str) -> str:
        try:
            return fn()
        except ValueError:
            return fallback

    # -- in-frame prompts (render INSIDE the rounded control plane) --------

    async def _prompt_in_frame(self, label, *, body=None, default="", placeholder=""):
        """Single-line text captured inside the frame. ``body`` is optional context
        (the diff, the finding, the question) drawn above the input line."""
        from rich.console import Group

        def _render(geometry, current: str) -> RenderedFrame:
            line = render_input_line(label, current, placeholder=placeholder, hint=_PROMPT_HINT)
            content = Group(body, line) if body is not None else line
            return self._frame(content, geometry)

        return await _interactive.prompt_in_frame(
            _render, default=default, input=self._input, output=self._output
        )

    async def _confirm_in_frame(self, question, *, body=None, default: bool = True) -> bool:
        """Yes/no captured inside the frame."""
        from rich.console import Group
        from rich.text import Text

        hint = f"y/n · enter = {'yes' if default else 'no'} · esc cancel"

        def _render(geometry) -> RenderedFrame:
            parts = [body] if body is not None else []
            parts.extend((Text(question), Text(hint, style="secondary")))
            return self._frame(Group(*parts), geometry)

        return await _interactive.confirm_in_frame(
            _render, default=default, input=self._input, output=self._output
        )

    async def _choose_in_frame(self, label, options, *, default: int = 0, body=None):
        """List selection captured inside the frame; returns the index or None."""
        from rich.console import Group
        from rich.text import Text

        def _render(geometry, index: int) -> RenderedFrame:
            parts = [body] if body is not None else []
            parts.append(Text(label))
            for i, opt in enumerate(options):
                marker = "›" if i == index else " "  # noqa: RUF001 — DESIGN cursor glyph
                parts.append(Text(f" {marker} {opt}", style="brand" if i == index else "secondary"))
            return self._frame(Group(*parts), geometry)

        return await _interactive.choose_in_frame(
            _render, len(options), default=default, input=self._input, output=self._output
        )


# Every per-view footer derives from the ONE registry (`_VIEW_KEYS`) — no parallel
# footer constants that can drift from the `?` keymap.
_FINDINGS_FOOTER = _VIEW_KEYS["Findings"]
_SMOKE_FOOTER = _VIEW_KEYS["Smoke"]
_DIFF_FOOTER = _VIEW_KEYS["Diff"]
_NEEDS_YOU_FOOTER = _VIEW_KEYS["needs-you"]


def _inbox_footer(items: list[InboxItem], cursor: int | None) -> tuple[KeyHint, ...]:
    """Only advertise actions valid for the current inbox and focused row."""
    by_key = {hint.key: hint for hint in _VIEW_KEYS["Inbox"]}
    hints: list[KeyHint] = []
    if items:
        hints.extend((by_key["↑↓ / j k"], by_key["enter"]))
        rows = fmt_inbox.selectable_rows(items)
        if cursor is not None and 0 <= cursor < len(rows):
            action_keys = {
                "drift": ("s", "a"),
                "interrupted": ("r",),
                "ci-failed": ("r",),
                "ready": ("p",),
            }.get(rows[cursor].signal, ())
            row_actions = {hint.key: hint for hint in _VIEW_KEYS["Inbox row actions"]}
            hints.extend(row_actions[key] for key in action_keys)
    hints.extend(by_key[key] for key in ("n", "w", "S", "?", "q"))
    return tuple(hints)


def _intake_footer(
    needed: int,
    *,
    can_run: bool,
    risk: str,
) -> tuple[KeyHint, ...]:
    """Only show decision actions while decisions remain and run when unlocked."""
    by_key = {hint.key: hint for hint in _VIEW_KEYS["Intake"]}
    hints: list[KeyHint] = []
    if needed:
        if needed > 1:
            hints.append(by_key["↑↓ / j k"])
        hints.extend((by_key["a"], by_key["x"]))
        if risk != "high":
            hints.append(by_key["A"])
    if can_run:
        hints.append(by_key["r"])
    hints.append(by_key["q"])
    return tuple(hints)


def _review_footer(
    task: Task,
    *,
    locked: bool,
    cooldown_remaining: int,
    has_focusable: bool,
) -> tuple[KeyHint, ...]:
    """Keep the dense review footer limited to actions that can do work now."""
    by_key = {hint.key: hint for hint in _VIEW_KEYS["Review"]}
    hints: list[KeyHint] = []
    if has_focusable:
        hints.extend((by_key["↑↓ / j k"], by_key["enter"]))
    if not locked and cooldown_remaining <= 0:
        hints.append(by_key["a"])
    from kagan.format.gate import _unanswered_keys

    if _unanswered_keys(task):
        hints.append(by_key["c"])
    hints.append(by_key["s"])
    if any(f.verdict is None for f in task.findings):
        hints.append(by_key["f"])
    if any(not smoke.verified for smoke in task.smoke_tests):
        hints.append(by_key["v"])
    hints.append(by_key["D"])
    hints.extend((by_key["r"], by_key["q"]))
    return tuple(hints)


def _workspace_footer(can_take_over: bool) -> tuple[KeyHint, ...]:
    by_key = {hint.key: hint for hint in _VIEW_KEYS["Workspaces"]}
    keys = ("t", "w", "q") if can_take_over else ("w", "q")
    return tuple(by_key[key] for key in keys)


def _help_groups(
    active: tuple[str, ...],
) -> tuple[tuple[tuple[str, tuple[KeyHint, ...]], ...], int]:
    """Order the keymap groups active-view-first; the rest follow under "Other views".

    Returns (ordered groups, count of leading active groups) — both derived from the
    one ``_VIEW_KEYS`` registry, so the keymap can never list a view the loops do not."""
    primary = [(name, _VIEW_KEYS[name]) for name in active if name in _VIEW_KEYS]
    rest = [(name, keys) for name, keys in _VIEW_KEYS.items() if name not in active]
    return (*primary, *rest), len(primary)


def build_session(*, data_dir: Path | None = None, repo_root: Path | None = None) -> Session:
    """Construct a Session with a Harness over the resolved ledger root."""
    from kagan.core import Harness, default_data_dir, git

    root = repo_root if repo_root is not None else git.repo_root(Path.cwd())
    resolved = data_dir if data_dir is not None else default_data_dir(root)
    return Session(Harness(data_dir=resolved, repo_root=root))


async def run(*, data_dir: Path | None = None, repo_root: Path | None = None) -> None:
    """Entry point for the bare `kagan` session (after the doctor preflight)."""
    session = build_session(data_dir=data_dir, repo_root=repo_root)
    await session.run()


__all__ = ["Session", "build_session", "run"]
