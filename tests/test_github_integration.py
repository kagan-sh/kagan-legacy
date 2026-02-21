"""GitHub integration: connect, sync, PR, and merge operations.

Covers:
- Repo connection preflight persists metadata
- Repo view JSON parsing with error handling
"""

from __future__ import annotations

from typing import Any

from kagan.core.plugins.github.gh_adapter import (
    GhRepoView,
    load_connection_metadata,
    parse_gh_repo_view,
)


class TestRepoMetadataParsing:
    """Repo view JSON parsing for connection preflight."""

    def test_parse_valid_repo_view(self) -> None:
        raw: dict[str, Any] = {
            "owner": {"login": "user"},
            "name": "repo",
            "url": "https://github.com/user/repo",
            "defaultBranchRef": {"name": "main"},
            "isPrivate": False,
        }
        view = parse_gh_repo_view(raw)
        assert isinstance(view, GhRepoView)
        assert view.full_name == "user/repo"
        assert view.default_branch == "main"

    def test_parse_empty_returns_error(self) -> None:
        result = parse_gh_repo_view({})
        assert not isinstance(result, GhRepoView)

    def test_parse_missing_owner_returns_error(self) -> None:
        raw: dict[str, Any] = {"name": "repo", "url": "https://github.com/user/repo"}
        result = parse_gh_repo_view(raw)
        assert not isinstance(result, GhRepoView)


class TestConnectionMetadataParsing:
    """Connection metadata compatibility parsing."""

    def test_load_connection_metadata_accepts_legacy_name_key(self) -> None:
        raw: dict[str, Any] = {
            "owner": "user",
            "name": "repo",
            "full_name": "user/repo",
            "default_branch": "main",
        }
        parsed = load_connection_metadata(raw)
        assert parsed is not None
        assert parsed["repo"] == "repo"
        assert "name" not in parsed

    def test_load_connection_metadata_prefers_repo_over_name(self) -> None:
        raw: dict[str, Any] = {
            "owner": "user",
            "repo": "canonical-repo",
            "name": "legacy-repo",
            "full_name": "user/canonical-repo",
            "default_branch": "main",
        }
        parsed = load_connection_metadata(raw)
        assert parsed is not None
        assert parsed["repo"] == "canonical-repo"
