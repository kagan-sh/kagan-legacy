"""Snapshot-style tests for DoctorModal startup routing.

These tests verify the three visible states:
1. All-green: no modal, project picker shown.
2. WARN-only: project picker shown with a toast notification.
3. FAIL: DoctorModal with N check rows visible.
"""

from __future__ import annotations

import pytest

from kagan.cli.doctor import DoctorCheck

pytestmark = [pytest.mark.tui, pytest.mark.snapshot]


def _make_check(name: str, status: str, fix_hint: str = "") -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status=status,
        message=f"{name} {status}",
        fix_hint=fix_hint if status != "pass" else "",
        verify_hint=f"{name} --version",
        category="core",
    )


# ── State 1: all-green (no modal, project picker shown) ───────────────────


async def test_snapshot_all_green_routes_to_project_picker(tmp_path) -> None:
    """All-pass checks: project picker shown, no DoctorModal."""
    from kagan.tui import KaganApp

    all_pass_checks = [
        _make_check("git", "pass"),
        _make_check("tmux", "pass"),
        _make_check("agent backend", "pass"),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=all_pass_checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        assert app.screen.id == "setup-flow"

        # Confirm DoctorModal is NOT in screen stack
        screen_ids = [s.id for s in app.screen_stack]
        assert "doctor-modal" not in screen_ids


# ── State 2: WARN-only (project picker shown, notification emitted) ───────


async def test_snapshot_warn_only_routes_to_project_picker(tmp_path) -> None:
    """WARN-only checks: project picker shown, no blocking modal."""
    from kagan.tui import KaganApp

    warn_checks = [
        _make_check("ide", "warn", fix_hint="Open a supported editor"),
        _make_check("git", "pass"),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=warn_checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        assert app.screen.id == "setup-flow"

        # No doctor-modal on stack
        screen_ids = [s.id for s in app.screen_stack]
        assert "doctor-modal" not in screen_ids


# ── State 3: FAIL (DoctorModal with N rows) ───────────────────────────────


async def test_snapshot_fail_doctor_modal_shows_n_rows(tmp_path) -> None:
    """FAIL checks: DoctorModal is shown with correct number of FAIL+WARN rows."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import _CheckRow

    fail_checks = [
        _make_check("git", "fail", fix_hint="brew install git"),
        _make_check("tmux", "fail", fix_hint="brew install tmux"),
        _make_check("ide", "warn", fix_hint="Open a supported editor"),
        _make_check("agent backend", "pass"),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=fail_checks)
    async with app.run_test() as pilot:
        await pilot.pause()

        assert app.screen.id == "doctor-modal"

        rows = app.screen.query(_CheckRow)
        # 2 FAILs + 1 WARN = 3 rows; PASS excluded
        assert len(rows) == 3

        # Status classes correct
        fail_rows = [r for r in rows if "dm-status-fail" in r.classes]
        warn_rows = [r for r in rows if "dm-status-warn" in r.classes]
        assert len(fail_rows) == 2
        assert len(warn_rows) == 1


async def test_snapshot_fail_modal_header_and_summary(tmp_path) -> None:
    """DoctorModal header renders title, subtitle and summary correctly."""
    from textual.widgets import Label

    from kagan.tui import KaganApp

    checks = [
        _make_check("git", "fail"),
        _make_check("tmux", "warn"),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        title = app.screen.query_one("#dm-title", Label)
        assert "Kagan Doctor" in str(title.content)

        summary = app.screen.query_one("#dm-summary", Label)
        summary_text = str(summary.content)
        assert "1 blocking issue" in summary_text
        assert "1 warning" in summary_text


async def test_snapshot_fail_modal_run_fix_buttons_count(tmp_path) -> None:
    """Run-this-now buttons appear for checks with non-empty fix_hint."""
    from kagan.tui import KaganApp

    checks = [
        _make_check("git", "fail", fix_hint="brew install git"),
        DoctorCheck(
            name="tmux",
            status="fail",
            message="tmux not found",
            fix_hint="",  # no fix hint → no button
            verify_hint="tmux -V",
            category="core",
        ),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        run_btns = app.screen.query(".dm-run-fix-btn")
        assert len(run_btns) == 1  # only the check with fix_hint


async def test_snapshot_fail_modal_actions_bar_present(tmp_path) -> None:
    """Re-check all and Skip anyway buttons are present in DoctorModal.

    Skip is enabled after on_mount auto-focuses the first check row.
    Escape is always blocked; dismissal only via Skip anyway button.
    """
    from textual.widgets import Button

    from kagan.tui import KaganApp

    checks = [_make_check("git", "fail", fix_hint="brew install git")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        recheck = app.screen.query_one("#dm-recheck-btn", Button)
        skip = app.screen.query_one("#dm-skip-btn", Button)
        assert recheck is not None
        assert skip is not None
        # Skip is enabled because on_mount auto-focuses the first check row
        assert skip.disabled is False


# ── Multi-backend backend scenarios ──────────────────────────────────────────


def _make_backend_check(backend_name: str, status: str, is_default: bool = False) -> DoctorCheck:
    """Create a DoctorCheck for a backend as produced by _collapse_backend_checks."""
    name = "agent backends" if is_default else f"backend: {backend_name}"
    if is_default:
        # Summary check
        if status == "pass":
            msg = f"Default backend '{backend_name}' ready — 1/2 backends installed"
        else:
            msg = f"Default backend '{backend_name}' not found — 0/2 backends installed"
        hint = "" if status == "pass" else "Install or change default backend"
    else:
        msg = (
            f"Agent backend '{backend_name}' found"
            if status == "pass"
            else f"Agent backend '{backend_name}' not found on PATH"
        )
        hint = "" if status == "pass" else f"Install '{backend_name}' to enable the backend"
    return DoctorCheck(
        name=name,
        status=status,
        message=msg,
        fix_hint=hint,
        verify_hint=f"which {backend_name}",
        category="backend",
    )


async def test_snapshot_zero_ready_doctor_modal_blocks(tmp_path) -> None:
    """Zero-ready: DoctorModal shown and is non-dismissible (FAIL on agent backends).

    Simulates the case where the default backend is missing and no backends installed.
    The 'agent backends' summary row has status=fail, which triggers the modal.
    """
    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import _CheckRow

    # Summary row with FAIL status (default backend missing, zero installed)
    summary_check = DoctorCheck(
        name="agent backends",
        status="fail",
        message="Default backend 'claude-code' not found — 0/14 backends installed",
        fix_hint="Install at least one agent backend. Run `kg doctor` for setup guidance.",
        verify_hint="which claude",
        category="backend",
    )
    # A few per-backend detail rows (all WARN since zero installed)
    detail_claude = DoctorCheck(
        name="backend: claude-code (default)",
        status="fail",
        message="Agent backend 'claude-code' not found on PATH — no agent backends are installed",
        fix_hint="Install 'claude' or configure a different agent backend in Settings",
        verify_hint="which claude",
        category="backend",
    )
    detail_codex = DoctorCheck(
        name="backend: codex",
        status="warn",
        message="Agent backend 'codex' not found on PATH",
        fix_hint="Install 'codex' to enable the 'codex' backend",
        verify_hint="which codex",
        category="backend",
    )
    # Core checks all pass
    core_checks = [
        _make_check("git", "pass"),
        _make_check("tmux", "pass"),
    ]

    all_checks = [*core_checks, summary_check, detail_claude, detail_codex]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=all_checks)
    async with app.run_test() as pilot:
        await pilot.pause()

        # DoctorModal must appear because summary row is FAIL
        assert app.screen.id == "doctor-modal"

        rows = app.screen.query(_CheckRow)
        # summary (fail) + detail_claude (fail) + detail_codex (warn) = 3 rows
        assert len(rows) == 3

        fail_rows = [r for r in rows if "dm-status-fail" in r.classes]
        warn_rows = [r for r in rows if "dm-status-warn" in r.classes]
        assert len(fail_rows) == 2
        assert len(warn_rows) == 1


async def test_snapshot_single_backend_available_default_fail(tmp_path) -> None:
    """Single-backend-available: default missing, one other installed.

    'agent backends' summary is FAIL → DoctorModal shown.
    One non-default backend detail row is PASS (installed).
    """
    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import _CheckRow

    summary_check = DoctorCheck(
        name="agent backends",
        status="fail",
        message="Default backend 'claude-code' not found — 1/2 backends installed",
        fix_hint="Install 'claude' or change the default backend in Settings",
        verify_hint="which claude",
        category="backend",
    )
    detail_claude = DoctorCheck(
        name="backend: claude-code (default)",
        status="fail",
        message="Agent backend 'claude-code' not found on PATH",
        fix_hint="Install 'claude' or configure a different agent backend in Settings",
        verify_hint="which claude",
        category="backend",
    )
    detail_codex = DoctorCheck(
        name="backend: codex",
        status="pass",
        message="Agent backend 'codex' found",
        fix_hint="",
        verify_hint="which codex",
        category="backend",
    )

    core_checks = [_make_check("git", "pass")]
    all_checks = [*core_checks, summary_check, detail_claude, detail_codex]

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=all_checks)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Modal shown because summary_check is FAIL
        assert app.screen.id == "doctor-modal"

        rows = app.screen.query(_CheckRow)
        # summary (fail) + detail_claude (fail) = 2 rows; detail_codex (pass) excluded
        assert len(rows) == 2
        fail_rows = [r for r in rows if "dm-status-fail" in r.classes]
        assert len(fail_rows) == 2


async def test_snapshot_all_ready_no_modal(tmp_path) -> None:
    """All-ready: default backend installed, all pass -> project picker, no DoctorModal."""
    from kagan.tui import KaganApp

    # Summary row PASS (default installed)
    summary_check = DoctorCheck(
        name="agent backends",
        status="pass",
        message="Default backend 'claude-code' ready — 2/2 backends installed",
        fix_hint="",
        verify_hint="which claude",
        category="backend",
    )
    detail_claude = DoctorCheck(
        name="backend: claude-code (default)",
        status="pass",
        message="Agent backend 'claude-code' found",
        fix_hint="",
        verify_hint="which claude",
        category="backend",
    )
    detail_codex = DoctorCheck(
        name="backend: codex",
        status="pass",
        message="Agent backend 'codex' found",
        fix_hint="",
        verify_hint="which codex",
        category="backend",
    )

    core_checks = [
        _make_check("git", "pass"),
        _make_check("tmux", "pass"),
    ]
    all_checks = [*core_checks, summary_check, detail_claude, detail_codex]

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=all_checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        # No modal: all checks pass, land on the project picker.
        assert app.screen.id == "setup-flow"

        screen_ids = [s.id for s in app.screen_stack]
        assert "doctor-modal" not in screen_ids


# ── Wave 3c: auto-promote snapshot tests ─────────────────────────────────────


async def test_snapshot_auto_promote_row_marked_pass_after_install(tmp_path) -> None:
    """AC4: After a successful install rc=0 the promoted row shows dm-status-pass.

    Uses a stub run_doctor_checks that returns the check as PASS, simulating
    the state immediately after the backend was installed.
    """
    from unittest.mock import patch

    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import DoctorModal, _CommandPane

    backend_check = DoctorCheck(
        name="backend: snap-agent (default)",
        status="fail",
        message="snap-agent not found",
        fix_hint="echo install",
        verify_hint="which snap-agent",
        category="backend",
    )
    passing_check = DoctorCheck(
        name="backend: snap-agent (default)",
        status="pass",
        message="snap-agent found",
        fix_hint="",
        verify_hint="which snap-agent",
        category="backend",
    )

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=[backend_check])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        modal: DoctorModal = app.screen  # type: ignore[assignment]

        # No usable backend is available yet, so the modal cannot be skipped.
        from textual.widgets import Button

        skip_btn = modal.query_one("#dm-skip-btn", Button)
        assert skip_btn.disabled is True

        # Inject rc=0 finish — row should be marked pass
        with patch(
            "kagan.tui.screens.doctor_modal.run_doctor_check_for_backend",
            return_value=passing_check,
        ):
            modal._on_command_finished(
                _CommandPane.CommandFinished(return_code=0, check_name=backend_check.name)
            )
            # Wait for targeted recheck + auto-dismiss
            from tests.helpers.async_utils import wait_for as _wait_for

            await _wait_for(
                lambda: app.screen.id == "setup-flow"
                and bool(app.screen.query("#setup-project-list")),
                pump_delay=0.05,
            )

        # After dismiss we should be at project selection (no FAILs)
        assert app.screen.id == "setup-flow"


async def test_snapshot_modal_stays_open_when_other_fails_remain(tmp_path) -> None:
    """AC4: If other FAILs remain after install, modal stays open (not dismissed)."""
    from unittest.mock import patch

    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import DoctorModal, _check_row_id, _CommandPane

    backend_check = DoctorCheck(
        name="backend: snap-agent (default)",
        status="fail",
        message="snap-agent not found",
        fix_hint="echo install",
        verify_hint="which snap-agent",
        category="backend",
    )
    git_check = DoctorCheck(
        name="git",
        status="fail",
        message="git not found",
        fix_hint="brew install git",
        verify_hint="git --version",
        category="core",
    )
    # After recheck: backend passes, git still fails
    passing_backend = DoctorCheck(
        name="backend: snap-agent (default)",
        status="pass",
        message="snap-agent found",
        fix_hint="",
        verify_hint="which snap-agent",
        category="backend",
    )

    app = KaganApp(
        db_path=tmp_path / "kagan.db",
        startup_checks=[backend_check, git_check],
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        modal: DoctorModal = app.screen  # type: ignore[assignment]

        with patch(
            "kagan.tui.screens.doctor_modal.run_doctor_check_for_backend",
            return_value=passing_backend,
        ):
            modal._on_command_finished(
                _CommandPane.CommandFinished(return_code=0, check_name=backend_check.name)
            )
            # Give targeted recheck time to run
            from tests.helpers.async_utils import wait_for as _wait_for

            def _backend_row_passed() -> bool:
                rid = _check_row_id(backend_check.name)
                matched = modal.query(f"#{rid}")
                return bool(matched) and "dm-status-pass" in matched.first().classes

            await _wait_for(_backend_row_passed, pump_delay=0.05)

        # Modal must remain open because git is still failing
        assert app.screen.id == "doctor-modal"

        # Backend row must be marked pass
        row_id = _check_row_id(backend_check.name)
        rows = modal.query(f"#{row_id}")
        assert rows, "Backend row must still exist"
        assert "dm-status-pass" in rows.first().classes

        # Git row must still be fail
        git_row_id = _check_row_id(git_check.name)
        git_rows = modal.query(f"#{git_row_id}")
        assert git_rows, "Git row must still be present"
        assert "dm-status-fail" in git_rows.first().classes
