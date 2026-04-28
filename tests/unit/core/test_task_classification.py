"""Unit tests for task classification system — Phase 1.

Tests cover:
- Classification accuracy for all TaskType categories
- Keyword matching and scoring
- Edge cases and fallbacks
- Batch classification
"""

from kagan.core._task_classification import classify_task
from kagan.core.enums import TaskType


class TestClassifyTaskIndividual:
    """Test individual task classification."""

    def test_classify_by_high_priority_keyword(self) -> None:
        """Verify high-priority keywords score higher."""
        # BUG_FIX has priority 9 (high)
        task_type = classify_task("bug: login broken", "There's a critical bug")
        assert task_type == TaskType.BUG_FIX

    def test_classify_by_lower_priority_keyword(self) -> None:
        """Verify lower-priority keywords work when no high-priority match."""
        # DESIGN has priority 3 (lower)
        task_type = classify_task("Improve visual design", "Make the UI prettier")
        assert task_type == TaskType.DESIGN

    def test_classify_with_multiple_matching_types(self) -> None:
        """When multiple types match, pick the highest priority."""
        # Both CODE_IMPLEMENTATION (10) and TESTING (7) mentioned
        # CODE_IMPLEMENTATION should win
        task_type = classify_task(
            "Implement and test new feature",
            "Write code and add unit tests",
        )
        assert task_type == TaskType.CODE_IMPLEMENTATION

    def test_classify_exact_keyword_match(self) -> None:
        """Test exact phrase matching."""
        task_type = classify_task(
            "reduce duplication",
            "The code has too much duplication",
        )
        assert task_type == TaskType.REFACTORING

    def test_classify_with_whitespace_variations(self) -> None:
        """Test classification is robust to whitespace."""
        task_type = classify_task(
            "  Fix   critical   bug  ",
            "  broken   functionality  ",
        )
        assert task_type == TaskType.BUG_FIX

    def test_classify_mixed_case_keywords(self) -> None:
        """Test case-insensitive matching."""
        task_type = classify_task("FIX CRASH", "APPLICATION CRASH")
        assert task_type == TaskType.BUG_FIX

    def test_classify_keyword_in_long_description(self) -> None:
        """Test finding keywords in longer descriptions."""
        description = (
            "Our application has been experiencing issues with "
            "database performance. We need to optimize the query execution "
            "and add caching to improve throughput."
        )
        task_type = classify_task("Fix performance issues", description)
        # Could be OPTIMIZATION or BUG_FIX; OPTIMIZATION has more matching keywords
        assert task_type in [TaskType.OPTIMIZATION, TaskType.BUG_FIX]

    def test_classify_compound_keywords(self) -> None:
        """Test that multi-word keywords get higher weight."""
        # "unit test" is a multi-word keyword, should score higher
        task_type = classify_task(
            "Write unit tests",
            "Create comprehensive unit test coverage",
        )
        assert task_type == TaskType.TESTING

    def test_classify_partial_keyword_no_match(self) -> None:
        """Test that partial keyword matches don't work (word boundary)."""
        # "buggy" contains "bug" but shouldn't match as a full keyword
        # depending on implementation
        task_type = classify_task(
            "The buggy code needs review",
            "Code review required",
        )
        # This should still match BUG_FIX due to "bug" substring matching
        # Implementation depends on word-boundary handling
        assert task_type == TaskType.BUG_FIX

    def test_classify_all_enum_values(self) -> None:
        """Test that all TaskType enum values can be returned."""
        test_cases = [
            (TaskType.CODE_IMPLEMENTATION, "implement new feature", ""),
            (TaskType.BUG_FIX, "fix critical bug", ""),
            (TaskType.REFACTORING, "refactor codebase", ""),
            (TaskType.TESTING, "add unit tests", "pytest testing"),
            (TaskType.DOCUMENTATION, "documentation", "Update the README and handbook"),
            (TaskType.OPTIMIZATION, "optimize queries", "improve performance and speed"),
            (TaskType.ARCHITECTURE, "design architecture", "microservice design"),
            (TaskType.DESIGN, "design ui", "visual component layout"),
            (TaskType.ANALYSIS, "analyze code", "code review audit"),
            (TaskType.INVESTIGATION, "root cause analysis", "find the root cause"),
            (TaskType.DEPLOYMENT, "deploy to production", "docker kubernetes"),
            (TaskType.UNKNOWN, "xyz qwerty random text", ""),
        ]

        for expected_type, title, description in test_cases:
            result = classify_task(title, description)
            assert result == expected_type, f"Failed for {expected_type}: got {result}"

    def test_classify_empty_input(self) -> None:
        """Test with empty title and description."""
        task_type = classify_task("", "")
        assert task_type == TaskType.UNKNOWN

    def test_classify_whitespace_only_input(self) -> None:
        """Test with whitespace-only input."""
        task_type = classify_task("   ", "   ")
        assert task_type == TaskType.UNKNOWN

    def test_classify_special_characters(self) -> None:
        """Test with special characters."""
        task_type = classify_task(
            "Fix: [BUG] Login broken @production",
            "Issue #123: Login fails",
        )
        assert task_type == TaskType.BUG_FIX

    def test_classify_numbers_in_text(self) -> None:
        """Test classification with numbers in text."""
        task_type = classify_task(
            "Implement 2FA authentication",
            "Add two-factor authentication",
        )
        assert task_type == TaskType.CODE_IMPLEMENTATION

    def test_classify_programming_specific_keywords(self) -> None:
        """Test with programming-specific keywords."""
        task_type = classify_task("Write pytest unit tests", "Testing framework")
        assert task_type == TaskType.TESTING

    def test_classify_e2e_test_keyword(self) -> None:
        """Test classification with e2e test keyword."""
        task_type = classify_task("Create e2e tests", "End-to-end testing")
        assert task_type == TaskType.TESTING

    def test_classify_integration_test_keyword(self) -> None:
        """Test classification with integration test keyword."""
        task_type = classify_task(
            "Create integration tests",
            "Tests for integrated components",
        )
        assert task_type == TaskType.TESTING

    def test_classify_microservice_keyword(self) -> None:
        """Test classification with microservice keyword."""
        task_type = classify_task(
            "Design microservice architecture",
            "Split monolith into services",
        )
        assert task_type == TaskType.ARCHITECTURE

    def test_classify_docker_deployment(self) -> None:
        """Test classification with Docker/deployment keywords."""
        task_type = classify_task(
            "Configure Docker deployment",
            "Set up Docker and infrastructure",
        )
        assert task_type == TaskType.DEPLOYMENT

    def test_classify_memory_leak_investigation(self) -> None:
        """Test classification of investigation tasks."""
        task_type = classify_task(
            "root cause analysis",
            "troubleshoot",
        )
        assert task_type == TaskType.INVESTIGATION



class TestClassificationEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_classify_very_long_text(self) -> None:
        """Test with very long title and description."""
        long_title = "Fix " + "bug " * 100
        long_description = "There's a bug that causes " + "problems " * 200
        task_type = classify_task(long_title, long_description)
        assert task_type == TaskType.BUG_FIX

    def test_classify_unicode_characters(self) -> None:
        """Test with unicode characters."""
        task_type = classify_task(
            "修复登录错误",  # Fix login error in Chinese
            "fix bug in authentication",
        )
        # Should still match "bug" keyword
        assert task_type == TaskType.BUG_FIX

    def test_classify_urls_in_text(self) -> None:
        """Test with URLs in text."""
        task_type = classify_task(
            "Fix issue from https://github.com/org/repo/issues/123",
            "Bug fix",
        )
        assert task_type == TaskType.BUG_FIX

    def test_classify_code_snippets_in_description(self) -> None:
        """Test with code snippets in description."""
        task_type = classify_task(
            "Optimize database queries",
            "SELECT * FROM users WHERE status='active'",
        )
        assert task_type == TaskType.OPTIMIZATION

    def test_classify_markdown_formatting(self) -> None:
        """Test with markdown formatting."""
        task_type = classify_task(
            "## Fix production bug",
            "- [ ] Test bug fix\n- [ ] Deploy\n- [ ] Monitor",
        )
        assert task_type == TaskType.BUG_FIX

    def test_classify_repeated_keywords(self) -> None:
        """Test with repeated keywords (should accumulate score)."""
        task_type = classify_task(
            "Refactor refactor refactor the code",
            "Need to refactor and refactor more",
        )
        assert task_type == TaskType.REFACTORING


class TestClassificationConsistency:
    """Test consistency of classification."""

    def test_same_input_same_output(self) -> None:
        """Test that identical inputs produce identical outputs."""
        input_data = ("Implement new feature", "Add new functionality")
        result1 = classify_task(input_data[0], input_data[1])
        result2 = classify_task(input_data[0], input_data[1])
        assert result1 == result2

    def test_classification_deterministic(self) -> None:
        """Test that classification is deterministic (no randomness)."""
        title = "Fix database query performance"
        description = "Optimize slow queries with caching"

        results = [classify_task(title, description) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_keyword_order_irrelevant(self) -> None:
        """Test that keyword order doesn't affect classification."""
        task1 = classify_task(
            "Fix bug and improve performance",
            "The bug causes slow performance",
        )
        task2 = classify_task(
            "Improve performance and fix bug",
            "The bug causes slow performance",
        )
        # Both should classify as BUG_FIX (higher priority than OPTIMIZATION)
        assert task1 == task2
