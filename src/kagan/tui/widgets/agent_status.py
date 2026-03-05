from datetime import UTC, datetime, timedelta

from textual.reactive import reactive
from textual.widgets import Static

STATUS_META = {
    "running": ("[yellow]●[/]", "Running"),
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

    def on_mount(self) -> None:
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

    def tick(self) -> None:
        if self.started_at is None:
            self.elapsed = "0m 00s"
            return
        started = self.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        self.elapsed = _format_elapsed(datetime.now(UTC) - started)

    def watch_backend(self, _: str) -> None:
        self._refresh_display()

    def watch_status(self, _: str) -> None:
        self._refresh_display()

    def watch_elapsed(self, _: str) -> None:
        self._refresh_display()

    def watch_run_id(self, _: str) -> None:
        self._refresh_display()

    def watch_pid(self, _: int | None) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        symbol, label = STATUS_META.get(self.status, ("[dim]○[/]", self.status.title() or "Idle"))
        pid_value = "-" if self.pid is None else str(self.pid)
        self.update(
            "\n".join(
                [
                    f"Backend: {self.backend}",
                    f"Status: {symbol} {label}",
                    f"Elapsed: {self.elapsed}",
                    f"Run ID: {self.run_id}",
                    f"PID: {pid_value}",
                ]
            )
        )


__all__ = ["AgentStatusPanel"]
