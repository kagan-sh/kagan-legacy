"""`kagan init` — interactive onboarding that drafts `.kagan/repo.yaml` + a rubric.

Tool-level setup (git/agent CLI/auth/gh) stays the developer's job — `init` only
checks it via the doctor preflight and points at fixes. Everything kagan-specific is
aided: an available agent CLI PROPOSES the manifest read-only, the human reads and
approves each command BEFORE anything runs, an opt-in pass verifies the approved
commands actually execute, and the result is written through `RepoConfig` validation.

The trust boundary is the human gate here, not the agent: nothing the agent proposes
runs until the user approves the literal string, and dangerous shapes force a second
confirm. `.kagan/repo.yaml` is a PROTECTED_PATH, so an agent can never silently
rewrite this contract afterwards.
"""

import asyncio
import contextlib
import shutil
import signal
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import click

from kagan.cli._bootstrap import run_async
from kagan.format._console import render_to_str

if TYPE_CHECKING:
    from kagan.core.onboard import ManifestDraft, ProposedCheck

_HARD_PREREQS = ("git", "python")  # a fail here stops init; agent/gh/manifest only warn
_DRAFT_TIMEOUT = 300.0  # 5 min — a foreground agent call must never wedge the CLI (rule 12)
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_VALID_AX_E = frozenset({"a", "x", "e"})
_MENU_INTERRUPT_WINDOW = 1.0  # seconds — two ctrl-c's within this window quit the walk


class _WalkCancelled(Exception):
    """The human bailed out of the check walk (double ctrl-c at the a/x/e menu)."""


class _Spinner:
    """Indeterminate stderr spinner — no-op when stderr is not a TTY (tests, pipes)."""

    def __init__(self, label: str) -> None:
        self._label = label
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start = 0.0

    def start(self) -> None:
        if not sys.stderr.isatty():
            return
        self._start = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        index = 0
        while not self._stop.is_set():
            elapsed = int(time.monotonic() - self._start)
            frame = _SPINNER_FRAMES[index % len(_SPINNER_FRAMES)]
            click.echo(
                f"\r  {frame} {self._label}…  {elapsed}s · ctrl-c to skip   ",
                nl=False,
                err=True,
            )
            index += 1
            self._stop.wait(1.0)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=2.0)
        click.echo("\r" + " " * 64 + "\r", nl=False, err=True)


async def _draft_with_progress(cli: str, repo_root: Path):
    """Run the agent draft with a spinner (B), a 5-min bound (D), and a ctrl-c skip (E).

    Antifragile shape: the agent draft is a bounded experiment over a robust floor (the
    skeleton). Any of timeout / ctrl-c / crash returns None so the caller falls to that
    floor — downside capped, exit preserved, no wedge (Taleb §3/§4/§5/§12)."""
    from kagan.core.agent import launch_manifest_draft

    loop = asyncio.get_running_loop()
    draft_task = asyncio.ensure_future(launch_manifest_draft(cli, repo_root))
    spinner = _Spinner(f"{cli} is reading the repo")
    spinner.start()
    skipped = {"v": False}

    def _on_sigint() -> None:  # ctrl-c cancels only the draft, not the whole session
        skipped["v"] = True
        draft_task.cancel()

    have_handler = False
    with contextlib.suppress(NotImplementedError, RuntimeError):
        loop.add_signal_handler(signal.SIGINT, _on_sigint)
        have_handler = True
    try:
        return await asyncio.wait_for(draft_task, _DRAFT_TIMEOUT)
    except asyncio.CancelledError:
        if skipped["v"]:
            click.echo("  Skipped the agent draft — writing a skeleton instead.")
            return None
        raise  # a real cancellation (not our ctrl-c) must propagate
    except TimeoutError:
        click.echo(
            f"  Agent draft timed out after {int(_DRAFT_TIMEOUT)}s — writing a skeleton instead."
        )
        return None
    except Exception as exc:  # a flaky draft must fall to the floor, not crash
        click.echo(f"  Agent draft failed ({exc}) — writing a skeleton instead.")
        return None
    finally:
        if have_handler:
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(signal.SIGINT)
        spinner.stop()
        _drain_pending_sigint()


