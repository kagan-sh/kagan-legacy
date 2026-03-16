"""PAIR environment launchers for kagan.core.

LAUNCHERS maps launcher name → async launch function.
Three strategies: tmux (detached session), ide (vscode/cursor/windsurf/kiro/antigravity),
neovim (nvim at worktree path).

Each launcher writes .mcp.json into the worktree so the environment can
discover kagan's MCP server scoped to the session.
"""

import asyncio
import errno
import os
import subprocess
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from loguru import logger

from kagan.core._agent import (
    KIMI_CLI_BACKEND,
    OPENCODE_BACKEND,
    build_mcp_manifest,
    normalize_backend_name,
)
from kagan.core.errors import AgentError
from kagan.runtime_env import build_sanitized_subprocess_environment

_IDE_BINARIES: dict[str, str] = {
    "vscode": "code",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "kiro": "kiro",
    "antigravity": "agy",
}


COPILOT_CHAT_EXTENSION_ID: str = "github.copilot-chat"

_CHAT_CAPABLE_IDES: frozenset[str] = frozenset(
    {"vscode", "cursor", "windsurf", "kiro", "antigravity"}
)

_VSCODE_EXTENSION_DIRS: tuple[str, ...] = (
    "~/.vscode/extensions",
    "~/.cursor/extensions",
    "~/.windsurf/extensions",
    "~/.kiro/extensions",
    "~/.antigravity/extensions",
    "~/Library/Application Support/Code/User/globalStorage",  # macOS VSCode
    "~/Library/Application Support/Cursor/User/globalStorage",  # macOS Cursor
)


def _get_vscode_extensions_dirs(ide: str = "vscode") -> list[Path]:
    dirs: list[Path] = []
    home = Path.home()

    # Platform-specific paths
    if sys.platform == "darwin":
        # macOS
        if ide == "vscode":
            dirs.append(home / "Library/Application Support/Code/User/globalStorage")
        elif ide == "cursor":
            dirs.append(home / "Library/Application Support/Cursor/User/globalStorage")
        elif ide == "windsurf":
            dirs.append(home / "Library/Application Support/Windsurf/User/globalStorage")
        elif ide == "kiro":
            dirs.append(home / "Library/Application Support/Kiro/User/globalStorage")
        elif ide == "antigravity":
            dirs.append(home / "Library/Application Support/Antigravity/User/globalStorage")
    elif sys.platform == "win32":
        # Windows
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            if ide == "vscode":
                dirs.append(Path(appdata) / "Code/User/globalStorage")
            elif ide == "cursor":
                dirs.append(Path(appdata) / "Cursor/User/globalStorage")
            elif ide == "windsurf":
                dirs.append(Path(appdata) / "Windsurf/User/globalStorage")
            elif ide == "kiro":
                dirs.append(Path(appdata) / "Kiro/User/globalStorage")
            elif ide == "antigravity":
                dirs.append(Path(appdata) / "Antigravity/User/globalStorage")

    # Common cross-platform paths
    if ide == "vscode":
        dirs.append(home / ".vscode/extensions")
    elif ide == "cursor":
        dirs.append(home / ".cursor/extensions")
    elif ide == "windsurf":
        dirs.append(home / ".windsurf/extensions")
    elif ide == "kiro":
        dirs.append(home / ".kiro/extensions")
    elif ide == "antigravity":
        dirs.append(home / ".antigravity/extensions")

    return dirs


def detect_vscode_chat_autostart(ide: str = "vscode") -> bool:
    if ide not in _CHAT_CAPABLE_IDES:
        return False

    extension_dirs = _get_vscode_extensions_dirs(ide)

    for ext_dir in extension_dirs:
        try:
            if not ext_dir.exists():
                continue
            for entry in ext_dir.iterdir():
                if entry.is_dir() and entry.name.startswith(COPILOT_CHAT_EXTENSION_ID):
                    return True
        except OSError:
            continue

    return False


