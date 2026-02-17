"""Tests for path-safe validation of owner/repo in gh_adapter."""

from __future__ import annotations

import pytest

from kagan.core.plugins.github.gh_adapter import (
    _validate_path_segment,
    run_gh_api_comment_delete,
    run_gh_api_issue_comments,
)


class TestValidatePathSegment:
    """Verify _validate_path_segment rejects path-unsafe characters."""

    @pytest.mark.parametrize(
        "value",
        [
            "owner/inject",
            "../etc/passwd",
            "ok\0evil",
            "a/../b",
            "/leading-slash",
        ],
        ids=["slash", "dotdot-prefix", "null-byte", "dotdot-middle", "leading-slash"],
    )
    def test_rejects_unsafe_values(self, value: str) -> None:
        with pytest.raises(ValueError, match="contains unsafe characters"):
            _validate_path_segment(value, "owner")

    @pytest.mark.parametrize(
        "value",
        ["valid-owner", "my.repo", "some_repo123", "UPPER"],
    )
    def test_accepts_safe_values(self, value: str) -> None:
        _validate_path_segment(value, "owner")  # should not raise


class TestEndpointFunctionsRejectUnsafeOwnerRepo:
    """Ensure endpoint-constructing functions raise before building the URL."""

    def test_issue_comments_rejects_malicious_owner(self) -> None:
        with pytest.raises(ValueError, match="owner contains unsafe characters"):
            run_gh_api_issue_comments("/usr/bin/gh", "/tmp", "evil/../x", "repo", 1)

    def test_issue_comments_rejects_malicious_repo(self) -> None:
        with pytest.raises(ValueError, match="repo contains unsafe characters"):
            run_gh_api_issue_comments("/usr/bin/gh", "/tmp", "owner", "evil/repo", 1)

    def test_comment_delete_rejects_malicious_owner(self) -> None:
        with pytest.raises(ValueError, match="owner contains unsafe characters"):
            run_gh_api_comment_delete("/usr/bin/gh", "/tmp", "../admin", "repo", 1)

    def test_comment_delete_rejects_malicious_repo(self) -> None:
        with pytest.raises(ValueError, match="repo contains unsafe characters"):
            run_gh_api_comment_delete("/usr/bin/gh", "/tmp", "owner", "re\0po", 1)
