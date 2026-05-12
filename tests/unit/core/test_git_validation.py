"""Unit tests for git reference validation functions in kagan.core.git."""

from pathlib import Path

import pytest

from kagan.core.errors import WorktreeError
from kagan.core.git import validate_ref_name, worktree_add

pytestmark = [pytest.mark.unit]


class TestValidateRefName:
    """Tests for validate_ref_name() function."""

    @pytest.mark.asyncio
    async def test_rejects_names_starting_with_dash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Names starting with '-' should be rejected (option injection prevention)."""
        called: list[tuple] = []

        async def _never_called(*args, **kwargs):
            called.append((args, kwargs))
            return ("", "")

        monkeypatch.setattr("kagan.core.git._run_git", _never_called)
        result = await validate_ref_name("-force")
        assert result is False
        assert called == [], "_run_git must not be called for dash-prefix names"

    @pytest.mark.asyncio
    async def test_rejects_names_containing_double_dot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Names containing '..' should be rejected (directory traversal prevention)."""
        called: list[tuple] = []

        async def _never_called(*args, **kwargs):
            called.append((args, kwargs))
            return ("", "")

        monkeypatch.setattr("kagan.core.git._run_git", _never_called)
        result = await validate_ref_name("feature..branch")
        assert result is False
        assert called == [], "_run_git must not be called for double-dot names"

    @pytest.mark.asyncio
    async def test_rejects_names_containing_at_curly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Names containing '@{' should be rejected (reflog syntax prevention)."""
        called: list[tuple] = []

        async def _never_called(*args, **kwargs):
            called.append((args, kwargs))
            return ("", "")

        monkeypatch.setattr("kagan.core.git._run_git", _never_called)
        result = await validate_ref_name("branch@{1}")
        assert result is False
        assert called == [], "_run_git must not be called for @{ names"

    @pytest.mark.asyncio
    async def test_rejects_empty_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty string should be rejected."""
        called: list[tuple] = []

        async def _never_called(*args, **kwargs):
            called.append((args, kwargs))
            return ("", "")

        monkeypatch.setattr("kagan.core.git._run_git", _never_called)
        result = await validate_ref_name("")
        assert result is False
        assert called == [], "_run_git must not be called for empty names"

    @pytest.mark.asyncio
    async def test_rejects_name_with_only_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace-only names should pass to git check-ref-format for validation."""

        # Note: whitespace names are not rejected by the quick checks,
        # they go to git check-ref-format which will reject them
        async def _fake_run_git(*args, **kwargs):
            raise WorktreeError("invalid ref name")

        monkeypatch.setattr("kagan.core.git._run_git", _fake_run_git)
        result = await validate_ref_name("   ")
        assert result is False

    @pytest.mark.asyncio
    async def test_accepts_valid_branch_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
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
            git_calls: list[tuple] = []

            async def _fake_run_git(*args, _calls=git_calls, **kwargs):
                _calls.append((args, kwargs))
                return ("", "")

            monkeypatch.setattr("kagan.core.git._run_git", _fake_run_git)
            result = await validate_ref_name(name)
            assert result is True, f"Expected '{name}' to be valid"
            assert len(git_calls) == 1, f"Expected _run_git called once for '{name}'"
            assert git_calls[0][0] == ("check-ref-format", "--branch", name)
            assert git_calls[0][1] == {"cwd": Path.cwd(), "check": True}

    @pytest.mark.asyncio
    async def test_rejects_invalid_branch_names_via_git(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Names that pass quick checks but fail git check-ref-format should be rejected."""

        async def _fake_run_git(*args, **kwargs):
            raise WorktreeError("invalid ref name")

        monkeypatch.setattr("kagan.core.git._run_git", _fake_run_git)
        result = await validate_ref_name("name ending with space ")
        assert result is False

    @pytest.mark.asyncio
    async def test_handles_git_command_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WorktreeError from _run_git should be caught and return False."""

        async def _fake_run_git(*args, **kwargs):
            raise WorktreeError("command failed")

        monkeypatch.setattr("kagan.core.git._run_git", _fake_run_git)
        result = await validate_ref_name("invalid~name")
        assert result is False


class TestWorktreeAddValidation:
    """Tests for worktree_add() validation behavior."""

    @pytest.mark.asyncio
    async def test_raises_worktree_error_for_invalid_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """worktree_add should raise WorktreeError when branch name is invalid."""

        async def _fake_validate(name: str) -> bool:
            return False

        monkeypatch.setattr("kagan.core.git.validate_ref_name", _fake_validate)

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
    async def test_raises_worktree_error_for_invalid_base(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """worktree_add should raise WorktreeError when base reference is invalid."""
        _results = iter([True, False])

        async def _fake_validate(name: str) -> bool:
            return next(_results)

        monkeypatch.setattr("kagan.core.git.validate_ref_name", _fake_validate)

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
    async def test_calls_worktree_add_when_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """worktree_add should proceed when both branch and base are valid."""
        validate_calls: list[str] = []
        git_calls: list[tuple] = []

        async def _fake_validate(name: str) -> bool:
            validate_calls.append(name)
            return True

        async def _fake_run_git(*args, **kwargs):
            git_calls.append((args, kwargs))
            # Non-empty stdout for rev-parse so _has_local_branch returns True;
            # the worktree-create path skips the empty-repo seeding branch.
            return ("abc123", "")

        monkeypatch.setattr("kagan.core.git.validate_ref_name", _fake_validate)
        monkeypatch.setattr("kagan.core.git._run_git", _fake_run_git)
        monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)

        await worktree_add(
            repo_path="/tmp/repo",
            worktree_path="/tmp/wt",
            branch="feature/test",
            base="main",
        )

        # validate_ref_name called twice (branch + base).
        assert len(validate_calls) == 2
        # Two git calls when base exists: _has_local_branch lookup, then worktree add.
        assert len(git_calls) == 2
        assert git_calls[-1][0][0] == "worktree"
        assert git_calls[-1][0][1] == "add"

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
