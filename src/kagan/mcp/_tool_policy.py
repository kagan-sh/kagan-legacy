"""Shared protocol-policy helpers for MCP tool registration modules."""

from __future__ import annotations

from kagan.core.domain.coercion import TASK_TYPE_VALUES as TASK_TYPE_ENUM_VALUES
from kagan.core.policy import (
    CAPABILITY_PROFILES,
    AuditMethod,
    CapabilityProfile,
    DiagnosticsMethod,
    JobsMethod,
    PlanMethod,
    ProjectsMethod,
    ProtocolCapability,
    ProtocolMethod,
    ReviewMethod,
    SessionsMethod,
    SettingsMethod,
    TasksMethod,
    protocol_call,
)

TASK_TYPE_VALUES = frozenset(TASK_TYPE_ENUM_VALUES)

DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS = 1.5
JOB_NON_TERMINAL_STATUSES = frozenset({"queued", "running"})

type _ProtocolMethodEnum = (
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

_PROTOCOL_CALL_BINDINGS: tuple[tuple[str, ProtocolCapability, _ProtocolMethodEnum], ...] = (
    ("plan_propose", ProtocolCapability.PLAN, PlanMethod.PROPOSE),
    ("tasks_get", ProtocolCapability.TASKS, TasksMethod.GET),
    ("tasks_scratchpad", ProtocolCapability.TASKS, TasksMethod.SCRATCHPAD),
    ("tasks_list", ProtocolCapability.TASKS, TasksMethod.LIST),
    ("tasks_logs", ProtocolCapability.TASKS, TasksMethod.LOGS),
    ("tasks_wait", ProtocolCapability.TASKS, TasksMethod.WAIT),
    ("tasks_update_scratchpad", ProtocolCapability.TASKS, TasksMethod.UPDATE_SCRATCHPAD),
    ("tasks_create", ProtocolCapability.TASKS, TasksMethod.CREATE),
    ("tasks_update", ProtocolCapability.TASKS, TasksMethod.UPDATE),
    ("tasks_move", ProtocolCapability.TASKS, TasksMethod.MOVE),
    ("tasks_delete", ProtocolCapability.TASKS, TasksMethod.DELETE),
    ("projects_list", ProtocolCapability.PROJECTS, ProjectsMethod.LIST),
    ("projects_repos", ProtocolCapability.PROJECTS, ProjectsMethod.REPOS),
    ("projects_create", ProtocolCapability.PROJECTS, ProjectsMethod.CREATE),
    ("projects_open", ProtocolCapability.PROJECTS, ProjectsMethod.OPEN),
    ("audit_list", ProtocolCapability.AUDIT, AuditMethod.LIST),
    ("jobs_submit", ProtocolCapability.JOBS, JobsMethod.SUBMIT),
    ("jobs_get", ProtocolCapability.JOBS, JobsMethod.GET),
    ("jobs_wait", ProtocolCapability.JOBS, JobsMethod.WAIT),
    ("jobs_events", ProtocolCapability.JOBS, JobsMethod.EVENTS),
    ("jobs_cancel", ProtocolCapability.JOBS, JobsMethod.CANCEL),
    ("sessions_create", ProtocolCapability.SESSIONS, SessionsMethod.CREATE),
    ("sessions_exists", ProtocolCapability.SESSIONS, SessionsMethod.EXISTS),
    ("sessions_kill", ProtocolCapability.SESSIONS, SessionsMethod.KILL),
    ("review_request", ProtocolCapability.REVIEW, ReviewMethod.REQUEST),
    ("review_approve", ProtocolCapability.REVIEW, ReviewMethod.APPROVE),
    ("review_reject", ProtocolCapability.REVIEW, ReviewMethod.REJECT),
    ("review_merge", ProtocolCapability.REVIEW, ReviewMethod.MERGE),
    ("review_rebase", ProtocolCapability.REVIEW, ReviewMethod.REBASE),
    ("settings_get", ProtocolCapability.SETTINGS, SettingsMethod.GET),
    ("settings_update", ProtocolCapability.SETTINGS, SettingsMethod.UPDATE),
    (
        "diagnostics_instrumentation",
        ProtocolCapability.DIAGNOSTICS,
        DiagnosticsMethod.INSTRUMENTATION,
    ),
)

PROTOCOL_CALLS: dict[str, tuple[str, str]] = {
    name: protocol_call(capability, method) for name, capability, method in _PROTOCOL_CALL_BINDINGS
}


def is_allowed(
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


__all__ = [
    "DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS",
    "JOB_NON_TERMINAL_STATUSES",
    "PROTOCOL_CALLS",
    "TASK_TYPE_VALUES",
    "is_allowed",
]