def _drain_pending_sigint() -> None:
    """Drop a SIGINT queued while the asyncio draft skip handler was installed.

    Without this, the next blocking stdin read (a/x/e or an edit prompt) can raise
    KeyboardInterrupt even though the human already skipped the agent draft."""
    if not sys.stdin.isatty():
        return
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        time.sleep(0.05)
    finally:
        signal.signal(signal.SIGINT, previous)


def _columns() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _frame(renderable) -> str:
    return render_to_str(renderable, width=_columns(), no_color=False)


def _read_ax_e(*, last_interrupt: list[float]) -> str | None:
    """One-keystroke a/x/e menu on a TTY; line-based read when stdin is piped (tests).

    A single ctrl-c re-prompts the same check. Two ctrl-c's within
    ``_MENU_INTERRUPT_WINDOW`` raise ``_WalkCancelled`` so setup exits without
    taking down a parent ``kagan`` session via ``click.Abort``."""
    if not sys.stdin.isatty():
        while True:
            line = click.get_text_stream("stdin").readline().strip().lower()
            if line in _VALID_AX_E:
                click.echo(line)
                return line
            click.secho("Choose a, x, or e.", fg="red", err=True)
    while True:
        try:
            key = click.getchar(echo=False)
        except KeyboardInterrupt:
            now = time.monotonic()
            if now - last_interrupt[0] < _MENU_INTERRUPT_WINDOW:
                raise _WalkCancelled() from None
            last_interrupt[0] = now
            click.echo("  (ctrl-c again to quit setup)")
            return None
        except EOFError:
            raise click.Abort() from None
        if key in _VALID_AX_E:
            click.echo(key)
            return key


def _prompt_command(default: str) -> str | None:
    """Edit a proposed check command; ctrl-c returns to the a/x/e menu."""
    try:
        edited = click.prompt("Command", default=default)
    except click.Abort, KeyboardInterrupt:
        click.echo("  Edit cancelled.")
        return None
    stripped = edited.strip() if edited else ""
    return stripped or None


def _choose_cli(clis: list[str]) -> str:
    if len(clis) == 1:
        return clis[0]
    return click.prompt(
        "Which agent CLI should draft the manifest?",
        type=click.Choice(clis),
        show_choices=True,
        default=clis[0],
    )


def _walk_checks(checks: list[ProposedCheck]) -> dict[str, str]:
    """Read each proposed command one at a time; the human approves/drops/edits it.

    Returns the approved name -> command map. A dangerous shape requires a second
    confirm before it can be accepted — the human is the ACL on what may later run."""
    from dataclasses import replace

    from kagan.core.onboard import flag_dangerous
    from kagan.format.onboard import render_check_walk

    approved: dict[str, str] = {}
    total = len(checks)
    last_interrupt = [0.0]
    _drain_pending_sigint()
    for index, original in enumerate(checks):
        check = original
        while True:
            click.echo(_frame(render_check_walk(check, index, total)))
            click.echo("  a accept · x drop · e edit · ctrl-c twice to quit")
            key = _read_ax_e(last_interrupt=last_interrupt)
            if key is None:
                continue
            if key == "x":
                break
            if key == "e":
                edited = _prompt_command(check.command)
                if edited is not None:
                    check = replace(check, command=edited, provenance="edited", source="")
                continue
            # key == "a"
            danger = flag_dangerous(check.command)
            if danger:
                try:
                    ok = click.confirm(f"{danger} — approve anyway?", default=False)
                except click.Abort, KeyboardInterrupt:
                    click.echo("  Approve cancelled.")
                    continue
                if not ok:
                    continue
            approved[check.name] = check.command
            break
    return approved


