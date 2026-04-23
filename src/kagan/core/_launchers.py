"""ATTACHED environment launchers for kagan.core.

LAUNCHERS maps launcher name → async launch function.
Three strategies: tmux (detached session), ide (vscode/cursor/windsurf/kiro/antigravity),
neovim (nvim at worktree path).

Each launcher writes .mcp.json into the worktree so the environment can
discover kagan's MCP server scoped to the session.
"""

import asyncio
import errno
import json
import shlex
import subprocess
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from loguru import logger

from kagan.core._agent import build_mcp_manifest, get_backend_spec
from kagan.core._subprocess import resolve_spawn_command
from kagan.core.errors import AgentError
from kagan.runtime_env import build_sanitized_subprocess_environment

_IDE_BINARIES: dict[str, str] = {
    "vscode": "code",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "kiro": "kiro",
    "antigravity": "agy",
}


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------


def build_ide_command(*, ide: str, worktree_path: str, prompt_file: str | None = None) -> list[str]:
    binary = _IDE_BINARIES.get(ide)
    if binary is None:
        known = ", ".join(sorted(_IDE_BINARIES))
        raise AgentError(f"unknown ide {ide!r}. Known: {known}")
    cmd = [binary, "--new-window", worktree_path]
    if prompt_file:
        cmd.append(prompt_file)
    return cmd


def build_neovim_command(*, worktree_path: str) -> list[str]:
    return ["nvim", worktree_path]


def _build_launch_command(agent_backend: str, startup_prompt: str) -> str | None:
    """Build agent CLI command with startup prompt as argument.

    Uses the typed backend spec to resolve executable and prompt_flag.
    Returns the full command string, or None if the backend has no prompt_flag.
    """
    backend = get_backend_spec(agent_backend)
    executable = backend.executable
    if not executable:
        return None

    prompt_flag = backend.prompt_flag
    escaped = shlex.quote(startup_prompt)

    if prompt_flag:
        return f"{executable} {prompt_flag} {escaped}"
    return executable


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------


async def _write_mcp_json(worktree_path: Path, session_id: str, db_path: str) -> None:
    content = build_mcp_manifest(session_id=session_id, db_path=db_path, role="WORKER")
    mcp_path = worktree_path / ".mcp.json"
    try:
        await asyncio.to_thread(mcp_path.write_text, content, "utf-8")
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise AgentError(
                f"Cannot write MCP manifest to {mcp_path}: Disk is full. "
                f"Free up disk space and try again."
            ) from exc
        raise AgentError(f"Failed to write MCP manifest to {mcp_path}: {exc}") from exc


async def _write_startup_prompt(worktree_path: Path, startup_prompt: str) -> Path:
    bundle_dir = worktree_path / ".kagan"
    await asyncio.to_thread(bundle_dir.mkdir, parents=True, exist_ok=True)
    prompt_path = bundle_dir / "start_prompt.md"
    await asyncio.to_thread(prompt_path.write_text, startup_prompt, "utf-8")
    return prompt_path


async def _write_attach_context(worktree_path: Path, task_id: str, session_id: str) -> None:
    """Write attach context so IDE extensions can auto-open the task."""
    bundle_dir = worktree_path / ".kagan"
    await asyncio.to_thread(bundle_dir.mkdir, parents=True, exist_ok=True)
    context_path = bundle_dir / "attach_context.json"
    content = json.dumps({"task_id": task_id, "session_id": session_id}, indent=2)
    await asyncio.to_thread(context_path.write_text, content, "utf-8")


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


async def _run_detached(
    *cmd: str,
    use_devnull: bool = True,
    use_start_new_session: bool = True,
) -> None:
    kwargs: dict[str, Any] = {}
    if use_devnull:
        kwargs["stdin"] = asyncio.subprocess.DEVNULL
        kwargs["stdout"] = asyncio.subprocess.DEVNULL
        kwargs["stderr"] = asyncio.subprocess.DEVNULL
    if use_start_new_session and sys.platform != "win32":
        kwargs["start_new_session"] = True
    elif use_start_new_session and sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    kwargs["env"] = build_sanitized_subprocess_environment()

    resolved = resolve_spawn_command(cmd[0], *cmd[1:]) if cmd else list(cmd)
    proc = await asyncio.create_subprocess_exec(*resolved, **kwargs)
    await proc.wait()


