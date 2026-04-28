"""Smoke tests for analytics system — quick validation.

These tests can be run quickly and validate core functionality
without requiring complex setup.
"""

import pytest

from kagan.core._task_classification import classify_task
from kagan.core.enums import TaskType

pytestmark = [pytest.mark.core, pytest.mark.smoke]


class TestClassificationSmoke:
    """Quick smoke tests for task classification."""

    def test_classify_function_exists(self) -> None:
        """Verify classify_task function exists and is callable."""
        assert callable(classify_task)

    def test_classify_returns_task_type(self) -> None:
        """Verify classify_task returns TaskType enum."""
        result = classify_task("Fix bug", "There's a bug")
        assert isinstance(result, TaskType)

    def test_classify_bug_fix_basic(self) -> None:
        """Test basic bug fix classification."""
        result = classify_task("Fix", "bug")
        assert result == TaskType.BUG_FIX

    def test_classify_implementation_basic(self) -> None:
        """Test basic implementation classification."""
        result = classify_task("Implement", "feature")
        assert result in [TaskType.CODE_IMPLEMENTATION, TaskType.UNKNOWN]

    def test_classify_all_enum_values_creatable(self) -> None:
        """Verify all TaskType enum values exist."""
        task_types = [
            TaskType.CODE_IMPLEMENTATION,
            TaskType.BUG_FIX,
            TaskType.REFACTORING,
            TaskType.TESTING,
            TaskType.DOCUMENTATION,
            TaskType.OPTIMIZATION,
            TaskType.ARCHITECTURE,
            TaskType.DESIGN,
            TaskType.ANALYSIS,
            TaskType.INVESTIGATION,
            TaskType.DEPLOYMENT,
            TaskType.UNKNOWN,
        ]
        assert len(task_types) == 12

    def test_classify_deterministic(self) -> None:
        """Test that classification is deterministic."""
        title = "Fix login bug"
        desc = "Login is broken"
        result1 = classify_task(title, desc)
        result2 = classify_task(title, desc)
        assert result1 == result2

    def test_classify_empty_returns_unknown(self) -> None:
        """Test that empty input returns UNKNOWN."""
        result = classify_task("", "")
        assert result == TaskType.UNKNOWN

    def test_classify_whitespace_returns_unknown(self) -> None:
        """Test that whitespace-only input returns UNKNOWN."""
        result = classify_task("   ", "   ")
        assert result == TaskType.UNKNOWN
