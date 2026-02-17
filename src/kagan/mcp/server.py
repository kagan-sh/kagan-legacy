"""FastMCP server setup for Kagan.

Uses MCP SDK best practices:
- Lifespan for resource management (IPCClient, CoreClientBridge)
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
from mcp.types import ToolAnnotations

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
from kagan.mcp._tool_gen import (
    SharedToolRegistrationContext,
)
from kagan.mcp.tools import CoreClientBridge
from kagan.sdk import KaganSDK, SDKTransport
from kagan.version import get_kagan_version

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

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
    """Context available during MCP server lifetime via lifespan.

    Startup fails fast when core is unavailable, so context always has an
    active IPC client, bridge, and SDK.
    """

    bridge: CoreClientBridge
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
    """Lifespan manager for MCP server resources.

    Discovers the core endpoint (or uses the CLI override), connects an
    IPCClient, and wraps it in a CoreClientBridge.

    Startup fails when core is unavailable so MCP cannot bypass core
    coordination with degraded behavior.
    """
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

    bridge = CoreClientBridge(
        client,
        session_id,
        capability_profile=capability_profile,
        session_origin=session_origin,
        client_version=get_kagan_version(),
    )
    sdk = KaganSDK(
        transport=SDKTransport(
            endpoint=endpoint,
            session_id=session_id,
            session_origin=session_origin,
            client_version=get_kagan_version(),
            capability_profile=capability_profile,
        ),
    )
    try:
        yield MCPLifespanContext(bridge=bridge, client=client, sdk=sdk)
    finally:
        await client.close()


def _get_bridge(ctx: MCPContext) -> CoreClientBridge | None:
    """Extract CoreClientBridge from request context."""
    lifespan_ctx = ctx.request_context.lifespan_context
    if lifespan_ctx is None:
        return None
    return lifespan_ctx.bridge


def _require_bridge(ctx: MCPContext | None) -> CoreClientBridge:
    """Return an active bridge or raise a user-facing no-session error."""
    if ctx is None:
        raise ValueError(f"[NO_CONTEXT] {NO_SESSION_MESSAGE}")
    bridge = _get_bridge(ctx)
    if bridge is None:
        raise ValueError(f"[NO_SESSION] {NO_SESSION_MESSAGE}")
    return bridge


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
    """Resolve current bindings of _require_bridge, _is_allowed, _runtime_state_from_raw,
    and _build_plugin_registry from this module's globals.

    Tests monkeypatch kagan.mcp.server._require_bridge etc. via monkeypatch.setattr,
    which updates the module dict. Reading via globals() picks up those patches
    so tool closures capture the patched versions during server creation.
    """
    g = globals()
    return (
        g.get("_require_bridge", _require_bridge),
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

    # Resolve current bindings so monkeypatches on kagan.mcp.runtime take effect
    resolved_require_bridge, resolved_is_allowed, resolved_rsf, resolved_bpr = (
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
        require_bridge_fn=resolved_require_bridge,
        runtime_state_fn=resolved_rsf,
    )

    if not readonly:
        _register_full_mode_tools(
            mcp,
            allows_all=allows_all,
            effective_profile=effective_profile,
            enable_internal_instrumentation=config.enable_internal_instrumentation,
            require_bridge_fn=resolved_require_bridge,
            runtime_state_fn=resolved_rsf,
            build_plugin_registry_fn=resolved_bpr,
        )

    return mcp


def _register_shared_tools(
    mcp: FastMCP,
    *,
    allows_all: Callable[..., bool],
    effective_profile: str,
    require_bridge_fn: Callable[..., Any] | None = None,
    runtime_state_fn: Callable[..., Any] | None = None,
) -> None:
    """Register planner/read-only/shared MCP tools."""
    from kagan.mcp._tool_gen import (
        register_shared_tools as _register,
    )

    _register(
        mcp,
        allows_all=allows_all,
        effective_profile=effective_profile,
        helpers=SharedToolRegistrationContext(
            require_bridge=require_bridge_fn or _require_bridge,
            runtime_state_from_raw=runtime_state_fn or _runtime_state_from_raw,
        ),
    )


def _register_plugin_tools(
    mcp: FastMCP,
    *,
    effective_profile: str,
    require_bridge_fn: Callable[..., Any] | None = None,
    build_plugin_registry_fn: Callable[..., Any] | None = None,
) -> None:
    """Register MCP tools contributed by plugins via McpToolSchema descriptors."""
    import inspect

    from kagan.mcp._response_models import PluginToolResponse

    _MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
    _READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

    _JSON_TYPE_TO_PYTHON: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    _get_bridge = require_bridge_fn or _require_bridge
    _get_registry = build_plugin_registry_fn or _build_plugin_registry
    registry = _get_registry()
    if registry is None:
        return

    _PROFILE_RANK: dict[str, int] = {
        str(CapabilityProfile.VIEWER): 0,
        str(CapabilityProfile.PLANNER): 1,
        str(CapabilityProfile.PAIR_WORKER): 2,
        str(CapabilityProfile.OPERATOR): 3,
        str(CapabilityProfile.MAINTAINER): 4,
    }
    caller_rank = _PROFILE_RANK.get(effective_profile, 0)

    for operation in registry.all_operations():
        schema = operation.mcp_tool_schema
        if schema is None:
            continue

        op_min_rank = _PROFILE_RANK.get(str(operation.minimum_profile), 4)
        if caller_rank < op_min_rank:
            continue

        tool_name = schema.tool_name
        annotation = _READ_ONLY if schema.annotations == "read_only" else _MUTATING
        cap = operation.capability
        method = operation.method
        plugin_id = operation.plugin_id

        def _make_handler(
            _cap: str, _method: str, _plugin_id: str, _params: dict[str, Any]
        ) -> Callable[..., Any]:
            async def handler(ctx: MCPContext | None = None, **kwargs: Any) -> PluginToolResponse:
                op = registry.resolve_operation(_cap, _method)
                if op is None:
                    return PluginToolResponse(
                        success=False,
                        plugin_id=_plugin_id,
                        capability=_cap,
                        method=_method,
                        code="PLUGIN_OPERATION_NOT_REGISTERED",
                        message=f"Plugin operation is not registered: {_cap}.{_method}",
                        hint=(
                            "Restart MCP to refresh plugin discovery, or install/enable "
                            "the plugin that provides this capability."
                        ),
                        data={},
                    )
                bridge = _get_bridge(ctx)
                raw = await bridge.invoke_plugin(op.capability, op.method, kwargs or None)
                return PluginToolResponse(
                    success=bool(raw.get("success", True)),
                    message=raw.get("message"),
                    code=raw.get("code"),
                    hint=raw.get("hint"),
                    next_tool=raw.get("next_tool"),
                    next_arguments=raw.get("next_arguments"),
                    plugin_id=raw.get("plugin_id", op.plugin_id),
                    capability=op.capability,
                    method=op.method,
                    data={k: v for k, v in raw.items() if k not in ("success", "message")},
                )

            sig_params: list[inspect.Parameter] = [
                inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None),
            ]
            for param_name, param_spec in _params.items():
                py_annotation = _JSON_TYPE_TO_PYTHON.get(param_spec.get("type", ""), str)
                if param_spec.get("required", False):
                    sig_params.append(
                        inspect.Parameter(
                            param_name,
                            inspect.Parameter.KEYWORD_ONLY,
                            annotation=py_annotation,
                        ),
                    )
                else:
                    sig_params.append(
                        inspect.Parameter(
                            param_name,
                            inspect.Parameter.KEYWORD_ONLY,
                            default=None,
                            annotation=py_annotation | None,
                        ),
                    )
            handler.__signature__ = inspect.Signature(  # type: ignore[attr-defined]  # noqa: B023
                sig_params, return_annotation=PluginToolResponse
            )
            return handler  # noqa: B023

        handler = _make_handler(cap, method, plugin_id, schema.parameters)
        handler.__name__ = tool_name
        handler.__qualname__ = tool_name
        handler.__doc__ = schema.description
        mcp.tool(annotations=annotation)(handler)


def _str_or_none(value: object) -> str | None:
    """Extract a string or return None."""
    return value if isinstance(value, str) else None


def _dict_or_none(value: object) -> dict[str, object] | None:
    """Extract a dict or return None."""
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else None


def _int_or_none(value: object) -> int | None:
    """Extract an int or return None."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


