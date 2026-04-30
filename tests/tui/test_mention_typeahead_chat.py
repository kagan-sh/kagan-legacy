"""Tests for # mention typeahead in the chat input.

Chat uses an Input widget with its own @-mention machinery (session
references). Adding a parallel # trigger for kagan/GitHub mentions would
require significant surgery on the ChatPanel._sync_completion_overlays
and key routing logic without a clean seam. This is punted.

A TODO comment has been left in ChatPanel for future work.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.mark.skip(
    reason=(
        "Chat # typeahead not yet implemented. "
        "ChatPanel uses an Input widget with tightly coupled @-mention logic; "
        "a parallel # trigger needs its own seam. See TODO in chat.py."
    )
)
async def test_hash_in_chat_input_opens_typeahead() -> None:
    """Typing '#' in the chat input should open a kagan/GitHub typeahead popup."""
    ...
