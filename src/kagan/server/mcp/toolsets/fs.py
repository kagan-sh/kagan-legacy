"""kagan.server.mcp.toolsets.fs — File-system MCP tools.

Provides three mutation tools: fs_write_file, fs_edit_file, fs_read_file.

All mutation paths route through apply_edits() which:
  1. Reads the file as bytes and detects BOM.
  2. Decodes using the detected encoding (UTF-8 fallback).
  3. Normalizes EOLs to LF; remembers original eol_style.
  4. Applies requested edits to LF-normalized content.
  5. Reapplies the original EOL style.
  6. Writes bytes back, prepending the original BOM (if any).

This preserves CRLF line endings and BOMs across round-trips so that
editors that care (Windows, VS Code with CRLF settings) see unchanged
file metadata.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.core._edit_diff import (
    Edit,
    apply_edits_to_normalized_content,
    detect_bom,
    normalize_line_endings,
    reapply_line_endings,
)
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions
from kagan.server.mcp.toolsets import mcp_error_boundary

# ---------------------------------------------------------------------------
# Internal write result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteResult:
    """Result of a file-mutation operation."""

    path: str
    bytes_written: int
    bom_preserved: bool
    eol_style: str


# ---------------------------------------------------------------------------
# Shared apply_edits helper
# ---------------------------------------------------------------------------


async def apply_edits(file_path: Path, edits: list[Edit]) -> WriteResult:
    """Read *file_path*, apply *edits* to LF-normalized content, write back.

    Preserves BOM and EOL style detected on the original file.

    Steps:
    1. Read bytes; detect BOM.
    2. Decode with detected encoding (UTF-8 fallback).
    3. Normalise EOL → LF; record original eol_style.
    4. Apply edits (may raise ValueError on conflict / not-found).
    5. Reapply original EOL style.
    6. Encode back (same encoding); prepend BOM if present.
    7. Write bytes atomically (overwrite).
    """
    path_str = str(file_path)

    raw_bytes: bytes = await asyncio.to_thread(file_path.read_bytes)

    bom_bytes, encoding = detect_bom(raw_bytes)
    content_bytes = raw_bytes[len(bom_bytes) :] if bom_bytes else raw_bytes

    # Decode; errors='replace' avoids crash on rare corrupt files — the
    # replacement char will cause the edit to fail as "not found" which is
    # the correct user-visible outcome.
    text = content_bytes.decode(encoding, errors="replace")

    normalized, eol_style = normalize_line_endings(text)

    _, new_normalized = apply_edits_to_normalized_content(normalized, edits, path_str)

    new_text = reapply_line_endings(new_normalized, eol_style)

    # Use the base encoding name for encoding back (strip -sig suffix which
    # Python uses for the BOM-aware reader variant).
    encode_encoding = encoding.replace("-sig", "").replace("utf-8", "utf-8")
    new_bytes = new_text.encode(encode_encoding)
    if bom_bytes:
        new_bytes = bom_bytes + new_bytes

    await asyncio.to_thread(file_path.write_bytes, new_bytes)

    logger.debug(
        "apply_edits wrote {} bytes to {} (eol={}, bom={})",
        len(new_bytes),
        path_str,
        eol_style,
        bom_bytes is not None,
    )

    return WriteResult(
        path=path_str,
        bytes_written=len(new_bytes),
        bom_preserved=bom_bytes is not None,
        eol_style=eol_style,
    )


async def write_file(file_path: Path, content: str) -> WriteResult:
    """Write *content* to *file_path* as a fresh create/overwrite.

    No BOM, LF line endings.  Use this for generated files or when creating
    new files where there is no "original" to preserve.
    """
    path_str = str(file_path)
    data = content.encode("utf-8")
    await asyncio.to_thread(file_path.write_bytes, data)
    logger.debug("write_file wrote {} bytes to {}", len(data), path_str)
    return WriteResult(
        path=path_str,
        bytes_written=len(data),
        bom_preserved=False,
        eol_style="lf",
    )


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register filesystem tools on mcp, filtered by opts."""

    if is_tool_allowed("fs_read_file", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def fs_read_file(
            ctx: Context,
            path: str,
        ) -> dict:
            """Read a file from disk and return its content as text.

            Returns: {"path", "content", "eol_style", "has_bom", "encoding"}.
            """
            file_path = Path(path)
            raw_bytes: bytes = await asyncio.to_thread(file_path.read_bytes)
            bom_bytes, encoding = detect_bom(raw_bytes)
            content_bytes = raw_bytes[len(bom_bytes) :] if bom_bytes else raw_bytes
            text = content_bytes.decode(encoding, errors="replace")
            _, eol_style = normalize_line_endings(text)
            return {
                "path": path,
                "content": text,
                "eol_style": eol_style,
                "has_bom": bom_bytes is not None,
                "encoding": encoding,
            }

    if is_tool_allowed("fs_write_file", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def fs_write_file(
            ctx: Context,
            path: str,
            content: str,
        ) -> dict:
            """Write content to a file, creating or overwriting it.

            Use this for new files or full rewrites.  Does not preserve
            existing BOM or EOL style — use fs_edit_file for that.

            Returns: {"path", "bytes_written", "bom_preserved", "eol_style"}.
            """
            file_path = Path(path)
            await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
            result = await write_file(file_path, content)
            return {
                "path": result.path,
                "bytes_written": result.bytes_written,
                "bom_preserved": result.bom_preserved,
                "eol_style": result.eol_style,
            }

    if is_tool_allowed("fs_edit_file", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def fs_edit_file(
            ctx: Context,
            path: str,
            edits: list[dict],
        ) -> dict:
            """Apply one or more old→new text replacements to an existing file.

            Preserves the file's original BOM and line-ending style (CRLF/LF).
            Each edit must supply "old_text" (unique substring) and "new_text".

            Returns: {"path", "bytes_written", "bom_preserved", "eol_style"}.

            Raises on: empty old_text, text not found, duplicate matches,
            overlapping edits, replacement produces identical content.
            """
            file_path = Path(path)
            edit_list: list[Edit] = []
            for item in edits:
                edit_list.append(Edit(old_text=item["old_text"], new_text=item["new_text"]))
            result = await apply_edits(file_path, edit_list)
            return {
                "path": result.path,
                "bytes_written": result.bytes_written,
                "bom_preserved": result.bom_preserved,
                "eol_style": result.eol_style,
            }
