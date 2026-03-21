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


def test_string_json_arguments_distinguished() -> None:
    """String-encoded JSON arguments with different values must not collapse."""
    guard = RepetitionGuard(window=10, threshold=4)
    assert not guard.check("ReadFile", '{"path": "/a.rs"}')
    assert not guard.check("ReadFile", '{"path": "/b.rs"}')
    assert not guard.check("ReadFile", '{"path": "/c.rs"}')
    assert not guard.check("ReadFile", '{"path": "/d.rs"}')
    # 4 different files → should NOT trigger


def test_dict_arguments_distinguished() -> None:
    """Dict arguments with different values must not trigger."""
    guard = RepetitionGuard(window=10, threshold=4)
    result = False
    for i in range(6):
        result = guard.check("WriteFile", {"path": f"/file{i}.rs", "content": f"v{i}"})
    assert not result  # all different


def test_plain_string_arguments_not_json() -> None:
    """Non-JSON string arguments should be used as-is for hashing."""
    guard = RepetitionGuard(window=10, threshold=4)
    assert not guard.check("Bash", "ls -la /home")
    assert not guard.check("Bash", "ls -la /tmp")
    assert not guard.check("Bash", "ls -la /var")
    assert not guard.check("Bash", "cat /etc/hosts")
    # All different → no trigger


def test_list_arguments_handled() -> None:
    """List arguments should be handled without error."""
    guard = RepetitionGuard(window=10, threshold=4)
    assert not guard.check("multi", [1, 2, 3])
    assert not guard.check("multi", [4, 5, 6])
