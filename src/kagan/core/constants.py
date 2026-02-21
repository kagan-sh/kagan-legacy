from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.domain.enums import McpIdentity, TaskPriority, TaskStatus
from kagan.core.limits import (
    AGENT_TIMEOUT,
    AGENT_TIMEOUT_LONG,
    DEBUG_BUILD,
    MESSAGE_BUFFER,
    RESPONSE_BUFFER,
    SCRATCHPAD_LIMIT,
    SHUTDOWN_TIMEOUT,
    SUBPROCESS_LIMIT,
)
from kagan.core.policy import CapabilityProfile

if TYPE_CHECKING:
    from pathlib import Path

CARD_TITLE_LINE_WIDTH = 28
CARD_DESC_MAX_LENGTH = 28
CARD_REVIEW_MAX_LENGTH = 18
CARD_HAT_MAX_LENGTH = 8
CARD_ID_MAX_LENGTH = 4
CARD_BACKEND_MAX_LENGTH = 10


MODAL_TITLE_MAX_LENGTH = 50
APPROVAL_TITLE_MAX_LENGTH = 45
NOTIFICATION_TITLE_MAX_LENGTH = 40


DIFF_MAX_LENGTH = 10000


MIN_SCREEN_WIDTH = 80
MIN_SCREEN_HEIGHT = 20


# Note: MCP config files (.mcp.json, opencode.json, .gemini/settings.json)


KAGAN_GENERATED_PATTERNS = (
    ".mcp.json",
    "opencode.json",
    ".gemini/settings.json",
    "kagan*.mcp.json",
    "*kagan.json",
    ".vscode/mcp.json",
    ".cursor/mcp.json",
    ".kagan/",
    ".gitignore",
)


def default_db_path() -> str:
    """Resolve the default DB path from the current runtime context."""
    from kagan.core.runtime_context import resolve_runtime_context

    return str(resolve_runtime_context().db_path)


def get_database_path() -> Path:
    """Compatibility shim for callers/fixtures monkeypatching this symbol."""
    from kagan.core.paths import get_database_path as resolve_database_path

    return resolve_database_path()


def default_config_path() -> str:
    """Resolve the default config path from the current runtime context."""
    from kagan.core.runtime_context import resolve_runtime_context

    return str(resolve_runtime_context().config_path)


MCP_CAPABILITY_VIEWER = CapabilityProfile.VIEWER.value
MCP_CAPABILITY_PLANNER = CapabilityProfile.PLANNER.value
MCP_CAPABILITY_PAIR_WORKER = CapabilityProfile.PAIR_WORKER.value
MCP_CAPABILITY_OPERATOR = CapabilityProfile.OPERATOR.value
MCP_CAPABILITY_MAINTAINER = CapabilityProfile.MAINTAINER.value
MCP_CAPABILITY_CHOICES: frozenset[str] = frozenset(profile.value for profile in CapabilityProfile)

MCP_IDENTITY_DEFAULT = McpIdentity.DEFAULT.value
MCP_IDENTITY_ADMIN = McpIdentity.ADMIN.value
MCP_IDENTITY_CHOICES: frozenset[str] = frozenset(identity.value for identity in McpIdentity)

MCP_DEFAULT_SESSION_ID = "mcp-default"
MCP_DEFAULT_READONLY_CAPABILITY = MCP_CAPABILITY_PLANNER
MCP_DEFAULT_FULL_CAPABILITY = MCP_CAPABILITY_MAINTAINER
MCP_FALLBACK_CAPABILITY = MCP_CAPABILITY_VIEWER
KAGAN_BRANCH_CONFIGURED_KEY = "kagan.branch_configured"

COLUMN_ORDER = [
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
    TaskStatus.DONE,
]

STATUS_LABELS = {
    TaskStatus.BACKLOG: "BACKLOG",
    TaskStatus.IN_PROGRESS: "IN PROGRESS",
    TaskStatus.REVIEW: "REVIEW",
    TaskStatus.DONE: "DONE",
}

PRIORITY_LABELS = {
    TaskPriority.LOW: "Low",
    TaskPriority.MEDIUM: "Medium",
    TaskPriority.HIGH: "High",
}


KAGAN_LOGO = """\
 _  __    _    ____    _    _   _
| |/ /   / \\  / ___|  / \\  | \\ | |
| ' /   / _ \\| |  _  / _ \\ |  \\| |
| . \\  / ___ \\ |_| |/ ___ \\| |\\  |
|_|\\_\\/_/   \\_\\____/_/   \\_\\_| \\_|"""


KAGAN_LOGO_SMALL = "KG"


BOX_DRAWING = {
    "THICK_TL": "┏",
    "THICK_TR": "┓",
    "THICK_BL": "┗",
    "THICK_BR": "┛",
    "THICK_H": "━",
    "THICK_V": "┃",
    "THIN_TL": "┌",
    "THIN_TR": "┐",
    "THIN_BL": "└",
    "THIN_BR": "┘",
    "THIN_H": "─",
    "THIN_V": "│",
    "LIGHT_H": "─",
    "HEAVY_H": "═",
    "BULLET": "•",
    "DOT": "∙",
    "ARROW_RIGHT": "→",
    "ARROW_DOWN": "↓",
    "SECTION": "─",
    "DIVIDER_LIGHT": "─",
    "DIVIDER_HEAVY": "═",
}

__all__ = [
    "AGENT_TIMEOUT",
    "AGENT_TIMEOUT_LONG",
    "APPROVAL_TITLE_MAX_LENGTH",
    "BOX_DRAWING",
    "CARD_BACKEND_MAX_LENGTH",
    "CARD_DESC_MAX_LENGTH",
    "CARD_HAT_MAX_LENGTH",
    "CARD_ID_MAX_LENGTH",
    "CARD_REVIEW_MAX_LENGTH",
    "CARD_TITLE_LINE_WIDTH",
    "COLUMN_ORDER",
    "DEBUG_BUILD",
    "DIFF_MAX_LENGTH",
    "KAGAN_BRANCH_CONFIGURED_KEY",
    "KAGAN_GENERATED_PATTERNS",
    "KAGAN_LOGO",
    "KAGAN_LOGO_SMALL",
    "MCP_CAPABILITY_CHOICES",
    "MCP_CAPABILITY_MAINTAINER",
    "MCP_CAPABILITY_OPERATOR",
    "MCP_CAPABILITY_PAIR_WORKER",
    "MCP_CAPABILITY_PLANNER",
    "MCP_CAPABILITY_VIEWER",
    "MCP_DEFAULT_FULL_CAPABILITY",
    "MCP_DEFAULT_READONLY_CAPABILITY",
    "MCP_DEFAULT_SESSION_ID",
    "MCP_FALLBACK_CAPABILITY",
    "MCP_IDENTITY_ADMIN",
    "MCP_IDENTITY_CHOICES",
    "MCP_IDENTITY_DEFAULT",
    "MESSAGE_BUFFER",
    "MIN_SCREEN_HEIGHT",
    "MIN_SCREEN_WIDTH",
    "MODAL_TITLE_MAX_LENGTH",
    "NOTIFICATION_TITLE_MAX_LENGTH",
    "PRIORITY_LABELS",
    "RESPONSE_BUFFER",
    "SCRATCHPAD_LIMIT",
    "SHUTDOWN_TIMEOUT",
    "STATUS_LABELS",
    "SUBPROCESS_LIMIT",
    "default_config_path",
    "default_db_path",
    "get_database_path",
]
