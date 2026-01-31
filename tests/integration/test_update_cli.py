"""Tests for update CLI command."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from kagan.cli.update import InstallationInfo, update

pytestmark = pytest.mark.integration


class TestUpdateCommand:
    """Tests for the update CLI command."""

    def test_update_check_mode_up_to_date(self, mocker):
        """Test --check flag when up to date."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="0.1.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value="0.1.0")

        runner = CliRunner()
        result = runner.invoke(update, ["--check"])

        assert result.exit_code == 0
        assert "latest version" in result.output.lower()

    def test_update_check_mode_update_available(self, mocker):
        """Test --check flag when update is available."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value="2.0.0")

        runner = CliRunner()
        result = runner.invoke(update, ["--check"])

        assert result.exit_code == 1
        assert "update available" in result.output.lower()

    def test_update_check_mode_error(self, mocker):
        """Test --check flag when error occurs."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value=None)

        runner = CliRunner()
        result = runner.invoke(update, ["--check"])

        assert result.exit_code == 2
        assert "error" in result.output.lower()

    def test_update_dev_version_warning(self, mocker):
        """Test warning shown for dev versions."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="dev")

        runner = CliRunner()
        result = runner.invoke(update)

        assert "development version" in result.output.lower()
        assert result.exit_code == 0

    def test_update_already_latest(self, mocker):
        """Test message when already on latest version."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value="1.0.0")

        runner = CliRunner()
        result = runner.invoke(update)

        assert result.exit_code == 0
        assert "already the latest version" in result.output.lower()

    def test_update_force_flag_skips_confirmation(self, mocker):
        """Test --force flag skips confirmation prompt."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value="2.0.0")
        mock_detect = mocker.patch("kagan.cli.update.detect_installation_method")
        mock_upgrade = mocker.patch("kagan.cli.update.run_upgrade")
        mock_detect.return_value = InstallationInfo(
            method="uv tool",
            upgrade_command=["uv", "tool", "upgrade", "kagan@2.0.0"],
        )
        mock_upgrade.return_value = (True, "Success")

        runner = CliRunner()
        result = runner.invoke(update, ["--force"])

        # Should not prompt, should call upgrade directly
        mock_upgrade.assert_called_once()
        assert "successfully upgraded" in result.output.lower()

    def test_update_user_declines(self, mocker):
        """Test user declining update prompt."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value="2.0.0")
        mock_detect = mocker.patch("kagan.cli.update.detect_installation_method")
        mock_detect.return_value = InstallationInfo(
            method="uv tool",
            upgrade_command=["uv", "tool", "upgrade", "kagan@2.0.0"],
        )

        runner = CliRunner()
        result = runner.invoke(update, input="n\n")

        assert "cancelled" in result.output.lower()

    def test_update_with_prerelease_flag(self, mocker):
        """Test --prerelease flag includes prerelease versions."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        # Mock fetch_latest_version to return prerelease when called with prerelease=True
        mock_fetch = mocker.patch("kagan.cli.update.fetch_latest_version")
        mock_fetch.return_value = "2.0.0b1"

        runner = CliRunner()
        result = runner.invoke(update, ["--check", "--prerelease"])

        assert result.exit_code == 1  # Update available
        assert "2.0.0b1" in result.output
        # Verify fetch was called with prerelease=True
        mock_fetch.assert_called_once_with(prerelease=True)

    def test_update_unknown_installation_shows_manual_instructions(self, mocker):
        """Test that unknown installation method shows manual upgrade instructions."""
        mocker.patch("kagan.cli.update.get_installed_version", return_value="1.0.0")
        mocker.patch("kagan.cli.update.fetch_latest_version", return_value="2.0.0")
        mocker.patch("kagan.cli.update.detect_installation_method", return_value=None)

        runner = CliRunner()
        result = runner.invoke(update, ["--force"])

        assert "could not detect" in result.output.lower()
        assert "uv tool upgrade" in result.output
        assert "pipx install" in result.output
        assert "pip install" in result.output
