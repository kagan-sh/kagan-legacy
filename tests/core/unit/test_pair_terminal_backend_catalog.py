"""Consistency checks for the canonical PAIR backend catalog."""

from __future__ import annotations

from typing import get_args

from kagan.core import preflight
from kagan.core.config import PAIR_TERMINAL_BACKEND_VALUES as CONFIG_PAIR_TERMINAL_BACKEND_VALUES
from kagan.core.domain.enums import PairTerminalBackend
from kagan.core.domain.pair_terminal_backends import (
    ANTIGRAVITY_BACKEND,
    PAIR_TERMINAL_BACKEND_SELECT_OPTIONS,
    PAIR_TERMINAL_BACKEND_VALUES,
    UNIX_PAIR_TERMINAL_FALLBACK_ORDER,
    WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER,
    pair_terminal_backend_executable,
)
from kagan.mcp._response_models import TerminalBackendInput
from kagan.tui.terminals import installer
from kagan.tui.ui.widgets.base import PairTerminalBackendSelect


def test_catalog_values_match_domain_enum_order() -> None:
    assert tuple(backend.value for backend in PairTerminalBackend) == PAIR_TERMINAL_BACKEND_VALUES


def test_config_backend_values_match_catalog() -> None:
    assert frozenset(PAIR_TERMINAL_BACKEND_VALUES) == CONFIG_PAIR_TERMINAL_BACKEND_VALUES


def test_mcp_terminal_backend_literal_matches_catalog() -> None:
    assert get_args(TerminalBackendInput) == PAIR_TERMINAL_BACKEND_VALUES


def test_tui_backend_options_match_catalog() -> None:
    assert tuple(PairTerminalBackendSelect.OPTIONS) == PAIR_TERMINAL_BACKEND_SELECT_OPTIONS


def test_catalog_has_executable_for_every_backend() -> None:
    for backend in PAIR_TERMINAL_BACKEND_VALUES:
        assert pair_terminal_backend_executable(backend) is not None
    assert pair_terminal_backend_executable("invalid") is None


def test_preflight_windows_tmux_fallback_uses_catalog_order(monkeypatch) -> None:
    monkeypatch.setattr(preflight.platform, "system", lambda: "Windows")
    checked_commands: list[str] = []
    target_backend = WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER[2]

    def _fake_command_exists(command: str) -> bool:
        checked_commands.append(command)
        return command == pair_terminal_backend_executable(target_backend)

    monkeypatch.setattr(preflight, "_command_exists", _fake_command_exists)

    resolved = preflight._resolve_pair_terminal_backend("tmux", None)

    assert resolved == target_backend
    expected = [
        pair_terminal_backend_executable(backend)
        for backend in WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER[:3]
    ]
    assert checked_commands == [command for command in expected if command is not None]


def test_preflight_windows_tmux_fallback_defaults_to_first_catalog_candidate(monkeypatch) -> None:
    monkeypatch.setattr(preflight.platform, "system", lambda: "Windows")
    monkeypatch.setattr(preflight, "_command_exists", lambda _command: False)

    resolved = preflight._resolve_pair_terminal_backend("tmux", None)

    assert resolved == WINDOWS_PAIR_TERMINAL_FALLBACK_ORDER[0]


def test_installer_uses_catalog_executable_lookup_for_antigravity(monkeypatch) -> None:
    antigravity_executable = pair_terminal_backend_executable(ANTIGRAVITY_BACKEND)
    assert antigravity_executable is not None

    monkeypatch.setattr(
        installer,
        "_which",
        lambda command: "/tmp/agy" if command == antigravity_executable else None,
    )

    assert installer.check_terminal_installed(ANTIGRAVITY_BACKEND) is True


def test_installer_fallback_order_tracks_catalog(monkeypatch) -> None:
    last_candidate = UNIX_PAIR_TERMINAL_FALLBACK_ORDER[-1]

    def _is_last_candidate(backend: str) -> bool:
        return backend == last_candidate

    monkeypatch.setattr(installer, "check_terminal_installed", _is_last_candidate)

    resolved = installer.first_available_pair_backend(windows=False)

    assert resolved == last_candidate
