"""Unit tests for private GitHub integration helper functions.

These test internal pure functions (_extract_label_names, _map_labels) that
validate the label-mapping contract.  Private-import coupling is documented as
a known smell: these helpers have no public surface, but their contract is
load-bearing for every issue sync.
"""

from typing import cast

import pytest

from kagan.core import Priority
from kagan.core.integrations.github import (
    GitHubIssue,
    _extract_label_names,
    _map_labels,
)

pytestmark = [pytest.mark.unit]


def test_extract_label_names_from_gh_format() -> None:
    """Labels are extracted from nested gh JSON format."""
    issue: GitHubIssue = {"labels": [{"name": "bug"}, {"name": "priority:high"}]}
    assert _extract_label_names(issue) == ["bug", "priority:high"]


def test_extract_label_names_handles_empty() -> None:
    """Empty or missing labels return empty list."""
    assert _extract_label_names({}) == []
    assert _extract_label_names({"labels": []}) == []
    assert _extract_label_names(cast("GitHubIssue", {"labels": None})) == []


def test_map_labels_priority() -> None:
    """Priority labels map to Priority enum values."""
    priority, remaining = _map_labels(["priority:high", "bug"])
    assert priority == Priority.HIGH
    assert remaining == ["bug"]


def test_map_labels_unknown_labels_pass_through() -> None:
    priority, remaining = _map_labels(["kagan:detached", "enhancement"])
    assert priority == Priority.MEDIUM
    assert remaining == ["kagan:detached", "enhancement"]


def test_map_labels_combined() -> None:
    priority, remaining = _map_labels(["priority:critical", "kagan:attached", "frontend", "bug"])
    assert priority == Priority.CRITICAL
    assert remaining == ["kagan:attached", "frontend", "bug"]


def test_map_labels_case_insensitive() -> None:
    """Label matching is case-insensitive."""
    priority, _ = _map_labels(["Priority:HIGH"])
    assert priority == Priority.HIGH


def test_map_labels_defaults_when_no_mapped_labels() -> None:
    priority, remaining = _map_labels(["bug", "documentation"])
    assert priority == Priority.MEDIUM
    assert remaining == ["bug", "documentation"]