def build_vscode_chat_launcher_command(
    *,
    ide: str = "vscode",
    worktree_path: str,
    prompt_file: str,
    seed_prompt: str | None = None,
) -> list[str]:
    binary = _IDE_BINARIES.get(ide)
    if binary is None:
        known = ", ".join(sorted(_IDE_BINARIES))
        raise AgentError(f"unknown ide {ide!r}. Known: {known}")

    cmd = [binary, "chat", "--mode", "agent", "--add-file", prompt_file]
    cmd.append("--new-window")
    if seed_prompt and seed_prompt.strip():
        cmd.append(seed_prompt.strip())

    return cmd


def build_tmux_command(
    *,
    session_name: str,
    worktree_path: str,
    agent_cmd: str,
) -> list[str]:
    return [
        "tmux",
        "new-session",
        "-d",
        "-s",
        session_name,
        "-c",
        worktree_path,
        agent_cmd,
    ]


def build_ide_command(*, ide: str, worktree_path: str) -> list[str]:
    binary = _IDE_BINARIES.get(ide)
    if binary is None:
        known = ", ".join(sorted(_IDE_BINARIES))
        raise AgentError(f"unknown ide {ide!r}. Known: {known}")
    return [binary, "--new-window", worktree_path]


def build_neovim_command(*, worktree_path: str) -> list[str]:
    return ["nvim", worktree_path]


async def _write_mcp_json(worktree_path: Path, session_id: str, db_path: str) -> None:
    content = build_mcp_manifest(session_id=session_id, db_path=db_path, access_tier="default")
    mcp_path = worktree_path / ".mcp.json"
    try:
        await asyncio.to_thread(mcp_path.write_text, content, "utf-8")
    except OSError as exc:
        if exc.errno == errno.ENOSPC:  # No space left on device
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


def _single_line_prompt(prompt: str) -> str:
    return " ".join(line.strip() for line in prompt.splitlines() if line.strip())


async def _run_tmux_command(*args: str, capture_stdout: bool = False) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        *args,
        env=build_sanitized_subprocess_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if capture_stdout else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    text = ""
    if capture_stdout and stdout is not None:
        text = stdout.decode("utf-8", errors="replace")
    returncode = proc.returncode if proc.returncode is not None else 1
    return returncode, text


async def _tmux_pane_current_command(session_name: str) -> str | None:
    pane_target = _tmux_pane_target(session_name)
    code, output = await _run_tmux_command(
        "display-message",
        "-p",
        "-t",
        pane_target,
        "#{pane_current_command}",
        capture_stdout=True,
    )
    if code != 0:
        return None
    command = output.strip().lower()
    return command or None


def _tmux_pane_target(session_name: str) -> str:
    return f"{session_name}:0.0"


async def _tmux_pane_contains(session_name: str, needle: str) -> bool:
    pane_target = _tmux_pane_target(session_name)
    code, output = await _run_tmux_command(
        "capture-pane",
        "-p",
        "-t",
        pane_target,
        "-S",
        "-40",
        capture_stdout=True,
    )
    if code != 0:
        return False
    return needle in output


async def _wait_for_tmux_pane_command(
    session_name: str,
    expected_commands: tuple[str, ...],
    *,
    max_attempts: int = 20,
    sleep_seconds: float = 0.2,
) -> bool:
    expected = tuple(command.strip().lower() for command in expected_commands if command.strip())
    if not expected:
        return True
    for _ in range(max_attempts):
        current = await _tmux_pane_current_command(session_name)
        if current in expected:
            return True
        await asyncio.sleep(sleep_seconds)
    return False


