"""Shared numeric bounds for settings validation and normalization."""

from __future__ import annotations

DEFAULT_MAX_CONCURRENT_AGENTS = 3
MIN_MAX_CONCURRENT_AGENTS = 1
MAX_MAX_CONCURRENT_AGENTS = 10

MIN_TASK_WAIT_TIMEOUT_SECONDS = 1
MAX_TASK_WAIT_TIMEOUT_SECONDS = 3_600


def coerce_max_concurrent_agents(value: object) -> int:
    """Coerce untrusted config values to a safe max_concurrent_agents default."""
    if isinstance(value, bool):
        return DEFAULT_MAX_CONCURRENT_AGENTS
    if isinstance(value, int):
        if MIN_MAX_CONCURRENT_AGENTS <= value <= MAX_MAX_CONCURRENT_AGENTS:
            return value
        return DEFAULT_MAX_CONCURRENT_AGENTS
    if isinstance(value, str):
        cleaned = value.strip()
        try:
            parsed = int(cleaned)
        except ValueError:
            return DEFAULT_MAX_CONCURRENT_AGENTS
        if MIN_MAX_CONCURRENT_AGENTS <= parsed <= MAX_MAX_CONCURRENT_AGENTS:
            return parsed
        return DEFAULT_MAX_CONCURRENT_AGENTS
    return DEFAULT_MAX_CONCURRENT_AGENTS


__all__ = [
    "DEFAULT_MAX_CONCURRENT_AGENTS",
    "MAX_MAX_CONCURRENT_AGENTS",
    "MAX_TASK_WAIT_TIMEOUT_SECONDS",
    "MIN_MAX_CONCURRENT_AGENTS",
    "MIN_TASK_WAIT_TIMEOUT_SECONDS",
    "coerce_max_concurrent_agents",
]
