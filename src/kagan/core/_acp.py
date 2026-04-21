"""Thin ACP adapter for kagan.core agent sessions with a shared ACP client base."""

import asyncio
import contextlib
import inspect
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import acp
from acp import RequestError
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AllowedOutcome,
    AvailableCommandsUpdate,
    CreateTerminalResponse,
    CurrentModeUpdate,
    DeniedOutcome,
    EnvVariable,
    McpServerStdio,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    SessionInfoUpdate,
    TerminalOutputResponse,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UsageUpdate,
    UserMessageChunk,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

# ACP 0.9.0a1 renamed KillTerminalCommandResponse → KillTerminalResponse
try:
    from acp.schema import KillTerminalResponse
except ImportError:
    from acp.schema import KillTerminalCommandResponse as KillTerminalResponse
from loguru import logger

from kagan.core._agent import (
    CLAUDE_CODE_BACKEND,
    CODEX_BACKEND,
    GEMINI_CLI_BACKEND,
    OPENCODE_BACKEND,
    get_backend_spec,
)
from kagan.core.enums import SessionEventType
from kagan.core.errors import AgentError

_ACP_STARTUP_TIMEOUT_ENV_KEY = "KAGAN_ACP_STARTUP_TIMEOUT_SECONDS"
_ACP_HANDSHAKE_TIMEOUT_ENV_KEY = "KAGAN_ACP_HANDSHAKE_TIMEOUT_SECONDS"
_ACP_TIMEOUT_CLAUDE_SECONDS = 12.0
_ACP_TIMEOUT_CODEX_SECONDS = 45.0
_ACP_TIMEOUT_DEFAULT_SECONDS = 20.0
ACP_TIMEOUT_HINT = (
    "Set KAGAN_ACP_STARTUP_TIMEOUT_SECONDS "
    "(or KAGAN_ACP_HANDSHAKE_TIMEOUT_SECONDS) to increase this limit."
)
_CODEX_ACP_EACCES_HINT = (
    "Detected a local npm npx cache permission issue. "
    "Try `chmod +x ~/.npm/_npx/*/node_modules/"
    "@zed-industries/codex-acp-darwin-arm64/bin/codex-acp` "
    "or reset cache with `rm -rf ~/.npm/_npx && npx -y @zed-industries/codex-acp --help`."
)


class ACPClientBase(acp.Client):
    """Shared ACP client defaults for unsupported file/terminal/ext methods."""

    _conn: acp.Agent | None

    async def write_text_file(
        self,
        content: str,
        path: str,
        session_id: str,
        **kwargs: Any,
    ) -> WriteTextFileResponse | None:
        raise RequestError.method_not_found("fs/write_text_file")

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        raise RequestError.method_not_found("fs/read_text_file")

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        raise RequestError.method_not_found(method)

    def on_connect(self, conn: acp.Agent) -> None:
        self._conn = conn


def _configured_acp_timeout_seconds(*keys: str) -> float | None:
    for key in keys:
        env_value = os.environ.get(key, "")
        try:
            configured = float(env_value) if env_value else 0.0
        except ValueError:
            configured = 0.0
        if configured > 0.0:
            return configured
    return None


def _default_acp_timeout_seconds(agent_backend: str) -> float:
    if agent_backend == CLAUDE_CODE_BACKEND:
        return _ACP_TIMEOUT_CLAUDE_SECONDS
    if agent_backend == CODEX_BACKEND:
        return _ACP_TIMEOUT_CODEX_SECONDS
    return _ACP_TIMEOUT_DEFAULT_SECONDS


def _backend_auth_hint(agent_backend: str) -> str | None:
    try:
        cmd = get_backend_spec(agent_backend).resolve_command("auth")
        return cmd.description if cmd is not None else None
    except AgentError:
        return None


def acp_handshake_timeout_seconds(agent_backend: str) -> float:
    configured = _configured_acp_timeout_seconds(
        _ACP_HANDSHAKE_TIMEOUT_ENV_KEY,
        _ACP_STARTUP_TIMEOUT_ENV_KEY,
    )
    if configured is not None:
        return configured
    return _default_acp_timeout_seconds(agent_backend)


def acp_startup_timeout_seconds(agent_backend: str) -> float:
    configured = _configured_acp_timeout_seconds(
        _ACP_STARTUP_TIMEOUT_ENV_KEY,
        _ACP_HANDSHAKE_TIMEOUT_ENV_KEY,
    )
    if configured is not None:
        return configured
    return _default_acp_timeout_seconds(agent_backend)


def _acp_startup_timeout_seconds(agent_backend: str) -> float:
    return acp_startup_timeout_seconds(agent_backend)


def _infer_backend_name_from_process(process: asyncio.subprocess.Process) -> str:
    args = [str(part).lower() for part in (getattr(process, "args", []) or [])]
    joined = " ".join(args)
    if "claude" in joined:
        return CLAUDE_CODE_BACKEND
    if OPENCODE_BACKEND in joined:
        return OPENCODE_BACKEND
    if "gemini" in joined:
        return GEMINI_CLI_BACKEND
    if "codex" in joined:
        return CODEX_BACKEND
    if args:
        return str(getattr(process, "args", ["agent"])[0] or "agent")
    return "agent"


