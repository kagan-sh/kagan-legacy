"""DoctorModal — in-TUI preflight check screen.

Shown when run_doctor_checks() returns at least one FAIL-status check.
Non-dismissible via Escape until the user has focused at least one check
row (Tab or click). "Skip anyway" is always present but only becomes active
after that focus requirement is met.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import shlex
import subprocess
import time
from typing import TYPE_CHECKING, cast

from loguru import logger
from textual import on, work
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Footer, Label, Static

from kagan.cli.doctor import DoctorCheck, run_doctor_check_for_backend, run_doctor_checks
from kagan.core._analytics import emit_telemetry
from kagan.core._settings import set_settings
from kagan.core.enums import SessionEventType
from kagan.tui.keybindings import CHECK_ROW_BINDINGS, DOCTOR_MODAL_BINDINGS

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.app import KaganApp


# ── Check-row widget ─────────────────────────────────────────────────────────


def _check_row_id(check_name: str) -> str:
    """Return a valid Textual widget id for a check name.

    Textual requires ids that contain only letters, numbers, underscores, and
    hyphens, and must not begin with a digit. Non-conforming characters (colons,
    parentheses, dots, etc.) are replaced with hyphens, and leading hyphens are
    stripped.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", check_name)
    sanitized = sanitized.strip("-")
    return f"check-row-{sanitized}"


class _CheckRow(Widget):
    """One row in the doctor checklist."""

    BINDINGS = CHECK_ROW_BINDINGS

    DEFAULT_CSS = ""

    def __init__(self, check: DoctorCheck) -> None:
        super().__init__(
            id=_check_row_id(check.name),
            classes=f"dm-check-row dm-status-{check.status}",
        )
        self._check = check
        self.can_focus = True

    @property
    def check(self) -> DoctorCheck:
        return self._check

    def compose(self) -> ComposeResult:
        status_icon = {"pass": "✓", "warn": "!", "fail": "✗"}.get(self._check.status, "?")
        with Horizontal(classes="dm-check-header"):
            yield Static(status_icon, classes="dm-status-icon")
            yield Static(self._check.name, classes="dm-check-name")
            yield Static(self._check.category, classes="dm-check-category")
        yield Static(self._check.message, classes="dm-check-message")
        if self._check.fix_hint:
            yield Static(self._check.fix_hint, classes="dm-fix-hint")
            btn_id = f"run-fix-{re.sub(r'[^a-zA-Z0-9_-]', '-', self._check.name).strip('-')}"
            yield Button("Run this now", id=btn_id, classes="dm-run-fix-btn")

    def mark_passed(self) -> None:
        """Update row to green-pass state without rebuilding the DOM."""
        self.remove_class("dm-status-fail", "dm-status-warn")
        self.add_class("dm-status-pass")
        status_widget = self.query_one(".dm-status-icon", Static)
        status_widget.update("✓")

    def action_run_fix(self) -> None:
        btn_id = f"run-fix-{re.sub(r'[^a-zA-Z0-9_-]', '-', self._check.name).strip('-')}"
        buttons = self.query(f"#{btn_id}")
        if buttons:
            self.app.post_message(_RunFixRequested(self._check))


class _RunFixRequested(Message):
    """Posted when the user triggers 'Run this now' for a check."""

    def __init__(self, check: DoctorCheck) -> None:
        super().__init__()
        self.check = check


# ── Command runner pane ───────────────────────────────────────────────────────


class _CommandPane(Widget):
    """Inline terminal-like pane that runs a fix command and captures output."""

    class CommandFinished(Message):
        def __init__(self, return_code: int, check_name: str) -> None:
            super().__init__()
            self.return_code = return_code
            self.check_name = check_name

    def __init__(self, check: DoctorCheck) -> None:
        super().__init__(id="dm-command-pane", classes="dm-command-pane")
        self._check = check
        self._output_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(f"Running: {self._check.fix_hint}", classes="dm-cmd-header")
        yield Static("", id="dm-cmd-output", classes="dm-cmd-output")
        with Horizontal(classes="dm-cmd-actions"):
            yield Button("Close", id="dm-cmd-close", classes="dm-cmd-close-btn")

    def on_mount(self) -> None:
        self._run_command()

    @work(thread=True)
    def _run_command(self) -> None:
        hint = self._check.fix_hint
        if not hint:
            return
        try:
            cmd_parts = shlex.split(hint)
        except ValueError:
            cmd_parts = hint.split()
        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout or result.stderr or "(no output)"
            return_code = result.returncode
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            output = f"Error: {exc}"
            return_code = 1

        # Update UI from main thread
        self.app.call_from_thread(self._show_result, output, return_code)

    def _show_result(self, output: str, return_code: int) -> None:
        out_widget = self.query_one("#dm-cmd-output", Static)
        lines = output.splitlines()[:40]
        out_widget.update("\n".join(lines))
        self.post_message(self.CommandFinished(return_code, self._check.name))


