"""Onboarding, startup, and configuration persistence.

Covers:
- First-launch onboarding collects agent preference and auto-review
- Config.toml is persisted and survives restarts
- Returning user restores last active project context
- core_autostart config controls daemon startup
- Preflight checks (agent/tooling) with severity levels
- Settings normalization and validation
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from kagan.core.config import (
    DEFAULT_ORCHESTRATOR_PERSONA,
    DEFAULT_PR_REVIEWER_PERSONA,
    DEFAULT_WORKER_PERSONA,
    AgentConfig,
    GeneralConfig,
    KaganConfig,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestConfigPersistence:
    """Config.toml write and reload."""

    async def test_save_and_reload_config(self, tmp_path: Path) -> None:
        config = KaganConfig(
            general=GeneralConfig(
                default_worker_agent="claude",
                auto_review=True,
                auto_skill_discovery=True,
                max_concurrent_agents=3,
            ),
            agents={
                "claude": AgentConfig(
                    identity="claude.ai",
                    name="Claude",
                    short_name="claude",
                    run_command={"*": "echo claude"},
                ),
            },
        )
        config_path = tmp_path / "config.toml"
        await config.save(config_path)

        assert config_path.exists()
        reloaded = KaganConfig.load(config_path)
        assert reloaded.general.default_worker_agent == "claude"
        assert reloaded.general.auto_review is True
        assert reloaded.general.auto_skill_discovery is True
        assert reloaded.general.max_concurrent_agents == 3

    async def test_config_preserves_agent_entries(self, tmp_path: Path) -> None:
        config = KaganConfig(
            agents={
                "test": AgentConfig(
                    identity="test.agent",
                    name="Test",
                    short_name="test",
                    run_command={"*": "echo test"},
                ),
            },
        )
        config_path = tmp_path / "config.toml"
        await config.save(config_path)

        reloaded = KaganConfig.load(config_path)
        assert "test" in reloaded.agents
        assert reloaded.agents["test"].identity == "test.agent"

    def test_invalid_doctor_verbosity_coerces_to_short(self) -> None:
        config = KaganConfig.model_validate({"general": {"doctor_verbosity": "verbose"}})
        assert config.general.doctor_verbosity == "short"

    def test_invalid_interaction_verbosity_coerces_to_short(self) -> None:
        config = KaganConfig.model_validate({"general": {"interaction_verbosity": "verbose"}})
        assert config.general.interaction_verbosity == "short"

    def test_invalid_max_concurrent_agents_coerces_to_default(self) -> None:
        config = KaganConfig.model_validate({"general": {"max_concurrent_agents": 0}})
        assert config.general.max_concurrent_agents == 3

    def test_bool_max_concurrent_agents_coerces_to_default(self) -> None:
        config = KaganConfig.model_validate({"general": {"max_concurrent_agents": False}})
        assert config.general.max_concurrent_agents == 3

    def test_auto_skill_discovery_defaults_to_false(self) -> None:
        config = KaganConfig()
        assert config.general.auto_skill_discovery is False

    def test_auto_approve_defaults_to_true(self) -> None:
        config = KaganConfig()
        assert config.general.auto_approve is True

    def test_worktree_base_ref_strategy_defaults_to_local_if_ahead(self) -> None:
        config = KaganConfig()
        assert config.general.worktree_base_ref_strategy == "local_if_ahead"

    def test_invalid_worktree_base_ref_strategy_coerces_to_local_if_ahead(self) -> None:
        config = KaganConfig.model_validate({"general": {"worktree_base_ref_strategy": "invalid"}})
        assert config.general.worktree_base_ref_strategy == "local_if_ahead"

    def test_empty_persona_values_coerce_to_defaults(self) -> None:
        config = KaganConfig.model_validate(
            {
                "general": {
                    "worker_persona": "",
                    "orchestrator_persona": "  ",
                    "pr_reviewer_persona": "",
                }
            }
        )
        assert config.general.worker_persona == DEFAULT_WORKER_PERSONA
        assert config.general.orchestrator_persona == DEFAULT_ORCHESTRATOR_PERSONA
        assert config.general.pr_reviewer_persona == DEFAULT_PR_REVIEWER_PERSONA


class TestWriteTestConfig:
    """Shared test config helper produces valid TOML."""

    def test_write_test_config(self, tmp_path: Path) -> None:
        from tests.helpers.config import write_test_config

        config_path = write_test_config(tmp_path / "config.toml", auto_review=True)
        assert config_path.exists()

        reloaded = KaganConfig.load(config_path)
        assert reloaded.general.auto_review is True
        assert "claude" in reloaded.agents


class TestUIPreferences:
    """UI config options persistence."""

    async def test_skip_pair_instructions_persists(self, tmp_path: Path) -> None:
        config = KaganConfig()
        config_path = tmp_path / "config.toml"
        await config.save(config_path)

        await config.update_ui_preferences(config_path, skip_pair_instructions=True)
        reloaded = KaganConfig.load(config_path)
        assert reloaded.ui.skip_pair_instructions is True


class TestSettingsNormalization:
    """Settings validation and normalization for MCP/admin updates."""

    def test_unknown_field_raises(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="Unsupported settings field"):
            normalize_settings_updates({"unknown.field": True})

    def test_bool_field_accepts_bool(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.auto_review": True})
        assert result["general.auto_review"] is True

    def test_auto_skill_discovery_field_accepts_bool(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.auto_skill_discovery": True})
        assert result["general.auto_skill_discovery"] is True

    def test_bool_field_rejects_non_bool(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be a boolean"):
            normalize_settings_updates({"general.auto_review": "yes"})

    def test_max_concurrent_agents_valid(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.max_concurrent_agents": 5})
        assert result["general.max_concurrent_agents"] == 5

    def test_max_concurrent_agents_out_of_range(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="between 1 and 10"):
            normalize_settings_updates({"general.max_concurrent_agents": 0})

    def test_max_concurrent_agents_rejects_bool(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be an integer"):
            normalize_settings_updates({"general.max_concurrent_agents": True})

    def test_timeout_field_valid(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.tasks_wait_default_timeout_seconds": 120})
        assert result["general.tasks_wait_default_timeout_seconds"] == 120

    def test_timeout_field_out_of_range(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="between 1 and 3600"):
            normalize_settings_updates({"general.tasks_wait_default_timeout_seconds": 0})

    def test_pair_terminal_backend_accepts_nvim(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.default_pair_terminal_backend": "nvim"})
        assert result["general.default_pair_terminal_backend"] == "nvim"

    def test_pair_terminal_backend_rejects_invalid_value(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be one of"):
            normalize_settings_updates({"general.default_pair_terminal_backend": "emacs"})

    def test_optional_model_accepts_string(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.default_model_claude": "opus-4"})
        assert result["general.default_model_claude"] == "opus-4"

    def test_optional_model_accepts_none(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.default_model_claude": None})
        assert result["general.default_model_claude"] is None

    def test_optional_model_empty_string_becomes_none(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.default_model_claude": "  "})
        assert result["general.default_model_claude"] is None

    def test_optional_model_rejects_non_string(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be a string or null"):
            normalize_settings_updates({"general.default_model_claude": 42})

    def test_doctor_verbosity_valid(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.doctor_verbosity": "technical"})
        assert result["general.doctor_verbosity"] == "technical"

    def test_doctor_verbosity_rejects_invalid_value(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be one of"):
            normalize_settings_updates({"general.doctor_verbosity": "verbose"})

    def test_interaction_verbosity_valid(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"general.interaction_verbosity": "technical"})
        assert result["general.interaction_verbosity"] == "technical"

    def test_interaction_verbosity_rejects_invalid_value(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be one of"):
            normalize_settings_updates({"general.interaction_verbosity": "verbose"})

    def test_persona_fields_accept_non_empty_strings(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates(
            {
                "general.worker_persona": "Implementer persona",
                "general.orchestrator_persona": "Planner persona",
                "general.pr_reviewer_persona": "Reviewer persona",
            }
        )
        assert result["general.worker_persona"] == "Implementer persona"
        assert result["general.orchestrator_persona"] == "Planner persona"
        assert result["general.pr_reviewer_persona"] == "Reviewer persona"

    def test_persona_fields_reject_empty_strings(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="cannot be empty"):
            normalize_settings_updates({"general.worker_persona": "  "})

    def test_plugin_allowlist_valid(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        result = normalize_settings_updates({"ui.tui_plugin_ui_allowlist": ["kagan-github"]})
        assert result["ui.tui_plugin_ui_allowlist"] == ["kagan-github"]

    def test_plugin_allowlist_rejects_non_list(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must be a list"):
            normalize_settings_updates({"ui.tui_plugin_ui_allowlist": "string"})

    def test_plugin_allowlist_rejects_invalid_id(self) -> None:
        from kagan.core.settings import normalize_settings_updates

        with pytest.raises(ValueError, match="must match"):
            normalize_settings_updates({"ui.tui_plugin_ui_allowlist": ["AB"]})

    def test_settings_set_mapping_keeps_false_and_drops_none(self) -> None:
        from kagan.core.settings import build_settings_set_fields

        result = build_settings_set_fields(
            {
                "auto_review": False,
                "auto_skill_discovery": True,
                "max_concurrent_agents": 4,
                "worker_persona": "Implementer persona",
                "doctor_verbosity": "technical",
                "interaction_verbosity": "tldr",
                "default_model_claude": None,
                "skip_pair_instructions": True,
                "ctx": object(),
            }
        )
        assert result == {
            "general.auto_review": False,
            "general.auto_skill_discovery": True,
            "general.max_concurrent_agents": 4,
            "general.worker_persona": "Implementer persona",
            "general.doctor_verbosity": "technical",
            "general.interaction_verbosity": "tldr",
            "ui.skip_pair_instructions": True,
        }

    def test_settings_set_mapping_targets_only_exposed_keys(self) -> None:
        from kagan.core.settings import EXPOSED_SETTINGS, MCP_SETTINGS_SET_PARAM_TO_KEY

        assert set(MCP_SETTINGS_SET_PARAM_TO_KEY.values()).issubset(set(EXPOSED_SETTINGS))


class TestExposedSettingsSnapshot:
    """exposed_settings_snapshot returns full config dotted-path snapshot."""

    def test_snapshot_contains_all_exposed_keys(self) -> None:
        from kagan.core.settings import EXPOSED_SETTINGS, exposed_settings_snapshot

        config = KaganConfig()
        snapshot = exposed_settings_snapshot(config)
        for key in EXPOSED_SETTINGS:
            assert key in snapshot, f"Missing key: {key}"


class TestCoreRuntimeDirScoping:
    """Runtime metadata path should not collide across different executables."""

    def test_runtime_dir_is_scoped_by_executable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from kagan.core.paths import get_core_runtime_dir

        monkeypatch.setenv("KAGAN_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.delenv("KAGAN_CORE_RUNTIME_DIR", raising=False)

        monkeypatch.setattr(sys, "executable", "/tmp/python-a")
        runtime_a = get_core_runtime_dir()

        monkeypatch.setattr(sys, "executable", "/tmp/python-b")
        runtime_b = get_core_runtime_dir()

        assert runtime_a != runtime_b
        assert runtime_a.parent == tmp_path / "data" / "core" / "scoped"
        assert runtime_b.parent == tmp_path / "data" / "core" / "scoped"

    def test_runtime_dir_override_takes_precedence(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from kagan.core.paths import get_core_runtime_dir

        override = (tmp_path / "custom-runtime").resolve()
        monkeypatch.setenv("KAGAN_CORE_RUNTIME_DIR", str(override))
        monkeypatch.setattr(sys, "executable", "/tmp/python-a")

        assert get_core_runtime_dir() == override
