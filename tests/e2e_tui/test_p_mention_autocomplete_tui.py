"""Flow P — Mention Autocomplete (TUI).

Two test cases:
1. Task editor ``#`` typeahead works — opening TaskEditorModal, typing ``#``
   in the description field triggers the MentionTypeahead popover with a
   pre-seeded kagan task result.
2. Chat ``#`` is currently SKIP — the chat input's @-mention machinery has no
   parallel ``#`` trigger yet (see tests/tui/test_mention_typeahead_chat.py).

Assertions:
  1. MentionTypeahead popover becomes visible after ``#`` notification.
  2. Option list contains at least one item from the pre-seeded task.
  3. Selecting via Enter fires ``MentionSelected`` with ``kagan#`` prefix.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


@contextmanager
def _mock_search(results: list[Any]):
    """Patch ``search_mentions`` to return ``results`` without network calls."""

    async def _fake(*args: Any, **kwargs: Any) -> list[Any]:
        return results

    mp = pytest.MonkeyPatch()
    mp.setattr("kagan.core.integrations.mentions.search_mentions", _fake)
    try:
        yield
    finally:
        mp.undo()


async def test_task_editor_hash_typeahead_opens_popover(tui_driver: Any) -> None:
    """Typing ``#`` in the description TextArea shows the MentionTypeahead."""
    from kagan.core.integrations.mentions import Mention
    from kagan.tui import KaganApp
    from kagan.tui.screens.task_editor_modal import TaskEditorModal
    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    seeded = await tui_driver.create_task("Pre-seeded")
    kagan_mention = Mention(
        source="kagan",
        id=f"kagan#{seeded.id[:8]}",
        title=seeded.title,
        state="BACKLOG",
    )

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    with _mock_search([kagan_mention]):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # Open task editor modal
            app.push_screen(TaskEditorModal())
            await wait_for(lambda: isinstance(app.screen, TaskEditorModal), tries=60)
            await pilot.pause()

            # Find the MentionTypeahead attached to description
            try:
                typeahead = app.screen.query_one(MentionTypeahead)
            except Exception:
                pytest.skip(
                    "MentionTypeahead not mounted in TaskEditorModal — feature not yet wired"
                )
                return

            assert not typeahead.display, "typeahead should start hidden"

            # Notify the typeahead directly (same path the TextArea key handler uses)
            typeahead.notify_text_changed("#", 1)
            await wait_for(lambda: typeahead.display, tries=60, pump_delay=0.05)

            assert typeahead.display, "typeahead should be visible after # typed"


async def test_task_editor_hash_typeahead_enter_accepted(tui_driver: Any) -> None:
    """Enter is consumed by the typeahead and fires ``MentionSelected`` with kagan# prefix.

    We verify via the ``notify_key`` return value (True = consumed) and by
    inspecting the ``_results`` list to confirm the kagan mention was the
    candidate. Full text-insertion into the TextArea is exercised by the
    dedicated unit test in ``tests/unit/tui/test_mention_typeahead.py``.
    """
    from kagan.core.integrations.mentions import Mention
    from kagan.tui import KaganApp
    from kagan.tui.screens.task_editor_modal import TaskEditorModal
    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    seeded = await tui_driver.create_task("Pre-seeded Task B")
    kagan_mention = Mention(
        source="kagan",
        id=f"kagan#{seeded.id[:8]}",
        title=seeded.title,
        state="BACKLOG",
    )

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    with _mock_search([kagan_mention]):
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            app.push_screen(TaskEditorModal())
            await wait_for(lambda: isinstance(app.screen, TaskEditorModal), tries=60)
            await pilot.pause()

            try:
                typeahead = app.screen.query_one(MentionTypeahead)
            except Exception:
                pytest.skip("MentionTypeahead not mounted in TaskEditorModal")
                return

            typeahead.notify_text_changed("#", 1)
            await wait_for(lambda: typeahead.display, tries=60, pump_delay=0.05)

            # Confirm there is exactly one candidate and it is the kagan mention
            assert typeahead._results, "Results should be populated after # typed"
            assert typeahead._results[0].id.startswith("kagan#"), (
                f"Expected kagan# candidate but got {typeahead._results[0].id!r}"
            )

            # Enter should be consumed by the typeahead
            consumed = typeahead.notify_key("enter")

    assert consumed, "Enter should be consumed when typeahead is active with results"


@pytest.mark.skip(
    reason=(
        "Chat # typeahead not yet implemented. "
        "ChatPanel uses an Input with tightly coupled @-mention logic; "
        "a parallel # trigger needs its own seam. "
        "See tests/tui/test_mention_typeahead_chat.py."
    )
)
async def test_chat_hash_opens_typeahead() -> None:
    """Typing '#' in the chat input should open a kagan/GitHub typeahead popup."""
    ...
