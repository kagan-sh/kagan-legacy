import contextlib
from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.events import Key
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static

_HIGH_PRIORITY_COUNT_KEY = "__high_priority__"


_PRESETS: tuple[tuple[str, str, str | None], ...] = (
    ("Review ({n})", "@status:review", "REVIEW"),
    ("Active ({n})", "@status:in_progress", "IN_PROGRESS"),
    ("Backlog ({n})", "@status:backlog", "BACKLOG"),
    ("High Priority ({n})", "@priority:high", _HIGH_PRIORITY_COUNT_KEY),
    ("Recent", "@sort:recent", None),
    ("Priority", "@sort:priority", None),
)


class SearchPresets(Widget):
    can_focus = False

    selected_index: reactive[int] = reactive(-1)

    @dataclass
    class PresetSelected(Message):
        query: str

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._status_counts: dict[str, int] = {}
        self._high_priority_count = 0

    def compose(self) -> ComposeResult:
        with Horizontal(classes="presets-row"):
            for index, (label_template, query, count_key) in enumerate(_PRESETS):
                pill = Static(
                    label_template.format(n=self._count_for(count_key)),
                    id=f"preset-pill-{index}",
                    classes="preset-pill",
                )
                pill.tooltip = f"Filter by: {query}"
                yield pill

    def set_counts(self, status_counts: dict[str, int], high_priority_count: int) -> None:
        self._status_counts = dict(status_counts)
        self._high_priority_count = high_priority_count
        self._refresh_pills()

    def reset_selection(self) -> None:
        self.selected_index = -1

    def move_selection(self, delta: int) -> None:
        new_index = self.selected_index + delta
        self.selected_index = max(0, min(new_index, len(_PRESETS) - 1))

    def activate_selected(self) -> bool:
        if self.selected_index < 0 or self.selected_index >= len(_PRESETS):
            return False
        _, query, _count_key = _PRESETS[self.selected_index]
        self.post_message(self.PresetSelected(query))
        return True

    def watch_selected_index(self, old: int, new: int) -> None:
        if old >= 0:
            with contextlib.suppress(NoMatches):
                self.query_one(f"#preset-pill-{old}", Static).remove_class("focused")
        if new >= 0:
            with contextlib.suppress(NoMatches):
                self.query_one(f"#preset-pill-{new}", Static).add_class("focused")

    def on_click(self, event) -> None:  # type: ignore[override]
        for index, (_label, query, _count_key) in enumerate(_PRESETS):
            try:
                pill = self.query_one(f"#preset-pill-{index}", Static)
            except NoMatches:
                continue
            if pill.region.contains(event.screen_x, event.screen_y):
                self.post_message(self.PresetSelected(query))
                return

    def _count_for(self, count_key: str | None) -> int:
        if count_key is None:
            return 0
        if count_key == _HIGH_PRIORITY_COUNT_KEY:
            return self._high_priority_count
        return self._status_counts.get(count_key, 0)

    def _refresh_pills(self) -> None:
        for index, (label_template, _query, count_key) in enumerate(_PRESETS):
            try:
                pill = self.query_one(f"#preset-pill-{index}", Static)
            except NoMatches:
                continue
            pill.update(label_template.format(n=self._count_for(count_key)))


