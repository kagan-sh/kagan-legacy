"""Service layer interfaces."""

from kagan.adapters.db.repositories import ExecutionRepository
from kagan.services.automation import AutomationService, AutomationServiceImpl
from kagan.services.diffs import DiffService, DiffServiceImpl
from kagan.services.follow_ups import FollowUpService, FollowUpServiceImpl
from kagan.services.merges import MergeService, MergeServiceImpl
from kagan.services.projects import ProjectService, ProjectServiceImpl
from kagan.services.queued_messages import QueuedMessageService, QueuedMessageServiceImpl
from kagan.services.repo_scripts import RepoScriptService, RepoScriptServiceImpl
from kagan.services.reviews import ReviewService, ReviewServiceImpl
from kagan.services.runtime import (
    AutoOutputMode,
    AutoOutputReadiness,
    AutoOutputRecoveryResult,
    RuntimeContextState,
    RuntimeService,
    RuntimeServiceImpl,
    RuntimeSessionEvent,
    RuntimeSessionState,
    RuntimeTaskPhase,
    RuntimeTaskView,
    StartupSessionDecision,
)
from kagan.services.sessions import SessionService, SessionServiceImpl
from kagan.services.tasks import TaskService, TaskServiceImpl
from kagan.services.workspaces import WorkspaceService, WorkspaceServiceImpl

__all__ = [
    "AutoOutputMode",
    "AutoOutputReadiness",
    "AutoOutputRecoveryResult",
    "AutomationService",
    "AutomationServiceImpl",
    "DiffService",
    "DiffServiceImpl",
    "ExecutionRepository",
    "FollowUpService",
    "FollowUpServiceImpl",
    "MergeService",
    "MergeServiceImpl",
    "ProjectService",
    "ProjectServiceImpl",
    "QueuedMessageService",
    "QueuedMessageServiceImpl",
    "RepoScriptService",
    "RepoScriptServiceImpl",
    "ReviewService",
    "ReviewServiceImpl",
    "RuntimeContextState",
    "RuntimeService",
    "RuntimeServiceImpl",
    "RuntimeSessionEvent",
    "RuntimeSessionState",
    "RuntimeTaskPhase",
    "RuntimeTaskView",
    "SessionService",
    "SessionServiceImpl",
    "StartupSessionDecision",
    "TaskService",
    "TaskServiceImpl",
    "WorkspaceService",
    "WorkspaceServiceImpl",
]
