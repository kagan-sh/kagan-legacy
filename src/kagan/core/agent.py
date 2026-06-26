import asyncio
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from kagan.core.errors import ConfigurationError
from kagan.core.recipes import recipe_for, resolve_model
from kagan.core.reports import read_ask
from kagan.runtime_env import build_sanitized_subprocess_environment

if TYPE_CHECKING:
    from kagan.core.models import Task


def _populate_sandbox(repo_root: Path, sandbox: Path) -> None:
    """Copy the repo into the sandbox: tracked files only (excludes ignored junk like
    references/ and never follows a dangling symlink). Falls back to a symlink-safe
    copytree outside a git repo. A copy error surfaces as ConfigurationError, never a
    crash to the shell."""
    try:
        ls = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            env=build_sanitized_subprocess_environment(),
        )
        if ls.returncode == 0:
            for rel in ls.stdout.decode(errors="replace").split("\0"):
                if not rel:
                    continue
                src = repo_root / rel
                if not src.is_file():  # skip a tracked-but-deleted or dangling path
                    continue
                dst = sandbox / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return
        # not a git repo: copy everything but never choke on a dangling symlink.
        for src in repo_root.iterdir():
            if src.name == ".git":
                continue
            dst = sandbox / src.name
            if src.is_dir():
                shutil.copytree(src, dst, symlinks=True, ignore_dangling_symlinks=True)
            else:
                shutil.copy2(src, dst)
    except (OSError, shutil.Error) as exc:
        raise ConfigurationError(
            context="intake sandbox", detail=f"could not copy {repo_root}: {exc}"
        ) from exc


def _intake_prompt(task: Task) -> str:
    return (
        f"Task: {task.title}\n{task.description}\n"
        "Mode: intake. You have NO write capability. Do not implement.\n"
        "Report your understanding and every decision you would assume, with options "
        "and a severity (blocking/question), via report_intake_decisions (or .kagan/ask).\n"
    )


def _validate_prompt(task: Task) -> str:
    from kagan.core.comprehension import prompts_for_risk, required_keys

    prompt = (
        f"Task: {task.title}\n{task.description}\n"
        "Mode: review. You are an adversarial validator, NOT the builder. You have "
        "NO write capability — do not implement or fix anything.\n"
        "Read the diff in this worktree and report blocking or question findings via "
        "report_findings (or .kagan/ask).\n"
        "Every finding MUST state a concrete failure path — the exact input or call "
        "sequence that breaks it. No speculative findings; if you cannot state how it "
        "breaks, do not report it. Set confidence 0-10 and status "
        "VERIFIED/UNVERIFIED/TENTATIVE per finding.\n"
    )
    n = len(prompts_for_risk(task.risk))
    if n > 0:
        keys = ", ".join(required_keys(task.risk))
        prompt += (
            f"Also generate exactly {n} own-words comprehension questions a human "
            "must answer to prove they understand THIS diff — target the riskiest "
            f"hunks. Use these keys in order: {keys}. Report them via "
            "report_comprehension_prompts. Each question must reference something "
            "concrete in the diff, not a generic template.\n"
        )
    return prompt


def _model_vocab_directive(cli: str) -> str:
    """Tell the drafting agent the model vocabulary THIS cli can actually run, so it never
    proposes a builder/reviewer the cli can't spawn (e.g. a Claude tier on codex).

    claude/opencode resolve the canonical tier aliases; codex/kimi are vendor-locked and a
    tier alias would fail there, so they must use a cli-native id or null."""
    from kagan.core.recipes import CANONICAL_TIERS

    aliases = "/".join(CANONICAL_TIERS)
    if cli in ("claude", "opencode"):
        return (
            f"This repo runs the {cli} CLI. For builder and reviewer use a canonical tier "
            f"alias ({aliases}) — NOT a native model id like claude-opus-4-8 — or null. "
            f"NEVER propose another vendor's model.\n"
        )
    return (
        f"This repo runs the {cli} CLI, which is vendor-locked: a canonical tier alias "
        f"({aliases}) does NOT map to it and would fail. For builder and reviewer use a "
        f"{cli}-native model id, or null if you cannot name one. NEVER propose a Claude "
        f"tier alias or any other vendor's model.\n"
    )


