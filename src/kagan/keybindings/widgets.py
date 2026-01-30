from __future__ import annotations

from kagan.keybindings.registry import KeyBindingDef

# Permission Prompt Widget
PERMISSION_PROMPT_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef("y", "allow_once", "Allow once", "modal", show_in_footer=False),
    KeyBindingDef("a", "allow_always", "Allow always", "modal", show_in_footer=False),
    KeyBindingDef("n", "deny", "Deny", "modal", show_in_footer=False),
    KeyBindingDef("escape", "deny", "Deny", "modal", show_in_footer=False),
]
