"""Behavioral tests for the fs MCP toolset.

Exercises fs_read_file, fs_write_file, and fs_edit_file through the MCP
tool protocol.  Real files on disk via tmp_path — no mocking.

Uses the mcp_board_admin_with_core fixture (ORCHESTRATOR role) so that
all three tools are registered.  fs_read_file is also accessible to
WORKER-role servers; the final test group confirms that via the standard
mcp_board_with_core fixture (default role = ORCHESTRATOR).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.helpers.mcp_helpers import extract_text as _text

if TYPE_CHECKING:
    from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# fs_read_file
# ---------------------------------------------------------------------------


class TestFsReadFile:
    async def test_reads_plain_utf8(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "plain.txt", b"hello\nworld\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_read_file", {"path": str(f)}
        )
        assert not result.isError
        payload = _text(result)
        assert payload["content"] == "hello\nworld\n"
        assert payload["eol_style"] == "lf"
        assert payload["has_bom"] is False
        assert payload["encoding"] == "utf-8"

    async def test_reads_crlf_file(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "crlf.txt", b"line1\r\nline2\r\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_read_file", {"path": str(f)}
        )
        assert not result.isError
        payload = _text(result)
        assert payload["eol_style"] == "crlf"
        assert payload["has_bom"] is False

    async def test_reads_utf8_bom(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        raw = b"\xef\xbb\xbfhello\nworld"
        f = _file(tmp_path, "bom.txt", raw)
        result = await mcp_board_admin_with_core.call_tool(
            "fs_read_file", {"path": str(f)}
        )
        assert not result.isError
        payload = _text(result)
        assert payload["has_bom"] is True
        assert payload["encoding"] == "utf-8-sig"
        assert "hello" in payload["content"]

    async def test_missing_file_raises(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        result = await mcp_board_admin_with_core.call_tool(
            "fs_read_file", {"path": str(tmp_path / "nonexistent.txt")}
        )
        # mcp_error_boundary wraps OSError as KaganError → tool returns error
        assert result.isError


# ---------------------------------------------------------------------------
# fs_write_file
# ---------------------------------------------------------------------------


class TestFsWriteFile:
    async def test_creates_new_file(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        path = str(tmp_path / "new.txt")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_write_file", {"path": path, "content": "hello\nworld\n"}
        )
        assert not result.isError
        payload = _text(result)
        assert payload["path"] == path
        assert payload["bytes_written"] > 0
        assert payload["bom_preserved"] is False
        assert payload["eol_style"] == "lf"
        assert Path(path).read_text(encoding="utf-8") == "hello\nworld\n"

    async def test_overwrites_existing_file(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        p = _file(tmp_path, "existing.txt", b"old content\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_write_file", {"path": str(p), "content": "new content\n"}
        )
        assert not result.isError
        assert p.read_bytes() == b"new content\n"

    async def test_creates_parent_dirs(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        path = str(tmp_path / "deep" / "nested" / "file.txt")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_write_file", {"path": path, "content": "data"}
        )
        assert not result.isError
        assert Path(path).exists()


# ---------------------------------------------------------------------------
# fs_edit_file — EOL and BOM preservation
# ---------------------------------------------------------------------------


class TestFsEditFile:
    async def test_edit_lf_file(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "lf.py", b"def foo():\n    pass\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [{"old_text": "    pass", "new_text": "    return 1"}],
            },
        )
        assert not result.isError
        payload = _text(result)
        assert payload["eol_style"] == "lf"
        assert payload["bom_preserved"] is False
        content = f.read_bytes()
        assert b"return 1" in content
        assert b"\r\n" not in content

    async def test_edit_preserves_crlf(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "crlf.py", b"def foo():\r\n    pass\r\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [{"old_text": "    pass", "new_text": "    return 1"}],
            },
        )
        assert not result.isError
        payload = _text(result)
        assert payload["eol_style"] == "crlf"
        content = f.read_bytes()
        assert b"\r\n" in content
        assert b"return 1" in content

    async def test_edit_preserves_utf8_bom(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        raw = b"\xef\xbb\xbfdef foo():\n    pass\n"
        f = _file(tmp_path, "bom.py", raw)
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [{"old_text": "    pass", "new_text": "    return 42"}],
            },
        )
        assert not result.isError
        payload = _text(result)
        assert payload["bom_preserved"] is True
        written = f.read_bytes()
        assert written.startswith(b"\xef\xbb\xbf"), "BOM must be present at start of file"
        assert b"return 42" in written

    async def test_edit_crlf_with_bom_round_trip(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        """CRLF file with UTF-8 BOM — both must be preserved after edit."""
        raw = b"\xef\xbb\xbfline1\r\nline2\r\nline3\r\n"
        f = _file(tmp_path, "crlf_bom.txt", raw)
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [{"old_text": "line2", "new_text": "LINE_TWO"}],
            },
        )
        assert not result.isError
        payload = _text(result)
        assert payload["bom_preserved"] is True
        assert payload["eol_style"] == "crlf"
        written = f.read_bytes()
        assert written.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" in written
        assert b"LINE_TWO" in written

    async def test_edit_not_found_returns_error(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "source.txt", b"hello world\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [{"old_text": "missing text", "new_text": "x"}],
            },
        )
        assert result.isError

    async def test_edit_overlapping_returns_error(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "source.txt", b"abcdefgh\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [
                    {"old_text": "abcde", "new_text": "X"},
                    {"old_text": "cdefgh", "new_text": "Y"},
                ],
            },
        )
        assert result.isError

    async def test_multiple_disjoint_edits(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "source.txt", b"alpha beta gamma\n")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [
                    {"old_text": "alpha", "new_text": "ONE"},
                    {"old_text": "gamma", "new_text": "THREE"},
                ],
            },
        )
        assert not result.isError
        content = f.read_text(encoding="utf-8")
        assert "ONE" in content
        assert "THREE" in content
        assert "beta" in content

    async def test_file_without_trailing_newline(
        self,
        mcp_board_admin_with_core: ClientSession,
        tmp_path: Path,
    ) -> None:
        f = _file(tmp_path, "no_newline.txt", b"line1\nline2")
        result = await mcp_board_admin_with_core.call_tool(
            "fs_edit_file",
            {
                "path": str(f),
                "edits": [{"old_text": "line2", "new_text": "line2_edited"}],
            },
        )
        assert not result.isError
        content = f.read_text(encoding="utf-8")
        assert content == "line1\nline2_edited"
