import pytest

from kagan.chat.repl import _bottom_toolbar, _build_prompt_style_rules, _history_cycle_target

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


def test_bottom_toolbar_mentions_clear_and_exit_shortcuts() -> None:
    toolbar = _bottom_toolbar()
    # FormattedText — extract text content
    text = "".join(fragment[1] for fragment in toolbar)
    assert "Ctrl-C" in text
    assert "Ctrl-D" in text


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
