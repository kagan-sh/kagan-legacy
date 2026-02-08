"""Base modal class for Kagan modals."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.screen import ModalScreen

if TYPE_CHECKING:
    from kagan.app import KaganApp
    from kagan.bootstrap import AppContext


class KaganModalScreen[ResultT](ModalScreen[ResultT]):
    @property
    def kagan_app(self) -> KaganApp:
        """Get the typed KaganApp instance."""
        return cast("KaganApp", self.app)

    @property
    def ctx(self) -> AppContext:
        """Get the application context for service access."""
        app = self.kagan_app
        try:
            return app.ctx
        except (AssertionError, AttributeError):
            if hasattr(app, "_ctx") and app._ctx is not None:
                return app._ctx
            msg = "AppContext not initialized. Ensure bootstrap has completed."
            raise RuntimeError(msg) from None
