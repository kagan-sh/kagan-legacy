"""Unit tests for check_agent_backends() multi-backend severity rules.

Covers all three severity paths:
1. Zero of N installed → default is FAIL, rest are WARN.
2. Default missing but at least one other installed → default FAIL,
   installed others PASS, uninstalled others WARN.
3. Default installed → default PASS, uninstalled others WARN,
   installed others PASS.
"""

from __future__ import annotations

import pytest

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


def _patch_backends(monkeypatch: pytest.MonkeyPatch, installed: set[str]) -> None:
    """Patch list_available_backends at the source module.

    check_agent_backends() does a local import inside its body, so we must patch
    at kagan.core._agent (where list_available_backends lives) rather than at
    kagan.core._preflight.
    """
    availability = _make_availability(installed, _BACKENDS)
    monkeypatch.setattr(
        "kagan.core._agent.list_available_backends",
        lambda *a, **kw: availability,
    )


# ---------------------------------------------------------------------------
# Rule 1: Zero of N installed → default FAIL, rest WARN
# ---------------------------------------------------------------------------


def test_rule1_zero_installed_default_is_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no backends are installed, the default backend result is FAIL."""
    _patch_backends(monkeypatch, set())
    results = check_agent_backends("claude-code")

    default_result = next(r for r in results if r.name == "agent_backend:claude-code")
    assert default_result.status == CheckStatus.FAIL, (
        "Default backend must be FAIL when zero backends are installed"
    )
    assert default_result.is_blocking is True


def test_rule1_zero_installed_others_are_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no backends are installed, non-default backends are WARN."""
    _patch_backends(monkeypatch, set())
    results = check_agent_backends("claude-code")

    non_default = [r for r in results if r.name != "agent_backend:claude-code"]
    assert non_default, "Expected non-default backend results"
    for result in non_default:
        assert result.status == CheckStatus.WARN, (
            f"Non-default backend {result.name!r} must be WARN when zero are installed,"
            f" got {result.status!r}"
        )


def test_rule1_zero_installed_all_results_emitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_agent_backends emits one result per registered backend."""
    _patch_backends(monkeypatch, set())
    results = check_agent_backends("claude-code")

    assert len(results) == len(_BACKENDS), f"Expected {len(_BACKENDS)} results, got {len(results)}"


# ---------------------------------------------------------------------------
# Rule 2: Default missing, at least one other installed → default FAIL,
#          installed others PASS, uninstalled others WARN
# ---------------------------------------------------------------------------


def test_rule2_default_missing_others_installed_default_is_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When default is absent but others are installed, default is FAIL."""
    installed = {"codex", "opencode"}  # claude-code NOT in installed
    _patch_backends(monkeypatch, installed)
    results = check_agent_backends("claude-code")

    default_result = next(r for r in results if r.name == "agent_backend:claude-code")
    assert default_result.status == CheckStatus.FAIL, (
        "Default backend must be FAIL when it's missing but others are installed"
    )
    assert default_result.is_blocking is True


def test_rule2_default_missing_installed_others_are_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When default is absent, installed non-default backends are PASS."""
    installed = {"codex", "opencode"}
    _patch_backends(monkeypatch, installed)
    results = check_agent_backends("claude-code")

    for name in installed:
        result = next(r for r in results if r.name == f"agent_backend:{name}")
        assert result.status == CheckStatus.PASS, (
            f"Installed backend '{name}' must be PASS, got {result.status!r}"
        )


def test_rule2_default_missing_uninstalled_others_are_warn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When default is absent, uninstalled non-default backends are WARN."""
    installed = {"codex"}  # opencode, goose, gemini-cli NOT installed (and not default)
    _patch_backends(monkeypatch, installed)
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


def test_rule3_default_installed_is_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the default backend is installed, its result is PASS."""
    installed = {"claude-code", "codex"}
    _patch_backends(monkeypatch, installed)
    results = check_agent_backends("claude-code")

    default_result = next(r for r in results if r.name == "agent_backend:claude-code")
    assert default_result.status == CheckStatus.PASS, "Default backend must be PASS when installed"
    assert default_result.is_blocking is False


def test_rule3_default_installed_uninstalled_others_are_warn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the default is installed, uninstalled non-default backends are WARN."""
    installed = {"claude-code"}  # only default installed
    _patch_backends(monkeypatch, installed)
    results = check_agent_backends("claude-code")

    non_default = [r for r in results if r.name != "agent_backend:claude-code"]
    for result in non_default:
        assert result.status == CheckStatus.WARN, (
            f"Non-default uninstalled backend {result.name!r} must be WARN, got {result.status!r}"
        )


def test_rule3_default_installed_other_installed_are_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the default is installed, other installed backends are PASS."""
    installed = {"claude-code", "codex", "opencode"}
    _patch_backends(monkeypatch, installed)
    results = check_agent_backends("claude-code")

    for name in {"codex", "opencode"}:
        result = next(r for r in results if r.name == f"agent_backend:{name}")
        assert result.status == CheckStatus.PASS, (
            f"Installed non-default backend '{name}' must be PASS, got {result.status!r}"
        )


# ---------------------------------------------------------------------------
# Default backend fallback: None → uses "claude-code"
# ---------------------------------------------------------------------------


def test_none_default_backend_falls_back_to_claude_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When default_backend is None, falls back to 'claude-code' as default slot."""
    _patch_backends(monkeypatch, set())
    results = check_agent_backends(None)

    names = {r.name for r in results}
    assert "agent_backend:claude-code" in names, (
        "Fallback default 'claude-code' must have its own result entry"
    )


# ---------------------------------------------------------------------------
# Default is first in output
# ---------------------------------------------------------------------------


def test_default_backend_result_is_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default backend result is always the first item in the output."""
    _patch_backends(monkeypatch, {"codex"})
    results = check_agent_backends("claude-code")

    assert results[0].name == "agent_backend:claude-code", (
        "Default backend result must be listed first"
    )


# ---------------------------------------------------------------------------
# run_all_checks integration: multi-backend results included
# ---------------------------------------------------------------------------


def test_run_all_checks_includes_multi_backend_results(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_all_checks always surveys all backends, not just the default."""
    db_path = tmp_path / "test.db"
    _patch_backends(monkeypatch, {"claude-code"})
    results = run_all_checks(db_path, agent_backend="claude-code")

    backend_results = [r for r in results if r.name.startswith("agent_backend:")]
    assert len(backend_results) == len(_BACKENDS), (
        "run_all_checks must emit one result per registered backend"
    )
