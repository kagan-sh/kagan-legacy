"""Analytics modal — backend stats and session activity summary."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.app import KaganApp

ANALYTICS_BINDINGS: list[Binding] = [
    Binding("escape", "close", "Close"),
    Binding("r", "refresh", "Refresh"),
]


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    if seconds < 60:
        return f"{round(seconds)}s"
    mins = int(seconds // 60)
    secs = round(seconds % 60)
    return f"{mins}m {secs}s" if secs else f"{mins}m"


def _build_backend_table(stats: list[dict[str, Any]]) -> str:
    if not stats:
        return "  No backend data yet. Run some sessions to see metrics."

    # Column widths
    name_w = max(len(s["agent_backend"]) for s in stats)
    name_w = max(name_w, 7)  # "Backend" header

    hdr = (
        f"  {'Backend':<{name_w}}  {'Sessions':>8}"
        f"  {'Success':>8}  {'Avg Duration':>13}  {'Retry':>6}"
    )
    sep = f"  {'─' * name_w}  {'─' * 8}  {'─' * 8}  {'─' * 13}  {'─' * 6}"
    lines = [hdr, sep]
    for s in stats:
        lines.append(
            f"  {s['agent_backend']:<{name_w}}"
            f"  {s['count']:>8}"
            f"  {_fmt_pct(s['success_rate']):>8}"
            f"  {_fmt_duration(s.get('avg_duration_seconds')):>13}"
            f"  {_fmt_pct(s.get('retry_rate', 0)):>6}"
        )
    return "\n".join(lines)


def _build_timeline_summary(timeline: list[dict[str, Any]]) -> str:
    if not timeline:
        return "  No session activity in this period."

    total = sum(d["total"] for d in timeline)
    completed = sum(d["completed"] for d in timeline)
    failed = sum(d["failed"] for d in timeline)
    cancelled = sum(d["cancelled"] for d in timeline)
    days_active = sum(1 for d in timeline if d["total"] > 0)

    lines = [
        f"  Total sessions: {total}",
        f"  Completed: {completed}  Failed: {failed}  Cancelled: {cancelled}",
        f"  Active days: {days_active} / {len(timeline)}",
    ]
    if total > 0:
        success_rate = completed / total
        lines.append(f"  Overall success rate: {_fmt_pct(success_rate)}")
    return "\n".join(lines)


class AnalyticsModal(ModalScreen[None]):
    DEFAULT_CSS = """
    AnalyticsModal {
        align: center middle;
    }

    AnalyticsModal #analytics-container {
        width: 90;
        max-height: 80%;
        background: $surface;
        border: round $border;
        padding: 1 2;
    }

    AnalyticsModal .analytics-title {
        text-align: center;
        text-style: bold;
        width: 100%;
        margin-bottom: 1;
    }

    AnalyticsModal .analytics-section-title {
        text-style: bold;
        width: 100%;
        margin-top: 1;
        color: $text-muted;
    }

    AnalyticsModal .analytics-body {
        width: 100%;
    }

    AnalyticsModal .analytics-hint {
        text-align: center;
        color: $text-muted;
        width: 100%;
        margin-top: 1;
    }
    """

    BINDINGS = ANALYTICS_BINDINGS

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="analytics-container"):
            yield Static("Analytics", classes="analytics-title")
            yield Static("▸ Backend Performance", classes="analytics-section-title")
            yield Static("Loading...", id="backend-stats", classes="analytics-body")
            yield Static("▸ Session Activity (30 days)", classes="analytics-section-title")
            yield Static("Loading...", id="timeline-summary", classes="analytics-body")
            yield Static("[r] refresh  [esc] close", classes="analytics-hint")
        yield Footer()

    async def on_mount(self) -> None:
        await self._load_data()

    async def _load_data(self) -> None:
        app: KaganApp = self.app  # type: ignore[assignment]
        project_id = app.core.active_project_id
        if not project_id:
            self.query_one("#backend-stats", Static).update("  No active project.")
            self.query_one("#timeline-summary", Static).update("")
            return

        try:
            stats, timeline = await asyncio.gather(
                app.core.analytics.backend_stats(project_id),
                app.core.analytics.session_timeline(project_id, days=30),
            )
            self.query_one("#backend-stats", Static).update(_build_backend_table(stats))
            self.query_one("#timeline-summary", Static).update(_build_timeline_summary(timeline))
        except Exception as exc:
            self.query_one("#backend-stats", Static).update(f"  Error: {exc}")

    async def action_refresh(self) -> None:
        self.query_one("#backend-stats", Static).update("Loading...")
        self.query_one("#timeline-summary", Static).update("Loading...")
        await self._load_data()

    def action_close(self) -> None:
        self.dismiss(None)