def friendly_acp_error_message(*, error: object, agent_backend: str, during: str) -> str:
    raw = str(error).strip() or "Unknown agent error"
    lowered = raw.lower()
    prefix = f"{agent_backend} initialization failed during {during}."

    if (
        "rate limit" in lowered
        or "rate_limit" in lowered
        or "429" in lowered
        or "too many requests" in lowered
    ):
        return (
            f"{prefix} Rate limit reached. Wait for reset or check billing/subscription, "
            "then retry."
        )
    if (
        "subscription" in lowered
        or "usage limit" in lowered
        or "quota" in lowered
        or "budget" in lowered
        or "active subscription required" in lowered
    ):
        return (
            f"{prefix} Account usage/subscription limit reached. "
            "Review your provider plan and billing limits."
        )
    if (
        "authentication" in lowered
        or "unauthorized" in lowered
        or "invalid api key" in lowered
        or "401" in lowered
    ):
        auth_hint = _backend_auth_hint(agent_backend)
        if auth_hint is None:
            auth_hint = "Re-authenticate with the selected backend CLI and verify credentials."
        return f"{prefix} Authentication failed. {auth_hint}"
    if (
        "enotfound" in lowered
        or "econnrefused" in lowered
        or "etimedout" in lowered
        or "fetch failed" in lowered
        or "network" in lowered
        or "tls" in lowered
        or "certificate" in lowered
    ):
        return (
            f"{prefix} Network connectivity issue to provider services. "
            "Check connection, VPN/proxy, then retry."
        )
    if "overloaded" in lowered or "529" in lowered or "service unavailable" in lowered:
        return f"{prefix} The provider service is overloaded right now. Retry shortly."
    return f"{prefix} {raw}"


def _friendly_startup_error_message(*, error: object, agent_backend: str, during: str) -> str:
    return friendly_acp_error_message(
        error=error,
        agent_backend=agent_backend,
        during=during,
    )


class KaganACPClient(ACPClientBase):
    """ACP client implementation forwarding session updates to a callback."""

    def __init__(self, on_update: Callable[[str, Any], Any]) -> None:
        self._on_update = on_update
        self._conn: acp.Agent | None = None

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        for option in options:
            if option.kind in {"allow_always", "allow_once"}:
                logger.debug(
                    "Auto-approving ACP permission session_id={} option_id={} tool_call_id={}",
                    session_id,
                    option.option_id,
                    tool_call.tool_call_id,
                )
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome="selected", option_id=option.option_id)
                )

        logger.warning(
            "No allow permission options provided by agent; rejecting "
            "session_id={} tool_call_id={}",
            session_id,
            tool_call.tool_call_id,
        )
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(
        self,
        session_id: str,
        update: UserMessageChunk
        | AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress
        | AgentPlanUpdate
        | AvailableCommandsUpdate
        | CurrentModeUpdate
        | SessionInfoUpdate
        | UsageUpdate,
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "ACP session update received session_id={} type={}",
            session_id,
            type(update).__name__,
        )
        maybe_awaitable = self._on_update(session_id, update)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable


def map_acp_update_to_event(
    update: UserMessageChunk
    | AgentMessageChunk
    | AgentThoughtChunk
    | ToolCallStart
    | ToolCallProgress
    | AgentPlanUpdate
    | AvailableCommandsUpdate
    | CurrentModeUpdate
    | SessionInfoUpdate
    | UsageUpdate,
) -> tuple[SessionEventType, dict[str, Any]] | None:
    """Map ACP session updates to kagan event types and payloads."""
    if isinstance(update, UserMessageChunk):
        return None
    if isinstance(update, AgentMessageChunk):
        chunk_text = str(getattr(update.content, "text", "") or "")
        return SessionEventType.OUTPUT_CHUNK, {
            "text": chunk_text,
            "acp": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": chunk_text},
            },
        }
    if isinstance(update, AgentThoughtChunk):
        chunk_text = str(getattr(update.content, "text", "") or "")
        return SessionEventType.OUTPUT_CHUNK, {
            "text": chunk_text,
            "thought": True,
            "acp": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": chunk_text},
            },
        }

    payload: dict[str, Any] = {
        "acp": update.model_dump(mode="json", by_alias=True, exclude_none=True)
    }
    if isinstance(update, ToolCallStart):
        return SessionEventType.TOOL_CALL_START, payload
    if isinstance(update, ToolCallProgress):
        return SessionEventType.TOOL_CALL_UPDATE, payload
    if isinstance(update, AgentPlanUpdate):
        return SessionEventType.PLAN_UPDATE, payload
    if isinstance(update, UsageUpdate):
        usage_payload: dict[str, Any] = {
            "usage": {
                "size": update.size,
                "used": update.used,
                "cost": update.cost.amount if update.cost else None,
                "cost_currency": update.cost.currency if update.cost else None,
            },
            "acp": update.model_dump(mode="json", by_alias=True, exclude_none=True),
        }
        return SessionEventType.AGENT_STATUS, usage_payload
    return SessionEventType.AGENT_STATUS, payload