async def _verify(
    approved: dict[str, str], repo_root: Path, out_columns: int
) -> tuple[bool, set[str]]:
    """Run the human-approved checks once in the repo (public run_mirror — sanitized
    env, per-check timeout). Returns (all_passed, names_that_failed)."""
    from kagan.core.config import RepoConfig
    from kagan.core.mirror import run_mirror
    from kagan.format.onboard import render_verify_results

    click.echo("  Running approved checks…")
    results = await run_mirror(repo_root, RepoConfig(checks=dict(approved)))
    click.echo(render_to_str(render_verify_results(results), width=out_columns, no_color=False))
    return all(r.passed for r in results), {r.name for r in results if not r.passed}


def _draft_to_config(draft: ManifestDraft, approved: dict[str, str], project_name: str) -> dict:
    # Only WALKED executables (checks) and DECLARATIVE fields (risk tiers, models) are
    # committed. `security` and `services.command` also execute later (gate SAST / task
    # start) but are NOT walked — so kagan does not auto-write them unreviewed; they are
    # surfaced as paste-ready suggestions instead (via negativa: remove the unreviewed
    # path rather than add more approval ceremony — see _print_unwalked_suggestions).
    cfg: dict = {"project_name": project_name, "base_branch": draft.base_branch}
    if approved:
        cfg["checks"] = approved
    if draft.risk_tiers:
        cfg["risk_tiers"] = draft.risk_tiers
    if draft.builder:
        cfg["builder"] = draft.builder
    if draft.reviewer:
        cfg["reviewer"] = draft.reviewer
    return cfg


def _print_unwalked_suggestions(draft: ManifestDraft) -> None:
    """Surface the agent-proposed executables kagan won't auto-commit (security/services).

    They run later, so committing them unreviewed would be the phantom-check hole the
    walk closes for `checks`. Rather than gate every one (approval fatigue trains
    rubber-stamping), print them: the user adds them by a deliberate hand-edit, which
    is itself the review."""
    import yaml

    extras: dict = {}
    if draft.security:
        extras["security"] = draft.security
    if draft.services:
        extras["services"] = draft.services
    if not extras:
        return
    click.echo("")
    click.echo("The agent also proposed these — they RUN later, so kagan did not auto-add them.")
    click.echo("Review and paste into .kagan/repo.yaml if you want them:")
    click.echo(yaml.safe_dump(extras, sort_keys=False).rstrip())


def _write_files(repo_root: Path, manifest_text: str) -> Path:
    """Write the manifest and (only if absent) the starter rubric. Never clobbers a
    hand-edited rubric. The gitignore for state/ is scaffolded by the Harness ctor."""
    from kagan.core.onboard import starter_rubric

    kagan_dir = repo_root / ".kagan"
    kagan_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = kagan_dir / "repo.yaml"
    manifest_path.write_text(manifest_text, encoding="utf-8")
    rubric_path = kagan_dir / "review.md"
    if not rubric_path.exists():
        rubric_path.write_text(starter_rubric(), encoding="utf-8")
    return manifest_path


def _ensure_git_repo(repo_root: Path | None) -> Path | None:
    """kagan needs a git repo (per-task worktrees + .kagan/ at the repo root). WHEN cwd
    isn't one, offer to bootstrap it (git init + .gitignore + first commit, Y default).
    If the user declines, return None so onboarding BLOCKS — kagan can't run without it."""
    if repo_root is not None:
        return repo_root
    from kagan.core.onboard import init_git_repo

    cwd = Path.cwd()
    click.echo("kagan needs a git repository here — it creates per-task worktrees and writes")
    click.echo(".kagan/ at the repo root.")
    if not click.confirm(
        "Not a git repo. Initialize one now (git init + .gitignore + first commit)?",
        default=True,
    ):
        click.echo(
            "kagan can't proceed without a git repo. Run `git init` and commit, then re-run."
        )
        return None
    if not init_git_repo(cwd):
        click.echo("git setup failed — configure a git user.name/email, then re-run `kagan init`.")
        return None
    click.echo(f"Initialized a git repository at {cwd} (recommended .gitignore + first commit).")
    return cwd


