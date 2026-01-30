from __future__ import annotations

from kagan.keybindings.registry import KeyBindingDef

# Agent Output Modal
AGENT_OUTPUT_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("y", "copy", "Copy", "modal", help_text="Copy content to clipboard"),
    KeyBindingDef("escape", "close", "Close", "modal"),
    KeyBindingDef("c", "cancel_agent", "Cancel Agent", "modal"),
]

# Confirm Modal
CONFIRM_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("y", "confirm", "Yes", "modal"),
    KeyBindingDef("n", "cancel", "No", "modal"),
    KeyBindingDef("escape", "cancel", "Cancel", "modal"),
]

# Description Editor Modal
DESCRIPTION_EDITOR_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "done", "Done", "modal"),
    KeyBindingDef("ctrl+s", "done", "Save", "modal"),
]

# Diff Modal
DIFF_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("y", "copy", "Copy", "modal", help_text="Copy content to clipboard"),
    KeyBindingDef("escape", "close", "Close", "modal"),
]

# Duplicate Ticket Modal
DUPLICATE_TICKET_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "cancel", "Cancel", "modal"),
    KeyBindingDef("ctrl+s", "create", "Create", "modal"),
]

# Help Modal
HELP_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "close", "Close", "modal"),
    KeyBindingDef("q", "close", "Close", "modal", show_in_footer=False),
]

# Rejection Input Modal
REJECTION_INPUT_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "cancel", "Cancel", "modal"),
    KeyBindingDef("ctrl+s", "submit", "Submit", "modal"),
]

# Review Modal
REVIEW_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("y", "copy", "Copy", "modal", help_text="Copy content to clipboard"),
    KeyBindingDef("escape", "close", "Close", "modal"),
    KeyBindingDef("a", "approve", "Approve", "modal"),
    KeyBindingDef("r", "reject", "Reject", "modal"),
    KeyBindingDef("g", "generate_review", "Generate AI Review", "modal"),
]

# Settings Modal
SETTINGS_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "cancel", "Cancel", "modal"),
    KeyBindingDef("ctrl+s", "save", "Save", "modal"),
]

# Ticket Details Modal
TICKET_DETAILS_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("y", "copy", "Copy", "modal", help_text="Copy content to clipboard"),
    KeyBindingDef("escape", "close_or_cancel", "Close/Cancel", "modal"),
    KeyBindingDef("e", "toggle_edit", "Edit", "modal"),
    KeyBindingDef("d", "delete", "Delete", "modal"),
    KeyBindingDef("f", "expand_description", "Expand", "modal"),
    KeyBindingDef("ctrl+s", "save", "Save", "modal", show_in_footer=False),
]

# Tmux Gateway Modal
TMUX_GATEWAY_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("enter", "proceed", "Continue", "modal", priority=True),
    KeyBindingDef("escape", "cancel", "Cancel", "modal", priority=True),
    KeyBindingDef("s", "skip_future", "Don't show again", "modal", priority=True),
]
