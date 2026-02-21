"""Capability profiles, authorization, session binding, and command decorator.

Consolidates security, session_binding, expose, and request_context into a
single policy module for auth/security/session/decoration logic.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from kagan.core.ipc.contracts import CoreRequest

# ---------------------------------------------------------------------------
# Capability profiles and protocol enums
# ---------------------------------------------------------------------------


class CapabilityProfile(StrEnum):
    """Named security profiles for MCP session authorization.

    Profiles are hierarchical — each level includes all permissions from
    the levels below it:

        viewer < planner < pair_worker < operator < maintainer
    """

    VIEWER = "viewer"
    PLANNER = "planner"
    PAIR_WORKER = "pair_worker"
    OPERATOR = "operator"
    MAINTAINER = "maintainer"


class ProtocolCapability(StrEnum):
    """Canonical MCP protocol capability names."""

    TASKS = "tasks"
    PROJECTS = "projects"
    AUDIT = "audit"
    PLAN = "plan"
    JOBS = "jobs"
    REVIEW = "review"
    SESSIONS = "sessions"
    DIAGNOSTICS = "diagnostics"
    SETTINGS = "settings"


class TasksMethod(StrEnum):
    """Task capability methods."""

    CONTEXT = "context"
    GET = "get"
    LIST = "list"
    LOGS = "logs"
    SCRATCHPAD = "scratchpad"
    WAIT = "wait"
    UPDATE_SCRATCHPAD = "update_scratchpad"
    CREATE = "create"
    UPDATE = "update"
    MOVE = "move"
    DELETE = "delete"


class ProjectsMethod(StrEnum):
    """Project capability methods."""

    GET = "get"
    LIST = "list"
    REPOS = "repos"
    CREATE = "create"
    OPEN = "open"


class AuditMethod(StrEnum):
    """Audit capability methods."""

    LIST = "list"


class PlanMethod(StrEnum):
    """Plan capability methods."""

    PROPOSE = "propose"


class JobsMethod(StrEnum):
    """Jobs capability methods."""

    SUBMIT = "submit"
    GET = "get"
    WAIT = "wait"
    EVENTS = "events"
    CANCEL = "cancel"


class ReviewMethod(StrEnum):
    """Review capability methods."""

    REQUEST = "request"
    APPROVE = "approve"
    REJECT = "reject"
    MERGE = "merge"
    REBASE = "rebase"


class SessionsMethod(StrEnum):
    """Session capability methods."""

    CREATE = "create"
    ATTACH = "attach"
    EXISTS = "exists"
    KILL = "kill"


class DiagnosticsMethod(StrEnum):
    """Diagnostics capability methods."""

    INSTRUMENTATION = "instrumentation"


class SettingsMethod(StrEnum):
    """Settings capability methods."""

    GET = "get"
    UPDATE = "update"


type ProtocolMethod = (
    TasksMethod
    | ProjectsMethod
    | AuditMethod
    | PlanMethod
    | JobsMethod
    | ReviewMethod
    | SessionsMethod
    | DiagnosticsMethod
    | SettingsMethod
)

type CapabilityMethod = tuple[str, str]

VALID_CAPABILITY_PROFILES: frozenset[str] = frozenset(
    profile.value for profile in CapabilityProfile
)


def normalize_profile(profile: CapabilityProfile | str) -> CapabilityProfile:
    """Normalize an input profile to :class:`CapabilityProfile`."""
    try:
        return CapabilityProfile(profile)
    except ValueError as exc:
        valid = ", ".join(sorted(VALID_CAPABILITY_PROFILES))
        msg = f"Unknown capability profile '{profile}'. Valid profiles: {valid}"
        raise ValueError(msg) from exc


def coerce_profile(profile: object) -> CapabilityProfile | None:
    """Coerce an arbitrary value to :class:`CapabilityProfile`."""
    if isinstance(profile, CapabilityProfile):
        return profile
    if isinstance(profile, str):
        try:
            return CapabilityProfile(profile)
        except ValueError:
            return None
    return None


def protocol_call(
    capability: ProtocolCapability | str,
    method: ProtocolMethod | str,
) -> CapabilityMethod:
    """Build a canonical ``(capability, method)`` tuple."""
    canonical_capability = (
        capability.value if isinstance(capability, ProtocolCapability) else capability
    )
    canonical_method = method.value if isinstance(method, StrEnum) else method
    return canonical_capability, canonical_method


# Read-only queries available to every profile.
_VIEWER_METHODS: frozenset[CapabilityMethod] = frozenset(
    {
        protocol_call(ProtocolCapability.TASKS, TasksMethod.CONTEXT),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.GET),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.LIST),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.LOGS),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.SCRATCHPAD),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.WAIT),
        protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.GET),
        protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.LIST),
        protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.REPOS),
        protocol_call(ProtocolCapability.AUDIT, AuditMethod.LIST),
    }
)

# Planner adds plan proposal capability.
_PLANNER_METHODS: frozenset[CapabilityMethod] = _VIEWER_METHODS | frozenset(
    {
        protocol_call(ProtocolCapability.PLAN, PlanMethod.PROPOSE),
    }
)

# Pair worker adds scratchpad updates, review request, and session management.
_PAIR_WORKER_METHODS: frozenset[CapabilityMethod] = _PLANNER_METHODS | frozenset(
    {
        protocol_call(ProtocolCapability.TASKS, TasksMethod.UPDATE_SCRATCHPAD),
        protocol_call(ProtocolCapability.JOBS, JobsMethod.SUBMIT),
        protocol_call(ProtocolCapability.JOBS, JobsMethod.GET),
        protocol_call(ProtocolCapability.JOBS, JobsMethod.WAIT),
        protocol_call(ProtocolCapability.JOBS, JobsMethod.EVENTS),
        protocol_call(ProtocolCapability.JOBS, JobsMethod.CANCEL),
        protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REQUEST),
        protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.CREATE),
        protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.ATTACH),
        protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.EXISTS),
        protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.KILL),
    }
)

# Operator adds full task CRUD and review approve/reject.
_OPERATOR_METHODS: frozenset[CapabilityMethod] = _PAIR_WORKER_METHODS | frozenset(
    {
        protocol_call(ProtocolCapability.TASKS, TasksMethod.CREATE),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.UPDATE),
        protocol_call(ProtocolCapability.TASKS, TasksMethod.MOVE),
        protocol_call(ProtocolCapability.REVIEW, ReviewMethod.APPROVE),
        protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REJECT),
    }
)

# Maintainer has unrestricted access.
_MAINTAINER_METHODS: frozenset[CapabilityMethod] = _OPERATOR_METHODS | frozenset(
    {
        protocol_call(ProtocolCapability.TASKS, TasksMethod.DELETE),
        protocol_call(ProtocolCapability.REVIEW, ReviewMethod.MERGE),
        protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REBASE),
        protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.CREATE),
        protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.OPEN),
        protocol_call(ProtocolCapability.DIAGNOSTICS, DiagnosticsMethod.INSTRUMENTATION),
        protocol_call(ProtocolCapability.SETTINGS, SettingsMethod.GET),
        protocol_call(ProtocolCapability.SETTINGS, SettingsMethod.UPDATE),
    }
)

CAPABILITY_PROFILES: dict[CapabilityProfile, frozenset[CapabilityMethod]] = {
    CapabilityProfile.VIEWER: _VIEWER_METHODS,
    CapabilityProfile.PLANNER: _PLANNER_METHODS,
    CapabilityProfile.PAIR_WORKER: _PAIR_WORKER_METHODS,
    CapabilityProfile.OPERATOR: _OPERATOR_METHODS,
    CapabilityProfile.MAINTAINER: _MAINTAINER_METHODS,
}


# ---------------------------------------------------------------------------
# Authorization policy
# ---------------------------------------------------------------------------


class AuthorizationError(Exception):
    """Raised when a request is denied by the authorization policy."""

    code: str = "AUTHORIZATION_DENIED"

    def __init__(
        self,
        capability: ProtocolCapability | str,
        method: ProtocolMethod | str,
        profile: CapabilityProfile,
    ) -> None:
        canonical_capability, canonical_method = protocol_call(capability, method)
        profile_value = profile.value
        self.capability = canonical_capability
        self.method = canonical_method
        self.profile = profile_value
        message = (
            f"Profile '{profile_value}' is not authorized for "
            f"{canonical_capability}.{canonical_method}"
        )
        super().__init__(message)


class AuthorizationPolicy:
    """Checks whether a given profile is allowed to invoke a capability method.

    Usage::

        policy = AuthorizationPolicy("viewer")
        policy.check("tasks", "list")  # True
        policy.check("tasks", "delete")  # False
        policy.enforce("tasks", "delete")  # raises AuthorizationError
    """

    def __init__(self, profile: CapabilityProfile | str) -> None:
        normalized_profile = normalize_profile(profile)
        self._profile = normalized_profile
        self._allowed: frozenset[CapabilityMethod] = CAPABILITY_PROFILES[normalized_profile]
        self._unrestricted = normalized_profile is CapabilityProfile.MAINTAINER

    @property
    def profile(self) -> CapabilityProfile:
        """The profile name this policy enforces."""
        return self._profile

    @property
    def allowed_methods(self) -> frozenset[CapabilityMethod]:
        """The set of (capability, method) tuples this profile may access."""
        return self._allowed

    def check(self, capability: ProtocolCapability | str, method: ProtocolMethod | str) -> bool:
        """Return *True* if the profile is allowed to call *capability.method*.

        The ``maintainer`` profile is unrestricted and always returns *True*.
        """
        if self._unrestricted:
            return True
        canonical_call = protocol_call(capability, method)
        return canonical_call in self._allowed

    def enforce(self, capability: ProtocolCapability | str, method: ProtocolMethod | str) -> None:
        """Raise :class:`AuthorizationError` if the call is not allowed."""
        if not self.check(capability, method):
            raise AuthorizationError(capability, method, self._profile)


# Default policy for unscoped sessions.
DEFAULT_PROFILE = CapabilityProfile.VIEWER


# ---------------------------------------------------------------------------
# Session binding and authorization lane helpers
# ---------------------------------------------------------------------------

_PROFILE_RANK: dict[CapabilityProfile, int] = {
    CapabilityProfile.VIEWER: 0,
    CapabilityProfile.PLANNER: 1,
    CapabilityProfile.PAIR_WORKER: 2,
    CapabilityProfile.OPERATOR: 3,
    CapabilityProfile.MAINTAINER: 4,
}


def profile_rank(profile: CapabilityProfile | str) -> int:
    """Return numeric privilege rank for a capability profile."""
    return _PROFILE_RANK[normalize_profile(profile)]


def apply_profile_ceiling(
    requested_profile: CapabilityProfile | str,
    *,
    ceiling_profile: CapabilityProfile | str,
) -> CapabilityProfile:
    """Return requested profile bounded by a maximum allowed ceiling."""
    normalized_requested = normalize_profile(requested_profile)
    normalized_ceiling = normalize_profile(ceiling_profile)
    if _PROFILE_RANK[normalized_requested] <= _PROFILE_RANK[normalized_ceiling]:
        return normalized_requested
    return normalized_ceiling


class SessionOrigin(StrEnum):
    KAGAN = "kagan"
    KAGAN_ADMIN = "kagan_admin"
    TUI = "tui"


class SessionNamespace(StrEnum):
    DEFAULT = "default"
    TASK = "task"
    PLANNER = "planner"
    EXT = "ext"
    TUI = "tui"


_SCOPED_SESSION_NAMESPACES: frozenset[SessionNamespace] = frozenset(
    {SessionNamespace.TASK, SessionNamespace.PLANNER, SessionNamespace.EXT, SessionNamespace.TUI}
)


_ORIGIN_PROFILE_CEILING: dict[SessionOrigin, CapabilityProfile] = {
    SessionOrigin.KAGAN: CapabilityProfile.PAIR_WORKER,
    SessionOrigin.KAGAN_ADMIN: CapabilityProfile.MAINTAINER,
    SessionOrigin.TUI: CapabilityProfile.MAINTAINER,
}

_ORIGIN_ALLOWED_NAMESPACES: dict[SessionOrigin, set[SessionNamespace]] = {
    SessionOrigin.KAGAN: {
        SessionNamespace.DEFAULT,
        SessionNamespace.TASK,
        SessionNamespace.PLANNER,
    },
    SessionOrigin.KAGAN_ADMIN: {SessionNamespace.EXT},
    SessionOrigin.TUI: {SessionNamespace.TUI},
}

_TASK_MUTATION_METHODS: set[tuple[str, str]] = {
    ("jobs", "submit"),
    ("jobs", "get"),
    ("jobs", "wait"),
    ("jobs", "events"),
    ("jobs", "cancel"),
    ("tasks", "update_scratchpad"),
    ("tasks", "delete"),
    ("review", "request"),
}


class SessionBindingError(Exception):
    """Raised when a request violates session binding / lane constraints."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class SessionBinding:
    """Resolved auth context bound to an IPC session."""

    policy: AuthorizationPolicy
    origin: SessionOrigin
    namespace: SessionNamespace
    scope_id: str


