"""Compatibility workarounds for Textual versions used by Kagan."""

from typing import Any

from textual.widgets._select import SelectOverlay

_PATCH_FLAG = "_kagan_select_overlay_move_page_patched"


def _patch_select_overlay_page_navigation() -> None:
    original_move_page = SelectOverlay._move_page
    if getattr(original_move_page, _PATCH_FLAG, False):
        return

    def _safe_move_page(self: SelectOverlay, direction: Any) -> None:
        options = getattr(self, "_options", None)
        if not options:
            return
        highlighted = self.highlighted
        anchor = highlighted if isinstance(highlighted, int) else 0
        index_to_line = getattr(self, "_index_to_line", {})
        if anchor not in index_to_line:
            if direction < 0:
                self.action_first()
            else:
                self.action_last()
            return
        try:
            original_move_page(self, direction)
        except KeyError:
            # Defensive guard for transient stale index maps on overlay updates.
            if direction < 0:
                self.action_first()
            else:
                self.action_last()

    setattr(_safe_move_page, _PATCH_FLAG, True)
    SelectOverlay._move_page = _safe_move_page


def apply_textual_compat_workarounds() -> None:
    """Apply runtime compatibility fixes for known Textual edge cases."""
    _patch_select_overlay_page_navigation()


__all__ = ["apply_textual_compat_workarounds"]
