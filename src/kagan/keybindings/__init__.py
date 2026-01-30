"""Keybindings registry for Kagan TUI application."""

from __future__ import annotations

from kagan.keybindings.app import APP_BINDINGS
from kagan.keybindings.kanban import KANBAN_BINDINGS, KANBAN_LEADER_BINDINGS
from kagan.keybindings.modals import (
    AGENT_OUTPUT_BINDINGS,
    CONFIRM_BINDINGS,
    DESCRIPTION_EDITOR_BINDINGS,
    DIFF_BINDINGS,
    DUPLICATE_TICKET_BINDINGS,
    HELP_BINDINGS,
    REJECTION_INPUT_BINDINGS,
    REVIEW_BINDINGS,
    SETTINGS_BINDINGS,
    TICKET_DETAILS_BINDINGS,
    TMUX_GATEWAY_BINDINGS,
)
from kagan.keybindings.registry import (
    KeyBindingDef,
    generate_leader_hint,
    get_binding_by_action,
    get_bindings_for_category,
    get_bindings_for_help,
    get_key_for_action,
    to_textual_bindings,
)
from kagan.keybindings.screens import (
    APPROVAL_BINDINGS,
    PLANNER_BINDINGS,
    TICKET_EDITOR_BINDINGS,
    TROUBLESHOOTING_BINDINGS,
    WELCOME_BINDINGS,
)
from kagan.keybindings.widgets import PERMISSION_PROMPT_BINDINGS

__all__ = [
    "AGENT_OUTPUT_BINDINGS",
    "APPROVAL_BINDINGS",
    "APP_BINDINGS",
    "CONFIRM_BINDINGS",
    "DESCRIPTION_EDITOR_BINDINGS",
    "DIFF_BINDINGS",
    "DUPLICATE_TICKET_BINDINGS",
    "HELP_BINDINGS",
    "KANBAN_BINDINGS",
    "KANBAN_LEADER_BINDINGS",
    "PERMISSION_PROMPT_BINDINGS",
    "PLANNER_BINDINGS",
    "REJECTION_INPUT_BINDINGS",
    "REVIEW_BINDINGS",
    "SETTINGS_BINDINGS",
    "TICKET_DETAILS_BINDINGS",
    "TICKET_EDITOR_BINDINGS",
    "TMUX_GATEWAY_BINDINGS",
    "TROUBLESHOOTING_BINDINGS",
    "WELCOME_BINDINGS",
    "KeyBindingDef",
    "generate_leader_hint",
    "get_binding_by_action",
    "get_bindings_for_category",
    "get_bindings_for_help",
    "get_key_for_action",
    "to_textual_bindings",
]