def get_binding(bindings: dict[str, SessionBinding], request: CoreRequest) -> SessionBinding:
    """Resolve and cache authorization/session lane binding for a request."""
    existing = bindings.get(request.session_id)
    if existing is not None:
        if request.session_profile:
            try:
                requested_profile = _normalize_profile(request.session_profile)
            except ValueError as exc:
                raise SessionBindingError("INVALID_PROFILE", str(exc)) from exc
            try:
                existing_profile = _normalize_profile(existing.policy.profile)
            except ValueError as exc:
                raise SessionBindingError("INVALID_PROFILE", str(exc)) from exc
            if requested_profile is not existing_profile:
                msg = (
                    f"Session '{request.session_id}' is already bound to profile "
                    f"'{existing.policy.profile}', cannot switch to '{request.session_profile}'"
                )
                raise SessionBindingError("INVALID_PROFILE", msg)
        requested_origin = _normalize_origin(request.session_origin)
        if requested_origin != existing.origin:
            msg = (
                f"Session '{request.session_id}' is already bound to origin "
                f"'{existing.origin}', cannot switch to '{requested_origin}'"
            )
            raise SessionBindingError("SESSION_ORIGIN_MISMATCH", msg)
        return existing

    origin = _normalize_origin(request.session_origin)
    try:
        requested_profile = _normalize_profile(str(request.session_profile or DEFAULT_PROFILE))
    except ValueError as exc:
        raise SessionBindingError("INVALID_PROFILE", str(exc)) from exc
    ceiling_profile = _ORIGIN_PROFILE_CEILING[origin]
    effective_profile = apply_profile_ceiling(requested_profile, ceiling_profile=ceiling_profile)

    namespace, scope_id = _parse_session_scope(request.session_id)
    allowed_namespaces = _ORIGIN_ALLOWED_NAMESPACES[origin]
    if namespace not in allowed_namespaces:
        allowed = ", ".join(sorted(item.value for item in allowed_namespaces))
        msg = (
            f"Origin '{origin}' is not authorized for session namespace '{namespace}'. "
            f"Allowed namespaces: {allowed}"
        )
        raise SessionBindingError("SESSION_NAMESPACE_DENIED", msg)

    binding = SessionBinding(
        policy=AuthorizationPolicy(str(effective_profile)),
        origin=origin,
        namespace=namespace,
        scope_id=scope_id,
    )
    bindings[request.session_id] = binding
    return binding


