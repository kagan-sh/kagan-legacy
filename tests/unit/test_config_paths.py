"""Config path resolution edge cases.

These tests validate KAGAN_CONFIG_DIR fallback logic in bootstrap config.
Acceptance tests create clients with explicit paths; these test the
platform-dependent path resolution that acceptance tests don't exercise.
"""

from pathlib import Path

import pytest

from kagan.core._db import default_config_path

pytestmark = [pytest.mark.unit]


def test_config_path_uses_kagan_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAGAN_CONFIG_DIR", str(tmp_path))
    path = default_config_path()
    assert path == tmp_path / "config.toml"


def test_config_path_falls_back_to_platformdirs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGAN_CONFIG_DIR", raising=False)
    path = default_config_path()
    # platformdirs uses different paths on different platforms
    # On macOS: ~/Library/Application Support/kagan/config.toml
    # On Linux: ~/.config/kagan/config.toml
    assert "kagan" in str(path)
    assert path.name == "config.toml"
