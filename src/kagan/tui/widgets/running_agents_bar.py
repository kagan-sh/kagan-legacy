"""RunningAgentsBar — compact horizontal agent-picker bar.

Shows one row per active worker/reviewer session.  Mirrors Claude Code's
"background agents — ↓ to manage" picker.

Keys:
  Arrow Up/Down  — move selection
  Enter          — fire ``AgentSelected`` message with the session_id
  Esc            — fire ``FocusInput`` message so the overlay returns focus
                   to the chat input
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from textual import on
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import ListItem, ListView, Static

from kagan.tui.keybindings import RUNNING_AGENTS_BAR_BINDINGS

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import ComposeResult

    from kagan.core._sessions_query import ActiveAgentRow

# Glyph per agent role
_ROLE_GLYPH: dict[str, str] = {
    "worker": "▶",
    "reviewer": "◈",
    "orchestrator": "◆",
}
_DEFAULT_GLYPH = "·"

_EMPTY_ROW_LABEL = "no agents running"


def _role_glyph(role: str | None) -> str:
    return _ROLE_GLYPH.get((role or "").lower(), _DEFAULT_GLYPH)


def _duration_str(started_at: datetime) -> str:
    """Human-readable elapsed time since *started_at*."""
    now = datetime.now(tz=UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    delta = now - started_at
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"


def _token_str(tokens: int | None) -> str:
    if tokens is None:
        return "?"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens // 1_000}k"
    return str(tokens)


def _row_label(row: ActiveAgentRow) -> str:
    glyph = _role_glyph(row.agent_role)
    title = row.task_title[:28] + "…" if len(row.task_title) > 29 else row.task_title
    duration = _duration_str(row.started_at)
    in_tok = _token_str(row.input_tokens)
    out_tok = _token_str(row.output_tokens)
    return f"{glyph} {title}  {duration}  ↑{in_tok} ↓{out_tok}"


class RunningAgentsBar(Vertical):
    """Compact list of active agent sessions.

    Parameters
    ----------
    on_select:
        Callback fired when the user selects an agent.  Receives
        ``(session_id, agent_role)``.
    poll_interval:
        Seconds between DB polls.  Set to ``0`` in tests to disable polling.
    """

    BINDINGS = RUNNING_AGENTS_BAR_BINDINGS

    DEFAULT_CSS = """
    RunningAgentsBar {
        height: auto;
        max-height: 6;
        width: 100%;
        border-top: solid $border;
        background: $surface;
        display: none;
    }
    RunningAgentsBar.has-agents {
        display: block;
    }
    RunningAgentsBar > ListView {
        height: auto;
        max-height: 5;
        background: $surface;
        padding: 0;
    }
    RunningAgentsBar > ListView > ListItem {
        padding: 0 1;
        height: 1;
        background: $surface;
    }
    RunningAgentsBar > ListView > ListItem.--highlight {
        background: $primary 20%;
        color: $text;
    }
    RunningAgentsBar > ListView > ListItem > Static {
        width: 1fr;
        height: 1;
        color: $text-muted;
    }
    RunningAgentsBar > ListView > ListItem.--highlight > Static {
        color: $text;
    }
    RunningAgentsBar .-empty > Static {
        color: $text-disabled;
        text-style: italic;
    }
    """

    # Message fired when the user presses Enter on a row
    class AgentSelected(Message):
        def __init__(self, session_id: str, agent_role: str | None, task_id: str) -> None:
            super().__init__()
            self.session_id = session_id
            self.agent_role = agent_role
            self.task_id = task_id

    # Message fired when Esc is pressed — overlay returns focus to input
    class FocusInput(Message):
        pass

    _rows: reactive[list[ActiveAgentRow]] = reactive([], recompose=True)

    def watch__rows(self, rows: list[ActiveAgentRow]) -> None:
        """Sync the has-agents CSS class whenever the row list changes."""
        self.set_class(bool(rows), "has-agents")

    def __init__(
        self,
        *,
        on_select: Callable[[str, str | None, str], None] | None = None,
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
        rows = self._rows
        if not rows:
            empty = ListItem(Static(_EMPTY_ROW_LABEL), classes="-empty")
            empty.can_focus = False
            yield ListView(empty, id="agents-list")
        else:
            items = [
                ListItem(
                    Static(
                        _row_label(row),
                        id=f"agent-row-{row.session_id[:8]}",
                    ),
                    id=f"agent-item-{row.session_id[:8]}",
                )
                for row in rows
            ]
            yield ListView(*items, id="agents-list")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        await self._refresh_rows()
        if self._poll_interval > 0:
            self._poll_task = asyncio.create_task(self._poll_loop(), name="running-agents-bar-poll")

    async def on_unmount(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def refresh_rows(self) -> None:
        """Force a refresh of the agent list (callable from the overlay)."""
        await self._refresh_rows()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _refresh_rows(self) -> None:
        from kagan.tui.app import KaganApp  # local import to avoid cycle

        app = self.app
        if not isinstance(app, KaganApp):
            return
        project = app.project
        project_id = project.id if project is not None else None
        try:
            rows = await app.core.list_running_agents(project_id=project_id)
        except Exception:
            rows = []
        self._rows = rows
        self.set_class(bool(rows), "has-agents")

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            if not self.is_mounted:
                break
            await self._refresh_rows()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(ListView.Selected)
    def _on_list_selected(self, event: ListView.Selected) -> None:
        event.stop()
        item = event.item
        item_id = item.id or ""
        # derive session_id from item id (format: agent-item-<first8>)
        if not item_id.startswith("agent-item-"):
            return
        short_id = item_id[len("agent-item-") :]
        row = next((r for r in self._rows if r.session_id.startswith(short_id)), None)
        if row is None:
            return
        if self._on_select is not None:
            self._on_select(row.session_id, row.agent_role, row.task_id)
        else:
            self.post_message(self.AgentSelected(row.session_id, row.agent_role, row.task_id))

    def action_return_focus(self) -> None:
        self.post_message(self.FocusInput())