_TASK_TYPE_VALUES = frozenset({"AUTO", "PAIR"})
_DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS = 1.5
_JOB_NON_TERMINAL_STATUSES = frozenset({"queued", "running"})


def _normalized_mode(value: str | None) -> str | None:
    """Return 'AUTO' or 'PAIR' if value is a task_type, else None."""
    if value is None:
        return None
    upper = value.strip().upper()
    return upper if upper in _TASK_TYPE_VALUES else None


def _build_plugin_registry() -> Any:
    """Build a PluginRegistry with plugins discovered from config."""
    from kagan.core.plugins.sdk import PluginRegistry

    config = KaganConfig.load(get_config_path())
    registry = PluginRegistry()
    registry.discover_and_register(config.plugins.discovery)
    return registry


def _register_full_mode_tools(
    mcp: FastMCP,
    *,
    allows_all: Callable[..., bool],
    effective_profile: str,
    enable_internal_instrumentation: bool = False,
    require_bridge_fn: Callable[..., Any] | None = None,
    runtime_state_fn: Callable[..., Any] | None = None,
    build_plugin_registry_fn: Callable[..., Any] | None = None,
) -> None:
    """Register mutating/full-mode-only MCP tools."""
    from kagan.core.policy import (
        DiagnosticsMethod,
        JobsMethod,
        ProjectsMethod,
        ProtocolCapability,
        ReviewMethod,
        SessionsMethod,
        SettingsMethod,
        TasksMethod,
        protocol_call,
    )
    from kagan.mcp._response_models import (
        InstrumentationSnapshotResponse,
        JobActionInput,
        JobEvent,
        JobEventsResponse,
        JobResponse,
        RejectionActionInput,
        ReviewActionInput,
        ReviewActionResponse,
        SettingsGetResponse,
        SettingsUpdateResponse,
        TaskCreateResponse,
        TaskDeleteResponse,
    )

    _get_bridge = require_bridge_fn or _require_bridge
    _get_runtime_state = runtime_state_fn or _runtime_state_from_raw

    _READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    _MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
    _DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)

    _PROTOCOL = {
        "tasks_create": protocol_call(ProtocolCapability.TASKS, TasksMethod.CREATE),
        "tasks_update": protocol_call(ProtocolCapability.TASKS, TasksMethod.UPDATE),
        "tasks_move": protocol_call(ProtocolCapability.TASKS, TasksMethod.MOVE),
        "tasks_delete": protocol_call(ProtocolCapability.TASKS, TasksMethod.DELETE),
        "tasks_update_scratchpad": protocol_call(
            ProtocolCapability.TASKS, TasksMethod.UPDATE_SCRATCHPAD
        ),
        "projects_create": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.CREATE),
        "projects_open": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.OPEN),
        "jobs_submit": protocol_call(ProtocolCapability.JOBS, JobsMethod.SUBMIT),
        "jobs_get": protocol_call(ProtocolCapability.JOBS, JobsMethod.GET),
        "jobs_wait": protocol_call(ProtocolCapability.JOBS, JobsMethod.WAIT),
        "jobs_events": protocol_call(ProtocolCapability.JOBS, JobsMethod.EVENTS),
        "jobs_cancel": protocol_call(ProtocolCapability.JOBS, JobsMethod.CANCEL),
        "sessions_create": protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.CREATE),
        "sessions_exists": protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.EXISTS),
        "sessions_kill": protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.KILL),
        "review_request": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REQUEST),
        "review_approve": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.APPROVE),
        "review_reject": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REJECT),
        "review_merge": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.MERGE),
        "review_rebase": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REBASE),
        "settings_get": protocol_call(ProtocolCapability.SETTINGS, SettingsMethod.GET),
        "settings_update": protocol_call(ProtocolCapability.SETTINGS, SettingsMethod.UPDATE),
        "diagnostics_instrumentation": protocol_call(
            ProtocolCapability.DIAGNOSTICS, DiagnosticsMethod.INSTRUMENTATION
        ),
    }

    can_create = allows_all(_PROTOCOL["tasks_create"])
    can_patch_note = allows_all(_PROTOCOL["tasks_update_scratchpad"])
    can_patch_fields = allows_all(_PROTOCOL["tasks_update"])
    can_patch_status = allows_all(_PROTOCOL["tasks_move"])
    can_delete = allows_all(_PROTOCOL["tasks_delete"])
    can_request_review = allows_all(_PROTOCOL["review_request"])

    if can_create:
        from kagan.mcp._response_models import TaskTypeInput

        @mcp.tool(annotations=_MUTATING)
        async def task_create(
            title: str,
            description: str = "",
            project_id: str | None = None,
            status: str | None = None,
            priority: str | None = None,
            task_type: TaskTypeInput | None = None,
            terminal_backend: str | None = None,
            agent_backend: str | None = None,
            parent_id: str | None = None,
            base_branch: str | None = None,
            acceptance_criteria: list[str] | str | None = None,
            created_by: str | None = None,
            ctx: MCPContext | None = None,
        ) -> TaskCreateResponse:
            """Create a new task."""
            bridge = _get_bridge(ctx)
            raw = await bridge.create_task(
                title=title,
                description=description,
                project_id=project_id,
                status=status,
                priority=priority,
                task_type=task_type,
                terminal_backend=terminal_backend,
                agent_backend=agent_backend,
                parent_id=parent_id,
                base_branch=base_branch,
                acceptance_criteria=acceptance_criteria,
                created_by=created_by,
            )
            return TaskCreateResponse(
                success=bool(raw.get("success", True)),
                message=raw.get("message"),
                code=raw.get("code"),
                hint=raw.get("hint"),
                next_tool=raw.get("next_tool"),
                next_arguments=raw.get("next_arguments"),
                task_id=raw.get("task_id", ""),
                title=raw.get("title", title),
                status=raw.get("status", "backlog"),
            )

    if can_patch_note or can_patch_fields or can_patch_status or can_request_review:

        @mcp.tool(annotations=_MUTATING)
        async def task_patch(
            task_id: str,
            set: dict[str, object] | None = None,
            transition: str | None = None,
            append_note: str | None = None,
            ctx: MCPContext | None = None,
        ) -> dict[str, object]:
            """Apply partial task changes, transitions, and scratchpad notes."""
            bridge = _get_bridge(ctx)
            if set is not None and not isinstance(set, dict):
                return {
                    "success": False,
                    "task_id": task_id,
                    "message": "set must be an object map",
                    "code": "INVALID_SET",
                }

            fields = dict(set) if isinstance(set, dict) else {}

            if append_note is not None:
                if not can_patch_note:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "append_note is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                note_raw = await bridge.update_scratchpad(task_id, append_note)
                if not bool(note_raw.get("success", False)):
                    return {
                        "success": False,
                        "task_id": task_id,
                        "code": note_raw.get("code"),
                        "message": note_raw.get("message"),
                    }

            status_for_move = fields.pop("status", None)

            if transition == "set_status":
                if status_for_move is None:
                    status_for_move = fields.pop("new_status", None)
                if not isinstance(status_for_move, str) or not status_for_move.strip():
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "set_status requires set.status",
                        "code": "INVALID_TRANSITION",
                    }
                mode_value = _normalized_mode(status_for_move)
                if mode_value is not None:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": (
                            f"Invalid status value {status_for_move!r}. "
                            "AUTO/PAIR are task_type values, not status values."
                        ),
                        "code": "TASK_TYPE_VALUE_IN_STATUS",
                        "hint": "Use transition='set_task_type' with set.task_type.",
                        "next_tool": "task_patch",
                        "next_arguments": {
                            "task_id": task_id,
                            "transition": "set_task_type",
                            "set": {"task_type": mode_value},
                        },
                    }
                if not can_patch_status:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "set_status is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await bridge.move_task(task_id, status_for_move)
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            if transition == "set_task_type":
                task_type_value = fields.get("task_type")
                if not isinstance(task_type_value, str) or not task_type_value.strip():
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "set_task_type requires set.task_type",
                        "code": "INVALID_TRANSITION",
                    }
                if not can_patch_fields:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": ("set_task_type is not allowed for this capability profile."),
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await bridge.update_task(task_id, task_type=task_type_value)
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            if transition == "request_review":
                if not can_request_review:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": ("request_review is not allowed for this capability profile."),
                        "code": "ACTION_NOT_ALLOWED",
                    }
                summary_raw = fields.pop("summary", "")
                summary = summary_raw if isinstance(summary_raw, str) else ""
                raw = await bridge.request_review(task_id, summary)
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            if transition is not None:
                return {
                    "success": False,
                    "task_id": task_id,
                    "message": (
                        f"Unsupported transition {transition!r}. "
                        "Valid transitions: set_status, set_task_type, request_review."
                    ),
                    "code": "INVALID_TRANSITION",
                }

            if status_for_move is not None:
                if not can_patch_status:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "status patch is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await bridge.move_task(task_id, status_for_move)
                if not bool(raw.get("success", False)):
                    return {"success": False, "task_id": task_id, **raw}

            if fields:
                if not can_patch_fields:
                    return {
                        "success": False,
                        "task_id": task_id,
                        "message": "field patch is not allowed for this capability profile.",
                        "code": "ACTION_NOT_ALLOWED",
                    }
                raw = await bridge.update_task(task_id, **fields)
                return {"success": bool(raw.get("success", True)), "task_id": task_id, **raw}

            return {"success": True, "task_id": task_id, "message": "Patch applied"}

    if can_delete:

        @mcp.tool(annotations=_DESTRUCTIVE)
        async def task_delete(
            task_id: str,
            ctx: MCPContext | None = None,
        ) -> TaskDeleteResponse:
            """Delete a task."""
            bridge = _get_bridge(ctx)
            raw = await bridge.delete_task(task_id)
            return TaskDeleteResponse(
                success=bool(raw.get("success", False)),
                message=raw.get("message"),
                code=raw.get("code"),
                hint=raw.get("hint"),
                next_tool=raw.get("next_tool"),
                next_arguments=raw.get("next_arguments"),
                task_id=task_id,
            )

    # --- Job tools ---

    if allows_all(_PROTOCOL["jobs_submit"]):

        @mcp.tool(annotations=_MUTATING)
        async def job_start(
            task_id: str,
            action: JobActionInput,
            arguments: dict[str, object] | None = None,
            ctx: MCPContext | None = None,
        ) -> JobResponse:
            """Submit an asynchronous core job."""
            bridge = _get_bridge(ctx)
            raw = await bridge.submit_job(task_id=task_id, action=action, arguments=arguments)
            job_id = _str_or_none(raw.get("job_id")) or ""
            returned_task_id = _str_or_none(raw.get("task_id")) or task_id
            success = bool(raw.get("success", False))
            next_tool = _str_or_none(raw.get("next_tool"))
            next_arguments = _dict_or_none(raw.get("next_arguments"))
            hint = _str_or_none(raw.get("hint"))
            if success and next_tool is None and job_id:
                next_tool = "job_poll"
                next_arguments = {
                    "job_id": job_id,
                    "task_id": returned_task_id,
                    "wait": True,
                    "timeout_seconds": _DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
                }
            return JobResponse(
                success=success,
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=hint,
                next_tool=next_tool,
                next_arguments=next_arguments,
                job_id=job_id,
                task_id=returned_task_id,
                action=_str_or_none(raw.get("action")) or str(action),
                status=_str_or_none(raw.get("status")),
            )

    if (
        allows_all(_PROTOCOL["jobs_get"])
        or allows_all(_PROTOCOL["jobs_wait"])
        or allows_all(_PROTOCOL["jobs_events"])
    ):

        @mcp.tool(annotations=_READ_ONLY)
        async def job_poll(
            job_id: str,
            task_id: str,
            wait: bool = False,
            timeout_seconds: float = _DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
            events: bool = False,
            limit: int = 50,
            offset: int = 0,
            ctx: MCPContext | None = None,
        ) -> JobResponse | JobEventsResponse:
            """Read job state, optionally waiting or paging events."""
            bridge = _get_bridge(ctx)
            if events:
                raw = await bridge.list_job_events(
                    job_id=job_id, task_id=task_id, limit=limit, offset=offset
                )
                event_items: list[JobEvent] = []
                events_raw = raw.get("events")
                if isinstance(events_raw, list):
                    for raw_event in events_raw:
                        if not isinstance(raw_event, dict):
                            continue
                        event_items.append(
                            JobEvent(
                                job_id=_str_or_none(raw_event.get("job_id")),
                                task_id=_str_or_none(raw_event.get("task_id")),
                                status=_str_or_none(raw_event.get("status")),
                                timestamp=_str_or_none(raw_event.get("timestamp")),
                                message=_str_or_none(raw_event.get("message")),
                                code=_str_or_none(raw_event.get("code")),
                            )
                        )
                total_events = _int_or_none(raw.get("total_events"))
                returned_events = _int_or_none(raw.get("returned_events"))
                page_offset = _int_or_none(raw.get("offset"))
                page_limit = _int_or_none(raw.get("limit"))
                next_offset = _int_or_none(raw.get("next_offset"))
                has_more_val = raw.get("has_more")
                has_more = (
                    has_more_val if isinstance(has_more_val, bool) else next_offset is not None
                )
                return JobEventsResponse(
                    success=bool(raw.get("success", False)),
                    message=_str_or_none(raw.get("message")),
                    code=_str_or_none(raw.get("code")),
                    job_id=_str_or_none(raw.get("job_id")) or job_id,
                    task_id=_str_or_none(raw.get("task_id")) or task_id,
                    events=event_items,
                    total_events=(total_events if total_events is not None else len(event_items)),
                    returned_events=(
                        returned_events if returned_events is not None else len(event_items)
                    ),
                    offset=page_offset if page_offset is not None else offset,
                    limit=page_limit if page_limit is not None else limit,
                    has_more=has_more,
                    next_offset=next_offset,
                )

            if wait:
                raw = await bridge.wait_job(
                    job_id=job_id, task_id=task_id, timeout_seconds=timeout_seconds
                )
            else:
                raw = await bridge.get_job(job_id=job_id, task_id=task_id)

            result = _dict_or_none(raw.get("result"))
            success = bool(raw.get("success", False))
            status = _str_or_none(raw.get("status"))
            code = _str_or_none(raw.get("code"))
            if code is None and result is not None:
                code = _str_or_none(result.get("code"))
            message = _str_or_none(raw.get("message"))
            if message is None and result is not None:
                message = _str_or_none(result.get("message"))

            timed_out_val = raw.get("timed_out")
            if not isinstance(timed_out_val, bool) and result is not None:
                timed_out_val = result.get("timed_out")
            timed_out = timed_out_val if isinstance(timed_out_val, bool) else None

            # Derive success for non-terminal/pending states (but not timeouts)
            if not success and not timed_out and status in _JOB_NON_TERMINAL_STATUSES:
                success = True
            if (
                not success
                and result is not None
                and _str_or_none(result.get("code")) == "START_PENDING"
            ):
                success = True
                code = "START_PENDING"

            # Timeout metadata
            timeout_metadata: dict[str, object] | None = None
            timeout_fields: dict[str, object] = {}
            for source in (raw, result or {}):
                for key, value in source.items():
                    if key.startswith("timeout_"):
                        timeout_fields[key] = value
            if timeout_fields:
                timeout_metadata = timeout_fields

            next_tool = _str_or_none(raw.get("next_tool"))
            next_arguments = _dict_or_none(raw.get("next_arguments"))
            hint = _str_or_none(raw.get("hint"))

            # Derive recovery for non-terminal / timed-out states
            if next_tool is None and (
                status in _JOB_NON_TERMINAL_STATUSES or timed_out or code == "START_PENDING"
            ):
                next_tool = "job_poll"
                next_arguments = {
                    "job_id": job_id,
                    "task_id": task_id,
                    "wait": True,
                    "timeout_seconds": _DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
                }

            runtime_raw = _dict_or_none(raw.get("runtime"))
            if runtime_raw is None and result is not None:
                runtime_raw = _dict_or_none(result.get("runtime"))

            return JobResponse(
                success=success,
                message=message,
                code=code,
                hint=hint,
                next_tool=next_tool,
                next_arguments=next_arguments,
                job_id=_str_or_none(raw.get("job_id")) or job_id,
                task_id=_str_or_none(raw.get("task_id")) or task_id,
                action=_str_or_none(raw.get("action")),
                status=status,
                timed_out=timed_out,
                timeout_metadata=timeout_metadata,
                result=result,
                runtime=_get_runtime_state(runtime_raw),
            )

    if allows_all(_PROTOCOL["jobs_cancel"]):

        @mcp.tool(annotations=_MUTATING)
        async def job_cancel(
            job_id: str,
            task_id: str,
            ctx: MCPContext | None = None,
        ) -> JobResponse:
            """Cancel a submitted job."""
            bridge = _get_bridge(ctx)
            raw = await bridge.cancel_job(job_id=job_id, task_id=task_id)
            success = bool(raw.get("success", False))
            next_tool = _str_or_none(raw.get("next_tool"))
            next_arguments = _dict_or_none(raw.get("next_arguments"))
            hint = _str_or_none(raw.get("hint"))
            if success and next_tool is None:
                next_tool = "job_poll"
                next_arguments = {
                    "job_id": job_id,
                    "task_id": task_id,
                    "wait": True,
                    "timeout_seconds": _DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS,
                }
            return JobResponse(
                success=success,
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=hint,
                next_tool=next_tool,
                next_arguments=next_arguments,
                job_id=_str_or_none(raw.get("job_id")) or job_id,
                task_id=_str_or_none(raw.get("task_id")) or task_id,
                action=_str_or_none(raw.get("action")),
                status=_str_or_none(raw.get("status")),
            )

    # --- Review tool ---

    if (
        allows_all(_PROTOCOL["review_approve"])
        or allows_all(_PROTOCOL["review_reject"])
        or allows_all(_PROTOCOL["review_merge"])
        or allows_all(_PROTOCOL["review_rebase"])
    ):

        @mcp.tool(annotations=_DESTRUCTIVE)
        async def review_apply(
            task_id: str,
            action: ReviewActionInput,
            feedback: str = "",
            rejection_action: RejectionActionInput = "reopen",
            ctx: MCPContext | None = None,
        ) -> ReviewActionResponse:
            """Perform a review action on a task."""
            bridge = _get_bridge(ctx)
            if not _is_allowed(effective_profile, ProtocolCapability.REVIEW, action):
                return ReviewActionResponse(
                    success=False,
                    task_id=task_id,
                    message=(f"Action '{action}' is not allowed for this capability profile."),
                    code="ACTION_NOT_ALLOWED",
                )
            raw = await bridge.review_action(
                task_id,
                action=action,
                feedback=feedback,
                rejection_action=rejection_action,
            )
            return ReviewActionResponse(
                success=bool(raw.get("success", False)),
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=_str_or_none(raw.get("hint")),
                next_tool=_str_or_none(raw.get("next_tool")),
                next_arguments=_dict_or_none(raw.get("next_arguments")),
                task_id=raw.get("task_id", task_id),
            )

    # --- Diagnostics ---

    if enable_internal_instrumentation and allows_all(_PROTOCOL["diagnostics_instrumentation"]):

        @mcp.tool(annotations=_READ_ONLY)
        async def diagnostics_instrumentation(
            ctx: MCPContext | None = None,
        ) -> InstrumentationSnapshotResponse:
            """Get internal in-memory core instrumentation snapshot."""
            bridge = _get_bridge(ctx)
            raw = await bridge.get_instrumentation_snapshot()

            counters: dict[str, int] = {}
            counters_raw = raw.get("counters", {})
            if isinstance(counters_raw, dict):
                for key, value in counters_raw.items():
                    if isinstance(value, int):
                        counters[str(key)] = value

            timings: dict[str, dict[str, float | int]] = {}
            timings_raw = raw.get("timings", {})
            if isinstance(timings_raw, dict):
                for metric_name, stats in timings_raw.items():
                    if not isinstance(stats, dict):
                        continue
                    normalized: dict[str, float | int] = {}
                    for field_name, field_value in stats.items():
                        if isinstance(field_value, int | float):
                            normalized[str(field_name)] = field_value
                    timings[str(metric_name)] = normalized

            return InstrumentationSnapshotResponse(
                enabled=bool(raw.get("enabled", False)),
                log_events=bool(raw.get("log_events", False)),
                counters=counters,
                timings=timings,
            )

    # --- Settings ---

    if allows_all(_PROTOCOL["settings_get"]):

        @mcp.tool(annotations=_READ_ONLY)
        async def settings_get(
            ctx: MCPContext | None = None,
        ) -> SettingsGetResponse:
            """Get MCP-exposed settings snapshot."""
            bridge = _get_bridge(ctx)
            raw = await bridge.get_settings()
            return SettingsGetResponse(settings=raw.get("settings", {}))

    if allows_all(_PROTOCOL["settings_update"]):

        @mcp.tool(annotations=_MUTATING)
        async def settings_set(
            auto_review: bool | None = None,
            auto_approve: bool | None = None,
            require_review_approval: bool | None = None,
            serialize_merges: bool | None = None,
            worktree_base_ref_strategy: str | None = None,
            max_concurrent_agents: int | None = None,
            default_worker_agent: str | None = None,
            default_pair_terminal_backend: str | None = None,
            default_model_claude: str | None = None,
            default_model_opencode: str | None = None,
            default_model_codex: str | None = None,
            default_model_gemini: str | None = None,
            default_model_kimi: str | None = None,
            default_model_copilot: str | None = None,
            tasks_wait_default_timeout_seconds: int | None = None,
            tasks_wait_max_timeout_seconds: int | None = None,
            skip_pair_instructions: bool | None = None,
            ctx: MCPContext | None = None,
        ) -> SettingsUpdateResponse:
            """Update allowlisted settings fields."""
            bridge = _get_bridge(ctx)
            fields: dict[str, Any] = {}
            if auto_review is not None:
                fields["general.auto_review"] = auto_review
            if auto_approve is not None:
                fields["general.auto_approve"] = auto_approve
            if require_review_approval is not None:
                fields["general.require_review_approval"] = require_review_approval
            if serialize_merges is not None:
                fields["general.serialize_merges"] = serialize_merges
            if worktree_base_ref_strategy is not None:
                fields["general.worktree_base_ref_strategy"] = worktree_base_ref_strategy
            if max_concurrent_agents is not None:
                fields["general.max_concurrent_agents"] = max_concurrent_agents
            if default_worker_agent is not None:
                fields["general.default_worker_agent"] = default_worker_agent
            if default_pair_terminal_backend is not None:
                fields["general.default_pair_terminal_backend"] = default_pair_terminal_backend
            if default_model_claude is not None:
                fields["general.default_model_claude"] = default_model_claude
            if default_model_opencode is not None:
                fields["general.default_model_opencode"] = default_model_opencode
            if default_model_codex is not None:
                fields["general.default_model_codex"] = default_model_codex
            if default_model_gemini is not None:
                fields["general.default_model_gemini"] = default_model_gemini
            if default_model_kimi is not None:
                fields["general.default_model_kimi"] = default_model_kimi
            if default_model_copilot is not None:
                fields["general.default_model_copilot"] = default_model_copilot
            if tasks_wait_default_timeout_seconds is not None:
                fields["general.tasks_wait_default_timeout_seconds"] = (
                    tasks_wait_default_timeout_seconds
                )
            if tasks_wait_max_timeout_seconds is not None:
                fields["general.tasks_wait_max_timeout_seconds"] = tasks_wait_max_timeout_seconds
            if skip_pair_instructions is not None:
                fields["ui.skip_pair_instructions"] = skip_pair_instructions
            raw = await bridge.update_settings(fields)
            return SettingsUpdateResponse(
                success=bool(raw.get("success", False)),
                message=raw.get("message"),
                code=raw.get("code"),
                hint=raw.get("hint"),
                next_tool=raw.get("next_tool"),
                next_arguments=raw.get("next_arguments"),
                updated=raw.get("updated", {}),
                settings=raw.get("settings", {}),
            )

    # --- Session tool ---

    if (
        allows_all(_PROTOCOL["sessions_create"])
        or allows_all(_PROTOCOL["sessions_exists"])
        or allows_all(_PROTOCOL["sessions_kill"])
    ):
        from kagan.mcp._response_models import SessionActionInput

        @mcp.tool(annotations=_MUTATING)
        async def session_manage(
            action: SessionActionInput,
            task_id: str,
            reuse_if_exists: bool = True,
            worktree_path: str | None = None,
            ctx: MCPContext | None = None,
        ) -> dict[str, object]:
            """Manage PAIR sessions with a single action-oriented interface."""
            bridge = _get_bridge(ctx)
            if action == "open":
                raw = await bridge.create_session(
                    task_id, reuse_if_exists=reuse_if_exists, worktree_path=worktree_path
                )
                return {
                    "success": bool(raw.get("success", False)),
                    "action": action,
                    "task_id": raw.get("task_id", task_id),
                    **{k: v for k, v in raw.items() if k != "success"},
                }
            if action == "read":
                raw = await bridge.session_exists(task_id)
                return {
                    "success": True,
                    "action": action,
                    "task_id": raw.get("task_id", task_id),
                    "exists": raw.get("exists", False),
                }
            if action == "close":
                raw = await bridge.kill_session(task_id)
                return {
                    "success": bool(raw.get("success", False)),
                    "action": action,
                    "task_id": raw.get("task_id", task_id),
                }
            return {
                "success": False,
                "task_id": task_id,
                "code": "INVALID_ACTION",
                "message": f"Unsupported session action {action!r}.",
            }

    # --- Project open ---

    if allows_all(_PROTOCOL["projects_open"]):
        from kagan.mcp._response_models import ProjectOpenResponse

        @mcp.tool(annotations=_MUTATING)
        async def project_open(
            project_id: str,
            ctx: MCPContext | None = None,
        ) -> ProjectOpenResponse:
            """Open/switch to a project."""
            bridge = _get_bridge(ctx)
            raw = await bridge.open_project(project_id)
            return ProjectOpenResponse(
                success=bool(raw.get("success", True)),
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=_str_or_none(raw.get("hint")),
                next_tool=_str_or_none(raw.get("next_tool")),
                next_arguments=_dict_or_none(raw.get("next_arguments")),
                project_id=raw.get("project_id", project_id),
                name=raw.get("name", ""),
            )

    # --- Plugin tools ---
    _register_plugin_tools(
        mcp,
        effective_profile=effective_profile,
        require_bridge_fn=_get_bridge,
        build_plugin_registry_fn=build_plugin_registry_fn or _build_plugin_registry,
    )


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
