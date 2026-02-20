"""Token budget and truncation logic for MCP responses."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

_SUMMARY_TEXT_LIMIT = 8_000
_FULL_TEXT_LIMIT = 32_000
_SUMMARY_DESCRIPTION_LIMIT = 2_000
_FULL_DESCRIPTION_LIMIT = 8_000
_SUMMARY_ACCEPTANCE_ITEM_LIMIT = 400
_FULL_ACCEPTANCE_ITEM_LIMIT = 1_000
_SUMMARY_ACCEPTANCE_ITEMS = 20
_FULL_ACCEPTANCE_ITEMS = 50
_SUMMARY_LOG_ENTRY_LIMIT = 2_500
_FULL_LOG_ENTRY_LIMIT = 10_000
_SUMMARY_LOG_ENTRIES = 3
_FULL_LOG_ENTRIES = 10
_SUMMARY_LOG_BUDGET = 7_500
_FULL_LOG_BUDGET = 24_000
_SUMMARY_RESPONSE_BUDGET = 12_000
_FULL_RESPONSE_BUDGET = 24_000
_SUMMARY_TITLE_LIMIT = 400
_FULL_TITLE_LIMIT = 1_000
_SUMMARY_SCRATCHPAD_FETCH_LIMIT = 6_000
_FULL_SCRATCHPAD_FETCH_LIMIT = 14_000
_SUMMARY_LOG_FETCH_ENTRY_LIMIT = 2_000
_FULL_LOG_FETCH_ENTRY_LIMIT = 6_000
_SUMMARY_LOG_FETCH_BUDGET = 6_000
_FULL_LOG_FETCH_BUDGET = 18_000
_LOG_ENTRY_OVERHEAD_CHARS = 256
_COMPACT_ACCEPTANCE_ITEMS_FULL = 20
_COMPACT_ACCEPTANCE_ITEMS_SUMMARY = 8
_COMPACT_ACCEPTANCE_ITEM_LIMIT_FULL = 320
_COMPACT_ACCEPTANCE_ITEM_LIMIT_SUMMARY = 160
_COMPACT_RUNTIME_REASON_LIMIT_FULL = 600
_COMPACT_RUNTIME_REASON_LIMIT_SUMMARY = 240
_COMPACT_RUNTIME_HINT_LIMIT_FULL = 240
_COMPACT_RUNTIME_HINT_LIMIT_SUMMARY = 120
_COMPACT_RUNTIME_BLOCKED_IDS_FULL = 16
_COMPACT_RUNTIME_BLOCKED_IDS_SUMMARY = 8
_COMPACT_RUNTIME_OVERLAP_HINTS_FULL = 12
_COMPACT_RUNTIME_OVERLAP_HINTS_SUMMARY = 6
_MINIMAL_TITLE_LIMIT = 120
_MINIMAL_TITLE_HARD_LIMIT = 32


def serialized_size(payload: dict[str, Any]) -> int:
    """Calculate serialized size of a payload."""
    return len(json.dumps(payload, ensure_ascii=True, default=str))


def truncate_text(value: str | None, *, limit: int) -> str | None:
    """Truncate text to a maximum character limit."""
    if value is None or len(value) <= limit:
        return value
    omitted_chars = len(value) - limit
    return f"{value[:limit]}\n\n[truncated {omitted_chars} chars]"


def trim_logs_to_budget(logs: list[dict[str, Any]], *, budget_chars: int) -> list[dict[str, Any]]:
    """Keep newest log entries within an overall size budget."""
    if budget_chars <= 0 or not logs:
        return []

    trimmed_newest_first: list[dict[str, Any]] = []
    used = 0
    for log in reversed(logs):
        remaining = budget_chars - used - _LOG_ENTRY_OVERHEAD_CHARS
        if remaining <= 0:
            break

        content = str(log.get("content", ""))
        if len(content) > remaining:
            content = content[-remaining:]

        trimmed_newest_first.append(
            {
                "run": int(log["run"]),
                "content": content,
                "created_at": str(log["created_at"]),
            }
        )
        used += len(content) + _LOG_ENTRY_OVERHEAD_CHARS

    return list(reversed(trimmed_newest_first))


def truncate_acceptance_criteria(value: object, *, mode: str) -> list[str] | None:
    """Truncate acceptance criteria list based on mode."""
    if not isinstance(value, list):
        return None

    item_limit = _FULL_ACCEPTANCE_ITEM_LIMIT if mode == "full" else _SUMMARY_ACCEPTANCE_ITEM_LIMIT
    max_items = _FULL_ACCEPTANCE_ITEMS if mode == "full" else _SUMMARY_ACCEPTANCE_ITEMS

    criteria = [truncate_text(str(item), limit=item_limit) or "" for item in value]
    if len(criteria) <= max_items:
        return criteria

    omitted_count = len(criteria) - max_items
    return [*criteria[:max_items], f"[truncated {omitted_count} criteria]"]


def compact_string_list(
    values: Sequence[object],
    *,
    max_items: int,
    item_limit: int,
    label: str,
) -> list[str]:
    """Compact a list of strings to fit within limits."""
    normalized = [truncate_text(str(value), limit=item_limit) or "" for value in values]
    if len(normalized) <= max_items:
        return normalized
    omitted = len(normalized) - max_items
    return [*normalized[:max_items], f"[truncated {omitted} {label}]"]


def compact_runtime(runtime: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """Compact runtime info to fit within limits."""
    compact = dict(runtime)
    reason_limit = (
        _COMPACT_RUNTIME_REASON_LIMIT_FULL
        if mode == "full"
        else _COMPACT_RUNTIME_REASON_LIMIT_SUMMARY
    )
    hint_limit = (
        _COMPACT_RUNTIME_HINT_LIMIT_FULL if mode == "full" else _COMPACT_RUNTIME_HINT_LIMIT_SUMMARY
    )
    blocked_ids = (
        _COMPACT_RUNTIME_BLOCKED_IDS_FULL
        if mode == "full"
        else _COMPACT_RUNTIME_BLOCKED_IDS_SUMMARY
    )
    overlap_hints = (
        _COMPACT_RUNTIME_OVERLAP_HINTS_FULL
        if mode == "full"
        else _COMPACT_RUNTIME_OVERLAP_HINTS_SUMMARY
    )

    for key in ("blocked_reason", "pending_reason"):
        value = compact.get(key)
        if isinstance(value, str):
            compact[key] = truncate_text(value, limit=reason_limit)

    blocked = compact.get("blocked_by_task_ids")
    if isinstance(blocked, list):
        compact["blocked_by_task_ids"] = compact_string_list(
            blocked,
            max_items=blocked_ids,
            item_limit=hint_limit,
            label="task IDs",
        )

    hints = compact.get("overlap_hints")
    if isinstance(hints, list):
        compact["overlap_hints"] = compact_string_list(
            hints,
            max_items=overlap_hints,
            item_limit=hint_limit,
            label="hints",
        )

    return compact


def fit_task_payload_budget(payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    """Fit task payload within transport budget."""
    budget = _FULL_RESPONSE_BUDGET if mode == "full" else _SUMMARY_RESPONSE_BUDGET
    if serialized_size(payload) <= budget:
        return payload

    trimmed = dict(payload)
    if isinstance(trimmed.get("scratchpad"), str):
        scratchpad_limit = max(0, budget // 3)
        trimmed["scratchpad"] = truncate_text(
            trimmed["scratchpad"],
            limit=scratchpad_limit,
        )

    if isinstance(trimmed.get("description"), str):
        description_limit = max(0, budget // 4)
        trimmed["description"] = truncate_text(
            trimmed["description"],
            limit=description_limit,
        )

    if serialized_size(trimmed) <= budget:
        return trimmed

    if isinstance(trimmed.get("logs"), list):
        logs_budget = max(0, budget // 3)
        trimmed["logs"] = trim_logs_to_budget(trimmed["logs"], budget_chars=logs_budget)

    if isinstance(trimmed.get("title"), str):
        title_limit = _FULL_TITLE_LIMIT if mode == "full" else _SUMMARY_TITLE_LIMIT
        trimmed["title"] = truncate_text(trimmed["title"], limit=title_limit) or ""

    if isinstance(trimmed.get("runtime"), dict):
        trimmed["runtime"] = compact_runtime(trimmed["runtime"], mode=mode)

    if isinstance(trimmed.get("acceptance_criteria"), list):
        if mode == "full":
            max_items = _COMPACT_ACCEPTANCE_ITEMS_FULL
            item_limit = _COMPACT_ACCEPTANCE_ITEM_LIMIT_FULL
        else:
            max_items = _COMPACT_ACCEPTANCE_ITEMS_SUMMARY
            item_limit = _COMPACT_ACCEPTANCE_ITEM_LIMIT_SUMMARY
        trimmed["acceptance_criteria"] = compact_string_list(
            trimmed["acceptance_criteria"],
            max_items=max_items,
            item_limit=item_limit,
            label="criteria",
        )

    if serialized_size(trimmed) <= budget:
        return trimmed

    for key in ("logs", "scratchpad", "runtime", "acceptance_criteria"):
        trimmed.pop(key, None)
        if serialized_size(trimmed) <= budget:
            return trimmed

    if isinstance(trimmed.get("description"), str):
        trimmed["description"] = truncate_text(
            trimmed["description"],
            limit=max(0, budget // 10),
        )
        if serialized_size(trimmed) <= budget:
            return trimmed

    title_value = trimmed.get("title")
    status_value = trimmed.get("status")
    minimal = {
        "task_id": str(trimmed.get("task_id", "")),
        "title": truncate_text(
            str(title_value) if title_value is not None else "",
            limit=_MINIMAL_TITLE_LIMIT,
        )
        or "",
        "status": str(status_value) if status_value is not None else "",
    }
    if serialized_size(minimal) <= budget:
        return minimal
    minimal["title"] = minimal["title"][:_MINIMAL_TITLE_HARD_LIMIT]
    return minimal


__all__ = [
    "compact_runtime",
    "compact_string_list",
    "fit_task_payload_budget",
    "serialized_size",
    "trim_logs_to_budget",
    "truncate_acceptance_criteria",
    "truncate_text",
]
