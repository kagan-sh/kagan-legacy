"""kagan.tui.widgets._mention_typeahead — dual-source ``#``-mention typeahead.

Attaches to a host ``TextArea`` or ``Input`` widget and listens for ``#``
keystrokes at word-start positions. When triggered, opens a popup that:

- Fetches merged kagan + GitHub mention results via
  ``kagan.core.integrations.mentions.search_mentions``.
- Renders rows with a source glyph (``[K]`` kagan, ``[GH]`` github).
- Lets the user navigate with ↑/↓, accept with Enter/Tab, or dismiss
  with Esc or Backspace beyond the ``#``.

Usage::

    # Inside a widget's compose() that has a TextArea with id="task-description":
    yield MentionTypeahead(
        host_id="task-description",
        project_id=self._project_id,
        client=self._client,
    )

The typeahead positions itself as an overlay via ``layer`` CSS.  Mount it
*after* the host widget so focus/event routing works correctly.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, OptionList, TextArea
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.core import KaganCore
    from kagan.core.integrations.mentions import Mention

_DEBOUNCE_SECONDS = 0.2
_MAX_RESULTS = 10

_SOURCE_GLYPH: dict[str, str] = {
    "kagan": "[K]",
    "github": "[GH]",
}


def _render_mention_option(mention: Mention) -> str:
    glyph = _SOURCE_GLYPH.get(mention.source, "[?]")
    state_text = f"  {mention.state}" if mention.state else ""
    return f"{glyph} {mention.id}  {mention.title}{state_text}"


class MentionTypeahead(Vertical):
    """Overlay widget that provides ``#``-mention autocomplete for a host widget.

    The host widget must be a ``TextArea`` or ``Input`` with the given
    ``host_id``.  The typeahead is invisible until a ``#`` is typed at a
    word-start boundary.

    Keyboard contract:
    - ↑ / ↓  — navigate the option list.
    - Enter / Tab — accept the highlighted option (insert its ``id``).
    - Esc — dismiss without inserting.
    - Backspace while query is empty (cursor immediately after ``#``) — dismiss.
    """

    DEFAULT_CSS = """
    MentionTypeahead {
        display: none;
        height: auto;
        max-height: 10;
        width: 100%;
        border: solid $accent;
        background: $surface;
        padding: 0;
        margin-top: 0;
    }

    MentionTypeahead OptionList {
        height: auto;
        max-height: 10;
        width: 100%;
        background: $surface;
        padding: 0;
    }
    """

    # ------------------------------------------------------------------ #
    # Messages                                                             #
    # ------------------------------------------------------------------ #

    class MentionSelected(Message):
        """Posted when the user accepts a mention."""

        def __init__(self, host_id: str, insert_text: str) -> None:
            super().__init__()
            self.host_id = host_id
            self.insert_text = insert_text

    class MentionDismissed(Message):
        """Posted when the typeahead closes without a selection."""

        def __init__(self, host_id: str) -> None:
            super().__init__()
            self.host_id = host_id

    # ------------------------------------------------------------------ #
    # Init                                                                 #
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        host_id: str,
        project_id: str,
        client: KaganCore,
        *,
        debounce_seconds: float = _DEBOUNCE_SECONDS,
    ) -> None:
        super().__init__()
        self._host_id = host_id
        self._project_id = project_id
        self._client = client
        self._debounce_seconds = debounce_seconds
        self._active = False  # True while user has typed a ``#``
        self._hash_position: int = -1  # cursor index just after ``#``
        self._current_query = ""
        self._results: list[Mention] = []
        self._debounce_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ #
    # Compose                                                              #
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield OptionList(id=f"mention-list-{self._host_id}")

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def notify_text_changed(self, text: str, cursor_position: int) -> None:
        """Call this from the host widget's on_changed handler."""
        if not self._active:
            # Detect ``#`` typed at word-start
            if cursor_position > 0 and text[cursor_position - 1] == "#":
                # Check word-start: either at beginning or preceded by whitespace/punctuation
                preceding = text[cursor_position - 2] if cursor_position >= 2 else ""
                at_word_start = not preceding or preceding in " \t\n,;:()[]{}\"'"
                if at_word_start:
                    self._active = True
                    self._hash_position = cursor_position - 1
                    self._current_query = ""
                    self._schedule_search("")
            return

        # Already active: check if we should close
        if cursor_position <= self._hash_position:
            # Backed up past the ``#``
            self._deactivate()
            return

        query = text[self._hash_position + 1 : cursor_position]
        # If there's whitespace in the query the ``#``-mention span ended
        if " " in query or "\n" in query:
            self._deactivate()
            return

        if query != self._current_query:
            self._current_query = query
            self._schedule_search(query)

    def notify_key(self, key: str) -> bool:
        """Handle navigation keys. Returns True if the key was consumed."""
        if not self._active:
            return False

        option_list = self.query_one(f"#mention-list-{self._host_id}", OptionList)

        if key in ("up", "ctrl+p"):
            option_list.action_cursor_up()
            return True

        if key in ("down", "ctrl+n"):
            option_list.action_cursor_down()
            return True

        if key in ("enter", "tab"):
            self._accept_highlighted()
            return True

        if key == "escape":
            self._deactivate()
            return True

        if key == "backspace" and not self._current_query:
            # Backspace deleted the ``#`` itself
            self._deactivate()
            return True

        return False

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _schedule_search(self, query: str) -> None:
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.ensure_future(self._debounced_search(query))

    async def _debounced_search(self, query: str) -> None:
        if self._debounce_seconds > 0:
            await asyncio.sleep(self._debounce_seconds)
        await self._run_search(query)

    async def _run_search(self, query: str) -> None:
        from kagan.core.integrations.mentions import search_mentions

        try:
            results = await search_mentions(
                self._client,
                self._project_id,
                query,
                limit=_MAX_RESULTS,
            )
        except Exception:  # quality-allow-broad-except
            results = []

        self._results = results
        self._refresh_list()

    def _refresh_list(self) -> None:
        option_list = self.query_one(f"#mention-list-{self._host_id}", OptionList)
        option_list.clear_options()
        for mention in self._results:
            option_list.add_option(Option(_render_mention_option(mention), id=mention.id))
        if self._results:
            option_list.highlighted = 0
            self.display = True
        else:
            self.display = False

    def _accept_highlighted(self) -> None:
        option_list = self.query_one(f"#mention-list-{self._host_id}", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None or not self._results:
            self._deactivate()
            return
        idx = highlighted if 0 <= highlighted < len(self._results) else 0
        selected = self._results[idx]
        self.post_message(self.MentionSelected(self._host_id, selected.id))
        self._deactivate(emit_dismissed=False)

    def _deactivate(self, *, emit_dismissed: bool = True) -> None:
        self._active = False
        self._hash_position = -1
        self._current_query = ""
        self._results = []
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None
        self.display = False
        if emit_dismissed:
            self.post_message(self.MentionDismissed(self._host_id))

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != f"mention-list-{self._host_id}":
            return
        event.stop()
        if event.option_id and self._results:
            # Find the mention by id
            selected = next(
                (m for m in self._results if m.id == event.option_id),
                self._results[0] if self._results else None,
            )
            if selected:
                self.post_message(self.MentionSelected(self._host_id, selected.id))
        self._deactivate(emit_dismissed=False)


# ---------------------------------------------------------------------------
# Helper: integrate a MentionTypeahead into a TextArea host
# ---------------------------------------------------------------------------


class MentionTextAreaHost(Widget):
    """Mixin-style base for widgets that host a TextArea with mention support.

    Subclasses compose a TextArea with ``id=self._text_area_id`` and call
    ``_setup_mention_typeahead(project_id, client)`` in ``on_mount``.

    This base handles routing ``TextArea.Changed`` → typeahead and
    inserting accepted mentions at the cursor.

    Note: this class is provided as a composition helper. If you cannot
    inherit from it, use ``MentionTypeahead`` directly and handle the wiring
    manually as shown in the class docstring.
    """

    _text_area_id: str = "mention-textarea"
    _typeahead: MentionTypeahead | None = None

    def _setup_mention_typeahead(self, project_id: str, client: KaganCore) -> None:
        """Mount and wire a MentionTypeahead. Call from on_mount()."""
        self._typeahead = MentionTypeahead(
            host_id=self._text_area_id,
            project_id=project_id,
            client=client,
        )
        # Mount after the host TextArea
        self.mount(self._typeahead, after=self.query_one(f"#{self._text_area_id}"))

    def _handle_typeahead_text_changed(self, textarea: TextArea) -> None:
        if self._typeahead is None:
            return
        text = textarea.text
        # Textual's TextArea cursor is (row, col); convert to linear position
        row, col = textarea.cursor_location
        lines = text.splitlines(keepends=True)
        pos = sum(len(lines[i]) for i in range(row)) + col
        self._typeahead.notify_text_changed(text, pos)

    def _handle_typeahead_key(self, key: str) -> bool:
        if self._typeahead is None:
            return False
        return self._typeahead.notify_key(key)

    def _apply_mention_to_textarea(self, textarea: TextArea, insert_text: str) -> None:
        """Replace the ``#<query>`` span with ``insert_text`` in the TextArea."""
        if self._typeahead is None:
            return
        text = textarea.text
        hash_pos = self._typeahead._hash_position
        # Determine current cursor linear position
        row, col = textarea.cursor_location
        lines = text.splitlines(keepends=True)
        cursor_pos = sum(len(lines[i]) for i in range(row)) + col
        if hash_pos < 0 or hash_pos >= len(text):
            return
        new_text = text[:hash_pos] + insert_text + " " + text[cursor_pos:]
        textarea.load_text(new_text)
        # Move cursor to end of inserted text
        new_cursor_pos = hash_pos + len(insert_text) + 1
        _move_textarea_cursor(textarea, new_cursor_pos, new_text)

    def _apply_mention_to_input(self, input_widget: Input, insert_text: str) -> None:
        """Replace the ``#<query>`` span with ``insert_text`` in an Input."""
        if self._typeahead is None:
            return
        text = input_widget.value
        hash_pos = self._typeahead._hash_position
        cursor_pos = input_widget.cursor_position
        if hash_pos < 0 or hash_pos >= len(text):
            return
        new_text = text[:hash_pos] + insert_text + " " + text[cursor_pos:]
        input_widget.value = new_text
        input_widget.cursor_position = hash_pos + len(insert_text) + 1


def _move_textarea_cursor(textarea: TextArea, linear_pos: int, text: str) -> None:
    """Move the TextArea cursor to the given linear character position."""
    lines = text.splitlines(keepends=True)
    remaining = linear_pos
    for row_idx, line in enumerate(lines):
        if remaining <= len(line):
            textarea.move_cursor((row_idx, remaining))
            return
        remaining -= len(line)
    # Fallback: move to end
    if lines:
        last_row = len(lines) - 1
        textarea.move_cursor((last_row, len(lines[last_row].rstrip("\n"))))


__all__ = [
    "MentionTextAreaHost",
    "MentionTypeahead",
]
