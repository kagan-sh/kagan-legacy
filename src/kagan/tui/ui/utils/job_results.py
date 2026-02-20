"""Shared helpers for reading async job results."""

from __future__ import annotations

from typing import Any


def job_result_payload(record: object | None) -> dict[str, Any] | None:
    """Return the structured job result payload when available."""
    if record is None:
        return None
    result = getattr(record, "result", None)
    if not isinstance(result, dict):
        return None
    return result


def job_message(record: object | None, default: str) -> str:
    """Resolve a human-readable job message with sensible fallbacks."""
    payload = job_result_payload(record)
    if payload is not None:
        payload_message = payload.get("message")
        if isinstance(payload_message, str) and payload_message.strip():
            return payload_message
    message = getattr(record, "message", None)
    if isinstance(message, str) and message.strip():
        return message
    return default


__all__ = ["job_message", "job_result_payload"]
