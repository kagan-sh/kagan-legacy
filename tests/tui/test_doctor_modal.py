"""Smoke tests for DoctorModal and WARN-only startup routing."""

from __future__ import annotations

import pytest
from tests.helpers.async_utils import wait_for

from kagan.cli.doctor import DoctorCheck

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


def _make_check(name: str, status: str, fix_hint: str = "echo fix") -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status=status,
        message=f"{name} {status} message",
        fix_hint=fix_hint if status != "pass" else "",
        verify_hint=f"{name} --version",
        category="core",
    )


async def _wait_for_setup_flow(app) -> None:
    from textual.widgets._select import SelectOverlay

    await wait_for(
        lambda: (
            app.screen.id == "setup-flow"
            and bool(app.screen.query("#setup-project-list"))
            and len(app.screen.query(SelectOverlay)) >= 2
        ),
        pump_delay=0.05,
    )


# ── DoctorModal: FAIL state ────────────────────────────────────────────────


async def test_doctor_modal_shown_on_fail_checks(tmp_path) -> None:
    """DoctorModal is pushed when a required startup check contains a FAIL."""
    from kagan.tui import KaganApp

    checks = [
        _make_check("git", "fail"),
        _make_check("agent backend", "warn"),
    ]

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"


async def test_doctor_modal_escape_always_blocked(tmp_path) -> None:
    """Escape NEVER dismisses DoctorModal — modal is non-dismissible via keyboard.

    The user must explicitly use 'Skip anyway' button.
    """
    from kagan.tui import KaganApp

    checks = [_make_check("git", "fail")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        # Press Escape multiple times — should always remain on doctor-modal
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "doctor-modal"


async def test_doctor_modal_skip_button_enabled_after_mount_autofocus(tmp_path) -> None:
    """Skip button becomes enabled when backend availability is not blocked."""
    from textual.widgets import Button

    from kagan.tui import KaganApp

    checks = [_make_check("git", "fail")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        # Auto-focus fires on mount → _row_focused_once=True → skip enabled
        skip_btn = app.screen.query_one("#dm-skip-btn", Button)
        assert skip_btn.disabled is False


async def test_doctor_modal_skip_button_disabled_when_no_backend_available(tmp_path) -> None:
    """Skip is blocked when doctor reports no usable agent backend."""
    from textual.widgets import Button

    from kagan.tui import KaganApp

    checks = [
        DoctorCheck(
            name="agent backends",
            status="fail",
            message="No available agent backends found",
            fix_hint="Install Claude Code or another supported backend",
            verify_hint="kagan doctor",
            category="backend",
        )
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        skip_btn = app.screen.query_one("#dm-skip-btn", Button)
        assert skip_btn.disabled is True


async def test_doctor_modal_skip_button_dismisses_modal(tmp_path) -> None:
    """Clicking 'Skip anyway' button dismisses DoctorModal and resumes startup."""
    from textual.widgets import Button

    from kagan.tui import KaganApp

    checks = [_make_check("git", "fail")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        skip_btn = app.screen.query_one("#dm-skip-btn", Button)
        skip_btn.press()
        await _wait_for_setup_flow(app)


async def test_doctor_modal_check_rows_rendered_for_fail_and_warn(tmp_path) -> None:
    """All FAIL and WARN check rows appear; PASS rows are excluded."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import _CheckRow

    checks = [
        _make_check("git", "fail"),
        _make_check("tmux", "warn"),
        _make_check("agent backend", "pass"),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        rows = app.screen.query(_CheckRow)
        assert rows
        assert len(rows) == 2  # git (fail) + tmux (warn), not agent backend (pass)

        row_ids = {r.id for r in rows}
        assert "check-row-git" in row_ids
        assert "check-row-tmux" in row_ids
        assert "check-row-agent-backend" not in row_ids


async def test_doctor_modal_recheck_btn_present(tmp_path) -> None:
    """Re-check all button is rendered in DoctorModal."""
    from textual.widgets import Button

    from kagan.tui import KaganApp

    checks = [_make_check("git", "fail")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        recheck_btn = app.screen.query_one("#dm-recheck-btn", Button)
        assert recheck_btn is not None


async def test_doctor_modal_fix_hint_shown_for_fail_rows(tmp_path) -> None:
    """fix_hint text is rendered as a dm-fix-hint block inside each failing row."""
    from textual.widgets import Static

    from kagan.tui import KaganApp

    hint_text = "brew install git"
    checks = [_make_check("git", "fail", fix_hint=hint_text)]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        hints = app.screen.query(".dm-fix-hint")
        assert hints
        hint_widget = hints.first()
        assert isinstance(hint_widget, Static)
        # The hint content is stored; checking class presence is sufficient for smoke
        assert "dm-fix-hint" in hint_widget.classes


# ── Startup routing: WARN-only / all-pass / no checks ──────────────────────


async def test_warn_only_routes_to_project_picker(tmp_path) -> None:
    """WARN-only checks continue without degraded-performance messaging."""
    from unittest.mock import patch

    from kagan.tui import KaganApp

    checks = [
        _make_check("ide", "warn", fix_hint="Install VS Code"),
        DoctorCheck(
            name="agent backends",
            status="pass",
            message="Default backend 'claude-code' ready - 1/3 backends installed",
            fix_hint="",
            verify_hint="claude --version",
            category="backend",
        ),
        DoctorCheck(
            name="backend: codex",
            status="warn",
            message="codex not found",
            fix_hint="Install codex",
            verify_hint="codex --version",
            category="backend",
        ),
    ]
    notified: list[str] = []
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    original_notify = app.notify

    def _capture_notify(message, *args, **kwargs):
        notified.append(str(message))
        return original_notify(message, *args, **kwargs)

    with patch.object(app, "notify", side_effect=_capture_notify):
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app.screen.id == "setup-flow"

    degraded = [m for m in notified if "degraded" in m.lower() or "performance" in m.lower()]
    assert not degraded


async def test_required_fail_routes_to_doctor_modal_with_error_state(tmp_path) -> None:
    """Required FAIL checks still show the blocking doctor modal."""
    from kagan.tui import KaganApp

    checks = [
        _make_check("git", "fail", fix_hint="Install git"),
        DoctorCheck(
            name="agent backends",
            status="pass",
            message="Default backend 'claude-code' ready",
            fix_hint="",
            verify_hint="claude --version",
            category="backend",
        ),
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"


async def test_all_pass_routes_to_project_picker(tmp_path) -> None:
    """All-pass checks route to the project picker by default."""
    from kagan.tui import KaganApp

    checks = [_make_check("git", "pass", fix_hint="")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert app.screen.id == "setup-flow"


async def test_no_checks_routes_to_project_picker(tmp_path) -> None:
    """When startup_checks is None, startup still begins at the project picker."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "setup-flow"


async def test_startup_project_picker_cannot_escape_to_blank_screen(tmp_path) -> None:
    """The boot picker is mandatory so Escape must not reveal Textual's empty screen."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=[])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "setup-flow"

        await pilot.press("escape")
        await pilot.pause()

        assert app.screen.id == "setup-flow"


# ── Command pane smoke ─────────────────────────────────────────────────────


async def test_run_fix_button_present_for_failing_check_with_hint(tmp_path) -> None:
    """'Run this now' button exists when fix_hint is present on a FAIL row."""

    from kagan.tui import KaganApp

    checks = [_make_check("git", "fail", fix_hint="brew install git")]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        run_fix_btns = app.screen.query(".dm-run-fix-btn")
        assert len(run_fix_btns) >= 1


async def test_no_run_fix_button_when_fix_hint_empty(tmp_path) -> None:
    """'Run this now' button absent when fix_hint is empty."""
    from kagan.tui import KaganApp

    checks = [
        DoctorCheck(
            name="git",
            status="fail",
            message="git not found",
            fix_hint="",
            verify_hint="git --version",
            category="core",
        )
    ]
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=checks)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        run_fix_btns = app.screen.query(".dm-run-fix-btn")
        assert len(run_fix_btns) == 0


# ── Auto-promote on install success (Wave 3c) ──────────────────────────────


async def test_install_rc_nonzero_no_state_change(tmp_path) -> None:
    """AC2: rc != 0 → no Settings write, no auto-dismiss, row stays fail."""
    from unittest.mock import patch

    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import DoctorModal, _check_row_id

    backend_check = DoctorCheck(
        name="backend: test-backend (default)",
        status="fail",
        message="test-backend not found",
        fix_hint="echo install",
        verify_hint="which test-backend",
        category="backend",
    )
    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=[backend_check])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        modal: DoctorModal = app.screen  # type: ignore[assignment]

        # Simulate CommandPane finishing with rc=1
        with patch(
            "kagan.tui.screens.doctor_modal.run_doctor_checks",
            return_value=[backend_check],
        ):
            from kagan.tui.screens.doctor_modal import _CommandPane

            modal._on_command_finished(
                _CommandPane.CommandFinished(return_code=1, check_name=backend_check.name)
            )
            await pilot.pause()

        # Row should still be fail-class (not promoted)
        row_id = _check_row_id(backend_check.name)
        rows = modal.query(f"#{row_id}")
        assert rows, "Row should still be present"
        assert "dm-status-pass" not in rows.first().classes

        # Settings must not have been written
        settings = await app.core.settings.get()
        promoted = settings.get("default_agent_backend")
        assert promoted != "test-backend", f"Settings must not be written on rc=1, got {promoted}"

        # Modal must still be showing
        assert app.screen.id == "doctor-modal"


async def test_install_rc_zero_promotes_settings_and_dismisses_modal(tmp_path) -> None:
    """AC3: rc=0 on a backend check → Settings written, modal auto-dismissed."""
    from unittest.mock import patch

    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import DoctorModal, _CommandPane

    backend_check = DoctorCheck(
        name="backend: my-agent (default)",
        status="fail",
        message="my-agent not found",
        fix_hint="echo install",
        verify_hint="which my-agent",
        category="backend",
    )
    # After recheck, pretend the backend now passes
    passing_check = DoctorCheck(
        name="backend: my-agent (default)",
        status="pass",
        message="my-agent found",
        fix_hint="",
        verify_hint="which my-agent",
        category="backend",
    )

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=[backend_check])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        modal: DoctorModal = app.screen  # type: ignore[assignment]

        # Simulate successful install completion — targeted recheck sees PASS
        with patch(
            "kagan.tui.screens.doctor_modal.run_doctor_check_for_backend",
            return_value=passing_check,
        ):
            modal._on_command_finished(
                _CommandPane.CommandFinished(return_code=0, check_name=backend_check.name)
            )
            # Pump until modal auto-dismisses (all FAILs resolved → dismiss(True))
            await _wait_for_setup_flow(app)

        # Observable: settings must contain the promoted backend (written before dismiss)
        settings = await app.core.settings.get()
        assert settings.get("default_agent_backend") == "my-agent", (
            f"Expected 'my-agent' in settings, got: {settings}"
        )

        # Observable: modal dismissed → app navigated to setup-flow (asserted by
        # _wait_for_setup_flow above); if we reach here the modal is gone.


async def test_install_rc_zero_non_backend_check_no_settings_write(tmp_path) -> None:
    """AC3 edge: rc=0 on a non-backend check (e.g. git) must NOT write default_agent_backend."""
    from unittest.mock import patch

    from kagan.tui import KaganApp
    from kagan.tui.screens.doctor_modal import DoctorModal, _CommandPane

    git_check = DoctorCheck(
        name="git",
        status="fail",
        message="git not found",
        fix_hint="brew install git",
        verify_hint="git --version",
        category="core",
    )
    passing_git = DoctorCheck(
        name="git",
        status="pass",
        message="git found",
        fix_hint="",
        verify_hint="git --version",
        category="core",
    )

    app = KaganApp(db_path=tmp_path / "kagan.db", startup_checks=[git_check])
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "doctor-modal"

        modal: DoctorModal = app.screen  # type: ignore[assignment]

        with patch(
            "kagan.tui.screens.doctor_modal.run_doctor_checks",
            return_value=[passing_git],
        ):
            modal._on_command_finished(
                _CommandPane.CommandFinished(return_code=0, check_name=git_check.name)
            )
            await _wait_for_setup_flow(app)

        # Settings must NOT have default_agent_backend written by the git fix
        settings = await app.core.settings.get()
        assert "default_agent_backend" not in settings
