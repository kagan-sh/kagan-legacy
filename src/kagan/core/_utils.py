from __future__ import annotations

from datetime import UTC, datetime


def utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat() + "Z"


def format_percentage(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    if seconds < 60:
        return f"{round(seconds)}s"
    mins = int(seconds // 60)
    secs = round(seconds % 60)
    return f"{mins}m {secs}s" if secs else f"{mins}m"
