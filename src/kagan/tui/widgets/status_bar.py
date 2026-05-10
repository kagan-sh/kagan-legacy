from collections.abc import Callable
from time import monotonic

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from kagan.tui.theme import MOTION_REDUCED

# A Segment is a zero-arg callable returning str | None.
# None means "hide this segment in the current render frame."
Segment = Callable[[], str | None]


def _render_segments(segments: list[Segment], sep: str = " · ") -> str:
    """Call each segment, drop Nones, join the rest with *sep*."""
    parts: list[str] = []
    for seg in segments:
        value = seg()
        if value is not None:
            parts.append(value)
    return sep.join(parts)


WAVE_FRAMES = ("◐", "◓", "◑", "◒")
WAVE_INTERVAL_SECONDS = 0.25  # 4 fps, matches chat REPL streaming glyph
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
    access_mode: reactive[str] = reactive("")
    branch_name: reactive[str] = reactive("")

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

    def watch_access_mode(self, _: str) -> None:
        self._update_display()

    def watch_branch_name(self, _: str) -> None:
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
        if MOTION_REDUCED or self._wave_timer is not None:
            return
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

    def _make_status_segments(self) -> list[Segment]:
        """Build the segment list for the left status column.

        Each Segment is a zero-arg callable returning str | None.
        None segments are dropped by _render_segments.
        """
        status = self.status
        label = STATUS_LABELS.get(status, status.capitalize())

        def _symbol_label() -> str | None:
            if status in WORKING_STATES:
                sym = f"[#fbbf24]{WAVE_FRAMES[self._frame_index]}[/]"
                elapsed = (
                    f"{label} · {_format_elapsed(monotonic() - self._work_started_at)}"
                    if self._work_started_at is not None
                    else label
                )
                return f"{sym} {elapsed}"
            sym = STATUS_SYMBOLS.get(status, "○")
            return f"{sym} {label}"

        def _access_mode() -> str | None:
            if not self.access_mode:
                return None
            mode_color = "#fbbf24" if self.access_mode == "Full" else ""
            mode_start = f"[{mode_color}]" if mode_color else ""
            mode_end = "[/]" if mode_color else ""
            return f"{mode_start}[{self.access_mode} ▾]{mode_end}"

        def _branch() -> str | None:
            return self.branch_name or None

        def _backend() -> str | None:
            return self.agent_backend or None

        def _msgs() -> str | None:
            if self.turn_count <= 0:
                return None
            noun = "msg" if self.turn_count == 1 else "msgs"
            return f"{self.turn_count} {noun}"

        return [_symbol_label, _access_mode, _branch, _backend, _msgs]

    def _build_status_text(self) -> str:
        return _render_segments(self._make_status_segments())

    def _update_display(self) -> None:
        try:
            self.query_one("#chat-overlay-status-left", Static).update(self._build_status_text())
            right_text = self.hint
            if not right_text and self.status in WORKING_STATES:
                right_text = "esc interrupt"
            self.query_one("#chat-overlay-status-right", Static).update(right_text)
        except Exception:
            pass  # Widget not yet composed — on_mount will call us again
