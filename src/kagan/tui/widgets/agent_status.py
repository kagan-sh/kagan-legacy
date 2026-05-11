from datetime import UTC, datetime, timedelta

from textual.reactive import reactive
from textual.widgets import Static

_HALF_DISC_FRAMES: tuple[str, ...] = ("◐", "◓", "◑", "◒")
_HALF_DISC_FPS: float = 4.0
_HALF_DISC_INTERVAL: float = 1.0 / _HALF_DISC_FPS

STATUS_META = {
    "running": ("[#d4a84b]◐[/]", "Running"),  # placeholder; glyph is animated in _refresh_display
    "completed": ("[green]✓[/]", "Completed"),
    "failed": ("[red]✗[/]", "Failed"),
    "idle": ("[dim]○[/]", "Idle"),
}


def _format_elapsed(delta: timedelta) -> str:
    total_seconds = max(int(delta.total_seconds()), 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds:02d}s"


class AgentStatusPanel(Static):
    DEFAULT_CSS = """
    AgentStatusPanel {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    backend: reactive[str] = reactive("-")
    status: reactive[str] = reactive("idle")
    started_at: reactive[datetime | None] = reactive(None)
    run_id: reactive[str] = reactive("-")
    pid: reactive[int | None] = reactive(None)
    elapsed: reactive[str] = reactive("0m 00s")
    context_used: reactive[int | None] = reactive(None)
    context_size: reactive[int | None] = reactive(None)
    cost_amount: reactive[float | None] = reactive(None)
    cost_currency: reactive[str | None] = reactive(None)
    _frame_index: reactive[int] = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._spin_timer = None

    def on_mount(self) -> None:
        self.tooltip = "Agent execution status, elapsed time, context usage, and cost"
        self._refresh_display()

    def set_run_info(
        self,
        backend: str,
        status: str,
        started_at: datetime | None,
        run_id: str,
        pid: int | None,
    ) -> None:
        self.backend = backend.strip() or "-"
        self.status = status.strip().lower() or "idle"
        self.started_at = started_at
        self.run_id = run_id.strip() or "-"
        self.pid = pid
        self.tick()

    def set_usage_info(
        self,
        context_used: int | None,
        context_size: int | None,
        cost_amount: float | None,
        cost_currency: str | None,
    ) -> None:
        self.context_used = context_used
        self.context_size = context_size
        self.cost_amount = cost_amount
        self.cost_currency = cost_currency

    def tick(self) -> None:
        if self.started_at is None:
            self.elapsed = "0m 00s"
            return
        started = self.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        self.elapsed = _format_elapsed(datetime.now(UTC) - started)

    def watch_status(self, status: str) -> None:
        if status == "running":
            self._start_spin()
        else:
            self._stop_spin()
        self._refresh_display()

    def watch_backend(self, _: str) -> None:
        self._refresh_display()

    def watch_elapsed(self, _: str) -> None:
        self._refresh_display()

    def watch_run_id(self, _: str) -> None:
        self._refresh_display()

    def watch_pid(self, _: int | None) -> None:
        self._refresh_display()

    def watch_context_used(self, _: int | None) -> None:
        self._refresh_display()

    def watch_context_size(self, _: int | None) -> None:
        self._refresh_display()

    def watch_cost_amount(self, _: float | None) -> None:
        self._refresh_display()

    def watch_cost_currency(self, _: str | None) -> None:
        self._refresh_display()

    def watch__frame_index(self, _: int) -> None:
        self._refresh_display()

    def _start_spin(self) -> None:
        if self._spin_timer is None:
            self._spin_timer = self.set_interval(_HALF_DISC_INTERVAL, self._next_frame, pause=False)

    def _stop_spin(self) -> None:
        if self._spin_timer is not None:
            self._spin_timer.stop()
            self._spin_timer = None
        self._frame_index = 0

    def _next_frame(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(_HALF_DISC_FRAMES)

    def _running_symbol(self) -> str:
        glyph = _HALF_DISC_FRAMES[self._frame_index]
        return f"[#d4a84b]{glyph}[/]"

    def _refresh_display(self) -> None:
        if self.status == "running":
            symbol = self._running_symbol()
            label = "Running"
        else:
            _fallback = ("[dim]○[/]", self.status.title() or "Idle")
            symbol, label = STATUS_META.get(self.status, _fallback)
        pid_value = "-" if self.pid is None else str(self.pid)
        context_line = "Context: -"
        ctx_used = self.context_used
        ctx_total = self.context_size
        if ctx_used is not None and ctx_total is not None and ctx_total > 0:
            pct = ctx_used / ctx_total
            if pct > 0.8:
                ctx_color = "red"
            elif pct > 0.6:
                ctx_color = "yellow"
            else:
                ctx_color = "green"
            context_line = (
                f"Context: [{ctx_color}]{ctx_used:,} / {ctx_total:,} ({pct:.0%})[/{ctx_color}]"
            )
        elif ctx_used is not None and ctx_total is not None:
            context_line = f"Context: {ctx_used:,} / {ctx_total:,}"
        cost_line = "Cost: -"
        if self.cost_amount is not None:
            currency = self.cost_currency or "USD"
            if currency == "USD":
                cost_line = f"Cost: ${self.cost_amount:.4f}"
            else:
                cost_line = f"Cost: {self.cost_amount:.4f} {currency}"
        self.update(
            "\n".join(
                [
                    f"Backend: {self.backend}",
                    f"Status: {symbol} {label}",
                    f"Elapsed: {self.elapsed}",
                    f"Run ID: {self.run_id}",
                    f"PID: {pid_value}",
                    context_line,
                    cost_line,
                ]
            )
        )


__all__ = ["AgentStatusPanel"]
