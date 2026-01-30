from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.binding import Binding, BindingType


@dataclass(frozen=True)
class KeyBindingDef:
    """Definition for a keybinding in the registry.

    Attributes:
        key: The key combination (e.g., "h", "ctrl+s", "slash")
        action: The action name to trigger (e.g., "focus_left", "save")
        description: Short label for Textual footer
        category: Grouping category: navigation, primary, leader, context, global, modal
        show_in_footer: Whether to show in Textual footer (default True)
        key_display: Override display text (e.g., "/" for "slash")
        help_text: Verbose description for help modal (falls back to description if None)
        context: Usage context hint (e.g., "REVIEW tickets only")
        leader_sequence: Whether this is part of leader key sequence (g+key)
        priority: Binding priority for Textual (default False)
        help_group: Grouping for help display (e.g., "vim_nav" to combine h/Left)
    """

    key: str
    action: str
    description: str
    category: str
    show_in_footer: bool = True
    key_display: str | None = None
    help_text: str | None = None
    context: str | None = None
    leader_sequence: bool = False
    priority: bool = False
    help_group: str | None = None

    @property
    def help_description(self) -> str:
        """Get the help description, with context appended if present."""
        text = self.help_text or self.description
        if self.context and self.context not in text:
            text = f"{text} ({self.context})"
        return text

    @property
    def display_key(self) -> str:
        """Get the display key for help/UI."""
        return self.key_display or self.key

    def to_binding(self) -> Binding:
        """Convert to a Textual Binding object."""
        from textual.binding import Binding

        return Binding(
            self.key,
            self.action,
            self.description,
            show=self.show_in_footer,
            key_display=self.key_display,
            priority=self.priority,
        )


def to_textual_bindings(bindings: list[KeyBindingDef]) -> list[BindingType]:
    """Convert a list of KeyBindingDef to Textual Binding objects."""
    return [b.to_binding() for b in bindings]


def get_bindings_for_category(
    bindings: list[KeyBindingDef],
    category: str,
) -> list[KeyBindingDef]:
    """Filter bindings by category."""
    return [b for b in bindings if b.category == category]


def get_bindings_for_help(
    bindings: list[KeyBindingDef],
    category: str,
) -> list[KeyBindingDef]:
    """Get bindings for help display, excluding utility bindings with no description."""
    return [
        b for b in bindings if b.category == category and b.description and b.category != "utility"
    ]


def generate_leader_hint(bindings: list[KeyBindingDef]) -> str:
    """Generate the leader key hint string from leader bindings."""
    leader_bindings = [b for b in bindings if b.leader_sequence]
    if not leader_bindings:
        return ""

    parts = []
    for b in leader_bindings:
        key = b.display_key
        # Extract short action description
        desc = b.description.split()[0] if b.description else b.action
        parts.append(f"{key}={desc}")

    return " LEADER: " + " ".join(parts) + " | Esc=Cancel"


def get_binding_by_action(
    bindings: list[KeyBindingDef],
    action: str,
) -> KeyBindingDef | None:
    """Find first binding matching an action name.

    Args:
        bindings: List of keybinding definitions to search
        action: The action name to find (e.g., "new_ticket", "focus_left")

    Returns:
        The matching KeyBindingDef, or None if not found
    """
    for b in bindings:
        if b.action == action:
            return b
    return None


def get_key_for_action(
    bindings: list[KeyBindingDef],
    action: str,
    default: str = "?",
) -> str:
    """Get the display key for an action.

    Args:
        bindings: List of keybinding definitions to search
        action: The action name to find
        default: Value to return if action not found (default: "?")

    Returns:
        The display key (using key_display if set, else raw key), or default if not found
    """
    b = get_binding_by_action(bindings, action)
    return b.display_key if b else default
