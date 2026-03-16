from contextlib import suppress
from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from kagan.tui.keybindings import SESSION_PICKER_BINDINGS


@dataclass(frozen=True, slots=True)
class SessionPickerOption:
    key: str
    icon: str
    label: str
    search_text: str = ""


@dataclass(frozen=True, slots=True)
class SessionPickerGroup:
    group_id: str
    icon: str
    label: str
    subtitle: str = ""
    search_text: str = ""
    options: tuple[SessionPickerOption, ...] = ()


class SessionPickerModal(ModalScreen[str | None]):
    EMPTY_GROUP_OPTION_ID = "__session-picker-empty-group__"
    EMPTY_SESSION_OPTION_ID = "__session-picker-empty-session__"

    BINDINGS = SESSION_PICKER_BINDINGS

    def __init__(
        self,
        sessions: list[tuple[str, str]] | None = None,
        *,
        groups: list[SessionPickerGroup] | None = None,
        active_key: str | None = None,
        initial_query: str = "",
    ) -> None:
        super().__init__(id="session-picker-modal")

        if groups is not None:
            self._all_groups = groups
        else:
            normalized = tuple(
                SessionPickerOption(
                    key=key,
                    icon="●",
                    label=label,
                    search_text=f"{label} {key}",
                )
                for label, key in (sessions or [])
                if label and key
            )
            self._all_groups = [
                SessionPickerGroup(
                    group_id="group:sessions",
                    icon="●",
                    label="Sessions",
                    subtitle=f"{len(normalized)} session(s)",
                    search_text="sessions chat targets",
                    options=normalized,
                )
            ]

        self._filtered_groups: list[SessionPickerGroup] = list(self._all_groups)
        self._filtered_options_by_group: dict[str, list[SessionPickerOption]] = {}
        self._active_key = active_key
        self._active_group_id: str | None = None
        self._initial_query = initial_query

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
            yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        filter_input = self.query_one("#session-picker-filter", Input)
        if self._initial_query:
            filter_input.value = self._initial_query
        self._apply_filter(filter_input.value)
        filter_input.focus()

    @on(Input.Changed, "#session-picker-filter")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    @on(Input.Submitted, "#session-picker-filter")
    def _on_filter_submitted(self, _event: Input.Submitted) -> None:
        self.action_select()

    @on(OptionList.OptionSelected, "#session-picker-groups")
    def _on_group_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id is None or str(option_id) == self.EMPTY_GROUP_OPTION_ID:
            return
        self._active_group_id = str(option_id)
        self._rebuild_group_options()
        self._rebuild_session_options()
        with suppress(NoMatches):
            self.query_one("#session-picker-options", OptionList).focus()

    @on(OptionList.OptionSelected, "#session-picker-options")
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        selected_key = str(event.option.id)
        if selected_key == self.EMPTY_SESSION_OPTION_ID:
            return
        self.dismiss(selected_key)

    def _apply_filter(self, query: str) -> None:
        q = query.strip().casefold()

        filtered_groups: list[SessionPickerGroup] = []
        filtered_options: dict[str, list[SessionPickerOption]] = {}

        for group in self._all_groups:
            group_search = f"{group.label} {group.subtitle} {group.search_text}".casefold()
            all_options = list(group.options)
            matched_options = [
                option
                for option in all_options
                if not q
                or q in option.label.casefold()
                or q in option.key.casefold()
                or q in option.search_text.casefold()
            ]
            if not q:
                if not all_options:
                    continue
                filtered_groups.append(group)
                filtered_options[group.group_id] = all_options
                continue

            group_matches = q in group_search
            if not group_matches and not matched_options:
                continue

            filtered_groups.append(group)
            filtered_options[group.group_id] = (
                all_options if group_matches and not matched_options else matched_options
            )

        self._filtered_groups = filtered_groups
        self._filtered_options_by_group = filtered_options
        self._select_best_group()
        self._update_count()
        self._rebuild_group_options()
        self._rebuild_session_options()

    def _update_count(self) -> None:
        count = sum(len(options) for options in self._filtered_options_by_group.values())
        noun = "session" if count == 1 else "sessions"
        self.query_one("#session-picker-match-count", Static).update(f"{count} {noun}")

    def _rebuild_group_options(self) -> None:
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
        options = self.query_one("#session-picker-options", OptionList)
        options.clear_options()

        current_options = self._options_for_active_group()
        if not current_options:
            options.add_option(
                Option("No sessions in selected group", id=self.EMPTY_SESSION_OPTION_ID)
            )
            options.highlighted = 0
            return

        highlight = 0
        for idx, option in enumerate(current_options):
            options.add_option(Option(f"{option.icon}  {option.label}", id=option.key))
            if self._active_key and option.key == self._active_key:
                highlight = idx
        options.highlighted = highlight

    def _select_best_group(self) -> None:
        if not self._filtered_groups:
            self._active_group_id = None
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

        if not self._filtered_groups:
            self._active_group_id = None
            return
        self._active_group_id = self._filtered_groups[0].group_id

    def _sync_group_from_highlight(self) -> None:
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
        if self._active_group_id is None:
            return []
        return list(self._filtered_options_by_group.get(self._active_group_id, []))

    def action_focus_filter(self) -> None:
        self.query_one("#session-picker-filter", Input).focus()

    def action_focus_groups(self) -> None:
        self.query_one("#session-picker-groups", OptionList).focus()

    def action_focus_sessions(self) -> None:
        self.query_one("#session-picker-options", OptionList).focus()

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

    def _active_option_list(self) -> OptionList:
        focused = self.app.focused
        if isinstance(focused, OptionList) and focused.id in {
            "session-picker-groups",
            "session-picker-options",
        }:
            return focused
        return self.query_one("#session-picker-options", OptionList)

    def action_toggle_pane(self) -> None:
        focused = self.app.focused
        if isinstance(focused, Input):
            self.query_one("#session-picker-groups", OptionList).focus()
            return
        if isinstance(focused, OptionList) and focused.id == "session-picker-groups":
            self.query_one("#session-picker-options", OptionList).focus()
            return
        self.query_one("#session-picker-filter", Input).focus()

    def action_select(self) -> None:
        focused = self.app.focused
        groups = self.query_one("#session-picker-groups", OptionList)
        options = self.query_one("#session-picker-options", OptionList)

        if focused is groups:
            self._sync_group_from_highlight()
            options.focus()
            return

        options = self.query_one("#session-picker-options", OptionList)
        idx = options.highlighted
        current_options = self._options_for_active_group()
        if idx is None or idx < 0 or idx >= len(current_options):
            return
        selected_key = current_options[idx].key
        if selected_key == self.EMPTY_SESSION_OPTION_ID:
            return
        self.dismiss(selected_key)

    def action_cancel(self) -> None:
        filter_input = self.query_one("#session-picker-filter", Input)
        if filter_input.value.strip():
            filter_input.value = ""
            self._apply_filter("")
            return
        self.dismiss(None)
