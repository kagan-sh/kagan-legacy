"""SessionList — unified session picker bar.

Shows one row per session (orchestrator, general, task worker/reviewer).
Queries ``client.list_session_items(project_id)``.

Keys:
  Enter  — fire ``SessionSelected`` message
  s      — fire ``SessionStopRequested`` (if ``can_stop``)
  x      — fire ``SessionCloseRequested`` (if ``can_close``)
  Esc    — fire ``FocusInput``
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from textual import on
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from kagan.tui.keybindings import SESSION_LIST_BINDINGS

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult

    from kagan.core._session_items import SessionItem

# Glyph per session type / role
_TYPE_GLYPH: dict[str | None, str] = {
    "orchestrator": "◆",
    "general": "◇",
    "worker": "▶",
    "reviewer": "◈",
}
_DEFAULT_TYPE_GLYPH = "·"

# Status indicator glyph
_STATUS_GLYPH: dict[str, str] = {
    "running": "◐",
    "pending": "◐",
    "idle": "●",
    "completed": "✓",
    "done": "✓",
    "failed": "✗",
    "cancelled": "⊘",
}
_DEFAULT_STATUS_GLYPH = "·"

_EMPTY_ROW_LABEL = "no sessions"


def _type_glyph(item: SessionItem) -> str:
    if item.type == "task" and item.role:
        return _TYPE_GLYPH.get(item.role.lower(), _DEFAULT_TYPE_GLYPH)
    return _TYPE_GLYPH.get(item.type, _DEFAULT_TYPE_GLYPH)


def _status_glyph(status: str) -> str:
    return _STATUS_GLYPH.get(status.lower(), _DEFAULT_STATUS_GLYPH)


def _row_label(item: SessionItem) -> str:
    glyph = _type_glyph(item)
    status = _status_glyph(item.status)
    if item.type == "task":
        role_label = item.role or "agent"
        title = item.title[:28] + "…" if len(item.title) > 29 else item.title
        return f"{status} {glyph} {title} · {role_label}"
    # orchestrator or general
    label = item.title[:28] + "…" if len(item.title) > 29 else item.title
    backend = f" · {item.backend}" if item.backend else ""
    return f"{status} {glyph} {label}{backend}"


class SessionList(Vertical):
    """Compact list of all sessions (chat + task).

    Parameters
    ----------
    on_select:
        Callback fired when the user selects a session.  Receives the
        ``SessionItem``.
    poll_interval:
        Seconds between DB polls.  Set to ``0`` in tests to disable polling.
    """

    BINDINGS = SESSION_LIST_BINDINGS

    DEFAULT_CSS = ""

    # Message fired when the user presses Enter on a row
    class SessionSelected(Message):
        def __init__(self, item: SessionItem) -> None:
            super().__init__()
            self.item = item

    # Message fired when the user presses 's' on a stoppable row
    class SessionStopRequested(Message):
        def __init__(self, item: SessionItem) -> None:
            super().__init__()
            self.item = item

    # Message fired when the user presses 'x' on a closable row
    class SessionCloseRequested(Message):
        def __init__(self, item: SessionItem) -> None:
            super().__init__()
            self.item = item

    # Message fired when Esc is pressed — overlay returns focus to input
    class FocusInput(Message):
        pass

    _items: reactive[list[SessionItem]] = reactive([], recompose=True)

    def watch__items(self, items: list[SessionItem]) -> None:
        """Sync the has-sessions CSS class whenever the item list changes."""
        self.set_class(bool(items), "has-sessions")

    def __init__(
        self,
        *,
        on_select: Callable[[SessionItem], None] | None = None,
        poll_interval: float = 2.0,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._on_select = on_select
        self._poll_interval = poll_interval
        self._poll_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        items = self._items
        if not items:
            empty = ListItem(Static(_EMPTY_ROW_LABEL), classes="-empty")
            empty.can_focus = False
            yield ListView(empty, id="session-list")
        else:
            list_items = [
                ListItem(
                    Static(
                        _row_label(item),
                        id=f"session-row-{re.sub(r'[^a-zA-Z0-9_-]', '-', item.id[:8])}",
                    ),
                    id=f"session-item-{re.sub(r'[^a-zA-Z0-9_-]', '-', item.id[:8])}",
                )
                for item in items
            ]
            yield ListView(*list_items, id="session-list")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        await self._refresh_items()
        if self._poll_interval > 0:
            self._poll_task = asyncio.create_task(self._poll_loop(), name="session-list-poll")

    async def on_unmount(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def refresh_items(self) -> None:
        """Force a refresh of the session list (callable from the overlay)."""
        await self._refresh_items()

    def snapshot_items(self) -> list[SessionItem]:
        """Return an ordered snapshot of the current session items (read-only copy)."""
        return list(self._items)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _refresh_items(self) -> None:
        from kagan.tui.app import KaganApp  # local import to avoid cycle

        app = self.app
        if not isinstance(app, KaganApp):
            return
        project = app.project
        project_id = project.id if project is not None else None
        try:
            items = await app.core.list_session_items(project_id=project_id)
        except Exception:
            items = []
        self._items = items
        self.set_class(bool(items), "has-sessions")

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            if not self.is_mounted:
                break
            await self._refresh_items()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        event.stop()
        item = event.item
        item_id = item.id or ""
        # derive session id from item id (format: session-item-<first8>)
        if not item_id.startswith("session-item-"):
            return
        short_id = item_id[len("session-item-") :]
        session_item = next((i for i in self._items if i.id.startswith(short_id)), None)
        if session_item is None:
            return
        if self._on_select is not None:
            self._on_select(session_item)
        else:
            self.post_message(self.SessionSelected(session_item))

    def action_stop_session(self) -> None:
        self._fire_capability_action("can_stop", self.SessionStopRequested)

    def action_close_session(self) -> None:
        self._fire_capability_action("can_close", self.SessionCloseRequested)

    def _fire_capability_action(
        self,
        cap_attr: str,
        msg_cls: type[SessionStopRequested | SessionCloseRequested],
    ) -> None:
        try:
            lv = self.query_one("#session-list", ListView)
        except Exception:
            return
        highlighted = lv.highlighted_child
        if highlighted is None:
            return
        item_id = highlighted.id or ""
        if not item_id.startswith("session-item-"):
            return
        short_id = item_id[len("session-item-") :]
        session_item = next((i for i in self._items if i.id.startswith(short_id)), None)
        if session_item is None:
            return
        if getattr(session_item.capabilities, cap_attr, False):
            self.post_message(msg_cls(session_item))

    def action_return_focus(self) -> None:
        self.post_message(self.FocusInput())
