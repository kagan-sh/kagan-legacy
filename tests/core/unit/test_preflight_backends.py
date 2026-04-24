"""Unit tests for check_agent_backends() multi-backend severity rules.

Covers all three severity paths:
1. Zero of N installed → default is FAIL, rest are WARN.
2. Default missing but at least one other installed → default FAIL,
   installed others PASS, uninstalled others WARN.
3. Default installed → default PASS, uninstalled others WARN,
   installed others PASS.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

from kagan.core._preflight import CheckStatus, check_agent_backends, run_all_checks

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_availability(installed: set[str], all_backends: set[str]) -> dict[str, bool]:
    """Build a fake availability dict with specific backends installed."""
    return {name: (name in installed) for name in all_backends}


# Real backend names from the registry (subset used to keep tests fast)
_BACKENDS = {"claude-code", "codex", "gemini-cli", "opencode", "goose"}


@contextmanager
def _patch_backends(installed: set[str]) -> Generator[None, None, None]:
    """Patch both list_available_backends and AGENT_BACKENDS at the source module.

    check_agent_backends() does local imports inside its body, so we must patch
    at kagan.core._agent (where AGENT_BACKENDS and list_available_backends live)
    rather than at kagan.core._preflight.
    """
    from kagan.core._agent import AGENT_BACKENDS

    fake_backends = {name: cfg for name, cfg in AGENT_BACKENDS.items() if name in _BACKENDS}
    availability = _make_availability(installed, _BACKENDS)

    with (
        patch("kagan.core._agent.list_available_backends", return_value=availability),
        patch("kagan.core._agent.AGENT_BACKENDS", fake_backends),
    ):
        yield


# ---------------------------------------------------------------------------
# Rule 1: Zero of N installed → default FAIL, rest WARN
# ---------------------------------------------------------------------------


def test_rule1_zero_installed_default_is_fail() -> None:
    """When no backends are installed, the default backend result is FAIL."""
    with _patch_backends(set()):
        results = check_agent_backends("claude-code")

    default_result = next(r for r in results if r.name == "agent_backend:claude-code")
    assert default_result.status == CheckStatus.FAIL, (
        "Default backend must be FAIL when zero backends are installed"
    )
    assert default_result.is_blocking is True


def test_rule1_zero_installed_others_are_warn() -> None:
    """When no backends are installed, non-default backends are WARN."""
    with _patch_backends(set()):
        results = check_agent_backends("claude-code")

    non_default = [r for r in results if r.name != "agent_backend:claude-code"]
    assert non_default, "Expected non-default backend results"
    for result in non_default:
        assert result.status == CheckStatus.WARN, (
            f"Non-default backend {result.name!r} must be WARN when zero are installed,"
            f" got {result.status!r}"
        )


def test_rule1_zero_installed_all_results_emitted() -> None:
    """check_agent_backends emits one result per registered backend."""
    with _patch_backends(set()):
        results = check_agent_backends("claude-code")

    assert len(results) == len(_BACKENDS), f"Expected {len(_BACKENDS)} results, got {len(results)}"


# ---------------------------------------------------------------------------
# Rule 2: Default missing, at least one other installed → default FAIL,
#          installed others PASS, uninstalled others WARN
# ---------------------------------------------------------------------------


def test_rule2_default_missing_others_installed_default_is_fail() -> None:
    """When default is absent but others are installed, default is FAIL."""
    installed = {"codex", "opencode"}  # claude-code NOT in installed
    with _patch_backends(installed):
        results = check_agent_backends("claude-code")

    default_result = next(r for r in results if r.name == "agent_backend:claude-code")
    assert default_result.status == CheckStatus.FAIL, (
        "Default backend must be FAIL when it's missing but others are installed"
    )
    assert default_result.is_blocking is True


def test_rule2_default_missing_installed_others_are_pass() -> None:
    """When default is absent, installed non-default backends are PASS."""
    installed = {"codex", "opencode"}
    with _patch_backends(installed):
        results = check_agent_backends("claude-code")

    for name in installed:
        result = next(r for r in results if r.name == f"agent_backend:{name}")
        assert result.status == CheckStatus.PASS, (
            f"Installed backend '{name}' must be PASS, got {result.status!r}"
        )


def test_rule2_default_missing_uninstalled_others_are_warn() -> None:
    """When default is absent, uninstalled non-default backends are WARN."""
    installed = {"codex"}  # opencode, goose, gemini-cli NOT installed (and not default)
    with _patch_backends(installed):
        results = check_agent_backends("claude-code")

    uninstalled_non_default = {"opencode", "goose", "gemini-cli"}
    for name in uninstalled_non_default:
        result = next(r for r in results if r.name == f"agent_backend:{name}")
        assert result.status == CheckStatus.WARN, (
            f"Uninstalled non-default backend '{name}' must be WARN, got {result.status!r}"
        )


# ---------------------------------------------------------------------------
# Rule 3: Default installed → default PASS, uninstalled others WARN,
#          installed others PASS
# ---------------------------------------------------------------------------


def test_rule3_default_installed_is_pass() -> None:
    """When the default backend is installed, its result is PASS."""
    installed = {"claude-code", "codex"}
    with _patch_backends(installed):
        results = check_agent_backends("claude-code")

    default_result = next(r for r in results if r.name == "agent_backend:claude-code")
    assert default_result.status == CheckStatus.PASS, "Default backend must be PASS when installed"
    assert default_result.is_blocking is False


def test_rule3_default_installed_uninstalled_others_are_warn() -> None:
    """When the default is installed, uninstalled non-default backends are WARN."""
    installed = {"claude-code"}  # only default installed
    with _patch_backends(installed):
        results = check_agent_backends("claude-code")

    non_default = [r for r in results if r.name != "agent_backend:claude-code"]
    for result in non_default:
        assert result.status == CheckStatus.WARN, (
            f"Non-default uninstalled backend {result.name!r} must be WARN, got {result.status!r}"
        )


def test_rule3_default_installed_other_installed_are_pass() -> None:
    """When the default is installed, other installed backends are PASS."""
    installed = {"claude-code", "codex", "opencode"}
    with _patch_backends(installed):
        results = check_agent_backends("claude-code")

    for name in {"codex", "opencode"}:
        result = next(r for r in results if r.name == f"agent_backend:{name}")
        assert result.status == CheckStatus.PASS, (
            f"Installed non-default backend '{name}' must be PASS, got {result.status!r}"
        )


# ---------------------------------------------------------------------------
# Default backend fallback: None → uses "claude-code"
# ---------------------------------------------------------------------------


def test_none_default_backend_falls_back_to_claude_code() -> None:
    """When default_backend is None, falls back to 'claude-code' as default slot."""
    with _patch_backends(set()):
        results = check_agent_backends(None)

    names = {r.name for r in results}
    assert "agent_backend:claude-code" in names, (
        "Fallback default 'claude-code' must have its own result entry"
    )


# ---------------------------------------------------------------------------
# Default is first in output
# ---------------------------------------------------------------------------


def test_default_backend_result_is_first() -> None:
    """The default backend result is always the first item in the output."""
    with _patch_backends({"codex"}):
        results = check_agent_backends("claude-code")

    assert results[0].name == "agent_backend:claude-code", (
        "Default backend result must be listed first"
    )


# ---------------------------------------------------------------------------
# run_all_checks integration: multi-backend results included
# ---------------------------------------------------------------------------


def test_run_all_checks_includes_multi_backend_results(tmp_path) -> None:
    """run_all_checks always surveys all backends, not just the default."""
    db_path = tmp_path / "test.db"
    with _patch_backends({"claude-code"}):
        results = run_all_checks(db_path, agent_backend="claude-code")

    backend_results = [r for r in results if r.name.startswith("agent_backend:")]
    assert len(backend_results) == len(_BACKENDS), (
        "run_all_checks must emit one result per registered backend"
    )
