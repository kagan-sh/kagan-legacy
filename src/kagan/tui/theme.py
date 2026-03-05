"""Shared Textual theme definitions for Kagan — premium night theme."""

from textual.theme import Theme

__all__ = [
    "KAGAN_THEME",
    "KAGAN_THEME_256",
]

KAGAN_THEME = Theme(
    name="kagan",
    primary="#d4a84b",
    secondary="#3fb58e",
    accent="#C27C4E",
    foreground="#FFFFFF",
    background="#0B0A09",
    surface="#151311",
    panel="#1E1B17",
    warning="#e6c07b",
    error="#e85535",
    success="#3fb58e",
    dark=True,
    variables={
        "border": "#2A251F",
        "border-blurred": "#2A251F80",
        "text-muted": "#B5AC9F",
        "text-disabled": "#A9A094",
        # Semantic status aliases.
        "status-running": "#3fb58e",
        "status-success": "#3fb58e",
        "status-warning": "#e6c07b",
        "status-error": "#e85535",
        "status-idle": "#B5AC9F",
        "status-bar-background": "#0B0A09",
        "status-bar-border": "#2A251F",
        "startup-error-surface": "#151311",
        "startup-error-border": "#e85535",
        "startup-error-detail-surface": "#0B0A09",
        "startup-error-message-surface": "#1E1B17",
        # Priority badges.
        "priority-high": "#e85535",
        "priority-high-text": "#0B0A09",
        "priority-medium": "#e6c07b",
        "priority-medium-text": "#0B0A09",
        "priority-low": "#2A251F",
        "priority-low-text": "#B5AC9F",
        # Badge text on colored backgrounds.
        "success-text": "#0B0A09",
        "error-text": "#0B0A09",
        "warning-text": "#0B0A09",
        # Kanban.
        "kanban-background": "#0F0E0C",
        # Input.
        "input-cursor-foreground": "#000000",
        "input-cursor-background": "#d4a84b",
        "input-selection-background": "#d4a84b33",
        # Scrollbar.
        "scrollbar": "#2A251F",
        "scrollbar-hover": "#d4a84b",
        "scrollbar-active": "#C27C4E",
        # Links.
        "link-color": "#6fa3d4",
        "link-hover-color": "#3fb58e",
        # Footer.
        "footer-key-foreground": "#C2B9AD",
        "footer-key-background": "transparent",
        "footer-description-foreground": "#B5AC9F",
    },
)

KAGAN_THEME_256 = Theme(
    name="kagan-256",
    primary="#d7af5f",
    secondary="#5faf87",
    accent="#d7875f",
    foreground="#ffffff",
    background="#141414",
    surface="#242424",
    panel="#303030",
    warning="#d7af87",
    error="#d75f5f",
    success="#5faf87",
    dark=True,
    variables={
        "border": "#353535",
        "border-blurred": "#35353580",
        "text-muted": "#bdbdbd",
        "text-disabled": "#b0b0b0",
        # Semantic status aliases.
        "status-running": "#5faf87",
        "status-success": "#5faf87",
        "status-warning": "#d7af87",
        "status-error": "#d75f5f",
        "status-idle": "#bdbdbd",
        "status-bar-background": "#141414",
        "status-bar-border": "#353535",
        "startup-error-surface": "#242424",
        "startup-error-border": "#d75f5f",
        "startup-error-detail-surface": "#141414",
        "startup-error-message-surface": "#303030",
        # Priority badges.
        "priority-high": "#d75f5f",
        "priority-high-text": "#141414",
        "priority-medium": "#d7af87",
        "priority-medium-text": "#141414",
        "priority-low": "#353535",
        "priority-low-text": "#bdbdbd",
        # Badge text on colored backgrounds.
        "success-text": "#141414",
        "error-text": "#141414",
        "warning-text": "#141414",
        # Kanban.
        "kanban-background": "#1e1e1e",
        # Input.
        "input-cursor-foreground": "#000000",
        "input-cursor-background": "#d7af5f",
        "input-selection-background": "#d7af5f33",
        # Scrollbar.
        "scrollbar": "#353535",
        "scrollbar-hover": "#d7af5f",
        "scrollbar-active": "#d7875f",
        # Links.
        "link-color": "#5fafd7",
        "link-hover-color": "#5faf87",
        # Footer.
        "footer-key-foreground": "#d0d0d0",
        "footer-key-background": "transparent",
        "footer-description-foreground": "#bdbdbd",
    },
)
