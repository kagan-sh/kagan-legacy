import pytest

from kagan.cli.chat.repl import (
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
    toolbar = _bottom_toolbar()
    # FormattedText — extract text content
    text = "".join(fragment[1] for fragment in toolbar)
    assert "tip:" in text  # rotating tip line
    assert "session:" in text  # session label on tip line


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
