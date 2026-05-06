"""ACP client helpers and orchestrator turn execution."""

import asyncio
import contextlib
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import acp
from acp.schema import (
    AgentMessageChunk,
    AllowedOutcome,
    ClientCapabilities,
    DeniedOutcome,
    Implementation,
    McpServerStdio,
    RequestPermissionResponse,
)
from loguru import logger

from kagan.cli.chat.prompt import (
    _format_user_request_block,
)
from kagan.core import (
    ACP_TIMEOUT_HINT,
    BackendCapability,
    KaganACPClient,
    acp_handshake_timeout_seconds,
    acp_process_exit_hint,
    build_agent_environment,
    build_mcp_manifest,
    default_db_path,
    friendly_acp_error_message,
    get_backend_spec,
    resolve_orchestrator_prompt,
    resolve_spawn_command,
    spawn_filtered_agent_process,
)
from kagan.core.errors import AgentError

_ACP_CLIENT_NAME = "kagan"
_ACP_CLIENT_TITLE = "Kagan"
_ACP_CLIENT_VERSION = "0.1.0"
_ACP_STDIO_BUFFER_LIMIT_BYTES = 50 * 1024 * 1024


@dataclass
class OrchestratorWarmupState:
    warmed_backends: set[str] = field(default_factory=set)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def get_lock(self, backend: str) -> asyncio.Lock:
        if backend not in self.locks:
            self.locks[backend] = asyncio.Lock()
        return self.locks[backend]


_WARMUP_STATE = OrchestratorWarmupState()


_acp_handshake_timeout_seconds = acp_handshake_timeout_seconds
_friendly_acp_error_message = friendly_acp_error_message


def _is_mcp_server_unsupported_error(error: object) -> bool:
    raw = str(error).lower()
    return "mcp" in raw and "server" in raw and ("not implemented" in raw or "unsupported" in raw)


async def _new_session_with_mcp_fallback(
    conn: Any,
    *,
    cwd: str,
    mcp_servers: list[Any],
    timeout_s: float,
    agent_backend: str,
) -> Any:
    try:
        return await asyncio.wait_for(
            conn.new_session(cwd=cwd, mcp_servers=mcp_servers),
            timeout=timeout_s,
        )
    except acp.RequestError as exc:
        if not mcp_servers or not _is_mcp_server_unsupported_error(exc):
            raise
        logger.warning(
            "{} rejected ACP MCP server registration; retrying chat session without "
            "registered MCP tools",
            agent_backend,
        )
        return await asyncio.wait_for(
            conn.new_session(cwd=cwd, mcp_servers=[]),
            timeout=timeout_s,
        )


class _CaptureACPClient(KaganACPClient):
    def __init__(
        self,
        *,
        on_update: Callable[[Any], Awaitable[None] | None] | None = None,
        permission_resolver: Callable[[Any], Awaitable[Any]] | None = None,
    ) -> None:
        super().__init__(lambda _session_id, _update: None)
        self.text_chunks: list[str] = []
        self._on_update = on_update
        self._permission_resolver = permission_resolver

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        del session_id, kwargs
        if isinstance(update, AgentMessageChunk):
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    self.text_chunks.append(text)
        on_update = self.__dict__.get("_on_update")
        if on_update is None:
            return
        try:
            maybe_awaitable = on_update(update)
            if isinstance(maybe_awaitable, Awaitable):
                await maybe_awaitable
        except (RuntimeError, ValueError, TypeError):
            logger.exception("Orchestrator turn update callback failed")

    async def request_permission(self, options: Any, session_id: str, tool_call: Any, **_kw: Any):
        del session_id
        # Engine-driven seam: when a resolver is wired, hand the request off
        # to it and translate its decision back into an ACP outcome.
        if self._permission_resolver is not None:
            from kagan.core.chat.acp import PermissionDecision, PermissionRequestPayload

            payload = PermissionRequestPayload(
                tool_call=_tool_call_to_dict(tool_call),
                options=[_permission_option_to_dict(opt) for opt in (options or ())],
            )
            try:
                decision = await self._permission_resolver(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("permission_resolver raised; falling back to deny")
                return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
            if isinstance(decision, PermissionDecision) and decision.outcome in {
                "allow_once",
                "allow_always",
            }:
                wanted = decision.outcome
                for option in options or ():
                    if option.kind == wanted:
                        return RequestPermissionResponse(
                            outcome=AllowedOutcome(outcome="selected", option_id=option.option_id)
                        )
                # No exact-match option; pick any allow_* option as fallback.
                for option in options or ():
                    if option.kind in {"allow_once", "allow_always"}:
                        return RequestPermissionResponse(
                            outcome=AllowedOutcome(outcome="selected", option_id=option.option_id)
                        )
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

        # Legacy auto-deny fallback: matches today's server behaviour when no
        # resolver is wired.
        del tool_call
        for option in options:
            if option.kind in {"allow_always", "allow_once"}:
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome="selected", option_id=option.option_id)
                )
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))