def _init_prompt(cli: str) -> str:
    return (
        "Mode: init. Do NOT modify the repository — only read it and report.\n"
        "Investigate this repository thoroughly and propose a kagan review manifest for it.\n"
        "PREFER EXECUTABLE sources of truth over prose — lift build/lint/test/typecheck "
        "from, in rough priority: CI workflows (.github/workflows, .gitlab-ci.yml), "
        "pre-commit config (.pre-commit-config.yaml), task runners (Makefile/justfile/"
        "Taskfile, package.json scripts, pyproject [tool.poe]/[tool.hatch] or tox/nox), and "
        "language manifests + their LOCKFILES (package.json/pnpm-lock, pyproject/uv.lock, "
        "Cargo.toml/Cargo.lock, go.mod) to pin the toolchain. Also read the README and any "
        "existing agent-instruction files (AGENTS.md, CLAUDE.md, .cursorrules) for declared "
        "commands and conventions. Only invent a command when NONE is declared anywhere.\n"
        "Report ONE JSON envelope of type 'manifest' whose payload has:\n"
        "  base_branch (str), checks (list of {name, command, provenance, source}),\n"
        "  risk_tiers ({low|medium|high: [globs]}), services ({name: {command, port_env}}),\n"
        "  security (SAST command or null), builder (model or null), reviewer (model or null).\n"
        + _model_vocab_directive(cli)
        + "The reviewer is spawned with that same CLI. Prefer a model DIFFERENT from builder "
        "(a different size of the same vendor is fine) so the adversarial validator is a "
        "fresh second opinion; leave null only if no second model is available.\n"
        "provenance is one of ci|precommit|scripts|makefile|pyproject|lockfile|instructions|"
        "invented; source names the file it was lifted from (empty when invented).\n"
    )


_MAX_RERUN_FINDINGS = 10


def _sendback_section(task: Task) -> list[str]:
    """On a re-run after send-back, tell the agent WHY it came back: the reviewer's
    note (the directive), the findings the human upheld (fix these), and the ones the
    human overruled (leave them as-is, with the reviewer's reason). Without this the
    re-run agent is blind to the review verdict and just rebuilds the same thing."""
    notes = [f.message for f in task.findings if f.source == "sendback" and f.message]
    upheld = [f for f in task.findings if f.verdict == "agree" and f.source != "sendback"]
    overruled = [f for f in task.findings if f.verdict == "disagree" and f.source != "sendback"]
    if not (notes or upheld or overruled):
        return []
    out = ["", "The reviewer sent this back — address it:"]
    out += [f"  - {n}" for n in notes[-3:]]  # the most recent send-back note(s)
    if upheld:
        out.append("Fix these (the reviewer upheld them):")
        for f in upheld[:_MAX_RERUN_FINDINGS]:
            out.append(f"  - {f.location + ': ' if f.location else ''}{f.message}")
    if overruled:
        out.append("Leave these as-is (the reviewer overruled them):")
        for f in overruled[:_MAX_RERUN_FINDINGS]:
            reason = f" (reason: {f.reply})" if f.reply else ""
            out.append(f"  - {f.location + ': ' if f.location else ''}{f.message}{reason}")
    return out


def _run_prompt(task: Task) -> str:
    lines = [f"Task: {task.title}", task.description, "Mode: run."]
    for d in task.decisions:
        lines.append(f"Decision: {d.question} -> {d.answer or 'blessed'}")
    if task.scope:
        lines.append(f"Scope (do not edit outside): {', '.join(task.scope)}")
    lines += _sendback_section(task)
    lines.append(
        "Report needs-you, smoke-tests, drift, and done via the report channel or .kagan/ask."
    )
    return "\n".join(lines) + "\n"


