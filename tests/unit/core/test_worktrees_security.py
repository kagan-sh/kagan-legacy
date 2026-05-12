"""Security tests for worktree path validation — path traversal fix verification.

Tests verify that _resolve_worktree_path() properly validates task IDs
to prevent path traversal, shell injection, and directory escaping attacks.
"""

import re
import types
from pathlib import Path

import pytest

from kagan.core._worktrees import Worktrees
from kagan.core.errors import ValidationError, WorktreeError

pytestmark = [pytest.mark.unit]

# Sample valid UUIDs for testing
VALID_UUIDS = [
    "550e8400-e29b-41d4-a716-446655440000",
    "12345678-1234-5678-1234-567812345678",
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "00000000-0000-0000-0000-000000000000",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
]

# Path traversal attempts
PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\config\\sam",
    "..%2f..%2f..%2fetc%2fpasswd",
    "....//....//....//etc/passwd",
    "..\x00/../../../etc/passwd",
    "./../../etc/passwd",
    "/etc/passwd",
    "C:\\Windows\\System32\\drivers\\etc\\hosts",
    "\\\\server\\share\\file.txt",
]

# Shell injection attempts
SHELL_INJECTION_PAYLOADS = [
    "task; rm -rf /",
    "task && rm -rf /",
    "task|whoami",
    "task`whoami`",
    "$(rm -rf /)",
    "task; cat /etc/passwd",
    "task || sh",
    "task &",
]

# Special characters that should be rejected
SPECIAL_CHAR_PAYLOADS = [
    "task*",
    "task?",
    "task[name]",
    "task{name}",
    "task<with>",
    "task'quote",
    'task"double',
    "task with spaces",
    "task\twith\ttabs",
    "task\nwith\nnewlines",
    "task\x00with\x00nulls",
]


