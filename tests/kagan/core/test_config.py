from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from kagan.core.config import (
    RepoConfig,
    ServiceConfig,
    find_repo_root,
    load_repo_config,
    load_review_rubric,
)
from kagan.core.errors import ConfigurationError


def test_field_docstrings_become_descriptions():
    # P11: the field docstrings ARE the config reference, so they must reach the
    # JSON schema (requires trailing placement + use_attribute_docstrings=True).
    assert RepoConfig.model_fields["checks"].description is not None
    assert (
        ServiceConfig.model_fields["command"].description
        == "Shell command that starts the service."
    )


def test_repo_config_defaults():
    cfg = RepoConfig()
    assert cfg.base_branch == "main"
    assert cfg.review_rubric == Path(".kagan/review.md")
    assert cfg.services == {}
    assert cfg.checks == {}
    assert cfg.pinned == []


def test_repo_config_from_dict():
    cfg = RepoConfig.model_validate(
        {
            "project_name": "kagan",
            "services": {
                "web": {
                    "command": "python -m http.server",
                    "port_env": "PORT",
                    "env": {"DEBUG": "1"},
                }
            },
            "checks": {"lint": "ruff check src"},
            "pinned": ["main", "deploy-bot"],
        }
    )
    assert cfg.project_name == "kagan"
    assert cfg.services["web"].command == "python -m http.server"
    assert cfg.services["web"].port_env == "PORT"
    assert cfg.services["web"].env == {"DEBUG": "1"}
    # checks is a flat name -> command map, NOT a list and NOT objects.
    assert cfg.checks["lint"] == "ruff check src"


def test_service_defaults_no_port():
    # A bare service declares only a command; port_env/env are opt-in.
    svc = ServiceConfig(command="python -m api")
    assert svc.port_env is None
    assert svc.env == {}


def test_empty_command_rejected():
    # A service with no command is unusable; reject it loudly, do not silently
    # store a blank command (TUI-CONFIG-04: no silent guessing).
    with pytest.raises(ValidationError):
        ServiceConfig(command="   ")


def test_unknown_service_key_rejected():
    # extra="forbid" catches typos like `prot_env` instead of dropping them.
    with pytest.raises(ValidationError):
        ServiceConfig(command="run", prot_env="PORT")


def test_unknown_key_rejected():
    # extra="forbid" catches typos in the manifest instead of ignoring them.
    with pytest.raises(ValidationError):
        RepoConfig.model_validate({"servces": {}})


def test_find_repo_root_discovers_manifest(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("project_name: demo\n")
    assert find_repo_root(tmp_path) == tmp_path


def test_find_repo_root_from_subdirectory(tmp_path: Path):
    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("project_name: demo\n")
    assert find_repo_root(sub) == tmp_path


def test_find_repo_root_returns_none_when_absent(tmp_path: Path):
    assert find_repo_root(tmp_path) is None


def test_load_repo_config_valid(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump(
            {
                "project_name": "demo",
                "services": {"api": {"command": "python -m api"}},
                "checks": {"test": "pytest"},
            }
        )
    )
    cfg = load_repo_config(tmp_path)
    assert cfg.project_name == "demo"
    assert cfg.services["api"].command == "python -m api"
    assert cfg.checks["test"] == "pytest"


def test_load_repo_config_rewrites_rubric_path(tmp_path: Path):
    # P11: a relative review_rubric is resolved against the manifest's own dir,
    # not the process cwd.
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("review_rubric: .kagan/review.md\n")
    cfg = load_repo_config(tmp_path)
    assert cfg.review_rubric == tmp_path / ".kagan" / "review.md"
    assert cfg.review_rubric.is_absolute()


def test_load_repo_config_missing_raises(tmp_path: Path):
    with pytest.raises(ConfigurationError) as exc_info:
        load_repo_config(tmp_path)
    assert "not found" in exc_info.value.detail


def test_load_repo_config_invalid_field_names_it(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("services: not-a-mapping\n")
    with pytest.raises(ConfigurationError) as exc_info:
        load_repo_config(tmp_path)
    # The error names the offending field so the user can fix it (TUI-CONFIG-04).
    assert "services" in exc_info.value.detail


def test_load_repo_config_empty_command_names_field(tmp_path: Path):
    # field_validator's ValueError flows through the same path and names the field.
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("services:\n  api:\n    command: '   '\n")
    with pytest.raises(ConfigurationError) as exc_info:
        load_repo_config(tmp_path)
    assert "command" in exc_info.value.detail


def test_risk_tiers_unknown_key_rejected():
    # Fix B (Rule 8): an unknown risk-tier name (e.g. "critical") must fail fast at
    # load, not silently route every matching task into MEDIUM. Valid keys load.
    with pytest.raises(ValidationError) as exc:
        RepoConfig.model_validate({"risk_tiers": {"critical": ["src/**"]}})
    assert "critical" in str(exc.value)


def test_risk_tiers_valid_keys_load():
    cfg = RepoConfig.model_validate(
        {"risk_tiers": {"low": ["docs/**"], "medium": ["src/**"], "high": ["migrations/**"]}}
    )
    assert cfg.risk_tiers["high"] == ["migrations/**"]


def test_reviewer_equal_to_builder_loads():
    # Fix 6: the anti-bias guarantee is the fresh separate spawn, not vendor identity,
    # so reviewer == builder is a valid one-vendor setup and must load cleanly.
    cfg = RepoConfig.model_validate({"agents": {"claude": {"builder": "opus", "reviewer": "opus"}}})
    models = cfg.agents.for_cli("claude")
    assert models.reviewer == models.builder == "opus"


def test_models_are_isolated_per_cli_and_unknown_cli_key_is_rejected():
    # The new contract: models live under their CLI's own key, so a cross-vendor mismatch
    # is unrepresentable — a value set under `codex` is never read for a `claude` task.
    cfg = RepoConfig.model_validate(
        {"agents": {"codex": {"builder": "gpt-5-codex"}, "claude": {"reviewer": "opus"}}}
    )
    assert cfg.agents.for_cli("codex").builder == "gpt-5-codex"
    assert cfg.agents.for_cli("codex").reviewer is None
    assert cfg.agents.for_cli("claude").builder is None
    # An unknown/typo'd CLI key is rejected at load (extra="forbid"), not silently ignored.
    with pytest.raises(ValidationError):
        RepoConfig.model_validate({"agents": {"opnecode": {"builder": "x"}}})


def test_agents_config_keys_match_the_supported_recipes():
    # Structural guard: the per-CLI agent sections must be exactly the recipe-backed CLIs,
    # so a new supported CLI can't be configurable without a launch recipe (or vice versa).
    from kagan.core.config import AgentsConfig
    from kagan.core.recipes import RECIPES

    assert set(AgentsConfig.model_fields) == set(RECIPES)


def test_load_repo_config_bad_yaml_raises(tmp_path: Path):
    # A YAMLError (not a ValidationError) is also wrapped in ConfigurationError.
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("project_name: [unclosed\n")
    with pytest.raises(ConfigurationError):
        load_repo_config(tmp_path)


def test_load_repo_config_not_a_mapping_raises(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigurationError):
        load_repo_config(tmp_path)


def test_load_review_rubric_reads_file(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("project_name: demo\n")
    (tmp_path / ".kagan" / "review.md").write_text("# Review rubric\n")
    assert load_review_rubric(tmp_path) == "# Review rubric\n"


def test_load_review_rubric_missing_raises(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("project_name: demo\n")
    with pytest.raises(ConfigurationError) as exc_info:
        load_review_rubric(tmp_path)
    assert "not found" in exc_info.value.detail