def _build_cmd(cli: str, prompt_path: Path, *, cwd: Path, model: str | None = None) -> list[str]:
    r = recipe_for(cli)
    cmd = list(r.command)
    # R-003: a repo.yaml builder/reviewer value is per-CLI — a canonical tier alias
    # (opus/sonnet/haiku) maps to THIS cli's native --model string; a native id passes
    # through; an alias with no mapping for this cli raises ConfigurationError (loud
    # fail, surfaced to the user — never a silent wrong-vendor run). This is the seam
    # where the CLI and the model meet, so resolution happens here.
    resolved = resolve_model(cli, model)
    if resolved and r.model_flag:
        cmd += [r.model_flag, resolved]
    if r.workdir_flag:
        # A CLI that ignores cwd (opencode walks up to a project root) must be pinned to
        # the worktree/sandbox, or it operates on the WRONG tree.
        cmd += [r.workdir_flag, str(cwd)]
    if r.prompt_flag:
        cmd += [r.prompt_flag, str(prompt_path)]
    else:
        cmd.append(str(prompt_path))
    return cmd


# Defense-in-depth (fix 1): blank the agent's git credential helper via GIT_CONFIG_*
# so its git invokes NO on-disk helper (keychain/store) — combined with the scrubbed
# env (no token/ssh-agent) and GIT_TERMINAL_PROMPT=0, an HTTPS push has no cred source.
# Layered FIRST so a recipe's own GIT_CONFIG_* (none today) still wins.
_NO_CREDENTIAL_HELPER: dict[str, str] = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "credential.helper",
    "GIT_CONFIG_VALUE_0": "",
}


def _agent_env(cli: str, extra: dict[str, str]) -> dict[str, str]:
    # P6: build_sanitized_subprocess_environment gives a clean child env (PATH/HOME,
    # secrets stripped) and already sets GIT_TERMINAL_PROMPT=0 by default — do NOT
    # inject it here. Recipe env + per-call extras layer on last.
    env = build_sanitized_subprocess_environment(
        allow_extra={**_NO_CREDENTIAL_HELPER, **recipe_for(cli).env, **extra}
    )
    # Fix 1: the agent works a local worktree — it never needs ssh to a remote. Drop the
    # forwarded ssh-agent socket so an ssh push can't authenticate (kagan's own read-only
    # ls-remote keeps SSH_AUTH_SOCK via its separate env). Residual: passphraseless on-disk
    # keys git reads from ~/.ssh directly — only OS sandboxing closes that.
    env.pop("SSH_AUTH_SOCK", None)
    return env


def _write_prompt(dir_: Path, name: str, text: str) -> Path:
    kagan = dir_ / ".kagan"
    kagan.mkdir(parents=True, exist_ok=True)
    path = kagan / name
    path.write_text(text)
    return path


async def _spawn(cmd: list[str], *, cwd: Path, env: dict[str, str], log: Path):
    # P4 launch half: DEVNULL stdin, redirect stdout+stderr to a FILE (never PIPE an
    # unparsed stream — buffer fills, child deadlocks), own process group for killpg.
    log.parent.mkdir(parents=True, exist_ok=True)
    return await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=open(log, "wb"),
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )


# F1: default wall-clock cap when a caller passes none (e.g. onboarding's manifest
# draft). The Harness threads the configurable repo.yaml value for builder/intake/
# validator runs; this is the floor for the rest.
_DEFAULT_AGENT_TIMEOUT = 1800.0


async def wait_bounded(proc: asyncio.subprocess.Process, timeout: float) -> bool:
    """Await ``proc`` with an F1 wall-clock cap. Return True if it exited on its own,
    False if it hit the cap and was killed. ``timeout <= 0`` disables the cap (wait
    unbounded). On timeout the process group is killed via ``terminate`` so its pid
    dies — ``reconcile_in_flight`` can then reap a stranded task cleanly."""
    if timeout <= 0:
        await proc.wait()
        return True
    try:
        await asyncio.wait_for(proc.wait(), timeout)
        return True
    except TimeoutError:
        await terminate(proc)
        return False


async def terminate(proc: asyncio.subprocess.Process) -> None:
    # P4 teardown half: killpg TERM -> 5s grace -> KILL, swallow ProcessLookupError,
    # ALWAYS await wait() (else the killed child becomes a zombie).
    if proc.returncode is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), 5.0)
        except TimeoutError:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            await proc.wait()
    except ProcessLookupError:
        await proc.wait()


