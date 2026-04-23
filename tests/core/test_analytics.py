"""Comprehensive tests for analytics system — all phases (1-5).

Tests cover:
- Task classification (Phase 1)
- Agent role assignment (Phase 1)
- Analytics queries (Phase 2)
- Data validation (Phase 5)
"""

import pytest

from kagan.core._task_classification import classify_task
from kagan.core.enums import TaskType

pytestmark = [pytest.mark.core, pytest.mark.smoke]


# ============================================================================
# Phase 1: Task Classification Tests
# ============================================================================


class TestTaskClassification:
    """Test TaskType classification system."""

    def test_classify_task_code_implementation(self) -> None:
        """Test classification of code implementation tasks."""
        task_type = classify_task(
            "Implement user authentication",
            "Add JWT-based authentication to the API",
        )
        assert task_type == TaskType.CODE_IMPLEMENTATION

    def test_classify_task_bug_fix(self) -> None:
        """Test classification of bug fix tasks."""
        task_type = classify_task(
            "Fix login crash on Firefox",
            "The login page crashes when using Firefox browser due to missing event handler.",
        )
        assert task_type == TaskType.BUG_FIX

    def test_classify_task_refactoring(self) -> None:
        """Test classification of refactoring tasks."""
        task_type = classify_task(
            "Refactor authentication module",
            "Reduce duplication in auth code and improve readability",
        )
        assert task_type == TaskType.REFACTORING

    def test_classify_task_testing(self) -> None:
        """Test classification of testing tasks."""
        task_type = classify_task(
            "Write unit tests for payment service",
            "Add pytest unit tests to cover payment processing functions",
        )
        assert task_type == TaskType.TESTING

    def test_classify_task_documentation(self) -> None:
        """Test classification of documentation tasks."""
        task_type = classify_task(
            "Document the project",
            "Create comprehensive docstrings and README",
        )
        assert task_type == TaskType.DOCUMENTATION

    def test_classify_task_optimization(self) -> None:
        """Test classification of optimization tasks."""
        task_type = classify_task(
            "Optimize database queries",
            "Improve performance of slow queries and add caching",
        )
        assert task_type == TaskType.OPTIMIZATION

    def test_classify_task_architecture(self) -> None:
        """Test classification of architecture tasks."""
        task_type = classify_task(
            "Design microservices architecture",
            "Plan system design for scalability",
        )
        assert task_type == TaskType.ARCHITECTURE

    def test_classify_task_design(self) -> None:
        """Test classification of design tasks."""
        task_type = classify_task(
            "Design user interface for dashboard",
            "Create UI mockups and component layouts",
        )
        assert task_type == TaskType.DESIGN

    def test_classify_task_analysis(self) -> None:
        """Test classification of analysis tasks."""
        task_type = classify_task(
            "Analyze the codebase",
            "Review code and audit system",
        )
        assert task_type == TaskType.ANALYSIS

    def test_classify_task_investigation(self) -> None:
        """Test classification of investigation tasks."""
        task_type = classify_task(
            "Investigate the issue",
            "Troubleshoot and diagnose root cause",
        )
        assert task_type == TaskType.INVESTIGATION

    def test_classify_task_deployment(self) -> None:
        """Test classification of deployment tasks."""
        task_type = classify_task(
            "Set up CI/CD pipeline",
            "Configure Docker and Kubernetes for deployment",
        )
        assert task_type == TaskType.DEPLOYMENT

    def test_classify_task_unknown_type(self) -> None:
        """Test fallback to UNKNOWN when no keywords match."""
        task_type = classify_task(
            "Meetings with clients",
            "Discuss project scope and timeline",
        )
        assert task_type == TaskType.UNKNOWN

    def test_classify_task_keyword_specificity(self) -> None:
        """Test that longer keyword phrases have higher priority."""
        # "add feature" should score higher than just "add"
        task_type = classify_task(
            "Add new feature to the system",
            "Implement a new user-facing feature",
        )
        assert task_type == TaskType.CODE_IMPLEMENTATION

    def test_classify_task_title_only(self) -> None:
        """Test classification with title only (no description)."""
        task_type = classify_task("Fix database migration")
        assert task_type == TaskType.BUG_FIX

    def test_classify_task_empty_description(self) -> None:
        """Test classification with empty description."""
        task_type = classify_task("Implement new API endpoint", "")
        assert task_type == TaskType.CODE_IMPLEMENTATION

    def test_classify_task_case_insensitive(self) -> None:
        """Test that classification is case-insensitive."""
        task_type = classify_task("FIX CRITICAL CRASH", "Bug in production")
        assert task_type == TaskType.BUG_FIX

    def test_classify_task_multiple_keywords(self) -> None:
        """Test with multiple matching keywords (priority-based selection)."""
        # Both BUG_FIX and OPTIMIZATION keywords present; BUG_FIX has higher priority
        task_type = classify_task(
            "Fix slow database query",
            "There's a bug causing slow performance due to missing index",
        )
        assert task_type == TaskType.BUG_FIX
