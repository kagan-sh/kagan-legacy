"""Canonical Rich Style palette for the kg chat REPL.

All hex values are sourced from the ``.tui`` scope in the Kagan Design System
(``kagan-design-system/project/colors_and_type.css``, lines 278-320).  This
module is the single source of truth — every other module in ``cli.chat``
**must** import from here instead of constructing inline ``Style(color=...)``
or hard-coding hex strings.

Truecolor auto-detection
------------------------
Call ``supports_truecolor()`` to decide which style set to use.  The function
checks ``COLORTERM`` first (``truecolor`` / ``24bit``), then ``TERM`` for the
``direct`` marker, and respects ``NO_COLOR``.  When truecolor is unavailable,
the fallback styles use the eight named ANSI colours that every terminal
emulator supports.

Usage
-----
::

    from kagan.cli.chat._palette import P, supports_truecolor

    console.print("done", style=P.rail_running)
    console.print("[bold]error[/bold]", style=P.rail_error)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from rich.style import Style

# ---------------------------------------------------------------------------
# Truecolor detection
# ---------------------------------------------------------------------------


def supports_truecolor() -> bool:
    """Return True when the terminal is known to support 24-bit colour."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    colorterm = os.environ.get("COLORTERM", "").casefold()
    term = os.environ.get("TERM", "").casefold()
    return "truecolor" in colorterm or "24bit" in colorterm or "direct" in term


# ---------------------------------------------------------------------------
# Canonical hex tokens — .tui scope (design-system source of truth)
# ---------------------------------------------------------------------------

# Surfaces
_BG = "#0B0A09"
_SURFACE_1 = "#151311"
_SURFACE_2 = "#1E1B17"
_SURFACE_3 = "#2A251F"

# Foreground
_FG = "#FFFFFF"
_FG_2 = "#C2B9AD"
_FG_MUTED = "#B5AC9F"
_FG_DIM = "#A9A094"

# Accent (amber phosphor) — prompt glyph, active badges, primary CTA
_PRIMARY = "#d4a84b"

# Rail / semantic signal
_RAIL_RUNNING = "#3fb58e"  # sage — success, running, done checks
_RAIL_WARNING = "#e6c07b"  # warning amber
_RAIL_REVIEW = "#c27c4e"  # review / in-progress orange
_RAIL_IDLE = "#B5AC9F"  # muted idle
_RAIL_ERROR = "#e85535"  # danger red

# Supplemental colours used in the REPL but not in the token table
_PLAN_BLUE = "#60a5fa"  # plan mode prompt — cool blue
_META = "#9ca3af"  # completion meta text
_META_CURRENT = "#7dd3fc"  # completion meta current
_THINKING = "#fbbf24"  # thinking animation — warm yellow
_ACCENT_SOFT_BG = "#1D3A31"  # completion menu current background


# ---------------------------------------------------------------------------
# Truecolor palette dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Palette:
    """Rich ``Style`` objects keyed by canonical token name."""

    # ── Surfaces ─────────────────────────────────────────────────────────────
    bg: Style
    surface: Style
    panel: Style

    # ── Foreground ────────────────────────────────────────────────────────────
    fg: Style
    fg_2: Style
    fg_muted: Style
    fg_dim: Style

    # ── Accent (amber) ────────────────────────────────────────────────────────
    primary: Style
    primary_bold: Style

    # ── Rail / semantic ───────────────────────────────────────────────────────
    rail_running: Style
    rail_warning: Style
    rail_review: Style
    rail_idle: Style
    rail_error: Style

    # ── Mode badges ───────────────────────────────────────────────────────────
    mode_auto: Style  # ORCHESTRATOR / AUTO — amber
    mode_pair: Style  # PAIR — info blue (#6fa3d4 is the canonical pair colour)
    mode_general: Style  # GENERAL — sage
    mode_task: Style  # TASK — muted

    # ── Prompt / UI chrome ────────────────────────────────────────────────────
    prompt_glyph: Style  # $ and > in amber bold
    plan_glyph: Style  # ◇ in plan mode — cool blue
    thinking: Style  # streaming indicator — warm yellow

    # ── Completion menu ───────────────────────────────────────────────────────
    completion_bg: Style
    completion_fg: Style
    completion_current_bg: Style
    completion_meta: Style
    completion_meta_current: Style


