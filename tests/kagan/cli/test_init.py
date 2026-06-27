"""`kagan init` flow tests (Phase 14): drives the init command headlessly via CliRunner
through the click prompt loop (confirm/prompt/getchar).

The agent draft is stubbed (launch_manifest_draft) so no subprocess runs; the walk,
risk-lint gate, opt-in verify, skeleton floor, and idempotency are exercised live.
"""

import subprocess
import sys
import time
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from kagan.cli.init import (
    _drain_pending_sigint,
    _prompt_command,
    _read_ax_e,
    _walk_checks,
    _WalkCancelled,
)
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


def test_init_writes_drafted_models_under_the_cli_section_verbatim(tmp_path, monkeypatch):
    # The drafting agent proposes builder/reviewer for the CLI it ran under; init writes
    # them verbatim under `agents.<cli>` (no translation, no compatibility judgement —
    # the CLI rejects a bad id at spawn). The verified checks/risk tiers survive alongside.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["codex"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [{"name": "test", "command": "pytest", "provenance": "invented"}],
            risk_tiers={"high": ["src/**"]},
            builder="gpt-5-codex",
            reviewer="o3",
        ),
    )
    result = _invoke_init(input="y\na\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"test": "pytest"}  # verified check survived
    assert cfg.risk_tiers == {"high": ["src/**"]}  # risk tiers survived
    models = cfg.agents.for_cli("codex")
    assert models.builder == "gpt-5-codex"
    assert models.reviewer == "o3"


def test_init_writes_claude_models_under_the_claude_section(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [{"name": "test", "command": "pytest", "provenance": "invented"}],
            builder="opus",
            reviewer="haiku",
        ),
    )
    result = _invoke_init(input="y\na\nn\n")
    assert result.exit_code == 0
    models = load_repo_config(tmp_path).agents.for_cli("claude")
    assert models.builder == "opus"
    assert models.reviewer == "haiku"


def test_init_reuses_builder_as_reviewer_when_agent_omits_reviewer(tmp_path, monkeypatch):
    # The default onboarding must not silently disable the validator. When the agent
    # only names a builder model, same-model review is valid and keeps lever 2 enabled.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["codex"])
    _stub_draft(
        monkeypatch,
        _manifest_payload(
            [{"name": "test", "command": "pytest", "provenance": "invented"}],
            builder="gpt-5-codex",
        ),
    )
    result = _invoke_init(input="y\na\nn\n")
    assert result.exit_code == 0
    models = load_repo_config(tmp_path).agents.for_cli("codex")
    assert models.builder == "gpt-5-codex"
    assert models.reviewer == "gpt-5-codex"


def test_init_offers_to_enable_validator_when_draft_names_no_reviewer(tmp_path, monkeypatch):
    # B1: when the draft leaves the validator (lever 2) unset, init must make enabling
    # it a CHOICE — accepting writes the reviewer the human names, not a commented stub.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    # y draft · a accept check · n skip verify · y enable validator · model id
    result = _invoke_init(input="y\na\nn\ny\nclaude-haiku\n")
    assert result.exit_code == 0
    models = load_repo_config(tmp_path).agents.for_cli("claude")
    assert models.reviewer == "claude-haiku"  # the validator is now enabled


def test_init_keeps_commented_agents_when_validator_declined(tmp_path, monkeypatch):
    # B1/F4: declining the validator is deliberate — it now requires an explicit "reviews
    # will be unaided" ack. With that ack the commented skeleton stays (no silent config).
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    # y draft · a accept check · n skip verify · n decline validator · y unaided-ack
    result = _invoke_init(input="y\na\nn\nn\ny\n")
    assert result.exit_code == 0
    assert load_repo_config(tmp_path).agents.for_cli("claude").reviewer is None
    text = (tmp_path / ".kagan" / "repo.yaml").read_text(encoding="utf-8")
    assert "#     reviewer: <reviewer-model>" in text


