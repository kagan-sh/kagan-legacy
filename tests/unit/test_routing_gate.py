"""Unit tests for the startup doctor failure gate in app.py."""

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


@pytest.fixture
def gate():
    from kagan.tui.app import _has_startup_doctor_failures

    return _has_startup_doctor_failures


def test_all_pass_checks_do_not_block_startup(gate) -> None:
    checks = [
        _make_check("agent backends", "pass", category="backend"),
        _make_check("backend: claude-code (default)", "pass", category="backend"),
        _make_check("git", "pass", category="core"),
    ]
    assert not gate(checks)


def test_warn_only_backend_detail_checks_do_not_block_startup(gate) -> None:
    checks = [
        _make_check("agent backends", "pass", category="backend"),
        _make_check("backend: claude-code (default)", "pass", category="backend"),
        _make_check("backend: opencode", "warn", category="backend"),
        _make_check("backend: gemini-cli", "warn", category="backend"),
    ]
    assert not gate(checks)


def test_warn_only_required_checks_do_not_block_startup(gate) -> None:
    checks = [
        _make_check("git", "warn", category="core"),
        _make_check("agent backends", "pass", category="backend"),
    ]
    assert not gate(checks)


def test_required_failure_blocks_startup(gate) -> None:
    checks = [
        _make_check("git", "fail", category="core"),
        _make_check("agent backends", "pass", category="backend"),
    ]
    assert gate(checks)


def test_default_backend_failure_blocks_startup(gate) -> None:
    checks = [
        _make_check("agent backends", "fail", category="backend"),
        _make_check("backend: claude-code (default)", "fail", category="backend"),
        _make_check("backend: opencode", "warn", category="backend"),
    ]
    assert gate(checks)