def enforce_task_scope(request: CoreRequest, binding: SessionBinding) -> None:
    if (request.capability, request.method) not in _TASK_MUTATION_METHODS:
        return
    if binding.namespace is not SessionNamespace.TASK:
        return
    task_id = request.params.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        msg = f"Task-scoped session '{request.session_id}' requires a non-empty task_id parameter"
        raise SessionBindingError("INVALID_PARAMS", msg)
    if task_id != binding.scope_id:
        msg = (
            f"Session '{request.session_id}' is scoped to task '{binding.scope_id}' "
            f"and cannot mutate task '{task_id}'"
        )
        raise SessionBindingError("SESSION_SCOPE_DENIED", msg)


def _normalize_profile(profile: str) -> CapabilityProfile:
    try:
        return CapabilityProfile(profile)
    except ValueError as exc:
        valid = ", ".join(str(item) for item in CapabilityProfile)
        msg = f"Unknown capability profile '{profile}'. Valid profiles: {valid}"
        raise ValueError(msg) from exc


def _normalize_origin(origin: str) -> SessionOrigin:
    normalized = origin.strip().lower()
    if not normalized:
        valid = ", ".join(sorted(item.value for item in SessionOrigin))
        msg = f"Unknown session origin '{origin}'. Valid origins: {valid}"
        raise SessionBindingError("INVALID_ORIGIN", msg)
    try:
        return SessionOrigin(normalized)
    except ValueError as exc:
        valid = ", ".join(sorted(item.value for item in SessionOrigin))
        msg = f"Unknown session origin '{origin}'. Valid origins: {valid}"
        raise SessionBindingError("INVALID_ORIGIN", msg) from exc