async def _tmux_send_keys(session_name: str, text: str) -> None:
    """Send keys to a tmux session."""
    env = build_sanitized_subprocess_environment()
    resolved = resolve_spawn_command("tmux", "send-keys", "-t", session_name, text, "Enter")
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


# ---------------------------------------------------------------------------
# Launchers
# ---------------------------------------------------------------------------


async def launch_tmux(
    *,
    worktree_path: Path,
    session_id: str,
    agent_cmd: str,
    agent_backend: str | None = None,
    db_path: str = "",
    startup_prompt: str | None = None,
    task_id: str | None = None,
) -> None:
    if sys.platform == "win32":
        raise AgentError(
            "tmux is not available on Windows. "
            "Use 'vscode', 'cursor', 'windsurf', or another IDE launcher instead."
        )
    logger.info("Launching tmux session")
    if db_path:
        await _write_mcp_json(worktree_path, session_id, db_path)
    if startup_prompt and startup_prompt.strip():
        await _write_startup_prompt(worktree_path, startup_prompt)
    if task_id:
        await _write_attach_context(worktree_path, task_id, session_id)

    session_name = f"kagan-{session_id.replace(':', '-')}"

    # Create empty tmux session in the worktree (v0.5.0 approach)
    await _run_detached(
        "tmux",
        "new-session",
        "-d",
        "-s",
        session_name,
        "-c",
        str(worktree_path),
    )

    # Build agent launch command with prompt as CLI arg
    launch_cmd: str | None = None
    if startup_prompt and agent_backend:
        launch_cmd = _build_launch_command(agent_backend, startup_prompt)
    if launch_cmd is None:
        launch_cmd = agent_cmd

    await _tmux_send_keys(session_name, launch_cmd)
    logger.debug("Launch complete")


async def launch_ide(
    *,
    worktree_path: Path,
    session_id: str,
    ide: str = "vscode",
    db_path: str = "",
    startup_prompt: str | None = None,
    **_kwargs: Any,
) -> None:
    logger.info("Launching IDE session ide={}", ide)
    if db_path:
        await _write_mcp_json(worktree_path, session_id, db_path)

    prompt_path: Path | None = None
    if startup_prompt and startup_prompt.strip():
        prompt_path = await _write_startup_prompt(worktree_path, startup_prompt)

    task_id = _kwargs.get("task_id")
    if task_id:
        await _write_attach_context(worktree_path, task_id, session_id)

    cmd = build_ide_command(
        ide=ide,
        worktree_path=str(worktree_path),
        prompt_file=str(prompt_path) if prompt_path else None,
    )
    await _run_detached(*cmd)
    logger.debug("Launch complete")


async def launch_neovim(
    *,
    worktree_path: Path,
    session_id: str,
    db_path: str = "",
    startup_prompt: str | None = None,
    **_kwargs: Any,
) -> None:
    logger.info("Preparing neovim session (TUI will attach interactively)")
    if db_path:
        await _write_mcp_json(worktree_path, session_id, db_path)
    if startup_prompt and startup_prompt.strip():
        await _write_startup_prompt(worktree_path, startup_prompt)

    task_id = _kwargs.get("task_id")
    if task_id:
        await _write_attach_context(worktree_path, task_id, session_id)
    logger.debug("Neovim preparation complete")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

LaunchFn = Callable[..., Coroutine[Any, Any, None]]

LAUNCHERS: dict[str, LaunchFn] = {
    "tmux": launch_tmux,
    "ide": launch_ide,
    "neovim": launch_neovim,
}


def get_launcher(name: str) -> LaunchFn:
    try:
        return LAUNCHERS[name]
    except KeyError:
        known = ", ".join(sorted(str(k) for k in LAUNCHERS))
        raise AgentError(f"unknown launcher {name!r}. Known: {known}") from None


def list_launchers() -> list[str]:
    return list(str(k) for k in LAUNCHERS)


_IDE_BACKENDS: frozenset[str] = frozenset({"vscode", "cursor", "windsurf", "kiro", "antigravity"})


def resolve_launcher(backend: str) -> tuple[str, str | None]:
    if backend == "tmux":
        return ("tmux", None)
    if backend in {"nvim", "neovim"}:
        return ("neovim", None)
    if backend in _IDE_BACKENDS:
        return ("ide", backend)
    return ("ide", backend)


__all__ = [
    "LAUNCHERS",
    "build_ide_command",
    "build_neovim_command",
    "get_launcher",
    "launch_ide",
    "launch_neovim",
    "launch_tmux",
    "list_launchers",
    "resolve_launcher",
]
