"""Tests for consolidated CLI routing boundary."""

from __future__ import annotations

import click
from click.testing import CliRunner

import kagan.cli.main as cli_main


def test_cli_invokes_tui_when_no_subcommand(monkeypatch) -> None:
    """`kagan` with no subcommand should invoke the default TUI command."""
    runner = CliRunner()

    @click.command()
    def fake_tui() -> None:
        click.echo("tui-invoked")

    monkeypatch.setattr(cli_main, "tui", fake_tui)

    result = runner.invoke(cli_main.cli, [])

    assert result.exit_code == 0
    assert "tui-invoked" in result.output


def test_cli_version_prints_version_and_exits() -> None:
    """`kagan --version` should print package version and exit."""
    runner = CliRunner()

    result = runner.invoke(cli_main.cli, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"kagan {cli_main.__version__}"


def test_cli_registers_expected_top_level_commands() -> None:
    """Consolidated CLI boundary should route all expected subcommands."""
    expected = {
        "core",
        "doctor",
        "list",
        "mcp",
        "reset",
        "tools",
        "tui",
        "update",
    }

    assert expected.issubset(set(cli_main.cli.commands))
