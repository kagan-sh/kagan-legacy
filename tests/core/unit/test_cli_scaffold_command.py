"""CLI tests for `kagan tools plugin-scaffold` command."""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

from click.testing import CliRunner

from kagan.cli.tools import tools

if TYPE_CHECKING:
    from pathlib import Path


def _invoke_scaffold(tmp_path: Path, name: str) -> tuple[object, CliRunner]:
    runner = CliRunner()
    result = runner.invoke(
        tools,
        ["plugin-scaffold", "--name", name, "--output", str(tmp_path)],
    )
    return result, runner


def test_scaffold_generates_valid_directory_structure(tmp_path: Path) -> None:
    """Scaffold creates expected files and directories."""
    result, _ = _invoke_scaffold(tmp_path, "test-plugin")

    assert result.exit_code == 0, result.output
    project = tmp_path / "test-plugin"
    assert project.is_dir()
    assert (project / "test_plugin" / "__init__.py").exists()
    assert (project / "test_plugin" / "plugin.py").exists()
    assert (project / "pyproject.toml").exists()
    assert (project / "README.md").exists()
    assert (project / "tests" / "__init__.py").exists()
    assert (project / "tests" / "test_plugin.py").exists()


def test_scaffold_generated_plugin_is_importable(tmp_path: Path) -> None:
    """Generated plugin module can be imported and instantiated."""
    result, _ = _invoke_scaffold(tmp_path, "imp-test")
    assert result.exit_code == 0, result.output

    project = tmp_path / "imp-test"
    pkg_dir = project / "imp_test"
    assert pkg_dir.is_dir()

    sys.path.insert(0, str(project))
    try:
        mod = importlib.import_module("imp_test.plugin")
        plugin = mod.ImpTestPlugin()
        assert plugin.manifest.id == "imp-test"
        assert plugin.manifest.version == "0.1.0"
    finally:
        sys.path.pop(0)
        for key in list(sys.modules):
            if key.startswith("imp_test"):
                del sys.modules[key]


def test_scaffold_generated_plugin_registers_in_registry(tmp_path: Path) -> None:
    """Generated plugin can register in PluginRegistry without errors."""
    from kagan.core.plugins.sdk import PluginRegistry

    result, _ = _invoke_scaffold(tmp_path, "reg-test")
    assert result.exit_code == 0, result.output

    project = tmp_path / "reg-test"
    sys.path.insert(0, str(project))
    try:
        mod = importlib.import_module("reg_test.plugin")
        plugin = mod.RegTestPlugin()

        registry = PluginRegistry()
        registry.register_plugin(plugin)
        assert registry.resolve_operation("reg_test", "hello") is not None
    finally:
        sys.path.pop(0)
        for key in list(sys.modules):
            if key.startswith("reg_test"):
                del sys.modules[key]


def test_scaffold_rejects_invalid_name() -> None:
    """Scaffold rejects plugin names that violate the ID pattern."""
    runner = CliRunner()
    result = runner.invoke(tools, ["plugin-scaffold", "--name", "AB"])
    assert result.exit_code != 0
    assert "invalid" in result.output.lower() or "error" in result.output.lower()


def test_scaffold_rejects_existing_directory(tmp_path: Path) -> None:
    """Scaffold refuses to overwrite an existing directory."""
    (tmp_path / "dup-test").mkdir()
    result, _ = _invoke_scaffold(tmp_path, "dup-test")
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_scaffold_pyproject_contains_entry_point(tmp_path: Path) -> None:
    """Generated pyproject.toml contains the kagan.plugins entry point."""
    result, _ = _invoke_scaffold(tmp_path, "ep-check")
    assert result.exit_code == 0, result.output

    pyproject = (tmp_path / "ep-check" / "pyproject.toml").read_text()
    assert '[project.entry-points."kagan.plugins"]' in pyproject
    assert "ep-check" in pyproject
    assert "EpCheckPlugin" in pyproject
