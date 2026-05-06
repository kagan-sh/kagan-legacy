from textual.binding import BindingType
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Label, Static

from kagan.tui.keybindings import (
    FooterBuilder,
)


class ContextFooter(Horizontal):
    DEFAULT_CSS = """
    ContextFooter {
        height: 1;
        background: $surface-darken-1;
        color: $text;
        dock: bottom;
    }
    ContextFooter > Static {
        content-align: center middle;
        height: 1;
    }
    ContextFooter .footer-left {
        width: 40%;
        content-align: left middle;
        padding-left: 1;
    }
    ContextFooter .footer-center {
        width: 35%;
        content-align: center middle;
        color: $text-muted;
    }
    ContextFooter .footer-right {
        width: 25%;
        content-align: right middle;
        padding-right: 1;
        color: $text-muted;
    }
    ContextFooter .footer-key {
        color: $text-accent;
        text-style: bold;
    }
    ContextFooter .footer-dim {
        color: $text-muted;
    }
    """

    context: reactive[str] = reactive("kanban")
    has_focused_item: reactive[bool] = reactive(False)
    sub_context: reactive[str] = reactive("")

    def compose(self):
        left_widget = Static("", classes="footer-left")
        left_widget.tooltip = "Primary actions for current context"
        yield left_widget
        center_widget = Static("", classes="footer-center")
        center_widget.tooltip = "Navigation hints and navigation options"
        yield center_widget
        right_widget = Static("", classes="footer-right")
        right_widget.tooltip = "Global keyboard shortcuts (press ? for help)"
        yield right_widget

    def watch_context(self, context: str) -> None:
        self._update_display()

    def watch_has_focused_item(self, has_focus: bool) -> None:
        self._update_display()

    def watch_sub_context(self, sub_context: str) -> None:
        self._update_display()

    def set_context(
        self,
        context: str,
        has_focused_item: bool = False,
        sub_context: str = "",
    ) -> None:
        self.context = context
        self.has_focused_item = has_focused_item
        self.sub_context = sub_context

    def _update_display(self) -> None:
        left = self.query_one(".footer-left", Static)
        center = self.query_one(".footer-center", Static)
        right = self.query_one(".footer-right", Static)

        width = self.app.size.width if self.app else 80
        left_content = self._build_primary_actions(width)
        center_content = self._build_navigation_hints(width)
        right_content = self._build_global_hints(width)

        left.update(left_content)
        center.update(center_content)
        right.update(right_content)

    def _build_primary_actions(self, width: int) -> str:
        if self.context == "kanban":
            return self._format_hints(FooterBuilder.kanban_core())
        elif self.context == "kanban_with_card":
            return self._format_hints(FooterBuilder.kanban_with_card())
        elif self.context == "task":
            if self.sub_context == "review":
                return self._format_hints(FooterBuilder.task_screen_review())
            return self._format_hints(FooterBuilder.task_screen())
        elif self.context == "session":
            return self._format_hints(FooterBuilder.session_dashboard())
        elif self.context == "settings":
            return self._format_hints(FooterBuilder.settings())
        elif self.context == "confirm":
            return self._format_hints(FooterBuilder.confirm())
        elif self.context == "chat":
            return self._format_hints(FooterBuilder.chat())
        return ""

    def _build_navigation_hints(self, width: int) -> str:
        if width < 100:
            return ""  # Hide navigation hints on narrow screens

        if self.context in ("kanban", "kanban_with_card"):
            return self._format_hints(FooterBuilder.kanban_navigation(), compact=True)
        elif self.context == "task":
            return "[dim]1/2 tabs · Esc back[/]"
        elif self.context == "session":
            return "[dim]Ctrl+K sessions · Ctrl+. AI panel[/]"
        return ""

    def _build_global_hints(self, width: int) -> str:
        if width < 80:
            return "[bold]?[/]"
        return "[bold]?[/] help  [bold]Ctrl+Shift+P[/] quick actions"

    def _format_hints(
        self,
        hints: list[tuple[str, str]],
        *,
        compact: bool = False,
    ) -> str:
        parts = []
        for key, desc in hints:
            if compact:
                parts.append(f"[bold]{key}[/]")
            else:
                parts.append(f"[bold]{key}[/] {desc}")
        separator = "  "
        return separator.join(parts)

    def on_resize(self) -> None:
        self._update_display()


class SimpleFooter(Label):
    DEFAULT_CSS = """
    SimpleFooter {
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        content-align: center middle;
        dock: bottom;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


def build_footer_for_bindings(
    bindings: list[BindingType],
    *,
    show_all: bool = False,
    max_items: int = 6,
) -> str:
    from textual.binding import Binding

    parts = []
    count = 0
    for binding in bindings:
        if not isinstance(binding, Binding):
            continue
        if binding.show is False and not show_all:
            continue
        if not binding.description:
            continue

        key = binding.key_display or binding.key
        desc = binding.description
        parts.append(f"[bold]{key}[/] {desc}")
        count += 1

        if count >= max_items:
            break

    return "  ".join(parts)
