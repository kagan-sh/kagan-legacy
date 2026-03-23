"""kagan.core — public surface re-exports.

Import everything you need from here::

    from kagan.core import KaganCore, Task, TaskStatus, NotFoundError
"""

# ruff: noqa: E402
from kagan.core._logging import configure_logging as _configure_logging

_configure_logging()

from kagan.core._acp import ACPClientBase
from kagan.core._agent import (
    CLAUDE_CODE_BACKEND,
    CODEX_BACKEND,
    GEMINI_CLI_BACKEND,
    KIMI_CLI_BACKEND,
    OPENCODE_BACKEND,
    AgentBackendConfig,
    build_agent_environment,
    build_mcp_manifest,
    get_backend,
    list_backends,
    resolve_acp_command,
    resolve_default_agent_backend,
)
from kagan.core._asyncio_compat import install_asyncio_subprocess_exception_filter
from kagan.core._db import default_db_path
from kagan.core._launchers import resolve_launcher
from kagan.core._preflight import CheckStatus, PreflightCheckResult
from kagan.core._prompts import (
    ADDITIONAL_INSTRUCTIONS_KEY,
    AUTO_CONFIRM_SINGLE_KEY,
    DEFAULT_ORCHESTRATOR_PROMPT,
    PERSONA_DEFINITIONS_KEY,
    PERSONA_USER_WHITELIST_KEY,
    PLANNING_DEPTH_KEY,
    REVIEW_STRICTNESS_KEY,
    build_conflict_resolution_feedback,
    detect_dotfile_overrides,
    load_persona_definitions,
    prepend_custom_prompt,
    resolve_orchestrator_prompt,
    resolve_review_prompt,
    resolve_task_prompt,
    serialize_persona_definitions,
)
from kagan.core.client import DBWatcher, KaganCore
from kagan.core.enums import (
    BranchRefStrategy,
    Priority,
    SessionEventType,
    SessionStatus,
    TaskStatus,
    parse_priority,
)
from kagan.core.errors import (
    AgentError,
    ConfigurationError,
    InvalidTransitionError,
    KaganError,
    MergeConflictError,
    MultiRepoUnsupportedError,
    NotFoundError,
    PreflightError,
    SessionError,
    ValidationError,
    WorktreeError,
)
from kagan.core.git import KAGAN_AGENT_EMAIL, KAGAN_AGENT_NAME, get_system_git_identity
from kagan.core.models import (
    AuditEntry,
    Project,
    Repository,
    Session,
    SessionEvent,
    Setting,
    Task,
    TaskNote,
    Worktree,
)

__all__ = [
    "ADDITIONAL_INSTRUCTIONS_KEY",
    "AUTO_CONFIRM_SINGLE_KEY",
    "CLAUDE_CODE_BACKEND",
    "CODEX_BACKEND",
    "DEFAULT_ORCHESTRATOR_PROMPT",
    "GEMINI_CLI_BACKEND",
    "KAGAN_AGENT_EMAIL",
    "KAGAN_AGENT_NAME",
    "KIMI_CLI_BACKEND",
    "OPENCODE_BACKEND",
    "PERSONA_DEFINITIONS_KEY",
    "PERSONA_USER_WHITELIST_KEY",
    "PLANNING_DEPTH_KEY",
    "REVIEW_STRICTNESS_KEY",
    "ACPClientBase",
    "AgentBackendConfig",
    "AgentError",
    "AuditEntry",
    "BranchRefStrategy",
    "CheckStatus",
    "ConfigurationError",
    "DBWatcher",
    "InvalidTransitionError",
    "KaganCore",
    "KaganError",
    "MergeConflictError",
    "MultiRepoUnsupportedError",
    "NotFoundError",
    "PreflightCheckResult",
    "PreflightError",
    "Priority",
    "Project",
    "Repository",
    "Session",
    "SessionError",
    "SessionEvent",
    "SessionEventType",
    "SessionStatus",
    "Setting",
    "Task",
    "TaskNote",
    "TaskStatus",
    "ValidationError",
    "Worktree",
    "WorktreeError",
    "build_agent_environment",
    "build_conflict_resolution_feedback",
    "build_mcp_manifest",
    "default_db_path",
    "detect_dotfile_overrides",
    "get_backend",
    "get_system_git_identity",
    "install_asyncio_subprocess_exception_filter",
    "list_backends",
    "load_persona_definitions",
    "parse_priority",
    "prepend_custom_prompt",
    "resolve_acp_command",
    "resolve_default_agent_backend",
    "resolve_launcher",
    "resolve_orchestrator_prompt",
    "resolve_review_prompt",
    "resolve_task_prompt",
    "serialize_persona_definitions",
]
