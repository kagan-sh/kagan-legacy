"""Agent backend registry and launcher for kagan.core.

AGENT_BACKENDS maps backend name ->
{executable, prompt_flag, workdir_flag, env_vars, supports_acp}.
spawn_agent() writes .mcp.json to the worktree and spawns a detached OS process.
"""

import asyncio
import contextlib
import errno
import functools
import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, TypedDict, cast

from loguru import logger

from kagan.core.errors import AgentError
from kagan.runtime_env import build_sanitized_subprocess_environment

# Registry of spawned processes for cleanup
_spawned_processes: dict[str, asyncio.subprocess.Process] = {}

# Scheduled timeout handles for agent processes (pid -> TimerHandle)
_AGENT_TIMEOUTS: dict[int, asyncio.TimerHandle] = {}

_AGENT_TIMEOUT_GRACE_SECONDS: Final[float] = 5.0


def _kill_agent(pid: int) -> None:
    """Send SIGTERM to an agent process, then SIGKILL after a grace period."""
    logger.warning("Agent pid={} exceeded timeout, sending SIGTERM", pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _AGENT_TIMEOUTS.pop(pid, None)
        return

    def _force_kill(pid: int) -> None:
        logger.warning("Agent pid={} did not exit after SIGTERM grace period, sending SIGKILL", pid)
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        _AGENT_TIMEOUTS.pop(pid, None)

    try:
        loop = asyncio.get_running_loop()
        handle = loop.call_later(_AGENT_TIMEOUT_GRACE_SECONDS, _force_kill, pid)
        _AGENT_TIMEOUTS[pid] = handle
    except RuntimeError:
        # No running loop — best-effort force kill
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        _AGENT_TIMEOUTS.pop(pid, None)


async def register_spawned_process(session_id: str, proc: asyncio.subprocess.Process) -> None:
    """Register a spawned process for tracking."""
    _spawned_processes[session_id] = proc


async def unregister_spawned_process(session_id: str) -> None:
    """Unregister a process when it's no longer needed."""
    _spawned_processes.pop(session_id, None)


async def cleanup_all_spawned_processes() -> None:
    """Terminate all tracked processes. Called on shutdown."""
    # Cancel all pending timeout handles
    for _pid, handle in list(_AGENT_TIMEOUTS.items()):
        handle.cancel()
    _AGENT_TIMEOUTS.clear()

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

    capabilities: tuple[str, ...]
    executable: str
    prompt_flag: str | None
    workdir_flag: str | None
    env_vars: dict[str, str]
    supports_acp: bool
    acp_command: list[str]
    acp_args: list[str]


class BackendCapability(StrEnum):
    """Capabilities that backend specs can declare."""

    MANAGED_DETACHED_RUN = "managed_detached_run"
    ACP_STREAMING = "acp_streaming"
    PROMPT_ARGUMENT = "prompt_argument"
    WORKDIR_ARGUMENT = "workdir_argument"
    TASK_SCOPED_MCP = "task_scoped_mcp"


@dataclass(frozen=True, slots=True)
class BackendSpec:
    """Typed backend metadata used to derive the legacy registry mapping."""

    name: str
    executable: str
    display_name: str | None = None
    prompt_flag: str | None = None
    workdir_flag: str | None = None
    env_vars: Mapping[str, str] = field(default_factory=dict)
    supports_acp: bool = False
    acp_command: tuple[str, ...] = ()
    acp_args: tuple[str, ...] = ()
    capabilities: frozenset[BackendCapability] = field(default_factory=frozenset)
    aliases: tuple[str, ...] = ()
    reference: bool = False
    install_hint: str | None = None
    auth_hint: str | None = None

    def to_legacy_config(self) -> AgentBackendConfig:
        """Project the typed spec into the legacy mapping contract."""
        return {
            "capabilities": tuple(sorted(cap.value for cap in self.capabilities)),
            "executable": self.executable,
            "prompt_flag": self.prompt_flag,
            "workdir_flag": self.workdir_flag,
            "env_vars": dict(self.env_vars),
            "supports_acp": self.has_capability(BackendCapability.ACP_STREAMING),
            "acp_command": list(self.acp_command),
            "acp_args": list(self.acp_args),
        }

    def has_capability(self, capability: BackendCapability) -> bool:
        """Return whether the backend declares *capability*."""
        return capability in self.capabilities

    def label(self) -> str:
        """Return a human-friendly backend label."""
        if not self.display_name or self.display_name == self.name:
            return self.name
        return f"{self.display_name} ({self.name})"

    def guidance_hints(self) -> tuple[str, ...]:
        """Return explicit setup hints for this backend."""
        return tuple(
            hint for hint in (self.install_hint, self.auth_hint) if isinstance(hint, str) and hint
        )


CLAUDE_CODE_BACKEND: Final = "claude-code"
CODEX_BACKEND: Final = "codex"
GEMINI_CLI_BACKEND: Final = "gemini-cli"
KIMI_CLI_BACKEND: Final = "kimi-cli"
OPENCODE_BACKEND: Final = "opencode"
GITHUB_COPILOT_BACKEND: Final = "github-copilot"
REFERENCE_BACKENDS: Final[tuple[str, ...]] = (CLAUDE_CODE_BACKEND, CODEX_BACKEND)


# ---------------------------------------------------------------------------
# Typed backend specs
# ---------------------------------------------------------------------------
_BACKEND_SPECS: dict[str, BackendSpec] = {
    CLAUDE_CODE_BACKEND: BackendSpec(
        name=CLAUDE_CODE_BACKEND,
        executable="claude",
        display_name="Claude Code",
        prompt_flag="-p",
        env_vars={"ANTHROPIC_MODEL": ""},
        supports_acp=True,
        acp_command=("npx", "claude-code-acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
        aliases=("claude",),
        reference=True,
        install_hint="Install with `curl -fsSL https://claude.ai/install.sh | bash`.",
        auth_hint="If Claude Code is already installed, run `claude` and follow the login prompts.",
    ),
    CODEX_BACKEND: BackendSpec(
        name=CODEX_BACKEND,
        executable="codex",
        display_name="Codex CLI",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("npx", "-y", "@zed-industries/codex-acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
        reference=True,
        install_hint="Install with `npm install -g @openai/codex`.",
        auth_hint=(
            "If Codex is already installed, run `codex` to sign in with ChatGPT or set"
            " `OPENAI_API_KEY`, then retry."
        ),
    ),
    GEMINI_CLI_BACKEND: BackendSpec(
        name=GEMINI_CLI_BACKEND,
        executable="gemini",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("gemini", "--experimental-acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
        aliases=("gemini",),
    ),
    KIMI_CLI_BACKEND: BackendSpec(
        name=KIMI_CLI_BACKEND,
        executable="kimi",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("kimi", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
        aliases=("kimi",),
    ),
    GITHUB_COPILOT_BACKEND: BackendSpec(
        name=GITHUB_COPILOT_BACKEND,
        executable="copilot",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("copilot", "--acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
        aliases=("copilot",),
    ),
    "goose": BackendSpec(
        name="goose",
        executable="goose",
        prompt_flag="--message",
        env_vars={"GOOSE_MODEL": ""},
        supports_acp=True,
        acp_command=("goose", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
    "openhands": BackendSpec(
        name="openhands",
        executable="openhands",
        prompt_flag="--task",
        workdir_flag="--workspace",
        supports_acp=True,
        acp_command=("openhands", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
                BackendCapability.WORKDIR_ARGUMENT,
            }
        ),
    ),
    OPENCODE_BACKEND: BackendSpec(
        name=OPENCODE_BACKEND,
        executable="opencode",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("opencode", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
    "auggie": BackendSpec(
        name="auggie",
        executable="auggie",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("auggie", "--acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
    "amp": BackendSpec(
        name="amp",
        executable="amp",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("npx", "-y", "amp-acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
    "docker-cagent": BackendSpec(
        name="docker-cagent",
        executable="cagent",
        prompt_flag="--task",
        workdir_flag="--workdir",
        supports_acp=True,
        acp_command=("cagent", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
                BackendCapability.WORKDIR_ARGUMENT,
            }
        ),
    ),
    "stakpak": BackendSpec(
        name="stakpak",
        executable="stakpak",
        prompt_flag="--task",
        supports_acp=True,
        acp_command=("stakpak", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
    "mistral-vibe": BackendSpec(
        name="mistral-vibe",
        executable="vibe",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("vibe-acp",),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
    "vt-code": BackendSpec(
        name="vt-code",
        executable="vtcode",
        prompt_flag="-p",
        supports_acp=True,
        acp_command=("vtcode", "acp"),
        capabilities=frozenset(
            {
                BackendCapability.ACP_STREAMING,
                BackendCapability.MANAGED_DETACHED_RUN,
                BackendCapability.PROMPT_ARGUMENT,
                BackendCapability.TASK_SCOPED_MCP,
            }
        ),
    ),
}
_AGENT_BACKEND_ALIASES: dict[str, str] = {
    alias: spec.name for spec in _BACKEND_SPECS.values() for alias in spec.aliases
}


def _build_legacy_backend_registry() -> dict[str, AgentBackendConfig]:
    return {name: spec.to_legacy_config() for name, spec in _BACKEND_SPECS.items()}


AGENT_BACKENDS: dict[str, AgentBackendConfig] = _build_legacy_backend_registry()


def normalize_backend_name(name: str) -> str:
    """Normalize user-provided backend names to canonical registry keys."""
    normalized = name.strip().lower()
    return _AGENT_BACKEND_ALIASES.get(normalized, normalized)


def get_backend_spec(name: str) -> BackendSpec:
    """Return the typed backend spec for *name*, raising AgentError if unknown."""
    resolved = normalize_backend_name(name)
    try:
        return _BACKEND_SPECS[resolved]
    except KeyError:
        known = ", ".join(sorted(_BACKEND_SPECS))
        raise AgentError(f"unknown agent backend {name!r}. Known: {known}") from None


def list_backend_specs() -> dict[str, BackendSpec]:
    """Return all registered backend specs."""
    return dict(_BACKEND_SPECS)


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
            capture_output=True,
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
    timeout_seconds: int | None = None,
) -> int:
    """Spawn an agent as a detached OS process.

    Args:
        timeout_seconds: Optional execution time limit in seconds.  When set,
            a timer is scheduled to SIGTERM (then SIGKILL) the process after
            *timeout_seconds* elapse.  ``None`` means no timeout (default).
    """
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

    # Schedule a timeout kill if requested
    if timeout_seconds is not None and proc.pid is not None:
        loop = asyncio.get_running_loop()
        handle = loop.call_later(timeout_seconds, _kill_agent, proc.pid)
        _AGENT_TIMEOUTS[proc.pid] = handle
        logger.debug("Agent process started, pid={}, timeout={}s", proc.pid, timeout_seconds)
    else:
        logger.debug("Agent process started, pid={}", proc.pid)
    return proc.pid


# ---------------------------------------------------------------------------
# ACP stream byte-counting guard (CWE-770)
# ---------------------------------------------------------------------------
_ACP_PER_MESSAGE_LIMIT: Final[int] = 10 * 1024 * 1024  # 10 MB per JSON-RPC line
_MAX_CUMULATIVE_BYTES: Final[int] = 500 * 1024 * 1024  # 500 MB total per session


class _ByteCountingStreamReader(asyncio.StreamReader):
    """StreamReader subclass that enforces a cumulative byte cap.

    The ACP JSON-RPC read loop (inside the ``acp`` library) calls ``readline()``
    or ``read()`` on the underlying reader.  This subclass wraps another reader,
    counts every byte returned, and terminates the associated process when the
    cumulative limit is exceeded, preventing unbounded memory growth.

    Inherits from ``asyncio.StreamReader`` so ``isinstance()`` checks pass when
    the ACP SDK validates stream types in ``ClientSideConnection.__init__``.
    Delegates all reads to the wrapped reader rather than using inherited state.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        process: asyncio.subprocess.Process,
        cumulative_limit: int = _MAX_CUMULATIVE_BYTES,
    ) -> None:
        # Note: We skip calling super().__init__() because we delegate all
        # operations to self._reader. The inheritance is only to pass
        # isinstance() checks in the ACP SDK.
        self._reader = reader
        self._process = process
        self._cumulative_bytes = 0
        self._cumulative_limit = cumulative_limit

    def _track(self, data: bytes) -> bytes:
        self._cumulative_bytes += len(data)
        if self._cumulative_bytes > self._cumulative_limit:
            logger.warning(
                "ACP stream exceeded cumulative byte limit ({} bytes), terminating pid={}",
                self._cumulative_bytes,
                self._process.pid,
            )
            self._process.terminate()
            raise AgentError(
                f"ACP stream exceeded cumulative byte limit "
                f"({self._cumulative_limit // (1024 * 1024)} MB)"
            )
        return data

    async def readline(self) -> bytes:
        while True:
            data = await self._reader.readline()
            if not data or data.strip():
                return self._track(data)
            self._track(data)  # count blank-line bytes even though we suppress them
            # skip blank/whitespace-only lines (workaround for upstream acp#87)

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        data = await self._reader.readuntil(separator)
        return self._track(data)

    async def read(self, n: int = -1) -> bytes:
        data = await self._reader.read(n)
        return self._track(data)

    async def readexactly(self, n: int) -> bytes:
        data = await self._reader.readexactly(n)
        return self._track(data)

    def at_eof(self) -> bool:
        return self._reader.at_eof()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)


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
    spec = get_backend_spec(backend_name)
    if not spec.has_capability(BackendCapability.ACP_STREAMING):
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
    if spec.acp_args:
        cmd.extend(spec.acp_args)

    kwargs["stdin"] = asyncio.subprocess.PIPE
    kwargs["stdout"] = asyncio.subprocess.PIPE
    kwargs["stderr"] = asyncio.subprocess.PIPE
    # Per-message StreamReader limit: 10 MB (reduced from 50 MB) so large
    # JSON-RPC lines don't hit the default 64 KB cap while still bounding
    # per-read memory usage.
    kwargs["limit"] = _ACP_PER_MESSAGE_LIMIT
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, **cast("Any", kwargs))
    except (FileNotFoundError, PermissionError) as exc:
        attempted = cmd[0] if cmd else spec.executable
        logger.error("Failed to spawn ACP agent backend={}: {}", backend_name, exc)
        raise AgentError(
            f"Failed to spawn ACP agent {backend_name!r} ({attempted!r}): {exc}"
        ) from exc

    if proc.stdin is None or proc.stdout is None:
        raise AgentError(f"spawned ACP agent {backend_name!r} does not expose stdio pipes")

    # Wrap stdout with cumulative byte-counting guard
    guarded_stdout = _ByteCountingStreamReader(proc.stdout, proc)
    proc.stdout = guarded_stdout  # type: ignore[assignment]

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
