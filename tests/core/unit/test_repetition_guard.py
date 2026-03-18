"""Unit tests for RepetitionGuard."""

from __future__ import annotations

from kagan.core._repetition_guard import RepetitionGuard


def test_check_returns_false_below_threshold() -> None:
    guard = RepetitionGuard(window=10, threshold=4)
    for _ in range(3):
        assert not guard.check("tool_a", {"key": "value"})


def test_check_returns_true_at_threshold() -> None:
    guard = RepetitionGuard(window=10, threshold=4)
    for _ in range(3):
        guard.check("tool_a", {"key": "value"})
    assert guard.check("tool_a", {"key": "value"})


def test_different_tools_do_not_trigger() -> None:
    guard = RepetitionGuard(window=10, threshold=4)
    for i in range(10):
        assert not guard.check(f"tool_{i}", {"key": "value"})


def test_window_evicts_old_entries() -> None:
    guard = RepetitionGuard(window=5, threshold=4)
    for _ in range(3):
        guard.check("tool_a", {"key": "value"})
    # Fill the window with other calls to push out the earlier ones
    for i in range(5):
        guard.check(f"tool_other_{i}", {"n": i})
    # Now tool_a should be evicted, so this won't trigger
    assert not guard.check("tool_a", {"key": "value"})


def test_reset_clears_history() -> None:
    guard = RepetitionGuard(window=10, threshold=4)
    for _ in range(3):
        guard.check("tool_a", {"key": "value"})
    guard.reset()
    assert not guard.check("tool_a", {"key": "value"})


def test_none_arguments_handled() -> None:
    guard = RepetitionGuard(window=10, threshold=4)
    for _ in range(3):
        guard.check("tool_a", None)
    assert guard.check("tool_a", None)


def test_different_arguments_do_not_trigger() -> None:
    guard = RepetitionGuard(window=10, threshold=4)
    for i in range(10):
        assert not guard.check("tool_a", {"counter": i})