class SearchBar(Widget):
    can_focus = False

    search_query: reactive[str] = reactive("", init=False)
    is_visible: reactive[bool] = reactive(False, init=False)
    filtered_count: reactive[int | None] = reactive(None, init=False)
    total_count: reactive[int] = reactive(0, init=False)
    status_filter: reactive[str] = reactive("", init=False)
    priority_filter: reactive[str] = reactive("", init=False)
    sort_filter: reactive[str] = reactive("", init=False)

    @dataclass
    class QueryChanged(Message):
        query: str

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._query_history: list[str] = []
        self._history_index: int | None = None
        self._history_programmatic_update = False

    def compose(self) -> ComposeResult:
        yield SearchPresets(id="search-presets")
        with Horizontal(classes="search-row"):
            shortcut_widget = Static("/", id="search-shortcut", classes="search-shortcut")
            shortcut_widget.tooltip = "Press / to activate search"
            yield shortcut_widget
            search_input = Input(
                placeholder="Search tasks  @status:review  @priority:high  @sort:recent",
                id="search-input",
            )
            search_input.tooltip = (
                "Search tasks by title, status, or priority."
                " Use @status:review, @priority:high, @sort:recent"
            )
            yield search_input
            meta_widget = Static("", id="search-meta", classes="search-meta")
            meta_widget.tooltip = "Current filter results and active filters"
            yield meta_widget
            clear_widget = Static("/ search", id="search-clear", classes="search-clear")
            clear_widget.tooltip = "Press / to close search, Ctrl+A to select all"
            yield clear_widget

    def on_mount(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#search-input", Input).can_focus = False
        self._render_state()

    @on(Input.Changed, "#search-input")
    def _on_input_changed(self, event: Input.Changed) -> None:
        if self._history_programmatic_update:
            self._history_programmatic_update = False
        elif self._history_index is not None:
            self._history_index = None
        self.search_query = event.value
        self.post_message(self.QueryChanged(self.search_query))
        if event.value:
            self._dismiss_presets()

    @on(SearchPresets.PresetSelected)
    def _on_preset_selected(self, event: SearchPresets.PresetSelected) -> None:
        event.stop()
        try:
            inp = self.query_one("#search-input", Input)
        except NoMatches:
            return
        inp.value = event.query
        inp.cursor_position = len(event.query)
        self.search_query = event.query
        self.post_message(self.QueryChanged(self.search_query))
        self._dismiss_presets()

    def watch_is_visible(self, is_visible: bool) -> None:
        try:
            inp = self.query_one("#search-input", Input)
            presets = self.query_one(SearchPresets)
        except NoMatches:
            return
        if is_visible:
            self.add_class("active")
            inp.can_focus = True
            inp.focus()
            if not self.search_query.strip():
                presets.reset_selection()
                presets.add_class("visible")
                self.add_class("has-presets")
        else:
            self.remove_class("active")
            self.remove_class("has-presets")
            inp.can_focus = False
            presets.remove_class("visible")
            if self.search_query:
                self.clear()
        self._render_state()

    def watch_search_query(self, query: str) -> None:
        del query
        self._render_state()

    def watch_filtered_count(self, count: int | None) -> None:
        del count
        self._render_state()

    def watch_total_count(self, count: int) -> None:
        del count
        self._render_state()

    def watch_status_filter(self, value: str) -> None:
        del value
        self._render_state()

    def watch_priority_filter(self, value: str) -> None:
        del value
        self._render_state()

    def watch_sort_filter(self, value: str) -> None:
        del value
        self._render_state()

    def show(self) -> None:
        """Activate search mode and focus the input."""
        self.is_visible = True

    def hide(self) -> None:
        """Deactivate search mode and clear the active query."""
        self.is_visible = False

    def clear(self) -> None:
        """Clear the search query and input field."""
        self.search_query = ""
        self._history_index = None
        with contextlib.suppress(NoMatches):
            self.query_one("#search-input", Input).value = ""

    def remember_current_query(self) -> None:
        query = self.search_query.strip()
        if not query:
            return
        if not self._query_history or self._query_history[-1] != query:
            self._query_history.append(query)
            self._query_history = self._query_history[-100:]
        self._history_index = None

    def update_state(
        self,
        *,
        filtered_count: int | None,
        total_count: int,
        status_filter: str = "",
        priority_filter: str = "",
        sort_filter: str = "",
        search_active: bool,
        status_counts: dict[str, int] | None = None,
        high_priority_count: int = 0,
    ) -> None:
        self.filtered_count = filtered_count
        self.total_count = max(0, int(total_count))
        self.status_filter = status_filter
        self.priority_filter = priority_filter
        self.sort_filter = sort_filter
        self.is_visible = bool(search_active)
        if status_counts is not None:
            with contextlib.suppress(NoMatches):
                self.query_one(SearchPresets).set_counts(dict(status_counts), high_priority_count)

    def focus_input(self) -> None:
        """Focus the search input field."""
        with contextlib.suppress(NoMatches):
            self.query_one("#search-input", Input).focus()

    def handle_preset_key(self, key: str) -> bool:
        """Handle arrow-key navigation within presets.

        Returns True if the key was consumed.
        """
        try:
            presets = self.query_one(SearchPresets)
        except NoMatches:
            return False
        if not presets.has_class("visible"):
            return False
        if key == "left":
            presets.move_selection(-1)
            return True
        if key == "right":
            presets.move_selection(1)
            return True
        if key in {"enter", "tab"}:
            return presets.activate_selected()
        return False

    def handle_history_key(self, key: str) -> bool:
        if key not in {"up", "down"}:
            return False
        if not self.is_visible or not self._query_history:
            return False
        if self._history_index is None:
            next_index = len(self._query_history) - 1 if key == "up" else 0
        else:
            step = -1 if key == "up" else 1
            next_index = (self._history_index + step) % len(self._query_history)
        self._history_index = next_index

        query = self._query_history[next_index]
        with contextlib.suppress(NoMatches):
            inp = self.query_one("#search-input", Input)
            self._history_programmatic_update = True
            inp.value = query
            inp.cursor_position = len(query)
            inp.focus()
        return True

    def on_key(self, event: Key) -> None:
        if event.key == "slash" and self.is_visible:
            event.prevent_default()
            event.stop()
            search = getattr(self.screen, "action_search", None)
            if callable(search):
                search()
            return
        if self.handle_history_key(event.key):
            event.prevent_default()
            event.stop()

    def _render_state(self) -> None:
        """Update meta text and clear/hide hint to reflect current state."""
        try:
            meta = self.query_one("#search-meta", Static)
            clear = self.query_one("#search-clear", Static)
        except NoMatches:
            return

        # Meta text
        filters: list[str] = []
        if self.status_filter:
            filters.append(f"@status:{self.status_filter}")
        if self.priority_filter:
            filters.append(f"@priority:{self.priority_filter}")
        if self.sort_filter:
            filters.append(f"@sort:{self.sort_filter}")

        task_word = "task" if self.total_count == 1 else "tasks"
        if self.filtered_count is None:
            count_text = f"{self.total_count} {task_word}"
        else:
            count_text = f"{self.filtered_count}/{self.total_count} {task_word}"
        if filters:
            count_text = f"{count_text}  {' '.join(filters)}"
        meta.update(count_text)

        # Clear hint
        has_filter = bool(
            self.search_query.strip()
            or self.status_filter
            or self.priority_filter
            or self.sort_filter
        )
        if has_filter:
            clear.update("✕ clear")
        elif self.is_visible:
            clear.update("Esc hide")
        else:
            clear.update("/ search tasks")

    def _dismiss_presets(self) -> None:
        """Hide the presets panel."""
        try:
            presets = self.query_one(SearchPresets)
        except NoMatches:
            return
        presets.remove_class("visible")
        presets.reset_selection()
        self.remove_class("has-presets")
