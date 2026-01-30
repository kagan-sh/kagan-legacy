from __future__ import annotations

from kagan.keybindings.registry import KeyBindingDef

# Approval Screen
APPROVAL_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "cancel", "Cancel", "modal"),
    KeyBindingDef("enter", "approve", "Approve", "modal"),
    KeyBindingDef("t", "toggle_type", "Toggle Type", "modal"),
]

# Planner Screen
PLANNER_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "to_board", "Go to Board", "primary"),
    KeyBindingDef("ctrl+c", "cancel", "Cancel", "utility", show_in_footer=False),
    KeyBindingDef("ctrl+e", "refine", "Enhance", "primary", priority=True),
]

# Ticket Editor Screen
TICKET_EDITOR_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "cancel", "Cancel", "modal"),
    KeyBindingDef("ctrl+s", "finish", "Finish Editing", "modal"),
]

# Troubleshooting Screen
TROUBLESHOOTING_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("q", "quit", "Quit", "global"),
    KeyBindingDef("escape", "quit", "Quit", "global"),
    KeyBindingDef("enter", "quit", "Quit", "global"),
]

# Welcome Screen
WELCOME_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("escape", "skip", "Continue", "primary"),
]
