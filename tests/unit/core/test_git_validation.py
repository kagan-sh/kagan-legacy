"""Unit tests for git reference validation functions in kagan.core.git."""

from pathlib import Path
from unittest.mock import patch

import pytest

from kagan.core.errors import WorktreeError
from kagan.core.git import validate_ref_name, worktree_add

pytestmark = [pytest.mark.unit]


class TestValidateRefName:
    """Tests for validate_ref_name() function."""

    @pytest.mark.asyncio
    async def test_rejects_names_starting_with_dash(self) -> None:
        """Names starting with '-' should be rejected (option injection prevention)."""
        with patch("kagan.core.git._run_git") as mock_run_git:
            # The function should return False before calling _run_git
            result = await validate_ref_name("-force")
            assert result is False
            mock_run_git.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_names_containing_double_dot(self) -> None:
        """Names containing '..' should be rejected (directory traversal prevention)."""
        with patch("kagan.core.git._run_git") as mock_run_git:
            result = await validate_ref_name("feature..branch")
            assert result is False
            mock_run_git.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_names_containing_at_curly(self) -> None:
        """Names containing '@{' should be rejected (reflog syntax prevention)."""
        with patch("kagan.core.git._run_git") as mock_run_git:
            result = await validate_ref_name("branch@{1}")
            assert result is False
            mock_run_git.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_empty_name(self) -> None:
        """Empty string should be rejected."""
        with patch("kagan.core.git._run_git") as mock_run_git:
            result = await validate_ref_name("")
            assert result is False
            mock_run_git.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_name_with_only_whitespace(self) -> None:
        """Whitespace-only names should pass to git check-ref-format for validation."""
        # Note: whitespace names are not rejected by the quick checks,
        # they go to git check-ref-format which will reject them
        with patch("kagan.core.git._run_git") as mock_run_git:
            mock_run_git.side_effect = WorktreeError("invalid ref name")
            result = await validate_ref_name("   ")
            assert result is False

    @pytest.mark.asyncio
    async def test_accepts_valid_branch_names(self) -> None:
        """Valid branch names should be accepted."""
        valid_names = [
            "main",
            "feature/new-thing",
            "bugfix/issue-123",
            "hotfix/v1.0.1",
            "release/2024.01",
            "kagan/agent-session-abc123",
            "branch_with_underscores",
            "branch.with.dots",  # single dots are ok
            "v1.0.0",
        ]

        for name in valid_names:
            with patch("kagan.core.git._run_git") as mock_run_git:
                mock_run_git.return_value = ("", "")  # Success
                result = await validate_ref_name(name)
                assert result is True, f"Expected '{name}' to be valid"
                mock_run_git.assert_called_once_with(
                    "check-ref-format", "--branch", name, cwd=Path.cwd(), check=True
                )

    @pytest.mark.asyncio
    async def test_rejects_invalid_branch_names_via_git(self) -> None:
        """Names that pass quick checks but fail git check-ref-format should be rejected."""
        with patch("kagan.core.git._run_git") as mock_run_git:
            mock_run_git.side_effect = WorktreeError("invalid ref name")
            result = await validate_ref_name("name ending with space ")
            assert result is False

    @pytest.mark.asyncio
    async def test_handles_git_command_failure(self) -> None:
        """WorktreeError from _run_git should be caught and return False."""
        with patch("kagan.core.git._run_git") as mock_run_git:
            mock_run_git.side_effect = WorktreeError("command failed")
            result = await validate_ref_name("invalid~name")
            assert result is False


class TestWorktreeAddValidation:
    """Tests for worktree_add() validation behavior."""

    @pytest.mark.asyncio
    async def test_raises_worktree_error_for_invalid_branch(self) -> None:
        """worktree_add should raise WorktreeError when branch name is invalid."""
        with patch("kagan.core.git.validate_ref_name") as mock_validate:
            mock_validate.return_value = False

            with pytest.raises(WorktreeError) as exc_info:
                await worktree_add(
                    repo_path="/tmp/repo",
                    worktree_path="/tmp/wt",
                    branch="-invalid",
                    base="main",
                )

            assert "Invalid branch name '-invalid'" in str(exc_info.value)
            assert "cannot start with '-'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_worktree_error_for_invalid_base(self) -> None:
        """worktree_add should raise WorktreeError when base reference is invalid."""
        with patch("kagan.core.git.validate_ref_name") as mock_validate:
            # First call (branch) returns True, second call (base) returns False
            mock_validate.side_effect = [True, False]

            with pytest.raises(WorktreeError) as exc_info:
                await worktree_add(
                    repo_path="/tmp/repo",
                    worktree_path="/tmp/wt",
                    branch="feature/test",
                    base="../malicious",
                )

            assert "Invalid base reference '../malicious'" in str(exc_info.value)
            assert "cannot start with '-'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_calls_worktree_add_when_valid(self) -> None:
        """worktree_add should proceed when both branch and base are valid."""
        with (
            patch("kagan.core.git.validate_ref_name") as mock_validate,
            patch("kagan.core.git._run_git") as mock_run_git,
            patch("pathlib.Path.mkdir"),
        ):
            mock_validate.return_value = True
            mock_run_git.return_value = ("", "")

            await worktree_add(
                repo_path="/tmp/repo",
                worktree_path="/tmp/wt",
                branch="feature/test",
                base="main",
            )

            # validate_ref_name should be called twice (for branch and base)
            assert mock_validate.call_count == 2
            # _run_git should be called to create the worktree
            mock_run_git.assert_called_once()
            args = mock_run_git.call_args[0]
            assert args[0] == "worktree"
            assert args[1] == "add"

    @pytest.mark.asyncio
    async def test_validates_branch_with_double_dot(self) -> None:
        """worktree_add should reject branch names containing '..'."""
        with pytest.raises(WorktreeError) as exc_info:
            await worktree_add(
                repo_path="/tmp/repo",
                worktree_path="/tmp/wt",
                branch="feature..test",
                base="main",
            )

        assert "Invalid branch name 'feature..test'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validates_branch_with_at_curly(self) -> None:
        """worktree_add should reject branch names containing '@{'."""
        with pytest.raises(WorktreeError) as exc_info:
            await worktree_add(
                repo_path="/tmp/repo",
                worktree_path="/tmp/wt",
                branch="branch@{1}",
                base="main",
            )

        assert "Invalid branch name 'branch@{1}'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validates_base_with_dash_prefix(self) -> None:
        """worktree_add should reject base references starting with '-'."""
        with pytest.raises(WorktreeError) as exc_info:
            await worktree_add(
                repo_path="/tmp/repo",
                worktree_path="/tmp/wt",
                branch="feature/test",
                base="-force",
            )

        assert "Invalid base reference '-force'" in str(exc_info.value)
