"""Base screen class for Kagan screens."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.screen import Screen

if TYPE_CHECKING:
    from kagan.app import KaganApp


class KaganScreen(Screen):
    """Base screen with typed app access."""

    @property
    def kagan_app(self) -> KaganApp:
        """Get the typed KaganApp instance."""
        return cast("KaganApp", self.app)