async def _run_readonly_sandbox(
    task: Task,
    source: Path,
    *,
    phase: str,
    prompt_name: str,
    prompt_text: str,
    env_flag: str,
    model: str | None = None,
    timeout: float = _DEFAULT_AGENT_TIMEOUT,
) -> tuple[list, bool]:
    """Run the agent over a chmod-read-only copy of ``source`` and return its reports.

    Returns ``(reports, ok)`` where ``ok`` is the agent exit code == 0, so the caller
    can tell a crashed/empty pass apart from one that genuinely reported nothing.

    Write capability is withheld by ONE lock: a 0o444 throwaway copy of ``source``
    (MCP-INTAKE-03, P8). ``.kagan`` is re-opened writable so the agent can still report
    via the ``.kagan/ask`` JSONL fallback — its only channel here (no MCP in the
    sandbox). The CLI's OWN read-only/plan sandbox is deliberately NOT enabled: it would
    block that report write too (verified, R-002), and the chmod is the real OS-level
    lock. Used for both intake (over the repo) and the lever-2 validator (over the
    builder's worktree, so the validator reads the diff but cannot touch it)."""
    sandbox = Path(tempfile.mkdtemp(prefix=f"kagan-{phase}-{task.id}-"))
    proc: asyncio.subprocess.Process | None = None
    try:
        _populate_sandbox(source, sandbox)
        for root, dirs, files in os.walk(sandbox):
            for d in dirs:
                os.chmod(Path(root) / d, 0o555)
            for f in files:
                os.chmod(Path(root) / f, 0o444)
        # .kagan stays writable so the agent can report; everything else is read-only.
        # A real repo ships a .kagan/ that the read-only pass just locked, so re-open
        # it (the source repo always has one — the copy did too).
        kagan_dir = sandbox / ".kagan"
        if kagan_dir.exists():
            os.chmod(kagan_dir, 0o755)
            for root, dirs, files in os.walk(kagan_dir):
                for n in (*dirs, *files):
                    os.chmod(Path(root) / n, 0o755)
        ask_path = sandbox / ".kagan" / "ask"
        # Tell the agent the exact fallback file. With no MCP config in this sandbox
        # the report tools do not exist, so the .kagan/ask JSONL fallback is the only
        # working channel here (DESIGN §3.6 "the agent's only structured channel").
        prompt_with_path = (
            f"{prompt_text}If the report tool is unavailable, append one JSON envelope "
            f'per line ({{"type": ..., "payload": ...}}) to: {ask_path}\n'
        )
        prompt = _write_prompt(sandbox, prompt_name, prompt_with_path)
        ask_path.touch()
        cmd = _build_cmd(task.agent_cli or "claude", prompt, cwd=sandbox, model=model)
        env = _agent_env(
            task.agent_cli or "claude",
            {env_flag: "1", "KAGAN_TASK_ID": task.id, "KAGAN_ASK_PATH": str(ask_path)},
        )
        proc = await _spawn(cmd, cwd=sandbox, env=env, log=sandbox / ".kagan" / f"{phase}.log")
        exited = await wait_bounded(proc, timeout)  # P4 + F1: bounded wait, output in the log
        if not exited:
            logger.warning(
                "{} exceeded {}s and was stopped (see {})",
                phase,
                timeout,
                sandbox / ".kagan" / f"{phase}.log",
            )
            return read_ask(sandbox), False  # ok=False — a timed-out pass is not clean
        if proc.returncode != 0:
            logger.warning(
                "{} rc={} (see {})", phase, proc.returncode, sandbox / ".kagan" / f"{phase}.log"
            )
        return read_ask(sandbox), proc.returncode == 0
    finally:
        # reap the agent (no orphan if the pass ends, errors, or is cancelled).
        if proc is not None:
            await terminate(proc)
        # chmod back so rmtree can delete the read-only tree.
        for root, dirs, files in os.walk(sandbox):
            for n in dirs + files:
                os.chmod(Path(root) / n, 0o755)
        shutil.rmtree(sandbox, ignore_errors=True)


