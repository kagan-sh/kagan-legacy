"""`kagan init` flow tests (Phase 14): drives the init command headlessly via CliRunner
through the click prompt loop (confirm/prompt/getchar).

The agent draft is stubbed (launch_manifest_draft) so no subprocess runs; the walk,
risk-lint gate, opt-in verify, skeleton floor, and idempotency are exercised live.
"""

import subprocess
from pathlib import Path

from click.testing import CliRunner

from kagan.cli.main import cli
from kagan.core import Harness
from kagan.core.config import load_repo_config
from kagan.core.models import ReportMessage

_PRESESSION_FILES = (
    "src/kagan/cli/init.py",
    "src/kagan/cli/main.py",
    "src/kagan/cli/doctor.py",
    "src/kagan/cli/reset.py",
    "src/kagan/cli/update.py",
)


def _git_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)


def _manifest_payload(checks, **extra):
    return {"base_branch": "main", "checks": checks, **extra}


def _stub_draft(monkeypatch, payload):
    async def _fake(cli, repo_root):
        return [ReportMessage(type="manifest", payload=payload)]

    monkeypatch.setattr("kagan.core.agent.launch_manifest_draft", _fake)


def _invoke_init(input: str | None = None):
    return CliRunner().invoke(cli, ["--skip-update-check", "init"], input=input)


def test_pre_session_uses_no_prompt_toolkit():
    root = Path(__file__).resolve().parents[3]
    for rel in _PRESESSION_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        assert "_interactive" not in text, f"{rel} must not import _interactive"
        assert "prompt_toolkit" not in text, f"{rel} must not import prompt_toolkit"


def test_skeleton_floor_when_no_agent(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: [])
    result = _invoke_init()
    assert result.exit_code == 0
    path = tmp_path / ".kagan" / "repo.yaml"
    assert path.exists()
    load_repo_config(tmp_path)  # the floor must parse
    assert (tmp_path / ".kagan" / "review.md").exists()


def test_agent_draft_accept_all_writes_manifest(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [
                {"name": "build", "command": "make build", "provenance": "ci", "source": "ci.yml"},
                {"name": "test", "command": "pytest", "provenance": "invented"},
            ],
            reviewer="claude-opus",
        ),
    )
    result = _invoke_init(input="y\na\na\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"build": "make build", "test": "pytest"}
    assert cfg.reviewer == "claude-opus"


def test_walk_drop_and_edit(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [
                {"name": "build", "command": "make build", "provenance": "ci"},
                {"name": "test", "command": "pytest", "provenance": "invented"},
            ]
        ),
    )
    result = _invoke_init(input="y\nx\ne\nruff check\na\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"test": "ruff check"}


def test_dangerous_command_requires_extra_confirm(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "wipe", "command": "rm -rf build", "provenance": "invented"}]),
    )
    result = _invoke_init(input="y\na\nn\nx\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {}  # the dangerous command was NOT written


def test_opt_in_verify_drops_failing_check(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [
                {"name": "ok", "command": "true", "provenance": "invented"},
                {"name": "bad", "command": "false", "provenance": "invented"},
            ]
        ),
    )
    result = _invoke_init(input="y\na\na\ny\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"ok": "true"}  # the phantom check died at setup


def test_unknown_risk_tier_in_draft_still_writes(tmp_path, monkeypatch):
    # Regression for the adversarial finding: an agent draft with a tier outside
    # low/medium/high must NOT abort the write after the human approved checks — the
    # bad tier is dropped at parse, the approved checks are written.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [{"name": "test", "command": "pytest", "provenance": "ci"}],
            risk_tiers={"critical": ["src/**"], "low": ["docs/**"]},
        ),
    )
    result = _invoke_init(input="y\na\nn\n")
    assert result.exit_code == 0
    assert (tmp_path / ".kagan" / "repo.yaml").exists()
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"test": "pytest"}
    assert "critical" not in cfg.risk_tiers and cfg.risk_tiers == {"low": ["docs/**"]}


def test_security_and_services_not_auto_committed(tmp_path, monkeypatch):
    # Via negativa: security + services.command also execute later but aren't walked,
    # so kagan does NOT auto-write them unreviewed — it surfaces them as suggestions
    # the user adds by a deliberate hand-edit (which is the review).
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [{"name": "test", "command": "pytest", "provenance": "ci"}],
            security="semgrep --config=auto",
            services={"api": {"command": "./run.sh"}},
        ),
    )
    result = _invoke_init(input="y\na\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"test": "pytest"}
    assert cfg.security is None  # NOT auto-committed
    assert cfg.services == {}  # NOT auto-committed
    assert "semgrep --config=auto" in result.output  # surfaced as paste-ready suggestion
    assert "./run.sh" in result.output


def test_draft_timeout_falls_to_skeleton(tmp_path, monkeypatch):
    # A hung agent must not wedge the CLI (rule 12 / Taleb §3,§12): the bounded draft
    # times out and falls to the deterministic skeleton floor.
    import asyncio

    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    monkeypatch.setattr("kagan.cli.init._DRAFT_TIMEOUT", 0.2)

    async def _hang(cli, repo_root):
        await asyncio.sleep(60)

    monkeypatch.setattr("kagan.core.agent.launch_manifest_draft", _hang)
    result = _invoke_init(input="y\n")
    assert result.exit_code == 0
    assert (tmp_path / ".kagan" / "repo.yaml").exists()
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {}  # skeleton floor, no checks from the timed-out draft


def test_picker_shown_when_multiple_clis(tmp_path, monkeypatch):
    # Multiple CLIs: click.prompt(Choice) with default=first; Enter accepts the default.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude", "codex"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    result = _invoke_init(input="y\n\na\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"test": "pytest"}


def test_picker_rejects_bad_choice_then_accepts(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude", "codex"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    result = _invoke_init(input="y\nbogus\nclaude\na\nn\n")
    assert result.exit_code == 0
    assert load_repo_config(tmp_path).checks == {"test": "pytest"}
    assert "bogus" in result.output.lower() or "invalid" in result.output.lower()


def test_non_git_folder_bootstraps_repo_then_continues(tmp_path, monkeypatch):
    # repo_root=None (not a git repo): init offers to bootstrap git (Y), creates the
    # repo, then proceeds to the manifest walk in the same run.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "ci"}]),
    )
    result = _invoke_init(input="y\ny\na\nn\n")
    assert result.exit_code == 0
    assert (tmp_path / ".git").is_dir()  # git bootstrapped
    assert load_repo_config(tmp_path).checks == {"test": "pytest"}


def test_non_git_folder_declined_blocks(tmp_path, monkeypatch):
    # Declining the git bootstrap must BLOCK — return None, write nothing.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    result = _invoke_init(input="n\n")
    assert result.exit_code == 0
    assert not (tmp_path / ".git").exists()
    assert not (tmp_path / ".kagan").exists()


def test_idempotent_decline_overwrite_leaves_file(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    sentinel = "project_name: handwritten\n"
    manifest = tmp_path / ".kagan" / "repo.yaml"
    manifest.write_text(sentinel)
    result = _invoke_init(input="n\n")
    assert result.exit_code == 0
    assert manifest.read_text() == sentinel  # untouched
    assert "Left your manifest untouched" in result.output


def test_init_command_is_registered():
    assert "init" in cli.list_commands(ctx=None)
