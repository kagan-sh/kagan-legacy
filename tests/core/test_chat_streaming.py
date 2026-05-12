"""Behavioral chat streaming tests through the KaganDriver DSL."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.smoke]


async def test_chat_stream_emits_chunks_before_final_message(board: KaganDriver) -> None:
    session = await board.chat_create_session(source="test", label="streaming-order")
    sid = session["id"]

    outcome = await board.chat_send(
        sid,
        "stream please",
        agent_chunks=["one ", "two ", "three"],
    )

    kinds = [event.type for event in outcome.events]
    chunk_indexes = [i for i, kind in enumerate(kinds) if kind == "assistant_chunk"]
    final_index = kinds.index("assistant_message")

    assert len(chunk_indexes) == 3
    assert chunk_indexes == sorted(chunk_indexes)
    assert chunk_indexes[-1] < final_index
    assert outcome.assistant_content == "one two three"


async def test_cancelled_chat_stream_persists_observable_partial(
    board: KaganDriver,
) -> None:
    session = await board.chat_create_session(source="test", label="streaming-cancel")
    sid = session["id"]

    outcome = await board.chat_send(
        sid,
        "start then cancel",
        agent_chunks=["partial response"],
        cancel_after_chars=1,
    )

    kinds = [event.type for event in outcome.events]

    assert "assistant_chunk" in kinds
    assert kinds.index("assistant_chunk") < kinds.index("assistant_message")
    assert outcome.terminated is True
    assert outcome.assistant_content.startswith("partial")
