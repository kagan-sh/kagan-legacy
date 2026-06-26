"""Surface API facade for kagan.core (skeleton).

CLI, TUI, and MCP import stable primitives from here (or documented stable
submodules like ``kagan.core.doctor_checks``), not from internal modules. The v2
domain surface (tasks, workspaces, gates, ledger) is added here during the
rebuild.
"""

from kagan.core._asyncio import install_asyncio_subprocess_exception_filter
from kagan.core.config import (
    RepoConfig,
    ServiceConfig,
    find_repo_root,
    load_repo_config,
    load_review_rubric,
)
from kagan.core.counts import attention_counts
from kagan.core.doctor_checks import DoctorCheck, doctor_has_failures, run_doctor_checks
from kagan.core.enums import TaskState, humanize_task_state
from kagan.core.errors import (
    AgentCapError,
    AgentError,
    ConfigurationError,
    InvalidTransitionError,
    KaganError,
    NotFoundError,
    PreflightError,
    ValidationError,
)
from kagan.core.gate import GateEngine
from kagan.core.harness import Harness, default_data_dir
from kagan.core.inbox import (
    InboxItem,
    after_hours_note,
    coach_hint,
    last_shipped_note,
    recent_approval_count,
    throughput_note,
)
from kagan.core.ledger import Ledger
from kagan.core.logging import configure_logging, default_log_path
from kagan.core.models import (
    CheckResult,
    Decision,
    DriftConcern,
    Finding,
    NeedsYou,
    SmokeTest,
    Task,
)
from kagan.core.notifications import NotificationEvent
from kagan.core.receipt import render_pr_body, render_receipt
from kagan.core.ship import ShipService
from kagan.core.stats import Scorecard
from kagan.core.workspace import RunningService, free_port

__all__ = [
    "AgentCapError",
    "AgentError",
    "CheckResult",
    "ConfigurationError",
    "Decision",
    "DoctorCheck",
    "DriftConcern",
    "Finding",
    "GateEngine",
    "Harness",
    "InboxItem",
    "InvalidTransitionError",
    "KaganError",
    "Ledger",
    "NeedsYou",
    "NotFoundError",
    "NotificationEvent",
    "PreflightError",
    "RepoConfig",
    "RunningService",
    "Scorecard",
    "ServiceConfig",
    "ShipService",
    "SmokeTest",
    "Task",
    "TaskState",
    "ValidationError",
    "after_hours_note",
    "attention_counts",
    "coach_hint",
    "configure_logging",
    "default_data_dir",
    "default_log_path",
    "doctor_has_failures",
    "find_repo_root",
    "free_port",
    "humanize_task_state",
    "install_asyncio_subprocess_exception_filter",
    "last_shipped_note",
    "load_repo_config",
    "load_review_rubric",
    "recent_approval_count",
    "render_pr_body",
    "render_receipt",
    "run_doctor_checks",
    "throughput_note",
]
