"""Config path resolution edge cases.

These tests validate XDG_CONFIG_HOME fallback logic in bootstrap config.
Acceptance tests create clients with explicit paths; these test the
platform-dependent path resolution that acceptance tests don't exercise.
"""

from pathlib import Path

import pytest

from kagan.core._config import default_config_path

pytestmark = [pytest.mark.unit]


def test_config_path_uses_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = default_config_path()
    assert path == tmp_path / "kagan" / "config.toml"


def test_config_path_falls_back_to_home_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    path = default_config_path()
    assert path == Path.home() / ".config" / "kagan" / "config.toml"