def _build_mcp_server_from_manifest(mcp_manifest: str) -> McpServerStdio:
    payload = json.loads(mcp_manifest)
    servers = payload.get("mcpServers", {})
    if not servers:
        raise ValueError("No MCP servers found in MCP manifest")

    name, config = next(iter(servers.items()))
    command = config["command"]
    args = config.get("args", [])
    env = [EnvVariable(name=key, value=value) for key, value in (config.get("env") or {}).items()]
    return McpServerStdio(name=name, command=command, args=args, env=env)


def acp_process_exit_hint(*, agent_backend: str, details: str) -> str | None:
    lowered = details.lower()
    if agent_backend == CODEX_BACKEND and "eacces" in lowered and "codex-acp" in lowered:
        return _CODEX_ACP_EACCES_HINT
    if "eacces" in lowered or "permission denied" in lowered:
        return "Detected a local permission issue while launching the backend executable."
    return None


def _acp_process_exit_hint(*, agent_backend: str, details: str) -> str | None:
    return acp_process_exit_hint(agent_backend=agent_backend, details=details)


async def _acp_process_exit_message(
    process: asyncio.subprocess.Process, *, during: str, agent_backend: str
) -> str | None:
    if process.returncode is None:
        return None
    details = ""
    if process.stderr is not None:
        with contextlib.suppress(OSError, RuntimeError, ValueError, TimeoutError):
            raw = await asyncio.wait_for(process.stderr.read(4096), timeout=0.2)
            if raw:
                details = raw.decode("utf-8", "replace").strip()
    message = f"agent process exited before ACP {during} (exit code {process.returncode})."
    if details:
        compact = " ".join(line.strip() for line in details.splitlines() if line.strip())
        message = f"{message} {compact[:500]}"
        hint = acp_process_exit_hint(agent_backend=agent_backend, details=details)
        if hint:
            message = f"{message} {hint}"
    return message


async def run_acp_session(
    process: asyncio.subprocess.Process,
    client: KaganACPClient,
    worktree_path: Path,
    prompt: str,
    mcp_manifest: str,
    backend_name: str | None = None,
) -> None:
    """Run ACP handshake and session loop for a spawned agent process."""
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("ACP process must expose stdin/stdout pipes")

    conn = acp.connect_to_agent(client, process.stdin, process.stdout)
    resolved_backend = backend_name or _infer_backend_name_from_process(process)
    timeout_s = _acp_startup_timeout_seconds(resolved_backend)
    try:
        try:
            await asyncio.wait_for(
                conn.initialize(protocol_version=acp.PROTOCOL_VERSION),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            early_exit = await _acp_process_exit_message(
                process,
                during="initialize",
                agent_backend=resolved_backend,
            )
            if early_exit is not None:
                raise RuntimeError(f"{resolved_backend} {early_exit}") from exc
            timeout_message = (
                f"{resolved_backend} initialization timed out after {timeout_s:.0f}s "
                "during ACP initialize. "
                f"{ACP_TIMEOUT_HINT}"
            )
            raise RuntimeError(timeout_message) from exc
        mcp_server = await asyncio.to_thread(_build_mcp_server_from_manifest, mcp_manifest)
        try:
            session = await asyncio.wait_for(
                conn.new_session(cwd=str(worktree_path), mcp_servers=[mcp_server]),
                timeout=timeout_s,
            )
        except TimeoutError as exc:
            early_exit = await _acp_process_exit_message(
                process,
                during="session creation",
                agent_backend=resolved_backend,
            )
            if early_exit is not None:
                raise RuntimeError(f"{resolved_backend} {early_exit}") from exc
            timeout_message = (
                f"{resolved_backend} initialization timed out after {timeout_s:.0f}s "
                "during ACP session creation. "
                f"{ACP_TIMEOUT_HINT}"
            )
            raise RuntimeError(timeout_message) from exc
        await conn.prompt(session_id=session.session_id, prompt=[acp.text_block(prompt)])
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        logger.info(
            "ACP one-shot prompt completed for pid={} rc={}", process.pid, process.returncode
        )
    except (RequestError, OSError, RuntimeError, ValueError, AttributeError) as exc:
        logger.exception("ACP session failed for pid={} cwd={}", process.pid, worktree_path)
        if process.returncode is None:
            process.terminate()
            with contextlib.suppress(ProcessLookupError):
                await process.wait()
        raise RuntimeError(
            friendly_acp_error_message(
                error=exc,
                agent_backend=resolved_backend,
                during="ACP startup",
            )
        ) from exc
    finally:
        with contextlib.suppress(RequestError, OSError, RuntimeError):
            await conn.close()
