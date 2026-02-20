"""Shared settings allowlist and normalization for MCP/admin updates."""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

from kagan.core.builtin_agents import BUILTIN_AGENTS
from kagan.core.config import (
    DOCTOR_VERBOSITY_VALUES,
    INTERACTION_VERBOSITY_VALUES,
    WORKTREE_BASE_REF_STRATEGY_VALUES,
)
from kagan.core.domain.enums import VALID_PAIR_BACKENDS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from kagan.core.config import KaganConfig


@dataclasses.dataclass(frozen=True, slots=True)
class _SettingBinding:
    dotted_key: str
    section: str
    field: str
    mcp_param: str | None = None
    copy_on_snapshot: bool = False


_EXPOSED_SETTING_BINDINGS: tuple[_SettingBinding, ...] = (
    _SettingBinding("general.auto_review", "general", "auto_review", mcp_param="auto_review"),
    _SettingBinding("general.auto_approve", "general", "auto_approve", mcp_param="auto_approve"),
    _SettingBinding(
        "general.auto_skill_discovery",
        "general",
        "auto_skill_discovery",
        mcp_param="auto_skill_discovery",
    ),
    _SettingBinding(
        "general.require_review_approval",
        "general",
        "require_review_approval",
        mcp_param="require_review_approval",
    ),
    _SettingBinding(
        "general.serialize_merges",
        "general",
        "serialize_merges",
        mcp_param="serialize_merges",
    ),
    _SettingBinding(
        "general.worktree_base_ref_strategy",
        "general",
        "worktree_base_ref_strategy",
        mcp_param="worktree_base_ref_strategy",
    ),
    _SettingBinding(
        "general.max_concurrent_agents",
        "general",
        "max_concurrent_agents",
        mcp_param="max_concurrent_agents",
    ),
    _SettingBinding(
        "general.default_worker_agent",
        "general",
        "default_worker_agent",
        mcp_param="default_worker_agent",
    ),
    _SettingBinding(
        "general.worker_persona",
        "general",
        "worker_persona",
        mcp_param="worker_persona",
    ),
    _SettingBinding(
        "general.orchestrator_persona",
        "general",
        "orchestrator_persona",
        mcp_param="orchestrator_persona",
    ),
    _SettingBinding(
        "general.pr_reviewer_persona",
        "general",
        "pr_reviewer_persona",
        mcp_param="pr_reviewer_persona",
    ),
    _SettingBinding(
        "general.default_pair_terminal_backend",
        "general",
        "default_pair_terminal_backend",
        mcp_param="default_pair_terminal_backend",
    ),
    _SettingBinding(
        "general.doctor_verbosity",
        "general",
        "doctor_verbosity",
        mcp_param="doctor_verbosity",
    ),
    _SettingBinding(
        "general.interaction_verbosity",
        "general",
        "interaction_verbosity",
        mcp_param="interaction_verbosity",
    ),
    _SettingBinding(
        "general.default_model_claude",
        "general",
        "default_model_claude",
        mcp_param="default_model_claude",
    ),
    _SettingBinding(
        "general.default_model_opencode",
        "general",
        "default_model_opencode",
        mcp_param="default_model_opencode",
    ),
    _SettingBinding(
        "general.default_model_codex",
        "general",
        "default_model_codex",
        mcp_param="default_model_codex",
    ),
    _SettingBinding(
        "general.default_model_gemini",
        "general",
        "default_model_gemini",
        mcp_param="default_model_gemini",
    ),
    _SettingBinding(
        "general.default_model_kimi",
        "general",
        "default_model_kimi",
        mcp_param="default_model_kimi",
    ),
    _SettingBinding(
        "general.default_model_copilot",
        "general",
        "default_model_copilot",
        mcp_param="default_model_copilot",
    ),
    _SettingBinding(
        "general.default_model_goose",
        "general",
        "default_model_goose",
        mcp_param="default_model_goose",
    ),
    _SettingBinding(
        "general.default_model_openhands",
        "general",
        "default_model_openhands",
        mcp_param="default_model_openhands",
    ),
    _SettingBinding(
        "general.default_model_auggie",
        "general",
        "default_model_auggie",
        mcp_param="default_model_auggie",
    ),
    _SettingBinding(
        "general.default_model_amp",
        "general",
        "default_model_amp",
        mcp_param="default_model_amp",
    ),
    _SettingBinding(
        "general.default_model_cagent",
        "general",
        "default_model_cagent",
        mcp_param="default_model_cagent",
    ),
    _SettingBinding(
        "general.default_model_stakpak",
        "general",
        "default_model_stakpak",
        mcp_param="default_model_stakpak",
    ),
    _SettingBinding(
        "general.default_model_vibe",
        "general",
        "default_model_vibe",
        mcp_param="default_model_vibe",
    ),
    _SettingBinding(
        "general.default_model_vtcode",
        "general",
        "default_model_vtcode",
        mcp_param="default_model_vtcode",
    ),
    _SettingBinding(
        "general.tasks_wait_default_timeout_seconds",
        "general",
        "tasks_wait_default_timeout_seconds",
        mcp_param="tasks_wait_default_timeout_seconds",
    ),
    _SettingBinding(
        "general.tasks_wait_max_timeout_seconds",
        "general",
        "tasks_wait_max_timeout_seconds",
        mcp_param="tasks_wait_max_timeout_seconds",
    ),
    _SettingBinding(
        "ui.skip_pair_instructions",
        "ui",
        "skip_pair_instructions",
        mcp_param="skip_pair_instructions",
    ),
    _SettingBinding(
        "ui.theme",
        "ui",
        "theme",
        mcp_param="theme",
    ),
    _SettingBinding(
        "ui.tui_plugin_ui_allowlist",
        "ui",
        "tui_plugin_ui_allowlist",
        copy_on_snapshot=True,
    ),
)