def _tool_call_to_dict(tool_call: Any) -> dict[str, Any]:
    """Reduce an ACP tool-call object to a JSON-serialisable dict."""
    if tool_call is None:
        return {}
    if isinstance(tool_call, dict):
        return dict(tool_call)
    dump = getattr(tool_call, "model_dump", None)
    if callable(dump):
        try:
            return dict(dump())
        except (TypeError, ValueError):
            pass
    out: dict[str, Any] = {}
    for attr in ("tool_call_id", "title", "name", "kind", "raw_input", "rawInput"):
        value = getattr(tool_call, attr, None)
        if value is not None:
            out[attr] = value
    return out


def _permission_option_to_dict(option: Any) -> dict[str, Any]:
    """Reduce an ACP ``PermissionOption`` to a JSON-serialisable dict."""
    if option is None:
        return {}
    if isinstance(option, dict):
        return dict(option)
    dump = getattr(option, "model_dump", None)
    if callable(dump):
        try:
            return dict(dump())
        except (TypeError, ValueError):
            pass
    out: dict[str, Any] = {}
    for attr in ("option_id", "name", "kind"):
        value = getattr(option, attr, None)
        if value is not None:
            out[attr] = value
    return out


def _resolve_acp_command_for_backend(agent_backend: str) -> tuple[str, list[str]]:
    spec = get_backend_spec(agent_backend)
    if not spec.has_capability(BackendCapability.ACP_STREAMING):
        raise RuntimeError(
            f"Agent backend {agent_backend!r} does not support ACP. "
            "Set a different orchestrator agent or use an ACP-capable backend."
        )

    acp_cmd = list(spec.acp_command) or ([spec.executable] if spec.executable else [])
    if not acp_cmd:
        raise RuntimeError(f"No ACP command configured for backend {agent_backend!r}")

    exe = acp_cmd[0]
    if shutil.which(exe) is None:
        hint = ""
        if exe == "npx":
            hint = " Install Node.js first: https://nodejs.org/"
        raise RuntimeError(f"ACP executable {exe!r} not found on PATH.{hint}")

    return exe, acp_cmd[1:]


async def _acp_process_exit_message(agent_backend: str, process: Any, *, during: str) -> str | None:
    return_code = getattr(process, "returncode", None)
    if not isinstance(return_code, int):
        return None
    details = ""
    stderr = getattr(process, "stderr", None)
    if stderr is not None:
        with contextlib.suppress(OSError, RuntimeError, ValueError, TimeoutError):
            raw = await asyncio.wait_for(stderr.read(4096), timeout=0.2)
            if raw:
                details = raw.decode("utf-8", "replace").strip()
    message = f"{agent_backend} process exited before ACP {during} (exit code {return_code})."
    if details:
        compact = " ".join(line.strip() for line in details.splitlines() if line.strip())
        message = f"{message} {compact[:500]}"
        hint = acp_process_exit_hint(agent_backend=agent_backend, details=details)
        if hint:
            message = f"{message} {hint}"
    return message