def _coerce_namespace(namespace: str) -> SessionNamespace | None:
    try:
        return SessionNamespace(namespace)
    except ValueError:
        return None


def _parse_session_scope(session_id: str) -> tuple[SessionNamespace, str]:
    if ":" in session_id:
        namespace_raw, _, scope = session_id.partition(":")
        namespace = _coerce_namespace(namespace_raw)
        if namespace is not None and namespace in _SCOPED_SESSION_NAMESPACES and scope:
            return namespace, scope
    return SessionNamespace.DEFAULT, session_id


# ---------------------------------------------------------------------------
# Command decorator
# ---------------------------------------------------------------------------

COMMAND_ATTR = "_kagan_expose"


@dataclass(frozen=True, slots=True)
class CommandMetadata:
    """Metadata attached to API methods for auto-registration."""

    capability: str
    method: str
    profile: str  # minimum required profile
    mutating: bool
    description: str


def command(
    capability: str,
    method: str,
    *,
    profile: str = "viewer",
    mutating: bool = False,
    description: str = "",
) -> Any:
    """Decorator marking an API method for auto-registration.

    Args:
        capability: Security capability namespace (e.g. ``"tasks"``).
        method: Method name within the capability (e.g. ``"get"``).
        profile: Minimum :class:`CapabilityProfile` required to invoke the tool.
        mutating: Whether the tool mutates state (affects ToolAnnotations).
        description: Human-readable tool description surfaced by the MCP host.

    Returns:
        A decorator that attaches :class:`CommandMetadata` to the wrapped function.
    """

    def decorator(fn: Any) -> Any:
        setattr(
            fn,
            COMMAND_ATTR,
            CommandMetadata(
                capability=capability,
                method=method,
                profile=profile,
                mutating=mutating,
                description=description,
            ),
        )
        return fn

    return decorator