EXPOSED_SETTINGS: tuple[str, ...] = tuple(
    binding.dotted_key for binding in _EXPOSED_SETTING_BINDINGS
)

MCP_SETTINGS_SET_PARAM_TO_KEY: dict[str, str] = {}
for _binding in _EXPOSED_SETTING_BINDINGS:
    if _binding.mcp_param is not None:
        MCP_SETTINGS_SET_PARAM_TO_KEY[_binding.mcp_param] = _binding.dotted_key

_BOOL_FIELDS: set[str] = {
    "general.auto_review",
    "general.auto_approve",
    "general.auto_skill_discovery",
    "general.require_review_approval",
    "general.serialize_merges",
    "ui.skip_pair_instructions",
}
_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
_TIMEOUT_SECONDS_FIELDS: set[str] = {
    "general.tasks_wait_default_timeout_seconds",
    "general.tasks_wait_max_timeout_seconds",
}
_OPTIONAL_MODEL_FIELDS: set[str] = {
    "general.default_model_claude",
    "general.default_model_opencode",
    "general.default_model_codex",
    "general.default_model_gemini",
    "general.default_model_kimi",
    "general.default_model_copilot",
    "general.default_model_goose",
    "general.default_model_openhands",
    "general.default_model_auggie",
    "general.default_model_amp",
    "general.default_model_cagent",
    "general.default_model_stakpak",
    "general.default_model_vibe",
    "general.default_model_vtcode",
}
_PERSONA_FIELDS: set[str] = {
    "general.worker_persona",
    "general.orchestrator_persona",
    "general.pr_reviewer_persona",
}
_WORKER_AGENTS: set[str] = set(BUILTIN_AGENTS.keys())


def exposed_settings_snapshot(config: KaganConfig) -> dict[str, object]:
    """Return MCP-safe settings snapshot as dotted-path keys."""
    snapshot: dict[str, object] = {}
    for binding in _EXPOSED_SETTING_BINDINGS:
        section = getattr(config, binding.section)
        value = getattr(section, binding.field)
        if binding.copy_on_snapshot and isinstance(value, list):
            snapshot[binding.dotted_key] = list(value)
        else:
            snapshot[binding.dotted_key] = value
    return snapshot


def build_settings_set_fields(params: Mapping[str, object]) -> dict[str, object]:
    """Map settings_set MCP parameters to dotted-key settings update payload."""
    mapped: dict[str, object] = {}
    for param_name, dotted_key in MCP_SETTINGS_SET_PARAM_TO_KEY.items():
        value = params.get(param_name)
        if value is not None:
            mapped[dotted_key] = value
    return mapped