async def _send_tmux_startup_prompt(
    session_name: str,
    prompt_path: Path,
    *,
    wait_for_commands: tuple[str, ...] | None = None,
    max_attempts: int = 12,
    use_literal_send_keys: bool = False,
    ready_text: str | None = None,
    settle_seconds: float = 0.0,
) -> bool:
    prompt_text = _single_line_prompt(prompt_path.read_text(encoding="utf-8"))
    if not prompt_text:
        return False
    pane_target = _tmux_pane_target(session_name)
    buffer_name = f"kagan-startup-{session_name[-12:]}"
    initial_settle_seconds = max(0.0, settle_seconds)
    for _ in range(max_attempts):
        has_session, _ = await _run_tmux_command("has-session", "-t", session_name)
        if has_session != 0:
            await asyncio.sleep(0.2)
            continue
        if wait_for_commands is not None:
            ready = await _wait_for_tmux_pane_command(
                session_name,
                wait_for_commands,
                max_attempts=1,
            )
            if not ready:
                await asyncio.sleep(0.2)
                continue
        if ready_text is not None:
            pane_ready = await _tmux_pane_contains(session_name, ready_text)
            if not pane_ready:
                await asyncio.sleep(0.2)
                continue
        if initial_settle_seconds > 0.0:
            await asyncio.sleep(initial_settle_seconds)
            initial_settle_seconds = 0.0
        if use_literal_send_keys:
            sent, _ = await _run_tmux_command(
                "send-keys",
                "-t",
                pane_target,
                "-l",
                prompt_text,
            )
            if sent != 0:
                await asyncio.sleep(0.2)
                continue
            return True
        loaded, _ = await _run_tmux_command(
            "load-buffer",
            "-b",
            buffer_name,
            str(prompt_path),
        )
        if loaded != 0:
            await asyncio.sleep(0.2)
            continue
        pasted, _ = await _run_tmux_command(
            "paste-buffer",
            "-b",
            buffer_name,
            "-t",
            pane_target,
        )
        if pasted != 0:
            await _run_tmux_command("delete-buffer", "-b", buffer_name)
            await asyncio.sleep(0.2)
            continue
        await _run_tmux_command("delete-buffer", "-b", buffer_name)
        return True
    return False


async def _submit_tmux_startup_prompt(session_name: str) -> bool:
    pane_target = _tmux_pane_target(session_name)
    sent, _ = await _run_tmux_command("send-keys", "-t", pane_target, "Enter")
    return sent == 0


def _prompt_injection_wait_commands(
    *,
    agent_cmd: str,
    agent_backend: str | None,
) -> tuple[str, ...] | None:
    executable = agent_cmd.strip().split(maxsplit=1)[0].lower()
    if executable == OPENCODE_BACKEND:
        return ("node", OPENCODE_BACKEND)
    normalized_backend = normalize_backend_name(agent_backend) if agent_backend else ""
    if normalized_backend == OPENCODE_BACKEND:
        return ("node", OPENCODE_BACKEND)
    return (executable,) if executable else None


def _tmux_prompt_injection_options(*, agent_backend: str | None) -> dict[str, Any]:
    normalized_backend = normalize_backend_name(agent_backend) if agent_backend else ""
    if normalized_backend == OPENCODE_BACKEND:
        return {
            "use_literal_send_keys": True,
            "ready_text": "Ask anything...",
            "settle_seconds": 0.35,
        }
    if normalized_backend == KIMI_CLI_BACKEND:
        return {
            "use_literal_send_keys": True,
            "ready_text": None,
            "settle_seconds": 0.35,
        }
    return {
        "use_literal_send_keys": False,
        "ready_text": None,
        "settle_seconds": 0.0,
    }


async def _inject_tmux_startup_prompt(
    *,
    session_name: str,
    prompt_path: Path,
    wait_commands: tuple[str, ...] | None,
    max_attempts: int,
    use_literal_send_keys: bool = False,
    ready_text: str | None = None,
    settle_seconds: float = 0.0,
) -> None:
    injected = await _send_tmux_startup_prompt(
        session_name,
        prompt_path,
        wait_for_commands=wait_commands,
        max_attempts=max_attempts,
        use_literal_send_keys=use_literal_send_keys,
        ready_text=ready_text,
        settle_seconds=settle_seconds,
    )
    if not injected:
        logger.warning("Unable to inject startup prompt into tmux session={}", session_name)
        return
    submitted = await _submit_tmux_startup_prompt(session_name)
    if not submitted:
        logger.warning("Unable to submit startup prompt in tmux session={}", session_name)