def _build_truecolor_palette() -> _Palette:
    return _Palette(
        bg=Style(bgcolor=_BG),
        surface=Style(bgcolor=_SURFACE_1),
        panel=Style(bgcolor=_SURFACE_2),
        fg=Style(color=_FG),
        fg_2=Style(color=_FG_2),
        fg_muted=Style(color=_FG_MUTED),
        fg_dim=Style(color=_FG_DIM, dim=True),
        primary=Style(color=_PRIMARY),
        primary_bold=Style(color=_PRIMARY, bold=True),
        rail_running=Style(color=_RAIL_RUNNING),
        rail_warning=Style(color=_RAIL_WARNING),
        rail_review=Style(color=_RAIL_REVIEW),
        rail_idle=Style(color=_RAIL_IDLE),
        rail_error=Style(color=_RAIL_ERROR),
        mode_auto=Style(color=_PRIMARY, bold=True),
        mode_pair=Style(color="#6fa3d4", bold=True),
        mode_general=Style(color=_RAIL_RUNNING, bold=True),
        mode_task=Style(color=_FG_MUTED, bold=True),
        prompt_glyph=Style(color=_PRIMARY, bold=True),
        plan_glyph=Style(color=_PLAN_BLUE, bold=True),
        thinking=Style(color=_THINKING, bold=True),
        completion_bg=Style(bgcolor=_SURFACE_1, color=_FG_MUTED),
        completion_fg=Style(bgcolor=_SURFACE_1, color=_FG_MUTED),
        completion_current_bg=Style(bgcolor=_ACCENT_SOFT_BG, color=_FG, bold=True),
        completion_meta=Style(bgcolor=_SURFACE_1, color=_META),
        completion_meta_current=Style(bgcolor=_ACCENT_SOFT_BG, color=_META_CURRENT),
    )


def _build_ansi_palette() -> _Palette:
    """256-colour / named-ANSI fallback palette.

    Rich ``Style`` objects use plain CSS color names (``"yellow"``, ``"green"``),
    not the ``ansi*`` prefix used by prompt_toolkit.
    """
    return _Palette(
        bg=Style(),
        surface=Style(),
        panel=Style(),
        fg=Style(),
        fg_2=Style(),
        fg_muted=Style(dim=True),
        fg_dim=Style(dim=True),
        primary=Style(color="yellow"),
        primary_bold=Style(color="yellow", bold=True),
        rail_running=Style(color="green"),
        rail_warning=Style(color="yellow"),
        rail_review=Style(color="yellow"),
        rail_idle=Style(dim=True),
        rail_error=Style(color="red"),
        mode_auto=Style(color="yellow", bold=True),
        mode_pair=Style(color="cyan", bold=True),
        mode_general=Style(color="green", bold=True),
        mode_task=Style(dim=True, bold=True),
        prompt_glyph=Style(color="yellow", bold=True),
        plan_glyph=Style(color="blue", bold=True),
        thinking=Style(color="yellow", bold=True),
        completion_bg=Style(),
        completion_fg=Style(),
        completion_current_bg=Style(color="black", bgcolor="yellow", bold=True),
        completion_meta=Style(dim=True),
        completion_meta_current=Style(color="cyan"),
    )


# ---------------------------------------------------------------------------
# Module-level singleton — resolved once at import time.
# Re-call ``_build_*`` only in tests that patch ``COLORTERM``.
# ---------------------------------------------------------------------------

P: _Palette = _build_truecolor_palette() if supports_truecolor() else _build_ansi_palette()

# ---------------------------------------------------------------------------
# prompt_toolkit style-rule dicts
# (prompt_toolkit uses string-keyed dicts, not Rich Style objects)
# ---------------------------------------------------------------------------

#: Hex tokens for use in prompt_toolkit ``Style.from_dict`` maps.
#: Keyed identically to ``_REPL_COLORS`` so callers can migrate key-by-key.
PROMPT_COLORS: dict[str, str] = {
    "bg": _BG,
    "surface": _SURFACE_1,
    "panel": _SURFACE_2,
    "text": _FG,
    "text_muted": _FG_MUTED,
    "text_soft": _FG_2,
    # prompt glyph uses primary amber (not sage), per design system rule 5
    "accent": _PRIMARY,
    "accent_soft": _ACCENT_SOFT_BG,
    "primary": _PRIMARY,
    "separator": _SURFACE_3,
    "plan": _PLAN_BLUE,
    "meta": _META,
    "meta_current": _META_CURRENT,
    "thinking": _THINKING,
    # sage kept for other semantic uses (e.g. running indicators)
    "rail_running": _RAIL_RUNNING,
}

PROMPT_COLORS_ANSI: dict[str, str] = {
    # In 8-colour terminals the prompt glyph keeps the legacy ansigreen
    # for maximum compatibility; truecolor terminals get the canonical amber.
    "accent": "ansigreen",
    "muted": "ansibrightblack",
    "primary": "ansiyellow",
}

__all__ = [
    "PROMPT_COLORS",
    "PROMPT_COLORS_ANSI",
    "P",
    "supports_truecolor",
]