async def launch_intake(
    task: Task, repo_root: Path, *, timeout: float = _DEFAULT_AGENT_TIMEOUT
) -> tuple[list, bool]:
    """Read-only intake. Write capability is withheld by a chmod-read-only copy of the
    repo (MCP-INTAKE-03, P8); the agent reports via ``.kagan/ask`` (kept writable). The
    CLI's own plan/read-only sandbox is NOT used (it would sever that report — R-002).
    Returns ``(reports, ok)`` so the caller can surface a crashed/empty/timed-out intake
    distinctly (``ok=False`` on a non-zero exit or the F1 timeout)."""
    return await _run_readonly_sandbox(
        task,
        repo_root,
        phase="intake",
        prompt_name="intake-prompt.txt",
        prompt_text=_intake_prompt(task),
        env_flag="KAGAN_INTAKE",
        timeout=timeout,
    )


async def launch_validate(
    task: Task, *, model: str, timeout: float = _DEFAULT_AGENT_TIMEOUT
) -> tuple[list, bool]:
    """Lever 2: one adversarial validator, read-only over the builder's worktree,
    on a DIFFERENT model from the builder. Reads the diff, reports blocking/question
    findings via report_findings (or .kagan/ask); it never writes the worktree.

    Returns ``(reports, ok)`` where ``ok`` is the clean-exit flag — False on a
    non-zero exit OR the F1 timeout. The caller must mark the validator stage failed
    when ``ok`` is False, else a timed-out validator would falsely read as one that
    ran (F2 honest provenance)."""
    worktree = task.worktree_path
    assert worktree is not None, "task must have a worktree before validation"
    return await _run_readonly_sandbox(
        task,
        Path(worktree),
        phase="validate",
        prompt_name="validate-prompt.txt",
        prompt_text=_validate_prompt(task),
        env_flag="KAGAN_VALIDATE",
        model=model,
        timeout=timeout,
    )


async def launch_manifest_draft(cli: str, repo_root: Path) -> list:
    """Phase 14 onboarding: run the agent read-only over the repo to PROPOSE a
    `.kagan/repo.yaml`. Same read-only sandbox the intake uses (P8, MCP-INTAKE-03):
    the agent reads the repo and reports a `manifest` envelope via .kagan/ask; it can
    write nothing. Returns the reports for `onboard.parse_manifest_report` to harvest.
    An ephemeral Task carries only the chosen CLI — no task exists yet at init time."""
    from kagan.core.models import Task

    task = Task(id="init", title="manifest draft", agent_cli=cli)
    reports, _ok = await _run_readonly_sandbox(
        task,
        repo_root,
        phase="init",
        prompt_name="init-prompt.txt",
        prompt_text=_init_prompt(cli),
        env_flag="KAGAN_INIT",
    )
    return reports


async def launch_run(task: Task, *, model: str | None = None) -> asyncio.subprocess.Process:
    """Spawn the builder agent in its writable worktree on the configured builder
    model (repo.yaml ``builder:``; None = the CLI's own default). Caller watches
    process + diff + ask."""
    worktree = task.worktree_path
    assert worktree is not None, "task must have a worktree before run"
    worktree = Path(worktree)
    prompt = _write_prompt(worktree, "prompt.txt", _run_prompt(task))
    (worktree / ".kagan" / "ask").touch()
    cmd = _build_cmd(task.agent_cli or "claude", prompt, cwd=worktree, model=model)
    env = _agent_env(
        task.agent_cli or "claude",
        {
            "KAGAN_RUN": "1",
            "KAGAN_TASK_ID": task.id,
            "KAGAN_ASK_PATH": str(worktree / ".kagan" / "ask"),
        },
    )
    logger.info("launching agent {} for task {}", task.agent_cli, task.id)
    return await _spawn(cmd, cwd=worktree, env=env, log=worktree / ".kagan" / "agent.log")


__all__ = [
    "launch_intake",
    "launch_manifest_draft",
    "launch_run",
    "launch_validate",
    "terminate",
]