def _log_injection_task_failure(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.opt(exception=exc).error(
            "Background tmux startup prompt injection failed task={}",
            task.get_name(),
        )


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

    proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
    await proc.wait()


async def launch_tmux(
    *,
    worktree_path: Path,
    session_id: str,
    agent_cmd: str,
    agent_backend: str | None = None,
    db_path: str = "",
    startup_prompt: str | None = None,
) -> None:
    if sys.platform == "win32":
        raise AgentError(
            "tmux is not available on Windows. "
            "Use 'vscode', 'cursor', 'windsurf', or another IDE launcher instead. "
            "Install Windows Terminal for a better command-line experience."
        )
    logger.info("Launching tmux session")
    if db_path:
        await _write_mcp_json(worktree_path, session_id, db_path)
    prompt_path: Path | None = None
    if startup_prompt and startup_prompt.strip():
        prompt_path = await _write_startup_prompt(worktree_path, startup_prompt)

    session_name = f"kagan-{session_id.replace(':', '-')}"
    cmd = build_tmux_command(
        session_name=session_name,
        worktree_path=str(worktree_path),
        agent_cmd=agent_cmd,
    )

    await _run_detached(*cmd)
    if prompt_path is not None:
        wait_commands = _prompt_injection_wait_commands(
            agent_cmd=agent_cmd,
            agent_backend=agent_backend,
        )
        injection_options = _tmux_prompt_injection_options(agent_backend=agent_backend)
        inject_kwargs: dict[str, Any] = {
            "session_name": session_name,
            "prompt_path": prompt_path,
            "wait_commands": wait_commands,
            "max_attempts": 60,
        }
        if injection_options["use_literal_send_keys"]:
            inject_kwargs["use_literal_send_keys"] = True
        ready_text = injection_options["ready_text"]
        if ready_text is not None:
            inject_kwargs["ready_text"] = ready_text
        settle_seconds = injection_options["settle_seconds"]
        if settle_seconds > 0.0:
            inject_kwargs["settle_seconds"] = settle_seconds
        injection_task = asyncio.create_task(
            _inject_tmux_startup_prompt(**inject_kwargs),
            name=f"tmux-startup-prompt:{session_name}",
        )
        injection_task.add_done_callback(_log_injection_task_failure)
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
    logger.info("Launching ide session")
    if db_path:
        await _write_mcp_json(worktree_path, session_id, db_path)

    prompt_path: Path | None = None
    if startup_prompt and startup_prompt.strip():
        prompt_path = await _write_startup_prompt(worktree_path, startup_prompt)

    if prompt_path is not None and detect_vscode_chat_autostart(ide):
        logger.info(f"IDE {ide} has chat capability, launching chat interface")
        cmd = build_vscode_chat_launcher_command(
            ide=ide,
            worktree_path=str(worktree_path),
            prompt_file=str(prompt_path),
            seed_prompt=startup_prompt,
        )
    else:
        cmd = build_ide_command(ide=ide, worktree_path=str(worktree_path))

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
    logger.debug("Neovim preparation complete")


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
    # Fall through — treat unknown as ide with the raw name
    return ("ide", backend)


__all__ = [
    "COPILOT_CHAT_EXTENSION_ID",
    "LAUNCHERS",
    "build_ide_command",
    "build_neovim_command",
    "build_tmux_command",
    "build_vscode_chat_launcher_command",
    "detect_vscode_chat_autostart",
    "get_launcher",
    "launch_ide",
    "launch_neovim",
    "launch_tmux",
    "list_launchers",
    "resolve_launcher",
]
