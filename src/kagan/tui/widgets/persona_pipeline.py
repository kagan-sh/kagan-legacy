from collections.abc import Sequence

from textual.reactive import reactive
from textual.widgets import Static

STATUS_SYMBOLS = {
    "completed": "[green]✓[/]",
    "running": "[yellow]●[/]",
    "pending": "[dim]○[/]",
}


class PersonaPipelineMap(Static):
    DEFAULT_CSS = """
    PersonaPipelineMap {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    """

    steps: reactive[list[tuple[str, str]]] = reactive(list)

    def on_mount(self) -> None:
        self._refresh_display()

    def set_pipeline(self, steps: list[tuple[str, str]]) -> None:
        self.steps = [(name.strip().upper(), status.strip().lower()) for name, status in steps]
        self.display = bool(self.steps)
        self._refresh_display()

    def watch_steps(self, _: Sequence[tuple[str, str]]) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        if not self.steps:
            self.update("")
            return

        chain = "  ─→  ".join(self._format_step(name, status) for name, status in self.steps)
        current_name, current_index = self._current_step()
        total = len(self.steps)
        self.update(f"{chain}\nCurrent: {current_name} (run {current_index}/{total})")

    def _format_step(self, name: str, status: str) -> str:
        symbol = STATUS_SYMBOLS.get(status, "[dim]○[/]")
        return f"{symbol} {name}"

    def _current_step(self) -> tuple[str, int]:
        for index, (name, status) in enumerate(self.steps, start=1):
            if status == "running":
                return name, index
        for index, (name, status) in enumerate(self.steps, start=1):
            if status == "pending":
                return name, index
        name, _ = self.steps[-1]
        return name, len(self.steps)


__all__ = ["PersonaPipelineMap"]
