"""Shared Textual theme definition for Kagan."""

from __future__ import annotations

from textual.theme import Theme

KAGAN_THEME = Theme(
    name="kagan",
    primary="#d4a84b",
    secondary="#3fb58e",
    accent="#C27C4E",
    foreground="#FFFFFF",
    background="#000000",
    surface="#0C0C0A",
    panel="#141210",
    warning="#e6c07b",
    error="#e85535",
    success="#3fb58e",
    dark=True,
    variables={
        "border": "#1C1A16",
        "border-blurred": "#1C1A1680",
        "text-muted": "#8A8278",
        "text-disabled": "#8A827850",
        "input-cursor-foreground": "#000000",
        "input-cursor-background": "#d4a84b",
        "input-selection-background": "#d4a84b33",
        "scrollbar": "#1C1A16",
        "scrollbar-hover": "#d4a84b",
        "scrollbar-active": "#C27C4E",
        "link-color": "#6fa3d4",
        "link-hover-color": "#3fb58e",
        "footer-key-foreground": "#8A8278",
        "footer-key-background": "transparent",
        "footer-description-foreground": "#8A827880",
        "button-foreground": "#FFFFFF",
        "button-color-foreground": "#000000",
    },
)


KAGAN_THEME_256 = Theme(
    name="kagan-256",
    primary="#d7af5f",
    secondary="#5faf87",
    accent="#d7875f",
    foreground="#ffffff",
    background="#000000",
    surface="#1c1c1c",
    panel="#262626",
    warning="#d7af87",
    error="#d75f5f",
    success="#5faf87",
    dark=True,
    variables={
        "border": "#303030",
        "border-blurred": "#30303080",
        "text-muted": "#8a8a8a",
        "text-disabled": "#8a8a8a80",
        "input-cursor-foreground": "#000000",
        "input-cursor-background": "#d7af5f",
        "input-selection-background": "#d7af5f33",
        "scrollbar": "#303030",
        "scrollbar-hover": "#d7af5f",
        "scrollbar-active": "#d7875f",
        "link-color": "#5fafd7",
        "link-hover-color": "#5faf87",
        "footer-key-foreground": "#8a8a8a",
        "footer-key-background": "transparent",
        "footer-description-foreground": "#8a8a8a80",
        "button-foreground": "#ffffff",
        "button-color-foreground": "#000000",
    },
)
