"""Token budget and truncation logic for MCP responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

_LOG_ENTRY_OVERHEAD_CHARS = 256
_MINIMAL_TITLE_LIMIT = 120
_MINIMAL_TITLE_HARD_LIMIT = 32


@dataclass(frozen=True, slots=True)
class TruncationProfile:
    text_limit: int
    description_limit: int
    acceptance_item_limit: int
    acceptance_items: int
    log_entry_limit: int
    log_entries: int
    log_budget: int
    response_budget: int
    title_limit: int
    scratchpad_fetch_limit: int
    log_fetch_entry_limit: int
    log_fetch_budget: int
    compact_acceptance_items: int
    compact_acceptance_item_limit: int
    compact_reason_limit: int
    compact_hint_limit: int
    compact_blocked_ids: int
    compact_overlap_hints: int


SUMMARY_PROFILE = TruncationProfile(
    text_limit=8_000,
    description_limit=2_000,
    acceptance_item_limit=400,
    acceptance_items=20,
    log_entry_limit=2_500,
    log_entries=3,
    log_budget=7_500,
    response_budget=12_000,
    title_limit=400,
    scratchpad_fetch_limit=6_000,
    log_fetch_entry_limit=2_000,
    log_fetch_budget=6_000,
    compact_acceptance_items=8,
    compact_acceptance_item_limit=160,
    compact_reason_limit=240,
    compact_hint_limit=120,
    compact_blocked_ids=8,
    compact_overlap_hints=6,
)

FULL_PROFILE = TruncationProfile(
    text_limit=32_000,
    description_limit=8_000,
    acceptance_item_limit=1_000,
    acceptance_items=50,
    log_entry_limit=10_000,
    log_entries=10,
    log_budget=24_000,
    response_budget=24_000,
    title_limit=1_000,
    scratchpad_fetch_limit=14_000,
    log_fetch_entry_limit=6_000,
    log_fetch_budget=18_000,
    compact_acceptance_items=20,
    compact_acceptance_item_limit=320,
    compact_reason_limit=600,
    compact_hint_limit=240,
    compact_blocked_ids=16,
    compact_overlap_hints=12,
)

_PROFILES: dict[str, TruncationProfile] = {"summary": SUMMARY_PROFILE, "full": FULL_PROFILE}


def get_profile(mode: str) -> TruncationProfile:
    """Return the TruncationProfile for the given mode, defaulting to SUMMARY_PROFILE."""
    return _PROFILES.get(mode, SUMMARY_PROFILE)


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

    profile = get_profile(mode)
    item_limit = profile.acceptance_item_limit
    max_items = profile.acceptance_items

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
    profile = get_profile(mode)
    compact = dict(runtime)

    reason_limit = profile.compact_reason_limit
    hint_limit = profile.compact_hint_limit
    blocked_ids = profile.compact_blocked_ids
    overlap_hints = profile.compact_overlap_hints

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
    profile = get_profile(mode)
    budget = profile.response_budget
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
        trimmed["title"] = truncate_text(trimmed["title"], limit=profile.title_limit) or ""

    if isinstance(trimmed.get("runtime"), dict):
        trimmed["runtime"] = compact_runtime(trimmed["runtime"], mode=mode)

    if isinstance(trimmed.get("acceptance_criteria"), list):
        max_items = profile.compact_acceptance_items
        item_limit = profile.compact_acceptance_item_limit
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
    "FULL_PROFILE",
    "SUMMARY_PROFILE",
    "TruncationProfile",
    "compact_runtime",
    "compact_string_list",
    "fit_task_payload_budget",
    "get_profile",
    "serialized_size",
    "trim_logs_to_budget",
    "truncate_acceptance_criteria",
    "truncate_text",
]