def test_init_declining_validator_without_ack_falls_through_to_a_reviewer(tmp_path, monkeypatch):
    # F4: turning the headline safety check OFF must be deliberate. Declining the enable
    # prompt but NOT acknowledging "reviews will be unaided" re-prompts for a reviewer —
    # a medium-risk repo never ends up silently unaided as the path of least resistance.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    # y draft · a accept check · n skip verify · n decline · n NOT-unaided · model id
    result = _invoke_init(input="y\na\nn\nn\nn\nclaude-sonnet\n")
    assert result.exit_code == 0
    assert load_repo_config(tmp_path).agents.for_cli("claude").reviewer == "claude-sonnet"


def test_init_scaffolds_commented_agents_when_agent_names_no_models(tmp_path, monkeypatch):
    # If there are no real model ids, init writes a commented agents.<cli> pair instead
    # of a fake live config or a false "models set" claim.
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["kimi", "codex"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    result = _invoke_init(input="y\nkimi\na\nn\n")
    assert result.exit_code == 0
    text = (tmp_path / ".kagan" / "repo.yaml").read_text(encoding="utf-8")
    assert "#   kimi:" in text
    assert "#     builder: <builder-model>" in text
    assert "#     reviewer: <reviewer-model>" in text
    assert "Models set under agents.kimi only" not in result.output


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
            reviewer="opus",
        ),
    )
    result = _invoke_init(input="y\na\na\nn\n")
    assert result.exit_code == 0
    cfg = load_repo_config(tmp_path)
    assert cfg.checks == {"build": "make build", "test": "pytest"}
    assert cfg.agents.for_cli("claude").reviewer == "opus"


def test_init_records_current_branch_when_repo_has_no_default_branch(tmp_path, monkeypatch):
    # No main/master/remote default exists in a brand-new feature-only repo. Init should
    # intentionally pin base_branch to the checked-out branch so later worktree adds
    # use a real ref instead of guessing `main`.
    _git_repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "checkout", "-q", "-b", "feature/only"], check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: [])
    result = _invoke_init()
    assert result.exit_code == 0
    assert load_repo_config(tmp_path).base_branch == "feature/only"


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


def test_read_ax_e_recovers_from_single_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    calls = {"n": 0}
    last_interrupt = [0.0]

    def _fake_getchar(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyboardInterrupt
        return "a"

    monkeypatch.setattr(click, "getchar", _fake_getchar)
    assert _read_ax_e(last_interrupt=last_interrupt) is None
    assert _read_ax_e(last_interrupt=last_interrupt) == "a"


def test_read_ax_e_double_keyboard_interrupt_raises_walk_cancelled(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        click, "getchar", lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt)
    )

    with pytest.raises(_WalkCancelled):
        _read_ax_e(last_interrupt=[time.monotonic() - 0.1])


def test_prompt_command_cancels_on_keyboard_interrupt(monkeypatch):
    def _raise_interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(click, "prompt", _raise_interrupt)
    assert _prompt_command("pytest") is None


def test_walk_edit_cancel_then_accept_writes_manifest(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    calls = {"n": 0}

    def _fake_prompt_command(default: str) -> str | None:
        calls["n"] += 1
        if calls["n"] == 1:
            click.echo("  Edit cancelled.")
            return None
        return "uv run poe check"

    monkeypatch.setattr("kagan.cli.init._prompt_command", _fake_prompt_command)
    result = _invoke_init(input="y\ne\ne\na\nn\n")
    assert result.exit_code == 0
    assert load_repo_config(tmp_path).checks == {"test": "uv run poe check"}
    assert "Edit cancelled" in result.output


def test_walk_double_ctrl_c_raises_walk_cancelled(monkeypatch):
    from kagan.core.onboard import ProposedCheck

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        click,
        "getchar",
        lambda **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    with pytest.raises(_WalkCancelled):
        _walk_checks([ProposedCheck("test", "pytest")])


def test_run_init_walk_cancelled_writes_nothing(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])
    _stub_draft(
        monkeypatch,
        _manifest_payload([{"name": "test", "command": "pytest", "provenance": "invented"}]),
    )
    monkeypatch.setattr(
        "kagan.cli.init._walk_checks",
        lambda _checks: (_ for _ in ()).throw(_WalkCancelled()),
    )
    result = _invoke_init(input="y\n")
    assert result.exit_code == 0
    assert not (tmp_path / ".kagan" / "repo.yaml").exists()
    assert "Setup interrupted" in result.output


def test_drain_pending_sigint_noop_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    _drain_pending_sigint()  # must not raise