def collect_command_methods(obj: object) -> list[tuple[str, Any, CommandMetadata]]:
    """Yield ``(method_name, bound_method, metadata)`` for decorated methods on *obj*.

    Inspects all public attributes of *obj* and returns those carrying
    :data:`COMMAND_ATTR` metadata.
    """
    results: list[tuple[str, Any, CommandMetadata]] = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        attr = getattr(obj, name, None)
        if attr is None or not callable(attr):
            continue
        meta = getattr(attr, COMMAND_ATTR, None)
        if isinstance(meta, CommandMetadata):
            results.append((name, attr, meta))
    return results


# ---------------------------------------------------------------------------
# Request context (contextvars)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestContext:
    request: CoreRequest
    binding: SessionBinding


_REQUEST_CONTEXT: ContextVar[RequestContext | None] = ContextVar(
    "kagan_request_context",
    default=None,
)


@contextmanager
def request_context(ctx: RequestContext) -> Iterator[None]:
    token = _REQUEST_CONTEXT.set(ctx)
    try:
        yield
    finally:
        _REQUEST_CONTEXT.reset(token)


def get_request_context() -> RequestContext | None:
    return _REQUEST_CONTEXT.get()


def require_request_context() -> RequestContext:
    ctx = get_request_context()
    if ctx is None:
        raise RuntimeError("Request context is not available")
    return ctx


