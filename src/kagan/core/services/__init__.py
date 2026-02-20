"""Service layer implementations."""

from kagan.core.adapters.db.repositories import ExecutionRepository
from kagan.core.services.automation import AutomationServiceImpl
from kagan.core.services.automation.runner import QueuedMessageServiceImpl
from kagan.core.services.jobs import JobServiceImpl
from kagan.core.services.projects import ProjectServiceImpl
from kagan.core.services.runtime import (
    AutoOutputMode,
    AutoOutputReadiness,
    AutoOutputRecoveryResult,
    RuntimeContextState,
    RuntimeServiceImpl,
    RuntimeSessionEvent,
    RuntimeTaskPhase,
    RuntimeTaskView,
    StartupSessionDecision,
)
from kagan.core.services.sessions import SessionServiceImpl
from kagan.core.services.tasks import TaskServiceImpl
from kagan.core.services.workspaces import (
    FileDiff,
    MergeResult,
    MergeRisk,
    MergeStrategy,
    RepoDiff,
    WorkspaceServiceImpl,
)

__all__ = [
    "AutoOutputMode",
    "AutoOutputReadiness",
    "AutoOutputRecoveryResult",
    "AutomationServiceImpl",
    "ExecutionRepository",
    "FileDiff",
    "JobServiceImpl",
    "MergeResult",
    "MergeRisk",
    "MergeStrategy",
    "ProjectServiceImpl",
    "QueuedMessageServiceImpl",
    "RepoDiff",
    "RuntimeContextState",
    "RuntimeServiceImpl",
    "RuntimeSessionEvent",
    "RuntimeTaskPhase",
    "RuntimeTaskView",
    "SessionServiceImpl",
    "StartupSessionDecision",
    "TaskServiceImpl",
    "WorkspaceServiceImpl",
]
