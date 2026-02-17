"""CLI tests for `kagan doctor` command."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kagan.cli.commands.doctor import doctor


def test_doctor_all_pass_exits_zero() -> None:
    """`kagan doctor` exits 0 when all checks pass."""
    runner = CliRunner()
    with (
        patch("kagan.cli.commands.doctor.cached_which", return_value="/usr/bin/fake"),
        patch("kagan.cli.commands.doctor.asyncio") as mock_asyncio,
        patch("kagan.core.paths.get_config_dir") as mock_config_dir,
    ):
        mock_config_dir.return_value.exists.return_value = True
        mock_asyncio.run.return_value = [
            ("Git version", "pass", "git 2.39.0", ""),
            ("Git user", "pass", "git user configured", ""),
        ]

        result = runner.invoke(doctor)

    assert result.exit_code == 0
    assert "All critical checks passed." in result.output


def test_doctor_missing_git_exits_one() -> None:
    """`kagan doctor` exits 1 when git is missing (FAIL check)."""
    runner = CliRunner()

    def _selective_which(name: str) -> str | None:
        if name == "git":
            return None
        return "/usr/bin/fake"

    with (
        patch("kagan.cli.commands.doctor.cached_which", side_effect=_selective_which),
        patch("kagan.core.paths.get_config_dir") as mock_config_dir,
    ):
        mock_config_dir.return_value.exists.return_value = True

        result = runner.invoke(doctor)

    assert result.exit_code == 1
    assert "git not found" in result.output


def test_doctor_structured_output_format() -> None:
    """`kagan doctor` outputs structured check lines with status icons."""
    runner = CliRunner()
    with (
        patch("kagan.cli.commands.doctor.cached_which", return_value="/usr/bin/fake"),
        patch("kagan.cli.commands.doctor.asyncio") as mock_asyncio,
        patch("kagan.core.paths.get_config_dir") as mock_config_dir,
    ):
        mock_config_dir.return_value.exists.return_value = True
        mock_asyncio.run.return_value = [
            ("Git version", "pass", "git 2.39.0", ""),
            ("Git user", "pass", "git user configured", ""),
        ]

        result = runner.invoke(doctor)

    assert "Kagan Doctor" in result.output
    assert "Python version" in result.output
    assert "Git:" in result.output
    assert "uv:" in result.output
    assert "tmux:" in result.output
    assert "npx:" in result.output
    assert "Project config:" in result.output


def test_doctor_python_too_old_exits_one() -> None:
    """`kagan doctor` exits 1 when Python version is below 3.12."""
    runner = CliRunner()
    fake_version_info = (3, 10, 0)
    with (
        patch("kagan.cli.commands.doctor.cached_which", return_value="/usr/bin/fake"),
        patch("kagan.cli.commands.doctor.sys") as mock_sys,
        patch("kagan.cli.commands.doctor.asyncio") as mock_asyncio,
        patch("kagan.core.paths.get_config_dir") as mock_config_dir,
    ):
        mock_sys.version_info = fake_version_info
        mock_config_dir.return_value.exists.return_value = True
        mock_asyncio.run.return_value = [
            ("Git version", "pass", "git 2.39.0", ""),
            ("Git user", "pass", "git user configured", ""),
        ]

        result = runner.invoke(doctor)

    assert result.exit_code == 1
    assert "3.12+ required" in result.output
