from time import monotonic

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

WAVE_FRAMES = (
    "ᘚᘚᘚᘚ",
    "ᘛᘚᘚᘚ",
    "ᘛᘛᘚᘚ",
    "ᘛᘛᘛᘚ",
    "ᘛᘛᘛᘛ",
    "ᘚᘛᘛᘛ",
    "ᘚᘚᘛᘛ",
    "ᘚᘚᘚᘛ",
)
WAVE_INTERVAL_SECONDS = 0.1
WORKING_STATES = frozenset({"thinking", "initializing"})
STATUS_LABELS = {
    "ready": "Ready",
    "thinking": "Thinking",
    "initializing": "Initializing",
    "error": "Error",
    "waiting": "Waiting",
}
STATUS_SYMBOLS = {
    "ready": "●",
    "error": "✗",
    "waiting": "○",
}


def _format_elapsed(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m"


class StatusBar(Horizontal):
    status: reactive[str] = reactive("ready")
    hint: reactive[str] = reactive("")
    agent_backend: reactive[str] = reactive("")
    turn_count: reactive[int] = reactive(0)

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id or "agent-status-bar", classes=classes)
        self._frame_index = 0
        self._wave_timer = None
        self._elapsed_timer = None
        self._work_started_at: float | None = None

    def compose(self) -> ComposeResult:
        left_widget = Static("", classes="status-left", id="chat-overlay-status-left")
        left_widget.tooltip = "Agent status and execution progress"
        yield left_widget
        right_widget = Static("", classes="status-right", id="chat-overlay-status-right")
        right_widget.tooltip = "Current action or hint (Press Esc to interrupt)"
        yield right_widget

    def on_mount(self) -> None:
        self._update_display()

    def watch_status(self, status: str) -> None:
        if status in WORKING_STATES:
            self._start_animation()
            self._start_elapsed_timer()
        else:
            self._stop_animation()
            self._stop_elapsed_timer()
        self._set_state_classes(status)
        self._update_display()

    def watch_hint(self, _hint: str) -> None:
        self._update_display()

    def update_status(self, status: str) -> None:
        self.status = status.strip().lower() or "ready"

    def update_hint(self, hint: str) -> None:
        self.hint = hint

    def update_agent_info(self, backend: str, turns: int) -> None:
        self.agent_backend = backend
        self.turn_count = turns

    def update_turn_count(self, count: int) -> None:
        self.turn_count = count

    def _start_animation(self) -> None:
        if self._wave_timer is None:
            self._frame_index = 0
            self._wave_timer = self.set_interval(
                WAVE_INTERVAL_SECONDS,
                self._next_frame,
                pause=False,
            )

    def _stop_animation(self) -> None:
        if self._wave_timer is not None:
            self._wave_timer.stop()
            self._wave_timer = None
            self._frame_index = 0

    def _next_frame(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(WAVE_FRAMES)
        self._update_display()

    def _start_elapsed_timer(self) -> None:
        if self._work_started_at is None:
            self._work_started_at = monotonic()
        if self._elapsed_timer is None:
            self._elapsed_timer = self.set_interval(1.0, self._update_display, pause=False)

    def _stop_elapsed_timer(self) -> None:
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
        self._work_started_at = None

    def _set_state_classes(self, status: str) -> None:
        for name in ("ready", "thinking", "initializing", "error", "waiting"):
            self.set_class(status == name, f"status-{name}")

    def _build_status_text(self) -> str:
        status = self.status
        label = STATUS_LABELS.get(status, status.capitalize())
        if status in WORKING_STATES:
            symbol = WAVE_FRAMES[self._frame_index]
            if self._work_started_at is not None:
                label = f"{label} · {_format_elapsed(monotonic() - self._work_started_at)}"
        else:
            symbol = STATUS_SYMBOLS.get(status, "○")
        extras: list[str] = []
        if self.agent_backend:
            extras.append(self.agent_backend)
        if self.turn_count > 0:
            noun = "msg" if self.turn_count == 1 else "msgs"
            extras.append(f"{self.turn_count} {noun}")
        suffix = f" · {' · '.join(extras)}" if extras else ""
        return f"{symbol} {label}{suffix}"

    def _update_display(self) -> None:
        try:
            self.query_one("#chat-overlay-status-left", Static).update(self._build_status_text())
            right_text = self.hint
            if not right_text and self.status in WORKING_STATES:
                right_text = "esc interrupt"
            self.query_one("#chat-overlay-status-right", Static).update(right_text)
        except Exception:
            pass  # Widget not yet composed — on_mount will call us again