# ── DoctorModal ───────────────────────────────────────────────────────────────


def _extract_backend_name(check_name: str) -> str | None:
    """Extract backend name from a DoctorCheck name if it is a backend check.

    Handles formats produced by _collapse_backend_checks:
    - "agent backends" (summary row — no single backend name)
    - "backend: claude-code (default)"
    - "backend: codex"
    - "agent backend: claude-code (default)"  (legacy _map_preflight_check path)

    Returns the bare backend name (e.g. "claude-code") or None for non-backend
    checks or the summary row.
    """
    # Summary row — no single backend to promote
    if check_name == "agent backends":
        return None

    # "backend: <name> (default)" or "backend: <name>"
    m = re.match(r"^(?:agent )?backend:\s*(.+?)(?:\s+\(default\))?$", check_name)
    if m:
        return m.group(1).strip()

    return None


class DoctorModal(ModalScreen[bool]):
    """Full-screen modal for zero-ready (FAIL) preflight state.

    Non-dismissible via Escape until the user has focused at least one
    check row. "Skip anyway" is always present.
    """

    BINDINGS = DOCTOR_MODAL_BINDINGS

    CSS_PATH = "doctor_modal.tcss"

    def __init__(self, checks: list[DoctorCheck]) -> None:
        super().__init__(id="doctor-modal")
        self._checks = checks
        # True once a _CheckRow has received focus (includes auto-focus on mount).
        # Skip becomes enabled at this point; Escape is always blocked.
        self._row_focused_once = False
        self._command_pane_active = False
        # Track when a fix was triggered (check_name → monotonic start time)
        self._install_started_at: dict[str, float] = {}

    @property
    def kagan_app(self) -> KaganApp:
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        fail_count = sum(1 for c in self._checks if c.status == "fail")
        warn_count = sum(1 for c in self._checks if c.status == "warn")

        summary_parts: list[str] = []
        if fail_count:
            summary_parts.append(f"{fail_count} blocking issue(s)")
        if warn_count:
            summary_parts.append(f"{warn_count} warning(s)")
        summary = " · ".join(summary_parts) if summary_parts else "checks complete"

        with Vertical(id="dm-container"):
            with Vertical(id="dm-header"):
                yield Label("Kagan Doctor", id="dm-title")
                yield Label(
                    "Resolve blocking issues before using Kagan.",
                    id="dm-subtitle",
                )
                yield Label(summary, id="dm-summary")
            with VerticalScroll(id="dm-checklist"):
                for check in self._checks:
                    if check.status in {"fail", "warn"}:
                        yield _CheckRow(check)
            with Horizontal(id="dm-actions"):
                yield Button("Re-check all", id="dm-recheck-btn", classes="dm-btn-recheck")
                yield Button(
                    "Skip anyway",
                    id="dm-skip-btn",
                    classes="dm-btn-skip",
                    disabled=True,
                )
            yield Static(
                "[dim]Tab[/] focus rows   [dim]Skip anyway[/] to continue",
                id="dm-hint",
            )
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        # A11y: focus lands on first failing row for screen readers.
        # This also triggers on_descendant_focus, enabling the skip button.
        rows = self.query(_CheckRow)
        if rows:
            rows.first().focus()

    def on_descendant_focus(self, event: object) -> None:
        """Enable skip button when any check row receives focus."""
        focused = self.app.focused
        if isinstance(focused, _CheckRow) and not self._row_focused_once:
            self._row_focused_once = True
            self._update_skip_button()

    def _update_skip_button(self) -> None:
        skip_btn = self.query_one("#dm-skip-btn", Button)
        skip_btn.disabled = not self._row_focused_once

    def on_key(self, event: object) -> None:
        """Escape is always blocked on DoctorModal; use Skip anyway button."""
        from textual import events

        if not isinstance(event, events.Key):
            return
        if event.key == "escape":
            # Always block — non-dismissible via Escape
            event.prevent_default()
            event.stop()

    @on(Button.Pressed, "#dm-skip-btn")
    def _on_skip(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#dm-recheck-btn")
    def _on_recheck(self) -> None:
        self._run_recheck()

    @on(Button.Pressed, ".dm-run-fix-btn")
    def _on_run_fix_pressed(self, event: Button.Pressed) -> None:
        # Find the check for this button by walking up to _CheckRow
        target = event.button
        row = target.ancestors_with_self
        check_row: _CheckRow | None = None
        for ancestor in row:
            if isinstance(ancestor, _CheckRow):
                check_row = ancestor
                break
        if check_row is None:
            return
        self._show_command_pane(check_row.check)

    @on(_RunFixRequested)
    def _on_run_fix_requested(self, event: _RunFixRequested) -> None:
        self._show_command_pane(event.check)

    def _show_command_pane(self, check: DoctorCheck) -> None:
        if self._command_pane_active:
            return
        self._command_pane_active = True
        self._install_started_at[check.name] = time.monotonic()
        pane = _CommandPane(check)
        checklist = self.query_one("#dm-checklist", VerticalScroll)
        checklist.display = False
        actions = self.query_one("#dm-actions", Horizontal)
        actions.display = False
        container = self.query_one("#dm-container", Vertical)
        self.run_worker(self._mount_command_pane(container, pane), exit_on_error=False)

    async def _mount_command_pane(self, container: Vertical, pane: _CommandPane) -> None:
        await container.mount(pane, before=self.query_one("#dm-actions", Horizontal))

    @on(_CommandPane.CommandFinished)
    def _on_command_finished(self, event: _CommandPane.CommandFinished) -> None:
        self._command_pane_active = False
        return_code = event.return_code
        check_name = event.check_name

        # Re-show main content
        checklist = self.query_one("#dm-checklist", VerticalScroll)
        checklist.display = True
        actions = self.query_one("#dm-actions", Horizontal)
        actions.display = True

        # Remove pane
        panes = self.query(_CommandPane)
        if panes:
            panes.first().remove()

        if return_code == 0:
            # Optimistically mark the row green; targeted recheck will confirm
            row_id = _check_row_id(check_name)
            rows = self.query(f"#{row_id}")
            if rows:
                rows.first().mark_passed()
            elapsed = time.monotonic() - self._install_started_at.pop(check_name, time.monotonic())
            self._run_targeted_recheck(check_name, elapsed)

    @on(Button.Pressed, "#dm-cmd-close")
    def _on_cmd_close(self) -> None:
        self._command_pane_active = False
        panes = self.query(_CommandPane)
        if panes:
            panes.first().remove()
        checklist = self.query_one("#dm-checklist", VerticalScroll)
        checklist.display = True
        actions = self.query_one("#dm-actions", Horizontal)
        actions.display = True

    @work(exclusive=False)
    async def _run_recheck(self) -> None:
        recheck_btn = self.query_one("#dm-recheck-btn", Button)
        recheck_btn.disabled = True
        recheck_btn.label = "Checking..."

        checks = await asyncio.to_thread(run_doctor_checks)
        self._checks = checks

        # Update all visible rows
        for check in checks:
            if check.status in {"fail", "warn"}:
                row_id = _check_row_id(check.name)
                rows = self.query(f"#{row_id}")
                if rows and check.status == "pass":
                    rows.first().mark_passed()

        # Update summary
        fail_count = sum(1 for c in checks if c.status == "fail")
        warn_count = sum(1 for c in checks if c.status == "warn")
        summary_parts: list[str] = []
        if fail_count:
            summary_parts.append(f"{fail_count} blocking issue(s)")
        if warn_count:
            summary_parts.append(f"{warn_count} warning(s)")
        summary = " · ".join(summary_parts) if summary_parts else "All checks passed"
        self.query_one("#dm-summary", Label).update(summary)

        recheck_btn.disabled = False
        recheck_btn.label = "Re-check all"

        if not fail_count:
            self.app.notify("All blocking issues resolved!", severity="information")

    def _run_targeted_recheck(self, check_name: str, elapsed: float = 0.0) -> None:
        self.run_worker(
            self._targeted_recheck(check_name, elapsed),
            exit_on_error=False,
        )

    async def _targeted_recheck(self, check_name: str, elapsed: float) -> None:
        """Re-verify a check after install.

        For backend checks: uses run_doctor_check_for_backend() — does NOT
        invoke environment, plugin, or IDE checks (AC1 requirement).
        For non-backend checks: uses run_doctor_checks() to refresh state.
        """
        backend_name = _extract_backend_name(check_name)

        if backend_name is not None:
            # Backend check — use targeted single-backend helper (no full survey).
            target = await asyncio.to_thread(run_doctor_check_for_backend, backend_name)
            if target is None:
                return

            if target.status == "pass":
                row_id = _check_row_id(check_name)
                rows = self.query(f"#{row_id}")
                if rows:
                    rows.first().mark_passed()
                await self._auto_promote_backend(backend_name, elapsed)

            # Patch self._checks in-place — only this one check is re-verified.
            updated_checks = [target if c.name == check_name else c for c in self._checks]
        else:
            # Non-backend check — refresh all checks via full survey.
            all_checks = await asyncio.to_thread(run_doctor_checks)
            target = next((c for c in all_checks if c.name == check_name), None)
            if target is not None and target.status == "pass":
                row_id = _check_row_id(check_name)
                rows = self.query(f"#{row_id}")
                if rows:
                    rows.first().mark_passed()
            updated_checks = all_checks

        self._checks = updated_checks
        self._refresh_summary(updated_checks)

        # Auto-dismiss if no FAILs remain
        fail_count = sum(1 for c in updated_checks if c.status == "fail")
        if fail_count == 0:
            self.app.notify("All blocking issues resolved!", severity="information")
            self.dismiss(True)

    async def _auto_promote_backend(self, backend_name: str, elapsed: float) -> None:
        """Write default_agent_backend to Settings and emit BACKEND_AUTO_PROMOTED."""
        try:
            from kagan.core import KaganCore

            app = self.kagan_app
            if not isinstance(app.core, KaganCore):
                return

            engine = app.core.engine
            await set_settings(engine, {"default_agent_backend": backend_name})
            logger.info("DoctorModal auto-promoted default backend to '{}'", backend_name)

            await emit_telemetry(
                engine,
                SessionEventType.BACKEND_AUTO_PROMOTED.value,
                {
                    "backend": backend_name,
                    "seconds_since_install_clicked": round(elapsed, 3),
                },
            )
            logger.debug(
                "Emitted BACKEND_AUTO_PROMOTED telemetry: backend={} elapsed={:.1f}s",
                backend_name,
                elapsed,
            )
        except Exception:
            logger.opt(exception=True).warning(
                "DoctorModal failed to auto-promote backend '{}'; continuing", backend_name
            )

    def _refresh_summary(self, checks: list[DoctorCheck]) -> None:
        """Update the summary label to reflect current check state."""
        fail_count = sum(1 for c in checks if c.status == "fail")
        warn_count = sum(1 for c in checks if c.status == "warn")
        summary_parts: list[str] = []
        if fail_count:
            summary_parts.append(f"{fail_count} blocking issue(s)")
        if warn_count:
            summary_parts.append(f"{warn_count} warning(s)")
        summary = " · ".join(summary_parts) if summary_parts else "All checks passed"
        with contextlib.suppress(Exception):
            self.query_one("#dm-summary", Label).update(summary)


# ── Public helper ─────────────────────────────────────────────────────────────


async def emit_doctor_warned_telemetry_async(
    core: object,
    *,
    fail_count: int,
    warn_count: int,
) -> None:
    """Emit DOCTOR_WARNED telemetry from within the TUI (best-effort).

    Args:
        core: KaganCore instance (uses its engine property for DB access).
        fail_count: Number of FAIL-status checks.
        warn_count: Number of WARN-status checks.
    """
    if fail_count == 0 and warn_count == 0:
        return
    try:
        from kagan.core import KaganCore

        if not isinstance(core, KaganCore):
            return
        await emit_telemetry(
            core.engine,
            SessionEventType.DOCTOR_WARNED.value,
            {
                "fail_count": fail_count,
                "warn_count": warn_count,
            },
        )
        logger.debug(
            "TUI emitted doctor_warned telemetry: warn={} fail={}",
            warn_count,
            fail_count,
        )
    except Exception:
        logger.opt(exception=True).debug("TUI failed to emit doctor_warned telemetry")
