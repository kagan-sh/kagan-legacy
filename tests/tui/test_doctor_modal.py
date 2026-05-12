"""Smoke tests for DoctorModal — unique-edge cases only.

Startup-routing cases (WARN-only, all-pass, no-checks) are covered by
Flow K (tests/e2e_tui/test_k_cold_start_tui.py).  Only the edges that
cannot be exercised at the flow level are kept here.
"""

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


# ── Unique edge: skip disabled when no backend is available ───────────────────


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


# ── Unique edge: fix_hint content rendered ────────────────────────────────────


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
        assert "dm-fix-hint" in hint_widget.classes


# ── Unique edge: recheck button present ───────────────────────────────────────


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


# ── Unique edge: auto-promote on install success (Wave 3c) ────────────────────


async def test_install_rc_nonzero_no_state_change(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: rc != 0 → no Settings write, no auto-dismiss, row stays fail."""
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

        monkeypatch.setattr(
            "kagan.tui.screens.doctor_modal.run_doctor_checks",
            lambda: [backend_check],
        )
        from kagan.tui.screens.doctor_modal import _CommandPane

        modal._on_command_finished(
            _CommandPane.CommandFinished(return_code=1, check_name=backend_check.name)
        )
        await pilot.pause()

        row_id = _check_row_id(backend_check.name)
        rows = modal.query(f"#{row_id}")
        assert rows, "Row should still be present"
        assert "dm-status-pass" not in rows.first().classes

        settings = await app.core.settings.get()
        promoted = settings.get("default_agent_backend")
        assert promoted != "test-backend", f"Settings must not be written on rc=1, got {promoted}"

        assert app.screen.id == "doctor-modal"


async def test_install_rc_zero_promotes_settings_and_dismisses_modal(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: rc=0 on a backend check → Settings written, modal auto-dismissed."""
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

        monkeypatch.setattr(
            "kagan.tui.screens.doctor_modal.run_doctor_check_for_backend",
            lambda _name: passing_check,
        )
        modal._on_command_finished(
            _CommandPane.CommandFinished(return_code=0, check_name=backend_check.name)
        )
        await _wait_for_setup_flow(app)

        settings = await app.core.settings.get()
        assert settings.get("default_agent_backend") == "my-agent", (
            f"Expected 'my-agent' in settings, got: {settings}"
        )


async def test_install_rc_zero_non_backend_check_no_settings_write(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3 edge: rc=0 on a non-backend check (e.g. git) must NOT write default_agent_backend."""
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

        monkeypatch.setattr(
            "kagan.tui.screens.doctor_modal.run_doctor_checks",
            lambda: [passing_git],
        )
        modal._on_command_finished(
            _CommandPane.CommandFinished(return_code=0, check_name=git_check.name)
        )
        await _wait_for_setup_flow(app)

        settings = await app.core.settings.get()
        assert "default_agent_backend" not in settings
