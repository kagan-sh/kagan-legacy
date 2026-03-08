"""Compatibility workarounds for Textual versions used by Kagan."""

from typing import Any

from loguru import logger
from textual.widgets._select import SelectOverlay

# Re-export from core so existing TUI imports continue to work.
from kagan.core._asyncio_compat import install_asyncio_subprocess_exception_filter

_PATCH_FLAG = "_kagan_select_overlay_move_page_patched"


def _patch_select_overlay_page_navigation() -> None:
    original_move_page = SelectOverlay._move_page
    if getattr(original_move_page, _PATCH_FLAG, False):
        return

    def _safe_move_page(self: SelectOverlay, direction: Any) -> None:
        # Guard 1: No options at all -> nothing to navigate
        options = getattr(self, "_options", None)
        if not options:
            return
        # Guard 2: No lines rendered yet -> cannot compute page offset
        lines = getattr(self, "_lines", None)
        if not lines:
            return
        # Guard 3: Index map empty or missing highlighted key -> fallback to boundary
        highlighted = self.highlighted
        anchor = highlighted if isinstance(highlighted, int) else 0
        index_to_line = getattr(self, "_index_to_line", None)
        if not index_to_line or anchor not in index_to_line:
            if direction < 0:
                self.action_first()
            else:
                self.action_last()
            return
        try:
            original_move_page(self, direction)
        except KeyError:
            # Defensive guard for transient stale index maps on overlay updates.
            logger.debug(
                "Caught KeyError in SelectOverlay._move_page, falling back to boundary action"
            )
            if direction < 0:
                self.action_first()
            else:
                self.action_last()

    setattr(_safe_move_page, _PATCH_FLAG, True)
    SelectOverlay._move_page = _safe_move_page


def apply_textual_compat_workarounds() -> None:
    """Apply runtime compatibility fixes for known Textual edge cases."""
    _patch_select_overlay_page_navigation()


__all__ = ["apply_textual_compat_workarounds", "install_asyncio_subprocess_exception_filter"]
