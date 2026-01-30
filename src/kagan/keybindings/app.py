from __future__ import annotations

from kagan.keybindings.registry import KeyBindingDef

APP_BINDINGS: list[KeyBindingDef] = [
    KeyBindingDef(
        "q",
        "quit",
        "Quit",
        "global",
        help_text="Quit application",
    ),
    # F1 is the primary help trigger - works even when TextArea/Input is focused
    # because function keys don't conflict with text input
    KeyBindingDef(
        "f1",
        "show_help",
        "Help",
        "global",
        key_display="F1",
        priority=True,
        help_text="Open this help screen",
    ),
    # ? is a secondary help trigger for vim-style users
    # Only works when not in a text input (no priority, so TextArea wins)
    KeyBindingDef(
        "question_mark",
        "show_help",
        "",
        "global",
        show_in_footer=False,
        key_display="?",
        help_text="Open this help screen",
    ),
    KeyBindingDef(
        "ctrl+p",
        "command_palette",
        "Palette",
        "global",
        show_in_footer=False,
        help_text="Open command palette",
    ),
]