def normalize_settings_updates(fields: Mapping[str, object]) -> dict[str, object]:
    """Validate and normalize an update payload for MCP settings mutation."""
    unknown = sorted(key for key in fields if key not in EXPOSED_SETTINGS)
    if unknown:
        unknown_keys = ", ".join(unknown)
        raise ValueError(f"Unsupported settings field(s): {unknown_keys}")

    normalized: dict[str, object] = {}
    for key, value in fields.items():
        normalized[key] = _normalize_value(key, value)
    return normalized


def _normalize_value(key: str, value: object) -> object:
    if key in _BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} must be a boolean")

    if key == "general.worktree_base_ref_strategy":
        strategy = _normalize_non_empty_string(key, value)
        if strategy not in WORKTREE_BASE_REF_STRATEGY_VALUES:
            options = ", ".join(sorted(WORKTREE_BASE_REF_STRATEGY_VALUES))
            raise ValueError(f"general.worktree_base_ref_strategy must be one of: {options}")
        return strategy

    if key == "general.max_concurrent_agents":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("general.max_concurrent_agents must be an integer")
        if value < 1 or value > 10:
            raise ValueError("general.max_concurrent_agents must be between 1 and 10")
        return value

    if key in _TIMEOUT_SECONDS_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be a positive integer")
        if value < 1 or value > 3600:
            raise ValueError(f"{key} must be between 1 and 3600")
        return value

    if key == "general.default_worker_agent":
        agent = _normalize_non_empty_string(key, value)
        if agent not in _WORKER_AGENTS:
            options = ", ".join(sorted(_WORKER_AGENTS))
            raise ValueError(f"general.default_worker_agent must be one of: {options}")
        return agent

    if key == "general.default_pair_terminal_backend":
        backend = _normalize_non_empty_string(key, value).lower()
        if backend not in VALID_PAIR_BACKENDS:
            options = ", ".join(sorted(VALID_PAIR_BACKENDS))
            raise ValueError(f"general.default_pair_terminal_backend must be one of: {options}")
        return backend

    if key == "general.doctor_verbosity":
        verbosity = _normalize_non_empty_string(key, value).lower()
        if verbosity not in DOCTOR_VERBOSITY_VALUES:
            options = ", ".join(sorted(DOCTOR_VERBOSITY_VALUES))
            raise ValueError(f"general.doctor_verbosity must be one of: {options}")
        return verbosity

    if key == "general.interaction_verbosity":
        verbosity = _normalize_non_empty_string(key, value).lower()
        if verbosity not in INTERACTION_VERBOSITY_VALUES:
            options = ", ".join(sorted(INTERACTION_VERBOSITY_VALUES))
            raise ValueError(f"general.interaction_verbosity must be one of: {options}")
        return verbosity

    if key in _OPTIONAL_MODEL_FIELDS:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        raise ValueError(f"{key} must be a string or null")

    if key in _PERSONA_FIELDS:
        return _normalize_non_empty_string(key, value)

    if key == "ui.tui_plugin_ui_allowlist":
        if not isinstance(value, list):
            raise ValueError("ui.tui_plugin_ui_allowlist must be a list of plugin IDs")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("ui.tui_plugin_ui_allowlist must contain only strings")
            cleaned = item.strip()
            if not cleaned:
                continue
            if not _PLUGIN_ID_PATTERN.fullmatch(cleaned):
                raise ValueError(
                    f"ui.tui_plugin_ui_allowlist items must match: {_PLUGIN_ID_PATTERN.pattern}"
                )
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    if key == "ui.theme":
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        raise ValueError("ui.theme must be a string or null")

    raise ValueError(f"Unsupported settings field: {key}")


def _normalize_non_empty_string(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


__all__ = [
    "EXPOSED_SETTINGS",
    "MCP_SETTINGS_SET_PARAM_TO_KEY",
    "build_settings_set_fields",
    "exposed_settings_snapshot",
    "normalize_settings_updates",
]
