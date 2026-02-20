"""FastMCP server setup for Kagan.

Uses MCP SDK best practices:
- Lifespan for resource management (IPCClient, SDK transport)
- Context injection for built-in logging
- Pydantic models for structured responses
- Progress reporting for long operations
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from kagan.core.config import KaganConfig
from kagan.core.constants import (
    MCP_DEFAULT_FULL_CAPABILITY,
    MCP_DEFAULT_READONLY_CAPABILITY,
    MCP_DEFAULT_SESSION_ID,
    MCP_FALLBACK_CAPABILITY,
    MCP_IDENTITY_ADMIN,
    MCP_IDENTITY_DEFAULT,
)
from kagan.core.ipc.client import IPCClient
from kagan.core.ipc.discovery import CoreEndpoint, discover_core_endpoint
from kagan.core.mcp_naming import get_mcp_server_name
from kagan.core.paths import get_config_path, get_core_token_path, get_database_path
from kagan.core.policy import (
    CAPABILITY_PROFILES,
    CapabilityProfile,
    ProtocolCapability,
    ProtocolMethod,
    protocol_call,
)
from kagan.core.services.runtime import ensure_core_running
from kagan.mcp._response_models import *  # noqa: F403  # Import all response models for FastMCP type inspection
from kagan.mcp._tool_closures import _register_full_mode_tools
from kagan.mcp._tool_gen import SharedToolRegistrationContext, register_shared_tools
from kagan.sdk import KaganSDK, SDKTransport
from kagan.version import get_kagan_runtime_hash, get_kagan_version

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from mcp.types import ToolAnnotations

    from kagan.mcp._response_models import TaskRuntimeState


logger = logging.getLogger(__name__)

NO_SESSION_MESSAGE = (
    "No active Kagan session. "
    "This MCP server is registered globally but Kagan is not managing the current directory. "
    "Run 'kagan' to start a session, or use this tool from a Kagan-managed project."
)


@dataclass(frozen=True, slots=True)
class MCPStartupError(RuntimeError):
    """Structured startup error for deterministic core-availability failures."""

    code: str
    message: str
    hint: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} Hint: {self.hint}"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


@dataclass(frozen=True, slots=True)
class MCPRuntimeConfig:
    """Runtime configuration for endpoint/session overrides in MCP server process."""

    endpoint: str | None = None
    session_id: str | None = None
    capability_profile: str | None = None
    identity: str | None = None
    enable_internal_instrumentation: bool = False


@dataclass
class MCPLifespanContext:
    """Context during MCP lifetime: IPC client and SDK. Fails fast when core unavailable."""

    client: IPCClient
    sdk: KaganSDK


MCPContext = Context[ServerSession, MCPLifespanContext]

_IDENTITY_PROFILE_CEILING: dict[str, CapabilityProfile] = {
    MCP_IDENTITY_DEFAULT: CapabilityProfile.PAIR_WORKER,
    MCP_IDENTITY_ADMIN: CapabilityProfile.MAINTAINER,
}
_PROFILE_RANK: dict[CapabilityProfile, int] = {
    CapabilityProfile.VIEWER: 0,
    CapabilityProfile.PLANNER: 1,
    CapabilityProfile.PAIR_WORKER: 2,
    CapabilityProfile.OPERATOR: 3,
    CapabilityProfile.MAINTAINER: 4,
}


def _runtime_config_or_default(runtime_config: MCPRuntimeConfig | None) -> MCPRuntimeConfig:
    """Normalize optional runtime config to a concrete value object."""
    return runtime_config if runtime_config is not None else MCPRuntimeConfig()


def _resolve_endpoint(runtime_config: MCPRuntimeConfig | None = None) -> CoreEndpoint | None:
    """Resolve the core endpoint from override or discovery."""
    config = _runtime_config_or_default(runtime_config)
    discovered = discover_core_endpoint()
    if not config.endpoint:
        return discovered

    raw = config.endpoint.strip()

    if raw.startswith("tcp://"):
        host_port = raw.removeprefix("tcp://")
        host, sep, port_raw = host_port.rpartition(":")
        if sep and port_raw.isdigit():
            return CoreEndpoint(
                transport="tcp",
                address=host,
                port=int(port_raw),
                token=_read_local_core_token(discovered),
            )
        return CoreEndpoint(
            transport="tcp",
            address=host_port,
            port=None,
            token=_read_local_core_token(discovered),
        )
    if raw.startswith("socket://"):
        return CoreEndpoint(
            transport="socket",
            address=raw.removeprefix("socket://"),
            token=_read_local_core_token(discovered),
        )

    if raw.startswith("pipe://") or raw.startswith("\\\\.\\pipe\\"):
        return None
    if raw.startswith("/") or raw.endswith(".sock"):
        return CoreEndpoint(
            transport="socket",
            address=raw,
            token=_read_local_core_token(discovered),
        )

    host, sep, port_raw = raw.rpartition(":")
    if sep and port_raw.isdigit():
        return CoreEndpoint(
            transport="tcp",
            address=host,
            port=int(port_raw),
            token=_read_local_core_token(discovered),
        )
    return CoreEndpoint(
        transport="socket",
        address=raw,
        token=_read_local_core_token(discovered),
    )


def _read_local_core_token(discovered: CoreEndpoint | None) -> str | None:
    """Read token from discovered endpoint or local runtime file."""
    if discovered is not None and discovered.token:
        return discovered.token
    with suppress(OSError):
        token = get_core_token_path().read_text(encoding="utf-8").strip()
        if token:
            return token
    return None


def _is_core_autostart_enabled() -> bool:
    """Return whether MCP should auto-start core when no endpoint is available."""
    try:
        config = KaganConfig.load(get_config_path())
    except Exception:
        return True
    return config.general.core_autostart


async def _resolve_or_autostart_endpoint(
    runtime_config: MCPRuntimeConfig | None = None,
) -> CoreEndpoint | None:
    """Resolve endpoint, auto-starting core when discovery fails and autostart is enabled."""
    config = _runtime_config_or_default(runtime_config)
    endpoint = _resolve_endpoint(config)
    if endpoint is not None:
        return endpoint
    if config.endpoint:
        return None
    if not _is_core_autostart_enabled():
        return None
    try:
        return await ensure_core_running(
            config_path=get_config_path(),
            db_path=get_database_path(),
        )
    except Exception:
        logger.warning("Failed to auto-start core endpoint", exc_info=True)
        return None


def _endpoint_description(endpoint: CoreEndpoint) -> str:
    if endpoint.transport == "tcp" and endpoint.port is not None:
        return f"tcp://{endpoint.address}:{endpoint.port}"
    return f"{endpoint.transport}://{endpoint.address}"


@asynccontextmanager
async def _mcp_lifespan(
    mcp: FastMCP,
    runtime_config: MCPRuntimeConfig | None = None,
) -> AsyncIterator[MCPLifespanContext]:
    """Lifespan: discover endpoint, connect IPC, create SDK. Fails fast when core unavailable."""
    config = _runtime_config_or_default(runtime_config)
    # Resolve through module globals so test monkeypatches take effect
    g = globals()
    resolve_fn = g.get("_resolve_or_autostart_endpoint", _resolve_or_autostart_endpoint)
    ipc_client_cls = g.get("IPCClient", IPCClient)
    endpoint = await resolve_fn(config)

    if endpoint is None:
        if config.endpoint:
            raise MCPStartupError(
                code="NO_ENDPOINT",
                message=f"Configured core endpoint override is unavailable: {config.endpoint!r}.",
                hint=(
                    "Provide a reachable tcp://host:port or socket://path endpoint, or "
                    "remove --endpoint and run `kagan core start`."
                ),
            )
        raise MCPStartupError(
            code="NO_ENDPOINT",
            message="No active Kagan core endpoint was discovered.",
            hint="Start Kagan or run `kagan core start`, then reconnect MCP.",
        )

    session_id = config.session_id or MCP_DEFAULT_SESSION_ID
    capability_profile = config.capability_profile or MCP_FALLBACK_CAPABILITY
    session_origin = config.identity or MCP_IDENTITY_DEFAULT
    client = ipc_client_cls(endpoint)

    try:
        await client.connect()
    except Exception as exc:
        logger.warning(
            "Failed to connect to core at %s",
            _endpoint_description(endpoint),
            exc_info=True,
        )
        raise MCPStartupError(
            code="DISCONNECTED",
            message=(f"Kagan core is unreachable at {_endpoint_description(endpoint)}: {exc}"),
            hint="Ensure core is running and reachable, then reconnect MCP.",
        ) from exc

    sdk = KaganSDK(
        transport=SDKTransport(
            endpoint=endpoint,
            client=client,
            session_id=session_id,
            session_origin=session_origin,
            client_version=get_kagan_version(),
            client_build_hash=get_kagan_runtime_hash(),
            capability_profile=capability_profile,
        ),
    )
    try:
        yield MCPLifespanContext(client=client, sdk=sdk)
    finally:
        await client.close()


def _get_transport(ctx: MCPContext) -> SDKTransport | None:
    """Extract SDKTransport from request context."""
    lifespan_ctx = ctx.request_context.lifespan_context
    if not isinstance(lifespan_ctx, MCPLifespanContext):
        return None
    return lifespan_ctx.sdk._transport


def _require_transport(ctx: MCPContext | None) -> SDKTransport:
    """Return an active transport or raise a user-facing no-session error."""
    if ctx is None:
        raise ValueError(f"[NO_CONTEXT] {NO_SESSION_MESSAGE}")
    transport = _get_transport(ctx)
    if transport is None:
        raise ValueError(f"[NO_SESSION] {NO_SESSION_MESSAGE}")
    return transport


def _build_server_instructions(readonly: bool) -> str:
    """Build MCP server instructions tailored to readonly vs full mode."""
    base = [
        "Kagan is a Kanban-style task management system for AI-assisted development.",
        "",
        "The task_id is provided in your system prompt when Kagan assigns you work.",
        "Use task_get to inspect any task (with include_logs=true for execution history).",
        "If task_get logs are truncated or logs_has_more=true, use task_logs.",
        "Use task_list to coordinate with other agents.",
        "Important: status is Kanban column, task_type is execution mode (AUTO/PAIR).",
        "Use job_start to spawn agents. job_poll(wait=true) tracks spawn state.",
        "Use task_wait to long-poll for agent completion (wait_for_status).",
        "If a tool returns next_tool/next_arguments, use them for deterministic recovery.",
    ]
    if readonly:
        base.extend(
            [
                "",
                "You are running in READ-ONLY mode.",
                "Available tools are capability-scoped read-only/planning tools.",
            ]
        )
    else:
        base.extend(
            [
                "",
                "When assigned a task, follow this workflow:",
                "1. Call task_get(mode='context') with your task_id for full bounded context",
                "2. Use task_patch(append_note=...) to record progress and blockers",
                "3. For automation runs: set task_type='AUTO' using task_patch.",
                "4. Call job_start to submit work.",
                "5. Use job_poll(wait=true) to confirm the spawn succeeded (short timeout).",
                "6. Use task_wait(task_id, wait_for_status=['REVIEW','DONE'])",
                "   to long-poll until the agent completes (default 1800s, max 3600s).",
                "7. Use job_cancel only to stop in-flight work.",
                "8. Call task_patch(transition='request_review') when implementation is complete",
                "9. Use review_apply(action='merge') (or no-change close flow) to complete task.",
                "   review_apply(action='approve') records approval but does not set DONE.",
            ]
        )
    return "\n".join(base)


def _runtime_state_from_raw(raw: dict[str, Any] | None) -> TaskRuntimeState | None:
    """Build TaskRuntimeState from raw response payload when present."""
    from kagan.mcp._response_models import TaskRuntimeState

    if raw is None or not isinstance(raw, dict):
        return None
    return TaskRuntimeState(
        is_running=bool(raw.get("is_running", False)),
        is_reviewing=bool(raw.get("is_reviewing", False)),
        is_blocked=bool(raw.get("is_blocked", False)),
        blocked_reason=raw.get("blocked_reason"),
        blocked_by_task_ids=[str(task_id) for task_id in raw.get("blocked_by_task_ids", [])],
        overlap_hints=[str(hint) for hint in raw.get("overlap_hints", [])],
        blocked_at=raw.get("blocked_at"),
        is_pending=bool(raw.get("is_pending", False)),
        pending_reason=raw.get("pending_reason"),
        pending_at=raw.get("pending_at"),
    )


def _resolve_effective_profile(
    default_profile: CapabilityProfile,
    default_identity: str,
    runtime_config: MCPRuntimeConfig | None = None,
) -> str:
    """Resolve effective capability profile after identity ceiling."""
    config = _runtime_config_or_default(runtime_config)
    raw_profile = (config.capability_profile or str(default_profile)).strip().lower()
    raw_identity = (config.identity or default_identity).strip().lower()
    try:
        requested = CapabilityProfile(raw_profile)
    except ValueError:
        requested = CapabilityProfile.VIEWER
    ceiling = _IDENTITY_PROFILE_CEILING.get(raw_identity, CapabilityProfile.PAIR_WORKER)
    effective = requested if _PROFILE_RANK[requested] <= _PROFILE_RANK[ceiling] else ceiling
    return str(effective)


def _is_allowed(
    profile: str,
    capability: ProtocolCapability | str,
    method: ProtocolMethod | str,
) -> bool:
    """Return whether profile may call capability.method."""
    if profile == str(CapabilityProfile.MAINTAINER):
        return True
    try:
        normalized_profile = CapabilityProfile(profile)
    except ValueError:
        return False
    return protocol_call(capability, method) in CAPABILITY_PROFILES.get(
        normalized_profile, frozenset()
    )


def _resolve_module_functions() -> tuple[
    Callable[..., Any], Callable[..., bool], Callable[..., Any], Callable[..., Any]
]:
    """Resolve transport, is_allowed, runtime_state, plugin_registry from globals."""
    g = globals()
    return (
        g.get("_require_transport", _require_transport),
        g.get("_is_allowed", _is_allowed),
        g.get("_runtime_state_from_raw", _runtime_state_from_raw),
        g.get("_build_plugin_registry", _build_plugin_registry),
    )


def _create_mcp_server(
    readonly: bool = False,
    runtime_config: MCPRuntimeConfig | None = None,
) -> FastMCP:
    """Create FastMCP instance with lifespan and tools."""
    config = _runtime_config_or_default(runtime_config)
    default_profile = CapabilityProfile.PLANNER if readonly else CapabilityProfile.MAINTAINER
    default_identity = MCP_IDENTITY_DEFAULT if readonly else MCP_IDENTITY_ADMIN

    # Resolve current bindings so monkeypatches on kagan.mcp.server take effect
    resolved_require_transport, resolved_is_allowed, resolved_rsf, resolved_bpr = (
        _resolve_module_functions()
    )

    effective_profile = _resolve_effective_profile(
        default_profile,
        default_identity,
        runtime_config=config,
    )

    def allows_all(*pairs: tuple[str, str]) -> bool:
        return all(
            resolved_is_allowed(effective_profile, capability, method)
            for capability, method in pairs
        )

    @asynccontextmanager
    async def lifespan(mcp_instance: FastMCP) -> AsyncIterator[MCPLifespanContext]:
        async with _mcp_lifespan(mcp_instance, config) as lifespan_ctx:
            yield lifespan_ctx

    mcp = FastMCP(
        get_mcp_server_name(),
        instructions=_build_server_instructions(readonly),
        lifespan=lifespan,
    )

    _register_shared_tools(
        mcp,
        allows_all=allows_all,
        effective_profile=effective_profile,
        require_transport_fn=resolved_require_transport,
        runtime_state_fn=resolved_rsf,
    )

    if not readonly:
        _register_full_mode_tools(
            mcp,
            allows_all=allows_all,
            effective_profile=effective_profile,
            enable_internal_instrumentation=config.enable_internal_instrumentation,
            require_transport_fn=resolved_require_transport,
            runtime_state_fn=resolved_rsf,
            build_plugin_registry_fn=resolved_bpr,
        )

    return mcp


def _register_shared_tools(
    mcp: FastMCP,
    *,
    allows_all: Callable[..., bool],
    effective_profile: str,
    require_transport_fn: Callable[..., Any] | None = None,
    runtime_state_fn: Callable[..., Any] | None = None,
) -> None:
    """Register planner/read-only/shared MCP tools."""
    register_shared_tools(
        mcp,
        allows_all=allows_all,
        effective_profile=effective_profile,
        helpers=SharedToolRegistrationContext(
            require_transport=require_transport_fn or _require_transport,
            runtime_state_from_raw=runtime_state_fn or _runtime_state_from_raw,
        ),
    )


def _build_plugin_registry() -> Any:
    """Build a PluginRegistry with plugins discovered from config."""
    from kagan.core.plugins.sdk import PluginRegistry

    config = KaganConfig.load(get_config_path())
    registry = PluginRegistry()
    registry.discover_and_register(config.plugins.discovery)
    return registry


def list_registered_tool_names(mcp: FastMCP) -> set[str]:
    """Return registered MCP tool names for contract tests and diagnostics."""
    return {tool.name for tool in mcp._tool_manager.list_tools()}


def get_registered_tool_annotations(mcp: FastMCP) -> dict[str, ToolAnnotations | None]:
    """Return tool annotation metadata keyed by tool name."""
    return {tool.name: tool.annotations for tool in mcp._tool_manager.list_tools()}


def main(
    readonly: bool = False,
    endpoint: str | None = None,
    session_id: str | None = None,
    capability: str | None = None,
    identity: str | None = None,
    enable_internal_instrumentation: bool = False,
) -> None:
    """Entry point for kagan-mcp command."""
    runtime_config = MCPRuntimeConfig(
        endpoint=endpoint,
        session_id=session_id,
        capability_profile=capability
        or (MCP_DEFAULT_READONLY_CAPABILITY if readonly else MCP_DEFAULT_FULL_CAPABILITY),
        identity=identity or (MCP_IDENTITY_DEFAULT if readonly else MCP_IDENTITY_ADMIN),
        enable_internal_instrumentation=enable_internal_instrumentation,
    )
    mcp = _create_mcp_server(readonly=readonly, runtime_config=runtime_config)
    try:
        mcp.run(transport="stdio")
    except MCPStartupError as exc:
        raise SystemExit(str(exc)) from exc


__all__ = [
    "MCPContext",
    "MCPLifespanContext",
    "MCPRuntimeConfig",
    "MCPStartupError",
    "get_registered_tool_annotations",
    "list_registered_tool_names",
    "main",
]
