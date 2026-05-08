"""Unit tests for the _is_optional_backend_warning gate in app.py.

Covers: cases (a)-(d) from the task brief, ensuring only non-degrading
backend WARNs are suppressed at the boot gate while all other WARNs
(and all FAILs) still trigger the "Degraded mode" toast.
"""

import pytest

from kagan.cli.doctor import DoctorCheck

pytestmark = [pytest.mark.unit]


def _make_check(
    name: str,
    status: str,
    *,
    category: str = "core",
) -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status=status,
        message="",
        fix_hint="",
        verify_hint="",
        category=category,
    )


def _backend(name: str, status: str) -> DoctorCheck:
    return _make_check(f"agent backend: {name}", status, category="backend")


# ---------------------------------------------------------------------------
# Import the helper under test
# ---------------------------------------------------------------------------


@pytest.fixture
def gate():
    from kagan.tui.app import _is_optional_backend_warning

    return _is_optional_backend_warning


# ---------------------------------------------------------------------------
# Case (a): all PASS — no WARNs at all
# ---------------------------------------------------------------------------


def test_case_a_all_pass_no_warnings(gate) -> None:
    checks = [
        _backend("claude-code", "pass"),
        _backend("opencode", "pass"),
        _make_check("git", "pass", category="core"),
    ]
    for c in checks:
        assert not gate(c, checks), f"Expected gate=False for {c.name!r} (all PASS)"


# ---------------------------------------------------------------------------
# Case (b): default PASS + 5 non-default WARNs — optional, not degrading
# ---------------------------------------------------------------------------


def test_case_b_default_pass_nondefault_warn_are_optional(gate) -> None:
    checks = [
        _backend("claude-code", "pass"),  # default (the one that matters)
        _backend("opencode", "warn"),
        _backend("gemini-cli", "warn"),
        _backend("codex", "warn"),
        _backend("aider", "warn"),
        _backend("continue", "warn"),
    ]
    passing_check = checks[0]
    assert not gate(passing_check, checks), "PASS check should not be optional"

    for warn_check in checks[1:]:
        assert gate(warn_check, checks), (
            f"Non-default WARN {warn_check.name!r} should be optional when a PASS exists"
        )


# ---------------------------------------------------------------------------
# Case (c): default WARN with no other PASSes — still degraded
# ---------------------------------------------------------------------------


def test_case_c_default_warn_no_pass_is_degraded(gate) -> None:
    checks = [
        _backend("claude-code", "warn"),  # the only backend, and it's WARN
        _backend("opencode", "warn"),
    ]
    for c in checks:
        assert not gate(c, checks), f"{c.name!r} should NOT be optional — no passing backend exists"


# ---------------------------------------------------------------------------
# Case (d): git WARN — not optional, not a backend check
# ---------------------------------------------------------------------------


def test_case_d_git_warn_is_not_optional(gate) -> None:
    checks = [
        _make_check("git", "warn", category="core"),
        _backend("claude-code", "pass"),
    ]
    git_check = checks[0]
    assert not gate(git_check, checks), "git WARN must not be treated as optional"


# ---------------------------------------------------------------------------
# Edge: non-WARN checks always return False regardless of others
# ---------------------------------------------------------------------------


def test_non_warn_always_false(gate) -> None:
    checks = [
        _backend("claude-code", "pass"),
        _backend("opencode", "fail"),
    ]
    for c in checks:
        assert not gate(c, checks), (
            f"gate must be False for status={c.status!r} (only WARN is optional-eligible)"
        )


# ---------------------------------------------------------------------------
# Edge: "agent_backend:" prefix (raw name) is also handled
# ---------------------------------------------------------------------------


def test_raw_agent_backend_prefix_handled(gate) -> None:
    checks = [
        _make_check("agent_backend:claude-code", "pass", category="backend"),
        _make_check("agent_backend:opencode", "warn", category="backend"),
    ]
    warn_check = checks[1]
    assert gate(warn_check, checks), (
        "agent_backend: prefix (underscore) should also be treated as optional backend"
    )
