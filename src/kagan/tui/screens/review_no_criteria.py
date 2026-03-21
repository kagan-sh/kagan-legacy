from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from kagan.tui.keybindings import REVIEW_NO_CRITERIA_BINDINGS
from kagan.tui.widgets.hint_bar import format_hint


class ReviewNoCriteriaModal(ModalScreen[str | None]):
    BINDINGS = REVIEW_NO_CRITERIA_BINDINGS

    DEFAULT_CSS = """
    ReviewNoCriteriaModal {
        align: center middle;
    }

    ReviewNoCriteriaModal #nac-container {
        width: 56;
        max-width: 90%;
        height: auto;
        background: $surface;
        border: round $warning;
        padding: 2 3;
    }

    ReviewNoCriteriaModal .nac-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        padding-bottom: 1;
        color: $warning;
    }

    ReviewNoCriteriaModal .nac-body {
        text-align: center;
        color: $text;
        padding-bottom: 1;
    }

    ReviewNoCriteriaModal .nac-options {
        width: 100%;
        height: auto;
        padding: 1 2;
        color: $text-muted;
    }

    ReviewNoCriteriaModal .nac-option-recommended {
        color: $primary;
    }

    ReviewNoCriteriaModal .nac-hint {
        width: 100%;
        text-align: center;
        color: $text-disabled;
        padding-top: 1;
        border-top: solid $border;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="nac-container"):
            yield Static("\u26a0 No Acceptance Criteria", classes="nac-title")
            yield Static(
                "This task has no criteria defined.\nChoose how to proceed:",
                classes="nac-body",
            )
            yield Static(
                "  a   Add criteria first (recommended)\n"
                "  Enter   Approve manually\n"
                "  x   Reject and send back",
                classes="nac-options",
            )
            yield Static(
                format_hint(
                    [
                        ("a", "add criteria"),
                        ("Enter", "approve"),
                        ("x", "reject"),
                        ("Esc", "cancel"),
                    ]
                ),
                classes="nac-hint",
            )

    def action_add_criteria(self) -> None:
        self.dismiss("add_criteria")

    def action_approve_manually(self) -> None:
        self.dismiss("approve_manually")

    def action_reject(self) -> None:
        self.dismiss("reject")

    def action_cancel(self) -> None:
        self.dismiss(None)
