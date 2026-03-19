from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.events import Click
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, Rule, Static

from kagan.tui.keybindings import TMUX_GATEWAY_BINDINGS
from kagan.tui.widgets.hint_bar import format_hint

__all__ = [
    "TMUX_DOCS_URL",
    "AttachedInstructionsModal",
]

TMUX_DOCS_URL = "https://github.com/tmux/tmux/wiki"


class AttachedInstructionsModal(ModalScreen[str | None]):
    BINDINGS = TMUX_GATEWAY_BINDINGS

    def __init__(
        self,
        task_id: str,
        task_title: str,
        backend: str,
        prompt_path: Path,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._task_id = task_id
        self._task_title = task_title
        self._backend = backend
        self._prompt_path = prompt_path

    def compose(self) -> ComposeResult:
        with Container(id="attached-instructions-container"):
            yield Label("Interactive Session Instructions", classes="modal-title")
            yield Rule()

            if self._backend == "tmux":
                yield Static(
                    "You are about to enter a [bold]tmux[/bold] session.\n"
                    "Kagan keybindings are paused until you detach back to Kagan.",
                    classes="tmux-intro",
                )
                yield Rule(line_style="heavy")
                yield Label("Essential Commands", classes="section-title")
                with Vertical(classes="hotkey-list"):
                    yield self._hotkey_row("Ctrl+b d", "Detach (return to Kagan)")
                    yield self._hotkey_row("Ctrl+b c", "Create new window")
                    yield self._hotkey_row("Ctrl+b n/p", "Next / previous window")
                    yield self._hotkey_row("Ctrl+b %", "Split pane vertically")
                    yield self._hotkey_row('Ctrl+b "', "Split pane horizontally")
                    yield self._hotkey_row("Ctrl+b ?", "Show all tmux bindings")
                yield Rule()
                yield Static(TMUX_DOCS_URL, classes="tmux-link")
            elif self._backend == "nvim":
                yield Static(
                    "Kagan will open [bold]Neovim[/bold] in this task worktree.\n"
                    "Startup prompt opens first for fast handoff into your AI plugin.",
                    classes="tmux-intro",
                )
                yield Rule(line_style="heavy")
                yield Label("Recommended Flow", classes="section-title")
                with Vertical(classes="hotkey-list"):
                    yield Static(
                        f"1. Neovim opens with startup prompt:\n{self._prompt_path}",
                        classes="tmux-desc",
                    )
                    yield Static(
                        "2. Kagan attempts to open chat automatically if one is installed.",
                        classes="tmux-desc",
                    )
                    yield Static(
                        "3. If needed, run one manually: :CodeCompanionChat / :AvanteChat / "
                        ":CopilotChat / :ClaudeCode",
                        classes="tmux-desc",
                    )
                    yield Static(
                        "4. Keep task in IN_PROGRESS while pairing; move to REVIEW when ready.",
                        classes="tmux-desc",
                    )
            else:
                tool_name = {
                    "vscode": "VS Code",
                    "cursor": "Cursor",
                    "windsurf": "Windsurf",
                    "kiro": "Kiro",
                    "antigravity": "Antigravity",
                }.get(self._backend, self._backend.title())
                yield Static(
                    f"Kagan will open [bold]{tool_name}[/bold] for this task.\n"
                    "Preferred workflow: paste Kagan startup prompt into chat first.",
                    classes="tmux-intro",
                )
                yield Rule(line_style="heavy")
                yield Label("What To Do Next", classes="section-title")
                with Vertical(classes="hotkey-list"):
                    yield Static(
                        "1. Open chat interface in the IDE (Copilot Chat/Cursor Chat).",
                        classes="tmux-desc",
                    )
                    yield Static(
                        f"2. Open startup prompt file:\n{self._prompt_path}",
                        classes="tmux-desc",
                    )
                    yield Static(
                        f"3. Copy prompt contents and paste into {tool_name} chat.",
                        classes="tmux-desc",
                    )
                    yield Static(
                        "4. Agent uses Kagan MCP and should move the task to REVIEW when done.",
                        classes="tmux-desc",
                    )

            yield Static(
                format_hint([("Enter", "continue"), ("s", "don't show again"), ("Esc", "cancel")]),
                classes="tmux-hint",
            )
        yield Footer(show_command_palette=False)

    def _hotkey_row(self, key: str, description: str) -> Horizontal:
        return Horizontal(
            Static(key, classes="tmux-key"),
            Static(description, classes="tmux-desc"),
            classes="tmux-hotkey-row",
        )

    def on_click(self, event: Click) -> None:
        try:
            container = self.query_one("#attached-instructions-container")
            if not container.region.contains(event.screen_x, event.screen_y):
                self.dismiss(None)
        except (NoMatches, AttributeError):
            pass

    def action_proceed(self) -> None:
        self.dismiss("proceed")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_skip_future(self) -> None:
        self.dismiss("skip_future")
