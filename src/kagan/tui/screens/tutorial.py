from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static


@dataclass(frozen=True)
class TutorialStep:
    title: str
    body: str


class TutorialOverlay(Widget):
    can_focus = True

    STEPS: tuple[TutorialStep, ...] = (
        TutorialStep("Move", "Use h j k l or arrows to move between cards."),
        TutorialStep(
            "Inspect",
            "Press Enter to inspect the selected task. "
            "Press Enter again to open the full task screen.",
        ),
        TutorialStep(
            "Create",
            "Press n to create a task. Start (s) to run it in the background "
            "or attach (a) to open it in your editor or terminal.",
        ),
        TutorialStep("Help", "Press ? or F1 for full help."),
    )

    class Dismissed(Message):
        pass

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.step_index = 0

    def compose(self) -> ComposeResult:
        with Container(classes="tutorial-container"):
            step = self.STEPS[self.step_index]
            yield Static(step.title, classes="tutorial-title")
            yield Static(step.body, classes="tutorial-subtitle")
            with Container(classes="tutorial-shortcuts"):
                yield self._shortcut_row("h j k l / arrows", "Move between cards")
                yield self._shortcut_row("Enter", "Inspect selected task")
                yield self._shortcut_row("Enter again", "Open full task screen")
                yield self._shortcut_row("Shift+Left / Shift+Right", "Move task between columns")
                yield self._shortcut_row("n", "Create task")
                yield self._shortcut_row("s / a", "Run in background / open in editor")
                yield self._shortcut_row("F2 / Ctrl+Shift+P", "Open Quick Actions")
                yield self._shortcut_row("Ctrl+O / Ctrl+R", "Projects / Repositories")
                yield self._shortcut_row("? / F1", "Open full help")
            yield Static("Esc to dismiss", classes="tutorial-hint")

    @staticmethod
    def _shortcut_row(keys: str, description: str) -> Horizontal:
        return Horizontal(
            Static(keys, classes="tutorial-key"),
            Static("|", classes="tutorial-separator"),
            Static(description, classes="tutorial-desc"),
            classes="tutorial-row",
        )

    def validate_step_index(self, value: int) -> int:
        if value < 0:
            return 0
        last = len(self.STEPS) - 1
        if value > last:
            return last
        return value

    def process_tutorial_key(self, key: str) -> bool:
        normalized = key.casefold()
        if normalized in {"escape", "q"}:
            self.post_message(self.Dismissed())
            return False
        if normalized in {"enter", "right", "l"}:
            last = len(self.STEPS) - 1
            if self.step_index < last:
                self.step_index = self.step_index + 1
                return True
            return normalized != "enter"
        if normalized in {"left", "h"}:
            self.step_index = self.validate_step_index(self.step_index - 1)
            return True
        return True

    def set_visible(self, visible: bool) -> None:
        self.display = visible
        self.set_class(visible, "visible")
