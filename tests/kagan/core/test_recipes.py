from pathlib import Path

import pytest

from kagan.core.agent import _build_cmd
from kagan.core.recipes import (
    RECIPES,
    available_clis,
    recipe_for,
)

SUPPORTED_CLIS = ("claude", "codex", "kimi", "opencode")


def test_every_doctor_cli_has_a_recipe():
    from kagan.core.doctor_checks import _AGENT_CLIS

    assert set(_AGENT_CLIS) == set(SUPPORTED_CLIS)  # gemini dropped (unsupported tier)
    for cli in _AGENT_CLIS:
        assert cli in RECIPES


def test_recipe_for_unknown_cli_is_bare_command():
    r = recipe_for("mystery")
    assert r.command == ["mystery"]
    assert r.prompt_flag is None


def test_no_recipe_enables_a_read_only_or_plan_sandbox():
    # R-002: a CLI's own read-only/plan sandbox blocks the agent's `.kagan/ask` write —
    # the only report channel in the sandbox (no MCP). Write withholding is the 0o444
    # chmod copy, NEVER a CLI flag. Fails if a plan/read-only flag creeps into any recipe.
    for cli, recipe in RECIPES.items():
        joined = " ".join(recipe.command)
        assert "--read-only" not in joined, cli
        assert "plan" not in joined, cli
        assert "-s read-only" not in joined and "--sandbox=read-only" not in joined, cli


def test_every_supported_recipe_is_headless_and_report_capable():
    # Each default CLI was probed (R-002 repro): the recipe must invoke the CLI HEADLESS
    # (no interactive TUI) and let it WRITE its report. These are the verified-correct
    # invocations — a regression to a bare/interactive command or a stripped flag breaks
    # a default CLI silently (codex `["codex"]` opened the TUI and never ran; kimi
    # `["kimi"] <path>` errored "unknown command"; opencode auto-rejected every write).
    expectations = {
        "claude": dict(command=["claude", "-p"], prompt_flag=None, workdir_flag=None),
        "codex": dict(
            command=["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write"],
            prompt_flag=None,
            workdir_flag=None,
        ),
        "kimi": dict(command=["kimi"], prompt_flag="-p", workdir_flag=None),
        "opencode": dict(
            command=["opencode", "run", "--dangerously-skip-permissions"],
            prompt_flag=None,
            workdir_flag="--dir",
        ),
    }
    assert set(RECIPES) == set(expectations)  # exactly the four supported CLIs
    for cli, exp in expectations.items():
        r = RECIPES[cli]
        assert r.command == exp["command"], cli
        assert r.prompt_flag == exp["prompt_flag"], cli
        assert r.workdir_flag == exp["workdir_flag"], cli


def test_build_cmd_pins_opencode_to_the_workdir(tmp_path: Path):
    # opencode ignores cwd and walks up to the nearest project root — it MUST be pinned
    # with --dir <workdir> or it mutates the wrong tree. Fails if workdir_flag is dropped.
    prompt = tmp_path / ".kagan" / "p.txt"
    prompt.parent.mkdir()
    prompt.write_text("x")
    cmd = _build_cmd("opencode", prompt, cwd=tmp_path)
    assert cmd[cmd.index("--dir") + 1] == str(tmp_path)
    # a CLI that honors cwd (claude) gets no --dir injected.
    assert "--dir" not in _build_cmd("claude", prompt, cwd=tmp_path)


def test_build_cmd_omits_the_flag_when_model_is_none(tmp_path: Path):
    # An unset builder/reviewer (None) must omit --model so the CLI's own default is used —
    # unchanged behaviour for the common case.
    prompt = tmp_path / ".kagan" / "p.txt"
    prompt.parent.mkdir()
    prompt.write_text("x")
    for cli in SUPPORTED_CLIS:
        assert "--model" not in _build_cmd(cli, prompt, cwd=tmp_path, model=None)


@pytest.mark.parametrize(
    ("cli", "model"),
    [
        ("claude", "opus"),
        ("claude", "claude-opus-4-8"),
        ("opencode", "opencode/claude-opus-4-8"),
        ("codex", "o3"),
        ("codex", "gpt-5-codex"),
        ("kimi", "kimi-code/kimi-for-coding"),
    ],
)
def test_build_cmd_passes_the_model_verbatim(cli: str, model: str, tmp_path: Path):
    # The model comes from repo.yaml `agents.<cli>` so it is already this CLI's own id —
    # kagan does NO translation. Whatever is configured reaches --model unchanged; a value
    # the CLI can't run is the CLI's own spawn error, not kagan's to second-guess.
    prompt = tmp_path / ".kagan" / "p.txt"
    prompt.parent.mkdir()
    prompt.write_text("x")
    cmd = _build_cmd(cli, prompt, cwd=tmp_path, model=model)
    assert cmd[cmd.index("--model") + 1] == model


def test_available_clis_filters_to_path(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\necho ok\n")
    fake.chmod(0o755)
    assert "claude" in available_clis(path=str(bin_dir))
    assert "codex" not in available_clis(path=str(bin_dir))
