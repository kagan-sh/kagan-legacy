"""Agent backend registry and launcher for kagan.core.

AGENT_BACKENDS maps backend name ->
{executable, prompt_flag, workdir_flag, env_vars, supports_acp}.
spawn_agent() writes .mcp.json to the worktree and spawns a detached OS process.
"""

import asyncio
import errno
import functools
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, TypedDict, cast

from loguru import logger

from kagan.core.errors import AgentError
from kagan.runtime_env import build_sanitized_subprocess_environment

# Registry of spawned processes for cleanup
_spawned_processes: dict[str, asyncio.subprocess.Process] = {}


async def register_spawned_process(session_id: str, proc: asyncio.subprocess.Process) -> None:
    """Register a spawned process for tracking."""
    _spawned_processes[session_id] = proc


async def unregister_spawned_process(session_id: str) -> None:
    """Unregister a process when it's no longer needed."""
    _spawned_processes.pop(session_id, None)


async def cleanup_all_spawned_processes() -> None:
    """Terminate all tracked processes. Called on shutdown."""
    for _session_id, proc in list(_spawned_processes.items()):
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except (TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
    _spawned_processes.clear()


def resolve_default_agent_backend(settings: dict[str, str]) -> str:
    """Return the default agent backend from settings, falling back to claude-code."""
    return settings.get("default_agent_backend") or "claude-code"


class AgentBackendConfig(TypedDict, total=False):
    """Schema for an agent backend registry entry."""

    executable: str
    prompt_flag: str | None
    workdir_flag: str | None
    env_vars: dict[str, str]
    supports_acp: bool
    acp_command: list[str]
    acp_args: list[str]


CLAUDE_CODE_BACKEND: Final = "claude-code"
CODEX_BACKEND: Final = "codex"
GEMINI_CLI_BACKEND: Final = "gemini-cli"
KIMI_CLI_BACKEND: Final = "kimi-cli"
OPENCODE_BACKEND: Final = "opencode"
GITHUB_COPILOT_BACKEND: Final = "github-copilot"


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------
AGENT_BACKENDS: dict[str, AgentBackendConfig] = {
    CLAUDE_CODE_BACKEND: {
        "executable": "claude",
        "prompt_flag": "-p",
        "workdir_flag": None,  # uses cwd
        "env_vars": {"ANTHROPIC_MODEL": ""},
        "supports_acp": True,
        "acp_command": ["npx", "claude-code-acp"],
        "acp_args": [],
    },
    CODEX_BACKEND: {
        "executable": "codex",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["npx", "-y", "@zed-industries/codex-acp"],
        "acp_args": [],
    },
    GEMINI_CLI_BACKEND: {
        "executable": "gemini",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["gemini", "--experimental-acp"],
        "acp_args": [],
    },
    KIMI_CLI_BACKEND: {
        "executable": "kimi",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["kimi", "acp"],
        "acp_args": [],
    },
    GITHUB_COPILOT_BACKEND: {
        "executable": "copilot",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["copilot", "--acp"],
        "acp_args": [],
    },
    "goose": {
        "executable": "goose",
        "prompt_flag": "--message",
        "workdir_flag": None,
        "env_vars": {"GOOSE_MODEL": ""},
        "supports_acp": True,
        "acp_command": ["goose", "acp"],
        "acp_args": [],
    },
    "openhands": {
        "executable": "openhands",
        "prompt_flag": "--task",
        "workdir_flag": "--workspace",
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["openhands", "acp"],
        "acp_args": [],
    },
    OPENCODE_BACKEND: {
        "executable": "opencode",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["opencode", "acp"],
        "acp_args": [],
    },
    "auggie": {
        "executable": "auggie",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["auggie", "--acp"],
        "acp_args": [],
    },
    "amp": {
        "executable": "amp",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["npx", "-y", "amp-acp"],
        "acp_args": [],
    },
    "docker-cagent": {
        "executable": "cagent",
        "prompt_flag": "--task",
        "workdir_flag": "--workdir",
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["cagent", "acp"],
        "acp_args": [],
    },
    "stakpak": {
        "executable": "stakpak",
        "prompt_flag": "--task",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["stakpak", "acp"],
        "acp_args": [],
    },
    "mistral-vibe": {
        "executable": "vibe",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["vibe-acp"],
        "acp_args": [],
    },
    "vt-code": {
        "executable": "vtcode",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": True,
        "acp_command": ["vtcode", "acp"],
        "acp_args": [],
    },
}
_AGENT_BACKEND_ALIASES: dict[str, str] = {
    "claude": CLAUDE_CODE_BACKEND,
    "copilot": GITHUB_COPILOT_BACKEND,
    "gemini": GEMINI_CLI_BACKEND,
    "kimi": KIMI_CLI_BACKEND,
}


def normalize_backend_name(name: str) -> str:
    """Normalize user-provided backend names to canonical registry keys."""
    normalized = name.strip().lower()
    return _AGENT_BACKEND_ALIASES.get(normalized, normalized)


def get_backend(name: str) -> AgentBackendConfig:
    """Return the registry entry for *name*, raising AgentError if unknown."""
    resolved = normalize_backend_name(name)
    try:
        return AGENT_BACKENDS[resolved]
    except KeyError:
        known = ", ".join(sorted(AGENT_BACKENDS))
        raise AgentError(f"unknown agent backend {name!r}. Known: {known}") from None


def list_backends() -> list[str]:
    """Return all registered backend names."""
    return list(AGENT_BACKENDS)


def list_available_backends() -> dict[str, bool]:
    """Return {backend_name: is_installed} for all registered backends."""
    return {
        name: shutil.which(cfg["executable"]) is not None for name, cfg in AGENT_BACKENDS.items()
    }


@functools.lru_cache(maxsize=1)
def _copilot_builtin_acp_supported() -> bool:
    """Return whether the locally installed Copilot CLI supports `--acp`."""
    if shutil.which("copilot") is None:
        return False

    try:
        completed = subprocess.run(
            ["copilot", "--acp", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    combined_output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    ).lower()
    return "unknown option '--acp'" not in combined_output


def resolve_acp_command(backend_name: str) -> list[str]:
    """Resolve the ACP launch command for a backend on the current machine."""
    entry = get_backend(backend_name)
    executable = entry.get("executable")
    fallback = [executable] if isinstance(executable, str) and executable else []
    acp_cmd = list(entry.get("acp_command", fallback))
    if not acp_cmd:
        raise AgentError(f"No ACP command configured for backend {backend_name!r}")

    if backend_name != GITHUB_COPILOT_BACKEND:
        return acp_cmd

    if _copilot_builtin_acp_supported():
        return acp_cmd

    raise AgentError(
        "Installed Copilot CLI does not support `--acp`. Current GitHub Copilot CLI releases "
        "do support ACP, so update your local Copilot installation with `copilot update`, "
        "`brew upgrade copilot-cli`, or reinstall the latest build from `github/copilot-cli`."
    )


def build_agent_environment(
    *,
    session_id: str,
    task_id: str | None,
    backend_env_vars: Mapping[str, str],
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a child-process environment for launching agent backends."""
    env = build_sanitized_subprocess_environment(base_env)

    env["KAGAN_SESSION_ID"] = session_id
    env["KAGAN_MCP_CMD"] = "kagan mcp"
    if task_id is not None:
        env["KAGAN_TASK_ID"] = task_id

    for key, default in backend_env_vars.items():
        if key not in env and default:
            env[key] = default
    return env


def build_mcp_manifest(
    *,
    session_id: str,
    db_path: str,
    role: str = "WORKER",
    project_id: str | None = None,
) -> str:
    """Build the .mcp.json content string for a given session."""
    mcp_args = ["kagan", "mcp", "--session-id", session_id, "--db", db_path]
    mcp_args += ["--role", role]
    if project_id is not None:
        mcp_args += ["--project-id", project_id]

    payload = {
        "mcpServers": {
            "kagan": {
                "command": mcp_args[0],
                "args": mcp_args[1:],
            }
        }
    }
    return json.dumps(payload, indent=2)


async def _prepare_spawn(
    backend_name: str,
    worktree_path: Path,
    prompt: str,
    session_id: str,
    task_id: str,
    db_path: str,
    project_id: str | None = None,
    *,
    write_mcp_manifest: bool = True,
) -> tuple[list[str], dict[str, str], dict[str, object], str]:
    entry = get_backend(backend_name)

    mcp_content = build_mcp_manifest(
        session_id=session_id, db_path=db_path, role="WORKER", project_id=project_id
    )
    if write_mcp_manifest:
        mcp_path = worktree_path / ".mcp.json"
        try:
            await asyncio.to_thread(mcp_path.write_text, mcp_content, "utf-8")
        except OSError as exc:
            if exc.errno == errno.ENOSPC:  # No space left on device
                raise AgentError(
                    f"Cannot write MCP manifest to {mcp_path}: Disk is full. "
                    f"Free up disk space and try again."
                ) from exc
            raise AgentError(f"Failed to write MCP manifest to {mcp_path}: {exc}") from exc

    cmd: list[str] = [entry["executable"]]
    if entry["workdir_flag"]:
        cmd += [entry["workdir_flag"], str(worktree_path)]

    env = build_agent_environment(
        session_id=session_id,
        task_id=task_id,
        backend_env_vars=entry.get("env_vars", {}),
    )

    base_kwargs: dict[str, object] = {
        "cwd": str(worktree_path),
        "env": env,
    }
    return cmd, env, base_kwargs, mcp_content


async def spawn_agent(
    backend_name: str,
    worktree_path: Path,
    prompt: str,
    *,
    session_id: str,
    task_id: str,
    db_path: str,
    project_id: str | None = None,
) -> int:
    """Spawn an agent as a detached OS process."""
    logger.info("Spawning agent backend={}", backend_name)
    entry = get_backend(backend_name)
    cmd, _env, kwargs, _mcp_content = await _prepare_spawn(
        backend_name,
        worktree_path,
        prompt,
        session_id,
        task_id,
        db_path,
        project_id,
    )
    if entry["prompt_flag"] and prompt:
        cmd += [entry["prompt_flag"], prompt]
    kwargs["stdin"] = asyncio.subprocess.DEVNULL
    kwargs["stdout"] = asyncio.subprocess.DEVNULL
    kwargs["stderr"] = asyncio.subprocess.DEVNULL
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    else:
        # Windows: create detached process
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, **cast("Any", kwargs))
    except (FileNotFoundError, PermissionError) as exc:
        logger.error("Failed to spawn agent backend={}: {}", backend_name, exc)
        raise AgentError(
            f"Failed to spawn agent {backend_name!r} ({entry['executable']!r}): {exc}"
        ) from exc

    await register_spawned_process(session_id, proc)  # Track for cleanup
    logger.debug("Agent process started, pid={}", proc.pid)
    return proc.pid


async def spawn_agent_via_acp(
    backend_name: str,
    worktree_path: Path,
    prompt: str,
    *,
    session_id: str,
    task_id: str,
    db_path: str,
    project_id: str | None = None,
    on_session_update: Callable,
) -> tuple[int, asyncio.Task]:
    """Spawn an ACP-capable agent with owned stdio and start ACP loop task."""
    logger.info("Spawning ACP agent backend={}", backend_name)
    entry = get_backend(backend_name)
    if not entry.get("supports_acp", False):
        raise AgentError(f"Agent backend {backend_name!r} does not support ACP execution.")

    cmd, _env, kwargs, mcp_content = await _prepare_spawn(
        backend_name,
        worktree_path,
        prompt,
        session_id,
        task_id,
        db_path,
        project_id,
        write_mcp_manifest=False,
    )
    acp_cmd = resolve_acp_command(backend_name)
    if acp_cmd:
        cmd = list(acp_cmd)
    acp_args = entry.get("acp_args")
    if isinstance(acp_args, list) and acp_args:
        cmd.extend(str(arg) for arg in acp_args)

    kwargs["stdin"] = asyncio.subprocess.PIPE
    kwargs["stdout"] = asyncio.subprocess.PIPE
    kwargs["stderr"] = asyncio.subprocess.PIPE
    # Raise the StreamReader pipe limit to 50 MB so large JSON-RPC lines
    # (e.g. file reads, multimodal payloads) don't hit the default 64 KB cap
    # and crash the receive loop with ValueError/LimitOverrunError.
    kwargs["limit"] = 50 * 1024 * 1024
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, **cast("Any", kwargs))
    except (FileNotFoundError, PermissionError) as exc:
        attempted = cmd[0] if cmd else entry["executable"]
        logger.error("Failed to spawn ACP agent backend={}: {}", backend_name, exc)
        raise AgentError(
            f"Failed to spawn ACP agent {backend_name!r} ({attempted!r}): {exc}"
        ) from exc

    if proc.stdin is None or proc.stdout is None:
        raise AgentError(f"spawned ACP agent {backend_name!r} does not expose stdio pipes")

    from kagan.core._acp import KaganACPClient, run_acp_session

    client = KaganACPClient(on_session_update)
    reader_task = asyncio.create_task(
        run_acp_session(
            process=proc,
            client=client,
            worktree_path=worktree_path,
            prompt=prompt,
            mcp_manifest=mcp_content,
        ),
        name=f"acp-session:{task_id}",
    )
    logger.debug("ACP agent process started, pid={}", proc.pid)
    return proc.pid, reader_task
