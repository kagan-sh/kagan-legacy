from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button

from kagan.sdk import CoreFailureError
from kagan.tui.app import KaganApp
from kagan.tui.ui.screens.startup_error import StartupErrorScreen
from tests.helpers.wait import wait_until


class _StartupErrorHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield Container()


class _KaganStartupHarness(KaganApp):
    CSS_PATH = str(
        Path(__file__).resolve().parents[3] / "src" / "kagan" / "tui" / "styles" / "kagan.tcss"
    )

    async def on_mount(self) -> None:
        return None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            CoreFailureError(
                "Client build hash 'old' does not match core build hash 'new'.",
                code="CLIENT_OUTDATED",
            ),
            True,
        ),
        (
            RuntimeError("Client build hash 'old' does not match core build hash 'new'."),
            True,
        ),
        (RuntimeError("Database is locked"), False),
    ],
)
def test_runtime_mismatch_detection_helper(error: BaseException, expected: bool) -> None:
    assert KaganApp._is_runtime_mismatch_error(error) is expected


@pytest.mark.asyncio
async def test_startup_self_heal_runs_once_for_runtime_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = KaganApp(db_path=":memory:")

    initialize_calls = 0
    self_heal_calls = 0
    startup_errors: list[str] = []

    async def _fail_initialize() -> None:
        nonlocal initialize_calls
        initialize_calls += 1
        raise CoreFailureError(
            "Client build hash 'old' does not match core build hash 'new'.",
            code="CLIENT_OUTDATED",
        )

    async def _fake_self_heal(*, error: BaseException) -> None:
        nonlocal self_heal_calls
        self_heal_calls += 1
        app._startup_self_heal_attempted = True
        assert isinstance(error, BaseException)

    async def _capture_startup_error(error: BaseException) -> None:
        startup_errors.append(str(error))

    monkeypatch.setattr(app, "_initialize_app_inner", _fail_initialize)
    monkeypatch.setattr(app, "_attempt_runtime_self_heal", _fake_self_heal)
    monkeypatch.setattr(app, "_present_startup_error_screen", _capture_startup_error)

    await app._initialize_app()

    assert initialize_calls == 2
    assert self_heal_calls == 1
    assert len(startup_errors) == 1


@pytest.mark.asyncio
async def test_startup_self_heal_is_not_retried_after_first_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = KaganApp(db_path=":memory:")

    initialize_calls = 0
    self_heal_calls = 0
    startup_errors: list[str] = []

    async def _fail_initialize() -> None:
        nonlocal initialize_calls
        initialize_calls += 1
        raise CoreFailureError(
            "Client build hash 'old' does not match core build hash 'new'.",
            code="CLIENT_OUTDATED",
        )

    async def _fake_self_heal(*, error: BaseException) -> None:
        nonlocal self_heal_calls
        self_heal_calls += 1
        app._startup_self_heal_attempted = True
        assert isinstance(error, BaseException)

    async def _capture_startup_error(error: BaseException) -> None:
        startup_errors.append(str(error))

    monkeypatch.setattr(app, "_initialize_app_inner", _fail_initialize)
    monkeypatch.setattr(app, "_attempt_runtime_self_heal", _fake_self_heal)
    monkeypatch.setattr(app, "_present_startup_error_screen", _capture_startup_error)

    await app._initialize_app()
    await app._initialize_app()

    assert initialize_calls == 3
    assert self_heal_calls == 1
    assert len(startup_errors) == 2


@pytest.mark.asyncio
async def test_startup_error_screen_triggers_retry_callbacks() -> None:
    app = _StartupErrorHarness()
    actions: list[str] = []

    async def _restart_callback() -> None:
        actions.append("restart")

    screen = StartupErrorScreen(
        error_message="Client build hash mismatch",
        on_retry=lambda: actions.append("retry"),
        on_restart_core_retry=_restart_callback,
        on_quit=lambda: actions.append("quit"),
    )

    async with app.run_test(size=(120, 30)) as pilot:
        app.push_screen(screen)
        await pilot.pause()

        await pilot.press("r")
        await wait_until(
            lambda: "retry" in actions,
            timeout=2.0,
            description="retry callback",
        )

        app.screen.query_one("#startup-error-restart", Button).press()
        await wait_until(
            lambda: "restart" in actions,
            timeout=2.0,
            description="restart callback",
        )

        await pilot.press("q")
        await wait_until(
            lambda: "quit" in actions,
            timeout=2.0,
            description="quit callback",
        )


@pytest.mark.asyncio
async def test_app_startup_error_screen_wires_callbacks_to_kagan_app_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _KaganStartupHarness(db_path=":memory:")
    actions: list[str] = []

    async def _retry_callback() -> None:
        actions.append("retry")

    async def _restart_callback() -> None:
        actions.append("restart")

    def _quit_callback() -> None:
        actions.append("quit")

    monkeypatch.setattr(app, "_retry_startup_from_error_screen", _retry_callback)
    monkeypatch.setattr(app, "_restart_core_and_retry_from_error_screen", _restart_callback)
    monkeypatch.setattr(app, "_quit_from_startup_error_screen", _quit_callback)

    async with app.run_test(size=(120, 30)) as pilot:
        await app._present_startup_error_screen(RuntimeError("Startup exploded"))
        await wait_until(
            lambda: isinstance(app.screen, StartupErrorScreen),
            timeout=2.0,
            description="startup error screen",
        )

        await pilot.press("r")
        await wait_until(
            lambda: "retry" in actions,
            timeout=2.0,
            description="app retry callback",
        )

        app.screen.query_one("#startup-error-restart", Button).press()
        await wait_until(
            lambda: "restart" in actions,
            timeout=2.0,
            description="app restart callback",
        )

        await pilot.press("q")
        await wait_until(
            lambda: "quit" in actions,
            timeout=2.0,
            description="app quit callback",
        )
