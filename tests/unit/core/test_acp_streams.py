"""Unit tests for ACP stream guards."""

import asyncio

import pytest

from kagan.core._acp_streams import JsonRpcObjectStreamReader

pytestmark = [pytest.mark.unit]


async def test_json_rpc_reader_skips_stdout_noise_before_object() -> None:
    source = asyncio.StreamReader()
    source.feed_data(b"\x1b[118;1:3u\n")
    source.feed_data(b'"terminal noise"\n')
    source.feed_data(b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
    source.feed_eof()

    reader = JsonRpcObjectStreamReader(source, backend_name="claude-code")

    assert await reader.readline() == b'{"jsonrpc":"2.0","id":1,"result":{}}\n'
    assert await reader.readline() == b""


async def test_json_rpc_reader_preserves_valid_object_line() -> None:
    source = asyncio.StreamReader()
    source.feed_data(b'{"method":"session/update","params":{}}\n')
    source.feed_eof()

    reader = JsonRpcObjectStreamReader(source, backend_name="claude-code")

    assert await reader.readline() == b'{"method":"session/update","params":{}}\n'
