"""Widget components for Kagan TUI."""

from kagan.tui.ui.widgets.base import (
    AcceptanceCriteriaArea,
    AgentBackendSelect,
    DescriptionArea,
    PrioritySelect,
    StatusSelect,
    TaskTypeSelect,
    TitleInput,
)
from kagan.tui.ui.widgets.card import TaskCard
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.chat_panel import ChatPanel
from kagan.tui.ui.widgets.column import KanbanColumn
from kagan.tui.ui.widgets.diff_browser import DiffBrowserWidget
from kagan.tui.ui.widgets.header import KaganHeader
from kagan.tui.ui.widgets.peek_overlay import PeekOverlay
from kagan.tui.ui.widgets.permission_prompt import PermissionPrompt
from kagan.tui.ui.widgets.plan_approval import PlanApprovalWidget
from kagan.tui.ui.widgets.plan_display import PlanDisplay
from kagan.tui.ui.widgets.search_bar import SearchBar
from kagan.tui.ui.widgets.slash_complete import SlashComplete
from kagan.tui.ui.widgets.status_bar import StatusBar
from kagan.tui.ui.widgets.streaming_markdown import StreamingMarkdown, UserInput
from kagan.tui.ui.widgets.streaming_output import StreamingOutput
from kagan.tui.ui.widgets.tool_call import ToolCall
from kagan.tui.ui.widgets.workspace_repos import WorkspaceReposWidget

__all__ = [
    "AcceptanceCriteriaArea",
    "AgentBackendSelect",
    "ChatOverlay",
    "ChatPanel",
    "DescriptionArea",
    "DiffBrowserWidget",
    "KaganHeader",
    "KanbanColumn",
    "PeekOverlay",
    "PermissionPrompt",
    "PlanApprovalWidget",
    "PlanDisplay",
    "PrioritySelect",
    "SearchBar",
    "SlashComplete",
    "StatusBar",
    "StatusSelect",
    "StreamingMarkdown",
    "StreamingOutput",
    "TaskCard",
    "TaskTypeSelect",
    "TitleInput",
    "ToolCall",
    "UserInput",
    "WorkspaceReposWidget",
]
