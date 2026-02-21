from __future__ import annotations

from textual.css.query import NoMatches

from kagan.tui.ui.screens.setup_flow import OnboardingScreen


class _ButtonStub:
    def __init__(self) -> None:
        self.focus_called = False
        self.disabled = False

    def focus(self) -> None:
        self.focus_called = True


class _HintStub:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str]] = []

    def show_hints(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows


def test_onboarding_mount_focuses_continue_button_and_renders_hints(
    monkeypatch,
) -> None:
    screen = OnboardingScreen()
    button = _ButtonStub()
    hint = _HintStub()

    def _query_one(selector: str, _type: object = None) -> object:
        if selector == "#btn-continue":
            return button
        if selector == "#onboarding-hint":
            return hint
        raise NoMatches(selector)

    monkeypatch.setattr(screen, "query_one", _query_one)
    monkeypatch.setattr(screen, "call_after_refresh", lambda callback: callback())

    screen.on_mount()

    assert button.focus_called is True
    assert ("Tab", "next") in hint.rows
    assert ("Shift+Tab", "previous") in hint.rows
    assert ("Enter", "continue") in hint.rows
    assert ("Esc", "quit") in hint.rows


def test_onboarding_continue_action_is_idempotent_while_saving(monkeypatch) -> None:
    screen = OnboardingScreen()
    button = _ButtonStub()
    run_calls: list[tuple[str | None, bool, bool, object]] = []

    def _query_one(selector: str, _type: object = None) -> object:
        if selector == "#btn-continue":
            return button
        raise NoMatches(selector)

    def _run_worker(
        work: object,
        *,
        group: str | None = None,
        exclusive: bool = False,
        exit_on_error: bool = True,
    ) -> None:
        run_calls.append((group, exclusive, exit_on_error, work))

    monkeypatch.setattr(screen, "query_one", _query_one)
    monkeypatch.setattr(screen, "run_worker", _run_worker)

    screen.action_continue_setup()
    screen.action_continue_setup()

    assert screen._is_saving is True
    assert button.disabled is True
    assert len(run_calls) == 1
    assert run_calls[0][0] == "onboarding-save"
    assert run_calls[0][1] is True
    assert run_calls[0][2] is False
    coroutine = run_calls[0][3]
    close = getattr(coroutine, "close", None)
    if callable(close):
        close()


def test_onboarding_focus_actions_use_shared_focus_selector(monkeypatch) -> None:
    screen = OnboardingScreen()
    seen_next: list[str] = []
    seen_prev: list[str] = []

    monkeypatch.setattr(screen, "focus_next", lambda selector: seen_next.append(selector))
    monkeypatch.setattr(screen, "focus_previous", lambda selector: seen_prev.append(selector))

    screen.action_focus_next()
    screen.action_focus_previous()

    expected_selector = "#agent-select, #auto-review-switch, #btn-continue"
    assert seen_next == [expected_selector]
    assert seen_prev == [expected_selector]
