import pytest

from kagan.tui.screens.tutorial import TutorialOverlay, TutorialStep

pytestmark = [pytest.mark.unit]


def test_tutorial_steps_are_nonempty() -> None:
    assert len(TutorialOverlay.STEPS) >= 3
    for step in TutorialOverlay.STEPS:
        assert isinstance(step, TutorialStep)
        assert step.title
        assert step.body


def test_process_tutorial_key_advances_through_all_steps() -> None:
    overlay = TutorialOverlay()
    total = len(overlay.STEPS)
    for i in range(total - 1):
        assert overlay.process_tutorial_key("enter") is True
        assert overlay.step_index == i + 1
    assert overlay.process_tutorial_key("enter") is False


def test_process_tutorial_key_right_stays_on_last_step() -> None:
    overlay = TutorialOverlay()
    total = len(overlay.STEPS)
    overlay.step_index = total - 1
    assert overlay.process_tutorial_key("right") is True
    assert overlay.step_index == total - 1


def test_process_tutorial_key_left_does_not_go_below_zero() -> None:
    overlay = TutorialOverlay()
    assert overlay.step_index == 0
    assert overlay.process_tutorial_key("left") is True
    assert overlay.step_index == 0


def test_process_tutorial_key_escape_dismisses() -> None:
    overlay = TutorialOverlay()
    overlay.step_index = 2
    assert overlay.process_tutorial_key("escape") is False


def test_process_tutorial_key_q_dismisses() -> None:
    overlay = TutorialOverlay()
    assert overlay.process_tutorial_key("q") is False


def test_process_tutorial_key_unknown_does_not_dismiss() -> None:
    overlay = TutorialOverlay()
    assert overlay.process_tutorial_key("z") is True
    assert overlay.step_index == 0


def test_validate_clamps_negative() -> None:
    overlay = TutorialOverlay()
    assert overlay.validate_step_index(-5) == 0


def test_validate_clamps_overflow() -> None:
    overlay = TutorialOverlay()
    assert overlay.validate_step_index(999) == len(overlay.STEPS) - 1


def test_overlay_is_focusable() -> None:
    assert TutorialOverlay.can_focus is True


def test_dismissed_message_exists() -> None:
    assert hasattr(TutorialOverlay, "Dismissed")
