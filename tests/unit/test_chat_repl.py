import pytest
from prompt_toolkit.formatted_text import FormattedText

from kagan.cli.chat.repl import (
    _TOOLBAR_STATE,
    SearchPickerOption,
    _bottom_toolbar,
    _build_prompt_style_rules,
    _cancel_search_picker,
    _history_cycle_target,
    _picker_move_completion,
    _picker_submit_value,
    _resolve_search_picker_value,
)

pytestmark = [pytest.mark.unit]


def _reset_toolbar_state(**kwargs: object) -> None:
    _TOOLBAR_STATE.is_streaming = False
    _TOOLBAR_STATE.agent_backend = ""
    _TOOLBAR_STATE.project_name = ""
    _TOOLBAR_STATE.turn_count = 0
    _TOOLBAR_STATE.queued_count = 0
    _TOOLBAR_STATE.context_pct = None
    _TOOLBAR_STATE.token_used_k = None
    _TOOLBAR_STATE.plan_mode = False
    _TOOLBAR_STATE.pending_approvals = 0
    _TOOLBAR_STATE.current_tool = ""
    _TOOLBAR_STATE.session_label = "orchestrator"
    _TOOLBAR_STATE.workspace_label = ""
    for key, value in kwargs.items():
        setattr(_TOOLBAR_STATE, key, value)


def test_history_cycle_target_returns_none_when_no_history_entries() -> None:
    assert _history_cycle_target(current_index=0, working_line_count=1, direction="up") is None
    assert _history_cycle_target(current_index=0, working_line_count=1, direction="down") is None


def test_history_cycle_target_wraps_up_from_oldest_to_latest() -> None:
    assert _history_cycle_target(current_index=0, working_line_count=4, direction="up") == 2


def test_history_cycle_target_wraps_down_from_latest_to_oldest() -> None:
    assert _history_cycle_target(current_index=2, working_line_count=4, direction="down") == 0


def test_history_cycle_target_from_draft_goes_to_edge_for_direction() -> None:
    assert _history_cycle_target(current_index=3, working_line_count=4, direction="up") == 2
    assert _history_cycle_target(current_index=3, working_line_count=4, direction="down") == 0


def test_bottom_toolbar_renders_status_and_rotating_tip() -> None:
    _reset_toolbar_state(session_label="orchestrator")
    toolbar = _bottom_toolbar()
    # FormattedText — extract text content
    text = "".join(fragment[1] for fragment in toolbar)
    assert "tip:" in text  # rotating tip line
    assert "session:" in text  # session label on tip line


def test_bottom_toolbar_idle_is_non_empty_and_contains_rule_status_tip() -> None:
    """_bottom_toolbar() with is_streaming=False must render a non-empty toolbar.

    This is the regression guard for the always-on toolbar bug: the toolbar
    must be visible even when no agent is streaming (i.e. at the idle prompt).
    """
    _reset_toolbar_state(
        is_streaming=False,
        session_label="smoke-session",
        workspace_label="~/projects/test",
    )
    toolbar = _bottom_toolbar()
    assert isinstance(toolbar, FormattedText)
    assert len(toolbar) > 0, "toolbar must not be empty at idle"
    text = "".join(fragment[1] for fragment in toolbar)
    # Must include rule separator, status (cwd), tip, and session label
    assert "─" in text, "toolbar must include a rule separator"
    assert "~/projects/test" in text, "toolbar must include cwd / workspace label"
    assert "tip:" in text, "toolbar must include the rotating tip"
    assert "session: smoke-session" in text, "toolbar must include the session label"


def test_bottom_toolbar_streaming_returns_empty_defensive_no_op() -> None:
    """When is_streaming=True the prompt-toolkit toolbar yields empty FormattedText.

    prompt_async is not active while the Rich Live streaming loop runs, so
    bottom_toolbar is not invoked during streaming.  The early-exit is kept as
    a defensive no-op to avoid any edge-case double-render if the REPL loop is
    ever restructured.  The full toolbar is rendered again once prompt_async
    resumes after the turn completes.
    """
    _reset_toolbar_state(is_streaming=True)
    toolbar = _bottom_toolbar()
    assert isinstance(toolbar, FormattedText)
    text = "".join(fragment[1] for fragment in toolbar)
    assert text == "", "toolbar must be empty during streaming (defensive no-op)"


def test_prompt_style_rules_truecolor_use_kagan_night_palette(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)

    rules = _build_prompt_style_rules()

    assert rules["bottom-toolbar"].startswith("noreverse bg:#1E1B17")
    assert rules["selected-text"] == "noreverse bg:#3fb58e fg:#0B0A09"
    assert "completion-menu.completion.current" in rules


def test_prompt_style_rules_ansi_fallback_use_terminal_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)

    rules = _build_prompt_style_rules()

    assert rules["bottom-toolbar"] == "noreverse bg:default fg:default"
    assert rules["selected-text"] == "noreverse bg:ansigreen fg:ansiblack"


def test_search_picker_value_resolves_unique_label_and_value_matches() -> None:
    options = [
        SearchPickerOption(value="claude-code", label="1. claude-code"),
        SearchPickerOption(value="opencode", label="2. opencode"),
    ]

    assert _resolve_search_picker_value("opencode", options) == "opencode"
    assert _resolve_search_picker_value("2.", options) == "opencode"
    assert _resolve_search_picker_value("open", options) == "opencode"
    assert _resolve_search_picker_value("ghost", options) is None


def test_cancel_search_picker_exits_with_keyboard_interrupt() -> None:
    class _FakeApp:
        def __init__(self) -> None:
            self.exception: BaseException | None = None

        def exit(self, *, exception: BaseException | None = None, result=None) -> None:
            del result
            self.exception = exception

    class _FakeEvent:
        def __init__(self) -> None:
            self.app = _FakeApp()

    event = _FakeEvent()

    _cancel_search_picker(event)

    assert isinstance(event.app.exception, KeyboardInterrupt)


def test_picker_move_completion_starts_menu_and_cycles_items() -> None:
    class _FakeBuffer:
        def __init__(self) -> None:
            self.complete_state = None
            self.actions: list[str] = []

        def start_completion(self, *, select_first: bool) -> None:
            self.actions.append(f"start:{select_first}")
            self.complete_state = object()

        def complete_previous(self) -> None:
            self.actions.append("previous")

        def complete_next(self) -> None:
            self.actions.append("next")

    class _FakeEvent:
        def __init__(self) -> None:
            self.current_buffer = _FakeBuffer()

    event = _FakeEvent()

    _picker_move_completion(event, "up")
    _picker_move_completion(event, "up")
    _picker_move_completion(event, "down")

    assert event.current_buffer.actions == ["start:False", "previous", "next"]


def test_picker_submit_value_prefers_highlighted_completion() -> None:
    class _Completion:
        def __init__(self, text: str) -> None:
            self.text = text

    class _CompleteState:
        def __init__(self) -> None:
            self.completions = [_Completion("claude-code"), _Completion("opencode")]
            self.current_completion = self.completions[1]

    class _Buffer:
        def __init__(self) -> None:
            self.complete_state = _CompleteState()
            self.text = "open"

    assert _picker_submit_value(_Buffer()) == "opencode"