async def run_orchestrator_turn(
    client: Any,
    *,
    prompt: str,
    agent_backend: str,
    mcp_session_id: str | None = None,
    on_update: Callable[[Any], Awaitable[None] | None] | None = None,
    send_prompt: bool = True,
    attachments: list[dict[str, str]] | None = None,
    cwd: Path | None = None,
    lightweight: bool = False,
    permission_resolver: Callable[[Any], Awaitable[Any]] | None = None,
) -> str:
    """Run a single orchestrator turn via ACP.

    When *lightweight* is True the turn is stripped down for simple completions
    (e.g. title generation): no MCP tools, no orchestrator system prompt, and
    the prompt is sent as-is without the "User request:" wrapper.
    """
    if send_prompt and not prompt.strip():
        return ""

    exe, exe_args = _resolve_acp_command_for_backend(agent_backend)
    resolved_cmd = resolve_spawn_command(exe, *exe_args)
    session_id = mcp_session_id or uuid4().hex[:16]
    db_path = str(default_db_path())
    resolved_cwd = cwd or Path.cwd()
    mcp_path = resolved_cwd / ".mcp.json"

    if not lightweight:
        mcp_content = build_mcp_manifest(
            session_id=session_id,
            db_path=db_path,
            role="ORCHESTRATOR",
            project_id=client.active_project_id,
        )
        await asyncio.to_thread(mcp_path.write_text, mcp_content, "utf-8")

    backend = get_backend_spec(agent_backend)
    env = build_agent_environment(
        session_id=session_id,
        task_id=None,
        backend_env_vars=backend.env_vars,
    )

    capture_client = _CaptureACPClient(on_update=on_update, permission_resolver=permission_resolver)
    timeout_s = _acp_handshake_timeout_seconds(agent_backend)
    try:
        async with spawn_filtered_agent_process(
            capture_client,
            resolved_cmd[0],
            *resolved_cmd[1:],
            backend_name=agent_backend,
            cwd=str(resolved_cwd),
            env=env,
            transport_kwargs={"limit": _ACP_STDIO_BUFFER_LIMIT_BYTES},
        ) as (conn, proc):
            client_caps = ClientCapabilities(terminal=False)
            try:
                await asyncio.wait_for(
                    conn.initialize(
                        protocol_version=acp.PROTOCOL_VERSION,
                        client_capabilities=client_caps,
                        client_info=Implementation(
                            name=_ACP_CLIENT_NAME,
                            title=_ACP_CLIENT_TITLE,
                            version=_ACP_CLIENT_VERSION,
                        ),
                    ),
                    timeout=timeout_s,
                )
            except TimeoutError as exc:
                early_exit = await _acp_process_exit_message(
                    agent_backend,
                    proc,
                    during="initialize",
                )
                if early_exit is not None:
                    raise AgentError(early_exit) from exc
                timeout_message = (
                    f"{agent_backend} initialization timed out after {timeout_s:.0f}s "
                    "during ACP initialize. "
                    f"{ACP_TIMEOUT_HINT}"
                )
                raise AgentError(timeout_message) from exc

            # Lightweight mode: no MCP tools — just a bare session
            if lightweight:
                mcp_servers: list[Any] = []
            else:
                mcp_servers = [
                    McpServerStdio(
                        name="kagan",
                        command="kagan",
                        args=[
                            "mcp",
                            "--session-id",
                            session_id,
                            "--db",
                            db_path,
                            "--admin",
                            *(
                                [
                                    "--project-id",
                                    client.active_project_id,
                                ]
                                if client.active_project_id
                                else []
                            ),
                        ],
                        env=[],
                    )
                ]

            try:
                sess = await _new_session_with_mcp_fallback(
                    conn,
                    cwd=str(resolved_cwd),
                    mcp_servers=mcp_servers,
                    timeout_s=timeout_s,
                    agent_backend=agent_backend,
                )
            except TimeoutError as exc:
                early_exit = await _acp_process_exit_message(
                    agent_backend,
                    proc,
                    during="session creation",
                )
                if early_exit is not None:
                    raise AgentError(early_exit) from exc
                timeout_message = (
                    f"{agent_backend} initialization timed out after {timeout_s:.0f}s "
                    "during ACP session creation. "
                    f"{ACP_TIMEOUT_HINT}"
                )
                raise AgentError(timeout_message) from exc

            if send_prompt:
                if lightweight:
                    # Lightweight: send the prompt directly — no orchestrator
                    # system prompt, no "User request:" wrapper.
                    prompt_blocks: list[Any] = [acp.text_block(prompt)]
                else:
                    settings = await client.settings.get()
                    system_prompt = resolve_orchestrator_prompt(settings, resolved_cwd)
                    prompt_blocks = [
                        acp.text_block(system_prompt),
                        acp.text_block(_format_user_request_block(prompt)),
                    ]
                    for att in attachments or []:
                        if att.get("type") == "image":
                            prompt_blocks.append(
                                acp.image_block(data=att["data"], mime_type=att["mime_type"]),
                            )
                        else:
                            prompt_blocks.append(
                                acp.text_block(f"--- {att['name']} ---\n{att['data']}"),
                            )
                try:
                    await conn.prompt(session_id=sess.session_id, prompt=prompt_blocks)
                except (acp.RequestError, OSError, RuntimeError, ValueError, AttributeError) as exc:
                    raise AgentError(
                        _friendly_acp_error_message(
                            error=exc,
                            agent_backend=agent_backend,
                            during="prompt delivery",
                        )
                    ) from exc
    except (acp.RequestError, OSError, RuntimeError, ValueError, AttributeError) as exc:
        raise AgentError(
            _friendly_acp_error_message(error=exc, agent_backend=agent_backend, during="handshake")
        ) from exc
    finally:
        if not lightweight and mcp_path.exists():
            with contextlib.suppress(OSError):
                mcp_path.unlink()

    return "".join(capture_client.text_chunks).strip()


def _orchestrator_warmup_lock(agent_backend: str) -> asyncio.Lock:
    return _WARMUP_STATE.get_lock(agent_backend)


async def warm_orchestrator_backend(client: Any, *, agent_backend: str) -> None:
    normalized_backend = agent_backend.strip()
    if not normalized_backend:
        return
    if normalized_backend in _WARMUP_STATE.warmed_backends:
        return

    async with _orchestrator_warmup_lock(normalized_backend):
        if normalized_backend in _WARMUP_STATE.warmed_backends:
            return
        logger.debug("Warming orchestrator backend {}", normalized_backend)
        await run_orchestrator_turn(
            client,
            prompt="",
            agent_backend=normalized_backend,
            send_prompt=False,
        )
        _WARMUP_STATE.warmed_backends.add(normalized_backend)
        logger.debug("Orchestrator backend {} warmed", normalized_backend)
