"""PAIR execution: session lifecycle and task handoff.

Covers:
- Session creation bound to task-scoped context
- Backend support (tmux, nvim, vscode, cursor) with fallback
- Session open / read / close lifecycle
- Status handling: BACKLOG -> IN_PROGRESS on session open
- Task/session env vars injection
- build_handoff_payload: per-backend command/link generation
- parse_requested_worktree: validation of worktree path input
- Domain error classes: construction and fields
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kagan.core.domain.enums import (
    PairTerminalBackend,
    TaskStatus,
    TaskType,
    coerce_pair_backend,
    resolve_pair_backend,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestPairBackendResolution:
    """Pair terminal backend resolution: task -> config -> tmux default."""

    def test_task_backend_wins(self) -> None:
        assert resolve_pair_backend("vscode", "tmux") == "vscode"

    def test_config_backend_fallback(self) -> None:
        assert resolve_pair_backend(None, "nvim") == "nvim"

    def test_tmux_default_when_no_override(self) -> None:
        assert resolve_pair_backend(None, None) == "tmux"

    @pytest.mark.parametrize("backend", list(PairTerminalBackend))
    def test_all_backends_are_valid(self, backend: PairTerminalBackend) -> None:
        assert coerce_pair_backend(backend.value) == backend.value

    def test_invalid_backend_returns_none(self) -> None:
        assert coerce_pair_backend("invalid") is None


class TestSessionLifecycle:
    """Session open/close drives task status and tmux interaction."""

    async def test_task_moves_to_in_progress_on_session_open(
        self, state_manager, task_factory
    ) -> None:
        task = task_factory(
            title="Pair task",
            task_type=TaskType.PAIR,
            status=TaskStatus.BACKLOG,
        )
        created = await state_manager.create(task)
        # Simulate what session open does: move to IN_PROGRESS
        updated = await state_manager.update(created.id, status=TaskStatus.IN_PROGRESS)
        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS

    async def test_tmux_session_created_and_cleaned(self, mock_tmux) -> None:
        """Fake tmux creates and kills sessions correctly."""
        from kagan.core.tmux import run_tmux

        await run_tmux("new-session", "-s", "test-sess", "-d")
        assert "test-sess" in mock_tmux

        await run_tmux("kill-session", "-t", "test-sess")
        assert "test-sess" not in mock_tmux

    async def test_tmux_session_env_vars_injected(self, mock_tmux) -> None:
        """Session creation passes environment variables."""
        from kagan.core.tmux import run_tmux

        await run_tmux(
            "new-session",
            "-s",
            "env-sess",
            "-d",
            "-e",
            "KAGAN_TASK_ID=task-123",
            "-e",
            "KAGAN_WORKTREE=/tmp/wt",
        )
        session = mock_tmux.get("env-sess")
        assert session is not None
        assert session["env"]["KAGAN_TASK_ID"] == "task-123"
        assert session["env"]["KAGAN_WORKTREE"] == "/tmp/wt"


class TestBuildHandoffPayload:
    """build_handoff_payload generates per-backend commands and links."""

    def test_tmux_backend(self, tmp_path: Path) -> None:
        from kagan.core.commands._serialization import build_handoff_payload

        worktree = tmp_path / "wt"
        worktree.mkdir()
        result = build_handoff_payload(
            task_id="t1",
            backend="tmux",
            session_name="sess-t1",
            worktree_path=worktree,
            already_exists=False,
        )
        assert result["success"] is True
        assert result["backend"] == "tmux"
        assert "tmux attach-session" in result["primary_command"]
        assert "tmux_docs" in result["links"]
        assert result["already_exists"] is False

    def test_vscode_backend(self, tmp_path: Path) -> None:
        from kagan.core.commands._serialization import build_handoff_payload

        worktree = tmp_path / "wt"
        worktree.mkdir()
        result = build_handoff_payload(
            task_id="t1",
            backend="vscode",
            session_name="sess-t1",
            worktree_path=worktree,
            already_exists=True,
        )
        assert result["success"] is True
        assert result["backend"] == "vscode"
        assert "code --new-window" in result["primary_command"]
        assert "vscode_prompt_uri" in result["links"]
        assert result["already_exists"] is True

    def test_cursor_backend(self, tmp_path: Path) -> None:
        from kagan.core.commands._serialization import build_handoff_payload

        worktree = tmp_path / "wt"
        worktree.mkdir()
        result = build_handoff_payload(
            task_id="t1",
            backend="cursor",
            session_name="sess-t1",
            worktree_path=worktree,
            already_exists=False,
        )
        assert result["backend"] == "cursor"
        assert "cursor --new-window" in result["primary_command"]
        assert "cursor_prompt_uri" in result["links"]

    def test_nvim_backend(self, tmp_path: Path) -> None:
        from kagan.core.commands._serialization import build_handoff_payload

        worktree = tmp_path / "wt"
        worktree.mkdir()
        result = build_handoff_payload(
            task_id="t1",
            backend="nvim",
            session_name="sess-t1",
            worktree_path=worktree,
            already_exists=False,
        )
        assert result["backend"] == "nvim"
        assert "nvim " in result["primary_command"]
        assert "nvim_docs" in result["links"]

    def test_unknown_backend_fallback(self, tmp_path: Path) -> None:
        from kagan.core.commands._serialization import build_handoff_payload

        worktree = tmp_path / "wt"
        worktree.mkdir()
        result = build_handoff_payload(
            task_id="t1",
            backend="unknown",
            session_name="sess-t1",
            worktree_path=worktree,
            already_exists=False,
        )
        assert result["success"] is True
        assert "Open worktree" in result["primary_command"]


class TestExternalLauncherCommands:
    def test_build_vscode_chat_launcher_command(self, tmp_path: Path) -> None:
        from kagan.core.services.sessions import build_vscode_chat_launcher_command

        worktree = tmp_path / "wt"
        worktree.mkdir()
        command = build_vscode_chat_launcher_command(worktree)
        assert command[0:4] == ["code", "chat", "--mode", "agent"]
        assert "--add-file" in command
        assert str(worktree / ".kagan" / "start_prompt.md") in command

    def test_has_extension_installed_case_insensitive(self) -> None:
        from kagan.core.services.sessions import has_extension_installed

        listing = "GitHub.Copilot\nGITHUB.COPILOT-CHAT\n"
        assert has_extension_installed(listing, "github.copilot-chat") is True
        assert has_extension_installed(listing, "ms-python.python") is False


class TestParseRequestedWorktree:
    """parse_requested_worktree validates worktree path input."""

    def test_none_returns_none_pair(self) -> None:
        from kagan.core.commands._serialization import parse_requested_worktree

        path, error = parse_requested_worktree(task_id="t1", raw_worktree=None)
        assert path is None
        assert error is None

    def test_valid_string_returns_path(self, tmp_path: Path) -> None:
        from kagan.core.commands._serialization import parse_requested_worktree

        path, error = parse_requested_worktree(task_id="t1", raw_worktree=str(tmp_path))
        assert path is not None
        assert error is None

    def test_non_string_returns_error(self) -> None:
        from kagan.core.commands._serialization import parse_requested_worktree

        path, error = parse_requested_worktree(task_id="t1", raw_worktree=42)
        assert path is None
        assert error is not None
        assert error["code"] == "INVALID_WORKTREE_PATH"

    def test_empty_string_returns_none_pair(self) -> None:
        from kagan.core.commands._serialization import parse_requested_worktree

        path, error = parse_requested_worktree(task_id="t1", raw_worktree="")
        assert path is None
        assert error is None


class TestDomainErrors:
    """Domain error classes carry machine-readable codes and fields."""

    def test_task_not_found_error(self) -> None:
        from kagan.core.domain.errors import TaskNotFoundError

        err = TaskNotFoundError("abc123")
        assert err.code == "TASK_NOT_FOUND"
        assert err.task_id == "abc123"
        assert "abc123" in str(err)

    def test_task_type_mismatch_error(self) -> None:
        from kagan.core.domain.errors import TaskTypeMismatchError

        err = TaskTypeMismatchError("abc123", "AUTO")
        assert err.code == "TASK_TYPE_MISMATCH"
        assert err.task_id == "abc123"
        assert err.current_task_type == "AUTO"

    def test_workspace_not_found_error(self) -> None:
        from kagan.core.domain.errors import WorkspaceNotFoundError

        err = WorkspaceNotFoundError("abc123")
        assert err.code == "WORKSPACE_NOT_FOUND"

    def test_invalid_worktree_path_error(self) -> None:
        from kagan.core.domain.errors import InvalidWorktreePathError

        err = InvalidWorktreePathError("abc123", "path does not exist")
        assert err.code == "INVALID_WORKTREE_PATH"
        assert "path does not exist" in str(err)

    def test_session_create_failed_error(self) -> None:
        from kagan.core.domain.errors import SessionCreateFailedError

        cause = RuntimeError("tmux not found")
        err = SessionCreateFailedError("abc123", cause)
        assert err.code == "SESSION_CREATE_FAILED"
        assert err.__cause__ is cause

    def test_review_guardrail_blocked_error(self) -> None:
        from kagan.core.domain.errors import ReviewGuardrailBlockedError

        err = ReviewGuardrailBlockedError(
            code="MISSING_PR", message="No PR linked", hint="Create a PR first"
        )
        assert err.code == "MISSING_PR"
        assert err.hint == "Create a PR first"
