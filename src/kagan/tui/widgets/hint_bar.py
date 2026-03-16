"""Hint bar widgets for displaying keybinding hints in the TUI."""

from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Static

KANBAN_GLOBAL_STRIP_FULL = "[bold]?[/] help  [bold]Ctrl+Shift+P[/] quick actions  [bold]/[/] search"
KANBAN_GLOBAL_STRIP_NARROW = "[bold]?[/]  [bold]Ctrl+Shift+P[/]  [bold]/[/]"
KEYBINDING_HINT_NARROW_TERMINAL_WIDTH = 80


def _render_group(hints: list[tuple[str, str]], *, separator: str = " · ") -> str:
    """Render a group of hints."""
    parts: list[str] = []
    for key, description in hints:
        if not key:
            continue
        if description:
            parts.append(f"[bold]{key}[/] {description}")
        else:
            parts.append(f"[bold]{key}[/]")
    return separator.join(parts)


def format_hint(hints: list[tuple[str, str]], *, separator: str = "  ") -> str:
    """Format hints for display."""
    return _render_group(hints, separator=separator)


def action_hints_from_bindings(
    bindings: list,
    specs: list[tuple[str | tuple[str, ...], str]],
) -> list[tuple[str, str]]:
    """Resolve key labels from bindings for action specs."""
    from kagan.tui.keybindings import get_key_for_action

    result: list[tuple[str, str]] = []
    for action_or_actions, label in specs:
        if isinstance(action_or_actions, tuple):
            keys: list[str] = []
            for a in action_or_actions:
                k = get_key_for_action(bindings, a)
                if k != "?":
                    keys.append(k)
            if not keys:
                continue
            result.append(("/".join(keys), label))
        else:
            key = get_key_for_action(bindings, action_or_actions)
            if key == "?":
                continue
            result.append((key, label))
    return result


def build_action_strip(
    bindings: list,
    specs: list[tuple[str | tuple[str, ...], str]],
    *,
    prefix_hints: list[tuple[str, str]] | None = None,
    separator: str = "  ",
) -> str:
    """Build a formatted action-hint strip from bindings and specs."""
    resolved = action_hints_from_bindings(bindings, specs)
    all_hints = list(prefix_hints or []) + resolved
    return format_hint(all_hints, separator=separator)


class KeybindingHint(Static):
    """Reactive keybinding hint widget."""

    hints: reactive[str] = reactive("")

    def watch_hints(self, hints: str) -> None:
        self.update(hints)

    def show_hints(self, hints: list[tuple[str, str]]) -> None:
        self.hints = _render_group(hints)

    def clear(self) -> None:
        self.hints = ""


class GlobalShortcutsStrip(Static):
    """Global shortcuts strip - updated for new binding scheme."""

    def on_mount(self) -> None:
        self._refresh_label()

    def on_resize(self, event) -> None:
        del event
        self._refresh_label()

    def _refresh_label(self) -> None:
        width = self.app.size.width
        if width < KEYBINDING_HINT_NARROW_TERMINAL_WIDTH:
            self.update(KANBAN_GLOBAL_STRIP_NARROW)
            return
        self.update(KANBAN_GLOBAL_STRIP_FULL)


class KanbanHintBar(Widget):
    """Kanban hint bar for navigation and action hints."""

    has_card: var[bool] = var(False, init=False)

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)

    def compose(self):
        with Horizontal(classes="hint-bar-row hint-bar-nav"):
            yield Static("", id="hint-nav-left", classes="hint-nav-left")
            yield Static("", id="hint-nav-center", classes="hint-nav-center")
            yield Static("", id="hint-nav-right", classes="hint-nav-right")
            yield GlobalShortcutsStrip(id="hint-nav-global", classes="hint-nav-global")
        with Horizontal(classes="hint-bar-row hint-bar-actions"):
            yield Static("", id="hint-actions-left", classes="hint-actions-left")
            yield Static("", id="hint-actions", classes="hint-actions")
            yield Static("", id="hint-global", classes="hint-global")

    def watch_has_card(self, has_card: bool) -> None:
        self.set_class(has_card, "card-focused")

    @staticmethod
    def _update_static(widget: Static, content: str) -> None:
        if str(getattr(widget, "renderable", "")) == content:
            return
        widget.update(content)

    def show_kanban_hints(
        self,
        navigation: list[tuple[str, str]],
        actions: list[tuple[str, str]],
        global_hints: list[tuple[str, str]],
        *,
        mode_label: str = "Board",
    ) -> None:
        """Update hint bar with navigation, action, and global hints."""
        try:
            nav_left = self.query_one("#hint-nav-left", Static)
            nav_center = self.query_one("#hint-nav-center", Static)
            nav_right = self.query_one("#hint-nav-right", Static)
            actions_left = self.query_one("#hint-actions-left", Static)
            actions_main = self.query_one("#hint-actions", Static)
            global_main = self.query_one("#hint-global", Static)
        except NoMatches:
            return

        self.has_card = bool(navigation or actions)

        left = navigation[0] if navigation else ("", "")
        right = navigation[1] if len(navigation) > 1 else ("", "")
        left_text = f"[dim]◀[/] [bold]{left[0]}[/] {left[1]}" if left[0] else ""
        right_text = f"[bold]{right[0]}[/] {right[1]} [dim]▶[/]" if right[0] else ""

        primary = ""
        remainder: list[tuple[str, str]] = []
        if actions:
            key, desc = actions[0]
            primary = f"[dim]Next[/] [bold]{key}[/] {desc}" if key else f"[dim]Next[/] {desc}"
            remainder = actions[1:]

        self._update_static(nav_left, left_text if self.has_card else "")
        self._update_static(nav_center, f"[dim]mode: {mode_label}[/]")
        self._update_static(nav_right, right_text if self.has_card else "")
        self._update_static(actions_left, primary)
        self._update_static(actions_main, _render_group(remainder))
        self._update_static(global_main, _render_group(global_hints, separator="  "))

    def update_hints(self, text: str) -> None:
        self.show_kanban_hints(
            navigation=[],
            actions=[("", text)] if text else [],
            global_hints=[],
        )

    def clear(self) -> None:
        for widget_id in (
            "#hint-nav-left",
            "#hint-nav-center",
            "#hint-nav-right",
            "#hint-actions-left",
            "#hint-actions",
            "#hint-global",
        ):
            try:
                self.query_one(widget_id, Static).update("")
            except NoMatches:
                return
        self.has_card = False
