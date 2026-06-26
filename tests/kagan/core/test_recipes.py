from pathlib import Path

import pytest

from kagan.core.agent import _build_cmd
from kagan.core.errors import ConfigurationError
from kagan.core.recipes import (
    RECIPES,
    available_clis,
    recipe_for,
    resolve_model,
    validate_model_for_cli,
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


def test_resolve_model_none_omits_the_flag():
    # R-003 STEP 3: an unset builder/reviewer must stay None so _build_cmd omits --model
    # and the CLI's own default is used — unchanged behaviour for the common case.
    for cli in SUPPORTED_CLIS:
        assert resolve_model(cli, None) is None


def test_resolve_model_claude_alias_stays_a_bare_alias():
    # claude --help documents opus/sonnet/haiku as native aliases it resolves itself, so
    # the resolver hands claude the BARE alias (never a drifting full id).
    assert resolve_model("claude", "opus") == "opus"
    assert resolve_model("claude", "sonnet") == "sonnet"
    assert resolve_model("claude", "haiku") == "haiku"


def test_resolve_model_opencode_alias_is_provider_qualified():
    # opencode `run --model` needs `provider/model`; a fresh install carries the claude
    # models under its own `opencode/` gateway provider. The alias must become that id,
    # never the bare tier (opencode rejects a bare alias).
    assert resolve_model("opencode", "opus") == "opencode/claude-opus-4-8"
    assert resolve_model("opencode", "sonnet") == "opencode/claude-sonnet-4-6"
    assert resolve_model("opencode", "haiku") == "opencode/claude-haiku-4-5"
    assert "/" in resolve_model("opencode", "opus")


def test_resolve_model_passes_native_ids_through_verbatim():
    # A power-user native id (NOT a canonical alias) is passed through unchanged for any
    # CLI — kagan never second-guesses an explicit vendor model string.
    assert resolve_model("claude", "claude-opus-4-8") == "claude-opus-4-8"
    assert resolve_model("codex", "o3") == "o3"
    assert resolve_model("codex", "gpt-5-codex") == "gpt-5-codex"
    assert resolve_model("kimi", "kimi-code/kimi-for-coding") == "kimi-code/kimi-for-coding"
    assert resolve_model("opencode", "openai/gpt-5") == "openai/gpt-5"


@pytest.mark.parametrize("cli", ["codex", "kimi"])
@pytest.mark.parametrize("alias", ["opus", "sonnet", "haiku"])
def test_resolve_model_alias_on_vendor_locked_cli_fails_loud(cli: str, alias: str):
    # codex/kimi are OpenAI-/Moonshot-locked with no verifiable claude-tier equivalent.
    # A canonical tier alias there MUST raise (loud fail), never silently pick a
    # wrong-vendor model — the message names the model and the CLI so the user can fix it.
    with pytest.raises(ConfigurationError) as exc:
        resolve_model(cli, alias)
    assert alias in str(exc.value)
    assert cli in str(exc.value)


def test_build_cmd_uses_the_resolved_model_for_the_flag(tmp_path: Path):
    # The (cli, alias) pair must reach --model RESOLVED: claude gets the bare alias,
    # opencode gets the provider-qualified id. Pins that _build_cmd resolves at the seam.
    prompt = tmp_path / ".kagan" / "p.txt"
    prompt.parent.mkdir()
    prompt.write_text("x")

    claude_cmd = _build_cmd("claude", prompt, cwd=tmp_path, model="opus")
    assert claude_cmd[claude_cmd.index("--model") + 1] == "opus"

    oc_cmd = _build_cmd("opencode", prompt, cwd=tmp_path, model="opus")
    assert oc_cmd[oc_cmd.index("--model") + 1] == "opencode/claude-opus-4-8"

    # a native id passes through to the flag unchanged.
    native = _build_cmd("codex", prompt, cwd=tmp_path, model="o3")
    assert native[native.index("--model") + 1] == "o3"


def test_build_cmd_raises_on_an_unresolvable_alias(tmp_path: Path):
    # _build_cmd is the seam: a canonical alias with no mapping for the CLI fails LOUD
    # there (rule 8 — the gate must be able to reject the violation), not silently.
    prompt = tmp_path / ".kagan" / "p.txt"
    prompt.parent.mkdir()
    prompt.write_text("x")
    with pytest.raises(ConfigurationError):
        _build_cmd("codex", prompt, cwd=tmp_path, model="opus")


def test_validate_model_rejects_claude_native_on_codex():
    # Rule 8: claude-opus is NOT a canonical tier alias, so resolve_model passes it
    # through — validate_model_for_cli must catch the cross-vendor mismatch loud.
    with pytest.raises(ConfigurationError) as exc:
        validate_model_for_cli("codex", "claude-opus")
    assert "claude-opus" in str(exc.value)
    assert "codex" in str(exc.value)


def test_validate_model_accepts_claude_native_on_claude():
    validate_model_for_cli("claude", "claude-opus")


def test_validate_model_accepts_codex_native_on_codex():
    validate_model_for_cli("codex", "o3")
    validate_model_for_cli("codex", "gpt-5-codex")


@pytest.mark.parametrize("cli", ["codex", "kimi"])
@pytest.mark.parametrize("alias", ["opus", "sonnet", "haiku"])
def test_validate_model_alias_on_vendor_locked_cli_fails_loud(cli: str, alias: str):
    with pytest.raises(ConfigurationError) as exc:
        validate_model_for_cli(cli, alias)
    assert alias in str(exc.value)
    assert cli in str(exc.value)


def test_available_clis_filters_to_path(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\necho ok\n")
    fake.chmod(0o755)
    assert "claude" in available_clis(path=str(bin_dir))
    assert "codex" not in available_clis(path=str(bin_dir))
