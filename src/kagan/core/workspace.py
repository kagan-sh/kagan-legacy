"""Per-task worktree + manifest services as plain functions (TUI-WS-01/02/04/06/07/08).

No Service/Manager class — these are module functions taking the ledger and
repo_root, the same shape as the kagan.core.git porcelain they delegate to (P5).
Worktree create/remove reuse kagan.core.git (already built); config comes from
kagan.core.config; env isolation reuses runtime_env (P6); subprocess launch and
teardown follow P4. Running services are in-memory only — never persisted.
"""

import asyncio
import os
import signal
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from kagan.core import git
from kagan.core.config import load_repo_config
from kagan.core.errors import ConfigurationError, NotFoundError
from kagan.runtime_env import build_sanitized_subprocess_environment

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.core.ledger import Ledger
    from kagan.core.models import Task


@dataclass
class RunningService:
    name: str
    command: str
    pid: int
    port: int | None
    log_path: Path
    process: asyncio.subprocess.Process


def free_port() -> int:
    # P10: kernel picks; TOCTOU window until the service binds it — acceptable
    # for a single-operator dev harness.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _logs_dir(ledger: Ledger, task_id: str) -> Path:
    # MUST match what 2-tui-workspaces.md tails: <data_dir>/tasks/<id>/logs/<name>.log
    return ledger.root / task_id / "logs"


def _pinned(repo_root: Path) -> set[str]:
    # TUI-WS-05: branch / service names the user declared off-limits to agents.
    return set(load_repo_config(repo_root).pinned)


async def destroy_workspace(
    ledger: Ledger,
    repo_root: Path,
    task_id: str,
    *,
    running: dict[str, list[RunningService]] | None = None,
    force: bool = False,
) -> Task:
    task = ledger.load_task(task_id)
    if task is None:
        raise NotFoundError("task", task_id)
    # TUI-WS-05: a pinned branch must survive teardown; refuse to remove it.
    if task.branch is not None and task.branch in _pinned(repo_root):
        raise ConfigurationError(
            "workspace", f"branch {task.branch} is pinned (off-limits to agents)"
        )
    if running is not None:
        await stop_services(repo_root, task_id, running)
    if task.worktree_path is not None and task.worktree_path.exists():
        # P5: do not auto-nuke uncommitted work; the TUI confirm sets force=True.
        if not force and await git.has_pending_changes(task.worktree_path):
            raise ConfigurationError(
                "workspace",
                f"task {task_id} worktree has uncommitted changes; pass force=True",
            )
        # Runs from repo_root, force-removes the dir, and prunes (git.py already
        # does worktree remove --force + worktree prune). Branch kept (Q2).
        await git.worktree_remove(repo_root, task.worktree_path)
    task.worktree_path = None
    task.ports.clear()  # TUI-WS-06: free port leases on task end
    ledger.save_task(task)
    logger.info("Destroyed workspace {}", task_id)
    return task


async def start_services(
    ledger: Ledger,
    repo_root: Path,
    task_id: str,
    running: dict[str, list[RunningService]],
) -> list[RunningService]:
    task = ledger.load_task(task_id)
    if task is None:
        raise NotFoundError("task", task_id)
    if task.worktree_path is None:
        raise ConfigurationError("workspace", f"task {task_id} has no worktree")

    config = load_repo_config(repo_root)
    logs = _logs_dir(ledger, task_id)
    logs.mkdir(parents=True, exist_ok=True)
    started: list[RunningService] = []

    for name, svc in config.services.items():
        # P6: each service gets its own sanitized copy; shared env never mutated.
        extra = {
            "KAGAN_TASK_ID": task.id,
            "KAGAN_WORKTREE": str(task.worktree_path),
            "GIT_TERMINAL_PROMPT": "0",
            **svc.env,
        }
        port: int | None = None
        if svc.port_env is not None:
            port = free_port()
            task.ports[name] = port
            ledger.save_task(task)
            extra[svc.port_env] = str(port)
        env = build_sanitized_subprocess_environment(allow_extra=extra)

        log_path = logs / f"{name}.log"
        # P4: redirect to a file (never PIPE unparsed output — buffer deadlock).
        proc = await asyncio.create_subprocess_shell(
            svc.command,
            cwd=task.worktree_path,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=open(log_path, "wb"),  # noqa: SIM115 — fd owned by the subprocess, outlives this call
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,  # P4: own process group, killpg reaps the tree
        )
        started.append(RunningService(name, svc.command, proc.pid, port, log_path, proc))
        logger.info("Started service {} (pid {}) for task {}", name, proc.pid, task_id)

    running[task_id] = started
    return started


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    # P4: signal the whole group, TERM -> 5s -> KILL, always await wait().
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
        pass  # child exited between the check and the signal


async def stop_services(
    repo_root: Path,
    task_id: str,
    running: dict[str, list[RunningService]],
) -> list[RunningService]:
    # TUI-WS-05: never kill a pinned process; leave it running across teardowns.
    pinned = _pinned(repo_root)
    kept: list[RunningService] = []
    for svc in running.get(task_id, []):
        if svc.name in pinned:
            kept.append(svc)
            continue
        await _terminate(svc.process)
    running[task_id] = kept
    return kept
