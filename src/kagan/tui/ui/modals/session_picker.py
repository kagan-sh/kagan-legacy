"""Session picker modal for quick chat target switching."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual import on
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from textual.app import ComposeResult


@dataclass(frozen=True, slots=True)
class SessionPickerOption:
    """Leaf session option (e.g. orchestrator, worker, reviewer)."""

    key: str
    icon: str
    label: str
    search_text: str = ""


@dataclass(frozen=True, slots=True)
class SessionPickerGroup:
    """Group row in the left pane (root/task)."""

    group_id: str
    icon: str
    label: str
    subtitle: str = ""
    search_text: str = ""
    options: tuple[SessionPickerOption, ...] = ()


class SessionPickerModal(ModalScreen[str | None]):
    """Two-pane quick-pick palette for grouped chat sessions."""

    EMPTY_GROUP_OPTION_ID = "__session-picker-empty-group__"
    EMPTY_SESSION_OPTION_ID = "__session-picker-empty-session__"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "select", "Select", show=False, priority=True),
        Binding("up", "cursor_up", "Up", show=False, priority=True),
        Binding("down", "cursor_down", "Down", show=False, priority=True),
        Binding("left", "focus_groups", "Groups", show=False, priority=True),
        Binding("right", "focus_sessions", "Sessions", show=False, priority=True),
        Binding("ctrl+f", "focus_filter", "Filter", show=False, priority=True),
        Binding("tab", "toggle_pane", "Pane", show=False, priority=True),
        Binding("shift+tab", "toggle_pane", "Pane", show=False, priority=True),
    ]

    def __init__(
        self,
        groups: list[SessionPickerGroup],
        active_key: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._all_groups = groups
        self._filtered_groups: list[SessionPickerGroup] = list(groups)
        self._filtered_options_by_group: dict[str, list[SessionPickerOption]] = {}
        self._active_key = active_key
        self._active_group_id: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="session-picker-container"):
            yield Label("Jump to Session", classes="modal-title")
            yield Input(
                placeholder="Filter tasks, ids, or sessions...",
                id="session-picker-filter",
            )
            yield Static("0 sessions", id="session-picker-match-count")
            with Horizontal(id="session-picker-grid"):
                with Vertical(classes="session-picker-column"):
                    yield Static("Sessions", classes="session-picker-column-title")
                    yield OptionList(id="session-picker-groups")
                with Vertical(classes="session-picker-column"):
                    yield Static("Agents", classes="session-picker-column-title")
                    yield OptionList(id="session-picker-options")
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Tab switch pane  |  Ctrl+F filter  |  Up/Down navigate  |  "
                    "Enter select  |  Esc clears filter first, Esc again closes",
                    id="session-picker-footer-hint",
                    classes="modal-action-hint",
                )

    def on_mount(self) -> None:
        self._apply_filter("")
        self.query_one("#session-picker-filter", Input).focus()

    @on(Input.Changed, "#session-picker-filter")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    @on(Input.Submitted, "#session-picker-filter")
    def _on_filter_submitted(self, _event: Input.Submitted) -> None:
        self.action_select()

    @on(OptionList.OptionSelected, "#session-picker-groups")
    def _on_group_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        group_id = str(event.option.id)
        if group_id == self.EMPTY_GROUP_OPTION_ID:
            return
        self._active_group_id = group_id
        self._rebuild_group_options()
        self._rebuild_session_options()
        self.query_one("#session-picker-options", OptionList).focus()

    @on(OptionList.OptionSelected, "#session-picker-options")
    def _on_session_selected(self, event: OptionList.OptionSelected) -> None:
        if not event.option.id:
            return
        option_id = str(event.option.id)
        if option_id == self.EMPTY_SESSION_OPTION_ID:
            return
        self.dismiss(option_id)

    def action_focus_groups(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#session-picker-groups", OptionList).focus()

    def action_focus_sessions(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#session-picker-options", OptionList).focus()

    def action_focus_filter(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#session-picker-filter", Input).focus()

    def action_toggle_pane(self) -> None:
        focused = getattr(self.app, "focused", None)
        with contextlib.suppress(NoMatches):
            filter_input = self.query_one("#session-picker-filter", Input)
            groups = self.query_one("#session-picker-groups", OptionList)
            options = self.query_one("#session-picker-options", OptionList)
            if focused is filter_input:
                groups.focus()
                return
            if focused is groups:
                options.focus()
                return
            filter_input.focus()

    def action_cursor_up(self) -> None:
        option_list = self._active_option_list()
        option_list.action_cursor_up()
        if option_list.id == "session-picker-groups":
            self._sync_group_from_highlight()

    def action_cursor_down(self) -> None:
        option_list = self._active_option_list()
        option_list.action_cursor_down()
        if option_list.id == "session-picker-groups":
            self._sync_group_from_highlight()

    def action_select(self) -> None:
        focused = getattr(self.app, "focused", None)
        with contextlib.suppress(NoMatches):
            groups = self.query_one("#session-picker-groups", OptionList)
            options = self.query_one("#session-picker-options", OptionList)
            if focused is groups:
                self._sync_group_from_highlight()
                options.focus()
                return
            highlighted = options.highlighted
            current_options = self._options_for_active_group()
            if highlighted is None or not (0 <= highlighted < len(current_options)):
                self.action_focus_filter()
                return
            selected_key = current_options[highlighted].key
            if selected_key == self.EMPTY_SESSION_OPTION_ID:
                self.action_focus_filter()
                return
            self.dismiss(selected_key)
            return
        self.action_focus_filter()

    def action_cancel(self) -> None:
        with contextlib.suppress(NoMatches):
            filter_input = self.query_one("#session-picker-filter", Input)
            if filter_input.value.strip():
                filter_input.value = ""
                filter_input.focus()
                self._apply_filter("")
                return
        self.dismiss(None)

    def _active_option_list(self) -> OptionList:
        focused = getattr(self.app, "focused", None)
        if isinstance(focused, OptionList) and focused.id in {
            "session-picker-groups",
            "session-picker-options",
        }:
            return focused
        return self.query_one("#session-picker-options", OptionList)

    def _apply_filter(self, raw_query: str) -> None:
        query = raw_query.strip().casefold()
        filtered_groups: list[SessionPickerGroup] = []
        filtered_options: dict[str, list[SessionPickerOption]] = {}

        for group in self._all_groups:
            group_search = f"{group.label} {group.subtitle} {group.search_text}".casefold()
            all_options = list(group.options)
            matched_options = [
                option
                for option in all_options
                if not query
                or query in option.label.casefold()
                or query in option.key.casefold()
                or query in option.search_text.casefold()
            ]
            if not query:
                if not all_options:
                    continue
                filtered_groups.append(group)
                filtered_options[group.group_id] = all_options
                continue

            group_matches = query in group_search
            if not group_matches and not matched_options:
                continue
            filtered_groups.append(group)
            filtered_options[group.group_id] = (
                all_options if group_matches and not matched_options else matched_options
            )

        self._filtered_groups = filtered_groups
        self._filtered_options_by_group = filtered_options
        self._select_best_group()
        self._update_match_count()
        self._rebuild_group_options()
        self._rebuild_session_options()

    def _update_match_count(self) -> None:
        count = sum(len(options) for options in self._filtered_options_by_group.values())
        label = "session" if count == 1 else "sessions"
        with contextlib.suppress(NoMatches):
            self.query_one("#session-picker-match-count", Static).update(f"{count} {label}")

    def _select_best_group(self) -> None:
        if not self._filtered_groups:
            self._active_group_id = None
            return
        total_visible_options = sum(
            len(options) for options in self._filtered_options_by_group.values()
        )
        if total_visible_options == 1:
            for group_id, options in self._filtered_options_by_group.items():
                if options:
                    self._active_group_id = group_id
                    return
        if self._active_group_id and any(
            group.group_id == self._active_group_id for group in self._filtered_groups
        ):
            return
        if self._active_key:
            for group in self._filtered_groups:
                for option in self._filtered_options_by_group.get(group.group_id, []):
                    if option.key == self._active_key:
                        self._active_group_id = group.group_id
                        return
        self._active_group_id = self._filtered_groups[0].group_id

    def _rebuild_group_options(self) -> None:
        with contextlib.suppress(NoMatches):
            groups = self.query_one("#session-picker-groups", OptionList)
            groups.clear_options()
            if not self._filtered_groups:
                groups.add_option(
                    Option("No matching sessions or tasks", id=self.EMPTY_GROUP_OPTION_ID)
                )
                groups.highlighted = 0
                return
            highlighted_index = 0
            for index, group in enumerate(self._filtered_groups):
                label = f"{group.icon}  {group.label}"
                if group.subtitle:
                    label = f"{label}  ·  {group.subtitle}"
                groups.add_option(Option(label, id=group.group_id))
                if group.group_id == self._active_group_id:
                    highlighted_index = index
            groups.highlighted = highlighted_index

    def _rebuild_session_options(self) -> None:
        with contextlib.suppress(NoMatches):
            options = self.query_one("#session-picker-options", OptionList)
            options.clear_options()
            current_options = self._options_for_active_group()
            if not current_options:
                options.add_option(
                    Option("No sessions in selected group", id=self.EMPTY_SESSION_OPTION_ID)
                )
                options.highlighted = 0
                return
            highlighted_index = 0
            for index, option in enumerate(current_options):
                options.add_option(Option(f"{option.icon}  {option.label}", id=option.key))
                if option.key == self._active_key:
                    highlighted_index = index
            options.highlighted = highlighted_index

    def _sync_group_from_highlight(self) -> None:
        with contextlib.suppress(NoMatches):
            groups = self.query_one("#session-picker-groups", OptionList)
            highlighted = groups.highlighted
            if highlighted is None or not (0 <= highlighted < len(self._filtered_groups)):
                return
            next_group_id = self._filtered_groups[highlighted].group_id
            if next_group_id == self._active_group_id:
                return
            self._active_group_id = next_group_id
            self._rebuild_session_options()

    def _options_for_active_group(self) -> list[SessionPickerOption]:
        if not self._active_group_id:
            return []
        return list(self._filtered_options_by_group.get(self._active_group_id, []))
