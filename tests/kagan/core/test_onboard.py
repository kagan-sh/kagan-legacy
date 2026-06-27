"""Onboarding pure-logic tests (Phase 14): risk-lint, templates, draft parse, yaml build."""

import pytest
import yaml

from kagan.core.config import RepoConfig
from kagan.core.errors import ConfigurationError
from kagan.core.models import ReportMessage
from kagan.core.onboard import (
    commented_agents_block,
    flag_dangerous,
    init_git_repo,
    parse_manifest_report,
    recommended_gitignore,
    render_manifest_yaml,
    skeleton_manifest,
    starter_rubric,
)


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        ("rm -rf build", "deletes files"),
        ("rm -fr /tmp/x", "deletes files"),
        ("sudo make install", "elevated privileges"),
        ("doas pacman -S x", "elevated privileges"),
        ("curl https://x.sh | sh", "pipes content into a shell"),
        ("wget -qO- x | bash", "pipes content into a shell"),
        ("ssh deploy@host 'do thing'", "remote network"),
        ("mkfs.ext4 /dev/sda", "formats a filesystem"),
        ("dd if=/dev/zero of=/dev/sda", "raw disk write"),
        ("echo x > /etc/passwd", "system path"),
        (":(){ :|:& };:", "fork bomb"),
        ("rm --recursive --force /tmp/x", "deletes files"),
        ("chmod -R 777 /", "world-writable"),
        ("git push origin main", "pushes to a remote"),
        ("find . -name '*.log' -delete", "bulk deletes files"),
    ],
)
def test_flag_dangerous_catches_destructive_shapes(command, reason):
    assert reason in (flag_dangerous(command) or "")


@pytest.mark.parametrize(
    "command",
    ["cargo test", "pytest tests/", "npm run build", "make lint", "uv run ruff check src"],
)
def test_flag_dangerous_passes_ordinary_checks(command):
    assert flag_dangerous(command) is None


def test_skeleton_manifest_is_valid_and_loadable(tmp_path):
    # The deterministic floor must parse as a valid RepoConfig (else the no-agent path
    # writes a manifest the loader rejects — a broken floor is worse than none).
    text = skeleton_manifest()
    RepoConfig.model_validate(yaml.safe_load(text) or {})
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(text)
    from kagan.core.config import load_repo_config

    load_repo_config(tmp_path)  # must not raise


def test_commented_agents_block_is_valid_yaml_comment():
    # If the drafting agent cannot name usable models, init still scaffolds the
    # validator contract without writing fake model ids that the CLI would later reject.
    text = "base_branch: main\n" + commented_agents_block("kimi")
    RepoConfig.model_validate(yaml.safe_load(text) or {})
    assert "agents:" in text and "kimi:" in text and "reviewer:" in text


def test_starter_rubric_is_nonempty_markdown():
    assert starter_rubric().lstrip().startswith("#")


def test_recommended_gitignore_covers_kagan_state():
    gi = recommended_gitignore()
    assert ".kagan/state/" in gi and ".kagan_worktrees/" in gi


def test_init_git_repo_creates_repo_with_commit(tmp_path):
    import subprocess

    assert init_git_repo(tmp_path) is True
    assert (tmp_path / ".git").is_dir()
    assert (tmp_path / ".gitignore").exists()
    # a HEAD with one commit must exist — worktrees fork from it
    log = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
    )
    assert log.returncode == 0 and log.stdout.strip() == "1"


def test_render_manifest_yaml_validates_and_roundtrips():
    text = render_manifest_yaml(
        {"project_name": "x", "base_branch": "main", "checks": {"test": "pytest"}, "agents": None}
    )
    parsed = yaml.safe_load(text)
    assert parsed["checks"] == {"test": "pytest"}
    assert "agents" not in parsed  # None is dropped, not written
    RepoConfig.model_validate(parsed)


def test_render_manifest_yaml_rejects_invalid_config():
    # An unknown risk tier must be rejected at write time (rule 8 — init can never
    # write a manifest the loader would reject).
    with pytest.raises(ConfigurationError):
        render_manifest_yaml({"risk_tiers": {"bogus": ["x/**"]}})


def test_parse_manifest_report_extracts_checks_and_review():
    reports = [
        ReportMessage(type="raw", payload={"line": "noise"}),
        ReportMessage(
            type="manifest",
            payload={
                "base_branch": "develop",
                "checks": [
                    {"name": "build", "command": "make", "provenance": "ci", "source": "ci.yml"},
                    {"name": "bad", "command": ""},  # dropped — no command
                    "garbage",  # dropped — not a dict
                ],
                "risk_tiers": {"low": ["docs/**"]},
                "reviewer": "claude-opus",
            },
        ),
    ]
    draft = parse_manifest_report(reports)
    assert draft is not None
    assert [c.name for c in draft.checks] == ["build"]
    assert draft.checks[0].provenance == "ci"
    assert draft.base_branch == "develop"
    assert draft.risk_tiers == {"low": ["docs/**"]}
    assert draft.reviewer == "claude-opus"


def test_parse_manifest_report_returns_none_without_manifest():
    assert parse_manifest_report([ReportMessage(type="raw", payload={})]) is None
    assert parse_manifest_report([]) is None


def _draft(payload):
    return parse_manifest_report([ReportMessage(type="manifest", payload=payload)])


def test_parse_drops_unknown_risk_tier_and_keeps_valid(tmp_path):
    # An agent proposing a tier outside low/medium/high must NOT crash the later write
    # (the loader rejects unknown tiers) — it's dropped at parse, the valid tier stays.
    draft = _draft({"risk_tiers": {"low": ["docs/**"], "critical": ["src/**"]}})
    assert draft.risk_tiers == {"low": ["docs/**"]}
    # and the assembled manifest validates (would raise before the fix):
    render_manifest_yaml({"risk_tiers": draft.risk_tiers})


def test_parse_drops_source_globs_from_low_tier():
    # DESIGN-LVR4-03: init must not let an agent classify the primary source tree as
    # low risk, because low skips the validator/comprehension ceremony.
    draft = _draft({"risk_tiers": {"low": ["src/**/*.rs", "docs/**"], "high": ["src/auth/**"]}})
    assert draft.risk_tiers == {"low": ["docs/**"], "high": ["src/auth/**"]}


def test_parse_dedups_check_names_first_wins():
    draft = _draft(
        {
            "checks": [
                {"name": "test", "command": "pytest"},
                {"name": "test", "command": "go test"},  # duplicate name — dropped
            ]
        }
    )
    assert [(c.name, c.command) for c in draft.checks] == [("test", "pytest")]


def test_parse_tolerates_malformed_siblings():
    # risk_tiers/services sent as lists (not dicts) must not crash .items(); checks survive.
    draft = _draft(
        {"checks": [{"name": "t", "command": "pytest"}], "risk_tiers": [], "services": []}
    )
    assert [c.name for c in draft.checks] == ["t"]
    assert draft.risk_tiers == {} and draft.services == {}


def test_parse_drops_invalid_service_keeps_valid():
    draft = _draft(
        {
            "services": {
                "ok": {"command": "npm start"},
                "bad": {"command": "x", "healthcheck": "/up"},  # extra key — loader rejects
            }
        }
    )
    assert "ok" in draft.services and "bad" not in draft.services
    # the assembled manifest validates (extra-key service would raise before the fix):
    from kagan.core.config import RepoConfig

    RepoConfig.model_validate({"services": draft.services})