# ---------------------------------------------------------------------------
# Agent permission policy
# ---------------------------------------------------------------------------


class AgentPermissionScope(StrEnum):
    """Execution scope used to resolve auto-approve behavior."""

    PLANNER = "planner"
    ORCHESTRATOR = "orchestrator"
    AUTOMATION_RUNNER = "automation_runner"
    AUTOMATION_REVIEWER = "automation_reviewer"
    PROMPT_REFINER = "prompt_refiner"


class PermissionDecisionReason(StrEnum):
    """Reason metadata for ACP permission handling decisions."""

    AUTO_APPROVE_ENABLED = "auto_approve_enabled"
    NO_MESSAGE_TARGET = "no_message_target"
    WAIT_FOR_USER = "wait_for_user"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """Permission prompt behavior for an ACP permission request."""

    auto_approve: bool
    reason: PermissionDecisionReason


def resolve_auto_approve(*, scope: AgentPermissionScope, planner_auto_approve: bool) -> bool:
    """Resolve whether a scope should auto-approve ACP permission requests."""
    if scope in (AgentPermissionScope.PLANNER, AgentPermissionScope.ORCHESTRATOR):
        return planner_auto_approve
    return True


def resolve_permission_decision(
    *,
    auto_approve_enabled: bool,
    has_message_target: bool,
) -> PermissionDecision:
    """Resolve ACP permission behavior for the current runtime context."""
    if auto_approve_enabled:
        return PermissionDecision(
            auto_approve=True,
            reason=PermissionDecisionReason.AUTO_APPROVE_ENABLED,
        )
    if not has_message_target:
        return PermissionDecision(
            auto_approve=True,
            reason=PermissionDecisionReason.NO_MESSAGE_TARGET,
        )
    return PermissionDecision(
        auto_approve=False,
        reason=PermissionDecisionReason.WAIT_FOR_USER,
    )


def resolve_mcp_capability(*, task_id: str, read_only: bool) -> CapabilityProfile:
    """Resolve MCP capability profile for an ACP-backed agent session."""
    normalized_task_id = task_id.strip()
    if read_only and not normalized_task_id:
        return CapabilityProfile.PLANNER
    if read_only:
        return CapabilityProfile.VIEWER
    if normalized_task_id:
        return CapabilityProfile.PAIR_WORKER
    return CapabilityProfile.MAINTAINER


__all__ = [
    "CAPABILITY_PROFILES",
    "COMMAND_ATTR",
    "DEFAULT_PROFILE",
    "VALID_CAPABILITY_PROFILES",
    "AgentPermissionScope",
    "AuthorizationError",
    "AuthorizationPolicy",
    "CapabilityMethod",
    "CapabilityProfile",
    "CommandMetadata",
    "PermissionDecision",
    "PermissionDecisionReason",
    "ProtocolCapability",
    "ProtocolMethod",
    "RequestContext",
    "SessionBinding",
    "SessionBindingError",
    "SessionNamespace",
    "SessionOrigin",
    "apply_profile_ceiling",
    "coerce_profile",
    "collect_command_methods",
    "command",
    "enforce_task_scope",
    "get_binding",
    "get_request_context",
    "normalize_profile",
    "profile_rank",
    "protocol_call",
    "request_context",
    "require_request_context",
    "resolve_auto_approve",
    "resolve_mcp_capability",
    "resolve_permission_decision",
]
