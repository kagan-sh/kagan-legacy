"""Skeleton smoke: the CLI boots and exposes the core commands."""

import pytest
from click.testing import CliRunner

from kagan.cli.main import _register_commands, cli


@pytest.mark.smoke
def test_help_lists_core_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("tui", "mcp", "doctor", "reset", "update"):
        assert command in result.output


@pytest.mark.smoke
def test_doctor_help_example_lines_stay_separate() -> None:
    # §1.6: the epilog example block is prefixed with a `\b` line so Click does not
    # rewrap the single-newline rows into one run-on blob. Each example must own a
    # line; before the fix they collapsed onto one (the lines ran together).
    result = CliRunner().invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0
    out = result.output
    assert "kagan doctor                      Quick health check" in out
    examples = [ln for ln in out.splitlines() if ln.strip().startswith("kagan doctor")]
    # Each of the four example commands renders on its own line, not merged.
    assert len(examples) == 4, examples
    # The next example's command must not be folded onto the previous summary.
    assert "One-line summary" not in next(
        ln for ln in examples if "tldr" not in ln and "Quick health check" in ln
    )


@pytest.mark.smoke
def test_doctor_and_update_show_summary_lines() -> None:
    # §4 Click: `doctor` and `update` carry one-line summaries, so the group help
    # lists them with a description instead of a bare name.
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Check system health" in result.output
    assert "Update kagan to the latest" in result.output


@pytest.mark.smoke
@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_dash_h_alias_works_on_group_and_subcommands(flag: str) -> None:
    # §4 Click: help_option_names = ["-h", "--help"] on the group; subcommands inherit.
    group = CliRunner().invoke(cli, [flag])
    assert group.exit_code == 0
    assert "Usage:" in group.output

    sub = CliRunner().invoke(cli, ["doctor", flag])
    assert sub.exit_code == 0
    assert "Usage:" in sub.output


@pytest.mark.smoke
def test_launch_preflight_renders_on_warn_and_proceeds_without_confirm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Phase 12c doctor §1: the launch preflight renders on ANY non-pass (warn too) so
    # degraded-mode warnings ("gh not found") are visible — and a warn-only run proceeds
    # WITHOUT the blocking "Continue anyway?" confirm (that gates only on a hard fail).
    from kagan.cli import main
    from kagan.core.doctor_checks import DoctorCheck

    warns = [
        DoctorCheck(name="git", status="pass", message="found"),
        DoctorCheck(name="gh", status="warn", message="gh not found", fix_hint="install gh"),
    ]
    monkeypatch.setattr("kagan.cli.doctor.run_doctor_checks", lambda: warns)
    confirmed: list[bool] = []
    monkeypatch.setattr(main.click, "confirm", lambda *_a, **_k: confirmed.append(True) or True)

    ran: list[bool] = []
    monkeypatch.setattr("kagan.cli.session.run", lambda **_k: ran.append(True))
    # run_async just drives the coroutine/None the stubbed session.run returns.
    monkeypatch.setattr("kagan.cli._bootstrap.run_async", lambda x: x)

    main._launch_session()

    out = capsys.readouterr().out
    assert "gh not found" in out  # the warn is surfaced in the rendered preflight
    assert "install gh" in out  # with its dim fix hint
    assert confirmed == []  # warn-only never triggers the blocking confirm
    assert ran == [True]  # the session still launches


@pytest.mark.smoke
def test_doctor_default_uses_the_calm_preflight_language() -> None:
    # Phase 12c doctor §2 + §4: the default `kagan doctor` reuses the calm preflight —
    # one visual language, calm sentence labels ("git repository"), not the raw check
    # name or the box-heavy panel form.
    result = CliRunner().invoke(cli, ["doctor"])
    out = result.output
    assert "git repository" in out  # the calm label, not the raw "git"
    # the preflight verdict line (one of the three) is present — the calm form
    assert any(v in out for v in ("Ready.", "Usable —", "Needs attention —"))


@pytest.mark.smoke
def test_doctor_technical_keeps_raw_check_names() -> None:
    # Phase 12c doctor §4: the raw check name is reserved for `--verbosity technical`.
    result = CliRunner().invoke(cli, ["doctor", "--verbosity", "technical"])
    out = result.output
    assert "detail:" in out  # the technical diagnostic form
    assert "git repository" not in out  # calm labels are NOT used in technical


@pytest.mark.smoke
def test_bare_invocation_launches_session(monkeypatch: pytest.MonkeyPatch) -> None:
    # Re-platform: bare `kagan` (no subcommand) launches the interactive session
    # (after the doctor preflight), NOT the Textual TUI. Stub the launcher so the
    # test asserts the routing, not the real session loop; --skip-update-check
    # avoids network.
    _register_commands()
    invoked = False

    def fake_launch() -> None:
        nonlocal invoked
        invoked = True

    monkeypatch.setattr("kagan.cli.main._launch_session", fake_launch)
    result = CliRunner().invoke(cli, ["--skip-update-check"])
    assert result.exit_code == 0, result.output
    assert invoked  # fails if the default-command routing is removed/changed
