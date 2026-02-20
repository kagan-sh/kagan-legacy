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

PROTOCOL_CALLS: dict[str, tuple[str, str]] = {
    "plan_propose": protocol_call(ProtocolCapability.PLAN, PlanMethod.PROPOSE),
    "tasks_get": protocol_call(ProtocolCapability.TASKS, TasksMethod.GET),
    "tasks_scratchpad": protocol_call(ProtocolCapability.TASKS, TasksMethod.SCRATCHPAD),
    "tasks_list": protocol_call(ProtocolCapability.TASKS, TasksMethod.LIST),
    "tasks_logs": protocol_call(ProtocolCapability.TASKS, TasksMethod.LOGS),
    "tasks_wait": protocol_call(ProtocolCapability.TASKS, TasksMethod.WAIT),
    "tasks_update_scratchpad": protocol_call(
        ProtocolCapability.TASKS, TasksMethod.UPDATE_SCRATCHPAD
    ),
    "tasks_create": protocol_call(ProtocolCapability.TASKS, TasksMethod.CREATE),
    "tasks_update": protocol_call(ProtocolCapability.TASKS, TasksMethod.UPDATE),
    "tasks_move": protocol_call(ProtocolCapability.TASKS, TasksMethod.MOVE),
    "tasks_delete": protocol_call(ProtocolCapability.TASKS, TasksMethod.DELETE),
    "projects_list": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.LIST),
    "projects_repos": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.REPOS),
    "projects_create": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.CREATE),
    "projects_open": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.OPEN),
    "audit_list": protocol_call(ProtocolCapability.AUDIT, AuditMethod.LIST),
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
