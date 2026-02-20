"""CLI tests for MCP access profile command naming and compatibility."""

from __future__ import annotations

from click.testing import CliRunner

from kagan.cli.main import cli


def test_profiles_command_lists_access_profiles() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["profiles"])

    assert result.exit_code == 0
    assert "Available MCP access profiles" in result.output
    assert "orchestrator" in result.output
    assert "Equivalent: kagan mcp --capability operator --identity kagan_admin" in result.output


def test_personas_command_is_removed() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["personas"])

    assert result.exit_code != 0
    assert "No such command 'personas'" in result.output


def test_cli_help_shows_profiles_command() -> None:
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "profiles" in result.output