async def run_init(repo_root: Path | None) -> Path | None:
    """Drive the onboarding flow. Returns the written manifest path, or None if the
    user aborted or a hard prerequisite is missing."""
    from kagan.core import Harness, default_data_dir
    from kagan.core.doctor_checks import run_doctor_checks
    from kagan.core.onboard import (
        parse_manifest_report,
        render_manifest_yaml,
        skeleton_manifest,
    )
    from kagan.format._console import print_themed
    from kagan.format.doctor import render_preflight
    from kagan.format.onboard import render_draft_summary

    # 1. preflight — tool setup stays the developer's job; only surface it.
    checks = run_doctor_checks()
    print_themed(render_preflight(checks))
    if any(c.status == "fail" and c.name in _HARD_PREREQS for c in checks):
        click.echo("Fix the prerequisites above, then re-run `kagan init`.")
        return None

    # 2. git is structural — bootstrap it (or block) before any manifest work.
    repo_root = _ensure_git_repo(repo_root)
    if repo_root is None:
        return None

    manifest_path = repo_root / ".kagan" / "repo.yaml"
    if manifest_path.exists() and not click.confirm(
        ".kagan/repo.yaml already exists — overwrite it?",
        default=False,
    ):
        click.echo("Left your manifest untouched. Edit it by hand anytime.")
        return None

    # Constructing the Harness scaffolds .kagan/.gitignore (state/ ignored) and gives
    # the same available-CLI resolver the session uses.
    core = Harness(data_dir=default_data_dir(repo_root), repo_root=repo_root)
    try:
        clis = core.available_clis()
        draft = None
        if clis and click.confirm(
            "Let an agent read the repo and draft a manifest?",
            default=True,
        ):
            cli = _choose_cli(clis)
            reports = await _draft_with_progress(cli, repo_root)
            if reports is not None:
                draft = parse_manifest_report(reports)

        if draft is None or not draft.checks:
            # Deterministic floor: a valid, mostly-commented skeleton to fill in by hand.
            manifest_path = _write_files(repo_root, skeleton_manifest())
            click.echo(f"Wrote a starter {manifest_path} — fill in your build/lint/test commands.")
            click.echo("Run `kagan doctor` to confirm. Edit the file by hand anytime.")
            return manifest_path

        print_themed(render_draft_summary(draft))
        try:
            approved = _walk_checks(draft.checks)
        except _WalkCancelled:
            click.echo("Setup interrupted — no manifest written. Re-run `kagan init` to continue.")
            return None

        if approved and click.confirm(
            f"Run the {len(approved)} approved check(s) once to confirm?",
            default=True,
        ):
            _ok, failed = await _verify(approved, repo_root, _columns())
            if failed and not click.confirm(
                f"{len(failed)} check(s) failed — keep them in the manifest anyway?",
                default=False,
            ):
                approved = {n: c for n, c in approved.items() if n not in failed}

        cfg = _draft_to_config(draft, approved, project_name=repo_root.name)
        manifest_path = _write_files(repo_root, render_manifest_yaml(cfg))
    finally:
        core.close()

    click.echo(f"Wrote {manifest_path} and a starter rubric.")
    click.echo("Run `kagan doctor` to confirm. Edit either file by hand — kagan flags AGENT edits.")
    _print_unwalked_suggestions(draft)
    return manifest_path


@click.command(name="init", help="Set up .kagan/repo.yaml and a review rubric for this repo.")
def init() -> None:
    from kagan.core import git

    # repo_root may be None (not a git repo) — run_init offers to bootstrap one.
    run_async(run_init(git.repo_root(Path.cwd())))


__all__ = ["init", "run_init"]