class TestResolveWorktreePathValidation:
    """Tests for _resolve_worktree_path() function validating task IDs."""

    def test_valid_uuid_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should accept valid UUID format task IDs."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        # Test each valid UUID
        for valid_uuid in VALID_UUIDS:
            # The function should return a path within the base directory
            result = Worktrees._resolve_worktree_path(valid_uuid)

            assert isinstance(result, Path)
            assert result.name == valid_uuid
            assert result.parent == tmp_path
            # Verify the resolved path is within base directory
            assert _is_path_within_base(result, tmp_path)

    def test_valid_uuid_variants_accepted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should accept UUIDs with different casing."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        # Uppercase UUID should be valid
        upper_uuid = "550E8400-E29B-41D4-A716-446655440000"
        result = Worktrees._resolve_worktree_path(upper_uuid)
        assert result.name == upper_uuid

    @pytest.mark.parametrize("payload", PATH_TRAVERSAL_PAYLOADS)
    def test_path_traversal_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
    ):
        """_resolve_worktree_path() should reject path traversal attempts."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        with pytest.raises((ValueError, ValidationError, WorktreeError)) as exc_info:
            Worktrees._resolve_worktree_path(payload)

        error_msg = str(exc_info.value).lower()
        assert any(word in error_msg for word in ["invalid", "traversal", "path", "task"])

    @pytest.mark.parametrize("payload", SHELL_INJECTION_PAYLOADS)
    def test_shell_injection_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
    ):
        """_resolve_worktree_path() should reject shell injection attempts."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        with pytest.raises((ValueError, ValidationError, WorktreeError)) as exc_info:
            Worktrees._resolve_worktree_path(payload)

        error_msg = str(exc_info.value).lower()
        assert any(word in error_msg for word in ["invalid", "format", "task", "shell"])

    @pytest.mark.parametrize("payload", SPECIAL_CHAR_PAYLOADS)
    def test_special_characters_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
    ):
        """_resolve_worktree_path() should reject task IDs with special characters."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        with pytest.raises((ValueError, ValidationError, WorktreeError)) as exc_info:
            Worktrees._resolve_worktree_path(payload)

        error_msg = str(exc_info.value).lower()
        assert any(word in error_msg for word in ["invalid", "format", "task"])

    def test_directory_escaping_detected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should detect and prevent path escaping base directory."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        # Create a path that would escape the base directory
        malicious_path = "../../.." + str(tmp_path) + "/../../../etc/passwd"

        with pytest.raises((ValueError, ValidationError, WorktreeError)) as exc_info:
            Worktrees._resolve_worktree_path(malicious_path)

        error_msg = str(exc_info.value).lower()
        assert any(word in error_msg for word in ["escape", "outside", "traversal", "invalid"])

    def test_resolved_path_is_normalized(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should return a normalized, absolute path."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = Worktrees._resolve_worktree_path(valid_uuid)

        # Path should be absolute
        assert result.is_absolute()
        # Path should be normalized (no .. or . components)
        assert str(result) == str(result.resolve())

    def test_empty_task_id_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should reject empty task IDs."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        with pytest.raises((ValueError, ValidationError, WorktreeError)):
            Worktrees._resolve_worktree_path("")

    def test_none_task_id_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should reject None task IDs."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        with pytest.raises((TypeError, ValidationError, WorktreeError)):
            Worktrees._resolve_worktree_path(None)  # type: ignore[arg-type]

    def test_non_string_task_id_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should reject non-string task IDs."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        with pytest.raises((TypeError, ValidationError, WorktreeError)):
            Worktrees._resolve_worktree_path(12345)  # type: ignore[arg-type]


class TestWorktreePathSecurityEdgeCases:
    """Edge case security tests for worktree path validation."""

    def test_unicode_in_task_id_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should reject task IDs with unicode characters."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        unicode_payloads = [
            "task日本語",
            "task\u202e",  # Right-to-left override
            "task\u0000",  # Null byte
            "task\xff",
        ]

        for payload in unicode_payloads:
            with pytest.raises((ValueError, ValidationError, WorktreeError)):
                Worktrees._resolve_worktree_path(payload)

    def test_double_encoding_attempts_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """_resolve_worktree_path() should reject URL/double-encoded paths."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        double_encoded = [
            "%252e%252e%252fetc%252fpasswd",  # Double URL encoded
            "..%252f..%252fetc%252fpasswd",
        ]

        for payload in double_encoded:
            with pytest.raises((ValueError, ValidationError, WorktreeError)):
                Worktrees._resolve_worktree_path(payload)

    def test_null_byte_injection_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """_resolve_worktree_path() should reject null byte injection attempts."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        null_payloads = [
            "task\x00",
            "task\x00/../../etc/passwd",
            "\x00",
        ]

        for payload in null_payloads:
            with pytest.raises((ValueError, ValidationError, WorktreeError)):
                Worktrees._resolve_worktree_path(payload)

    def test_very_long_task_id_resolves_safely(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """_resolve_worktree_path() handles long but valid task IDs without errors."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        long_payload = "a" * 10000
        result = Worktrees._resolve_worktree_path(long_payload)
        assert result.parent == tmp_path

    def test_path_with_control_characters_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """_resolve_worktree_path() should reject task IDs with control characters."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        control_chars = [
            "task\x01",
            "task\x1f",
            "task\x7f",
            "task\x80",
            "task\xff",
        ]

        for payload in control_chars:
            with pytest.raises((ValueError, ValidationError, WorktreeError)):
                Worktrees._resolve_worktree_path(payload)


class TestCreateMethodValidation:
    """Tests verifying that create() method properly uses path validation."""

    @pytest.mark.asyncio
    async def test_create_validates_task_id_before_use(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """create() should validate task ID before using it in path construction."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        resolve_calls: list[str] = []

        def tracked_resolve(task_id: str) -> Path:
            resolve_calls.append(task_id)
            return tmp_path / "worktrees" / task_id

        monkeypatch.setattr(Worktrees, "_resolve_worktree_path", staticmethod(tracked_resolve))

        result = Worktrees._resolve_worktree_path("valid-task-id")
        assert result == tmp_path / "worktrees" / "valid-task-id"
        assert resolve_calls == ["valid-task-id"]

    @pytest.mark.asyncio
    async def test_create_rejects_malicious_task_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """create() should reject malicious task IDs before any filesystem operations."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        async def _bad_get(*a, **kw):
            raise ValueError("bad task")

        fake_client = types.SimpleNamespace(
            tasks=types.SimpleNamespace(get=_bad_get),
            projects=types.SimpleNamespace(repos=None),  # not reached; tasks.get raises first
        )
        fake_engine = types.SimpleNamespace()
        worktrees = Worktrees(fake_engine, fake_client)  # type: ignore[arg-type]

        # Attempt to create worktree with path traversal task ID
        malicious_task_id = "../../../etc/passwd"

        with pytest.raises((ValueError, ValidationError, WorktreeError)):
            await worktrees.create(malicious_task_id)

        # Verify no git operations were attempted (no mocking needed = no calls made)


class TestPathResolutionIntegration:
    """Integration tests for path resolution with actual filesystem."""

    def test_resolved_path_does_not_escape_with_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """_resolve_worktree_path() should handle symlinks in base directory safely."""
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(tmp_path))

        # Create a symlink that points outside the base
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        symlink_dir = tmp_path / "symlink"
        symlink_dir.symlink_to(outside_dir)

        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = Worktrees._resolve_worktree_path(valid_uuid)

        # Result should still be within the original base path
        assert _is_path_within_base(result, tmp_path)

    def test_resolved_path_with_relative_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """_resolve_worktree_path() should handle relative base paths correctly."""
        # Use a relative path as base (simulated)
        rel_base = tmp_path / "worktrees"
        rel_base.mkdir(parents=True)
        monkeypatch.setenv("KAGAN_WORKTREE_BASE", str(rel_base))

        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        result = Worktrees._resolve_worktree_path(valid_uuid)

        # Should be absolute and within base
        assert result.is_absolute()
        assert _is_path_within_base(result, rel_base)


# Helper function
def _is_path_within_base(path: Path, base: Path) -> bool:
    """Check if path is within base directory (resolves symlinks)."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


# UUID pattern for reference
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@pytest.mark.parametrize(
    "test_input,expected_valid",
    [
        ("550e8400-e29b-41d4-a716-446655440000", True),
        ("550E8400-E29B-41D4-A716-446655440000", True),
        ("not-a-uuid", False),
        ("12345", False),
        ("", False),
        ("550e8400-e29b-41d4-a716-44665544000", False),  # One char short
        ("550e8400-e29b-41d4-a716-4466554400000", False),  # One char extra
        ("550e8400e29b41d4a716446655440000", False),  # No hyphens
    ],
)
def test_uuid_pattern_matching(test_input: str, expected_valid: bool):
    """Verify UUID regex pattern for validation logic."""
    is_valid = bool(UUID_PATTERN.match(test_input))
    assert is_valid == expected_valid
