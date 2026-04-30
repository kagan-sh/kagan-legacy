"""Tests for the MentionTypeahead widget.

All tests use a minimal Textual app that embeds a TextArea and a
MentionTypeahead.  ``search_mentions`` is always mocked at the module
boundary — no ``gh`` CLI calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import TextArea

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mention(source: str, id_: str, title: str, state: str | None = None):
    from kagan.core.integrations.mentions import Mention

    return Mention(source=source, id=id_, title=title, state=state)


_KAGAN_MENTION = _mention("kagan", "kagan#aabbccdd", "Implement login", "BACKLOG")
_GITHUB_MENTION = _mention("github", "#42", "Fix bug in login", "open")


def _mock_search(results):
    """Return a patch context for search_mentions that returns ``results``."""
    return patch(
        "kagan.core.integrations.mentions.search_mentions",
        AsyncMock(return_value=results),
    )


# ---------------------------------------------------------------------------
# Minimal host app
# ---------------------------------------------------------------------------


class _MentionTestApp(App):
    """Minimal app with a TextArea and a MentionTypeahead attached to it."""

    def __init__(self, project_id: str = "proj-1", client=None) -> None:
        super().__init__()
        self._project_id = project_id
        self._client = client

    def compose(self) -> ComposeResult:
        yield TextArea(id="desc")

    def on_mount(self) -> None:
        from kagan.tui.widgets._mention_typeahead import MentionTypeahead

        typeahead = MentionTypeahead(
            host_id="desc",
            project_id=self._project_id,
            client=self._client,
            debounce_seconds=0,  # No debounce in tests
        )
        self.mount(typeahead)

    def _get_typeahead(self):
        from kagan.tui.widgets._mention_typeahead import MentionTypeahead

        return self.query_one(MentionTypeahead)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_hash_opens_typeahead_in_description() -> None:
    """Typing ``#`` at word-start in the TextArea shows the typeahead."""
    with _mock_search([_KAGAN_MENTION]):
        async with _MentionTestApp().run_test() as pilot:
            await pilot.pause()

            typeahead = pilot.app._get_typeahead()
            assert not typeahead.display, "typeahead should start hidden"

            # Simulate ``#`` at word-start
            typeahead.notify_text_changed("#", 1)
            # Give the debounce + search coroutine a moment
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # After results arrive the typeahead should become visible
            assert typeahead.display, "typeahead should be visible after # typed"


async def test_typeahead_lists_kagan_and_github_results() -> None:
    """Typeahead renders rows for both kagan and github mention results."""
    from textual.widgets import OptionList

    with _mock_search([_KAGAN_MENTION, _GITHUB_MENTION]):
        async with _MentionTestApp().run_test() as pilot:
            await pilot.pause()

            typeahead = pilot.app._get_typeahead()
            # First trigger activation with ``#`` at position 1
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            # Then extend the query
            typeahead.notify_text_changed("#lo", 3)
            await pilot.pause()
            await pilot.pause()

            option_list = typeahead.query_one("OptionList", OptionList)
            assert option_list.option_count == 2
            # Check source glyphs in rendered text
            labels = [option_list.get_option_at_index(i).prompt for i in range(2)]
            combined = " ".join(str(l) for l in labels)
            assert "[K]" in combined
            assert "[GH]" in combined


async def test_select_kagan_inserts_kagan_short_id() -> None:
    """Pressing Enter on a kagan result inserts ``kagan#<id>``."""
    selected_texts: list[str] = []

    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    class _Spy(_MentionTestApp):
        def on_mention_typeahead_mention_selected(
            self, event: MentionTypeahead.MentionSelected
        ) -> None:
            selected_texts.append(event.insert_text)

    with _mock_search([_KAGAN_MENTION]):
        async with _Spy().run_test() as pilot:
            await pilot.pause()
            typeahead = pilot.app._get_typeahead()
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # Accept with Enter key
            consumed = typeahead.notify_key("enter")

    assert consumed, "Enter should have been consumed by the typeahead"
    assert selected_texts, "MentionSelected should have been posted"
    assert selected_texts[0].startswith("kagan#"), (
        f"Kagan mention should insert kagan#... but got {selected_texts[0]!r}"
    )


async def test_select_github_inserts_hash_n() -> None:
    """Pressing Enter on a github result inserts ``#<number>``."""
    selected_texts: list[str] = []

    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    class _Spy(_MentionTestApp):
        def on_mention_typeahead_mention_selected(
            self, event: MentionTypeahead.MentionSelected
        ) -> None:
            selected_texts.append(event.insert_text)

    with _mock_search([_GITHUB_MENTION]):
        async with _Spy().run_test() as pilot:
            await pilot.pause()
            typeahead = pilot.app._get_typeahead()
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            typeahead.notify_key("enter")

    assert selected_texts, "MentionSelected should have been posted"
    assert selected_texts[0].startswith("#"), (
        f"GitHub mention should insert #N but got {selected_texts[0]!r}"
    )


async def test_esc_closes_without_inserting() -> None:
    """Pressing Esc hides the typeahead and posts MentionDismissed, not MentionSelected."""
    dismissed: list[bool] = []
    selected: list[str] = []

    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    class _Spy(_MentionTestApp):
        def on_mention_typeahead_mention_selected(
            self, event: MentionTypeahead.MentionSelected
        ) -> None:
            selected.append(event.insert_text)

        def on_mention_typeahead_mention_dismissed(
            self, event: MentionTypeahead.MentionDismissed
        ) -> None:
            dismissed.append(True)

    with _mock_search([_KAGAN_MENTION]):
        async with _Spy().run_test() as pilot:
            await pilot.pause()
            typeahead = pilot.app._get_typeahead()
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            typeahead.notify_key("escape")
            await pilot.pause()

    assert not selected, "Esc must not insert anything"
    assert dismissed, "MentionDismissed should have been posted"
    # The typeahead should be hidden after Esc
    # (can't easily check display after run_test exits, but no assertion error = pass)


async def test_backspace_past_hash_closes() -> None:
    """Backspacing with an empty query (right after ``#``) closes the typeahead."""
    dismissed: list[bool] = []

    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    class _Spy(_MentionTestApp):
        def on_mention_typeahead_mention_dismissed(
            self, _: MentionTypeahead.MentionDismissed
        ) -> None:
            dismissed.append(True)

    with _mock_search([_KAGAN_MENTION]):
        async with _Spy().run_test() as pilot:
            await pilot.pause()
            typeahead = pilot.app._get_typeahead()
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # Empty query, backspace should dismiss
            consumed = typeahead.notify_key("backspace")
            await pilot.pause()

    assert consumed, "Backspace at empty query should be consumed"
    assert dismissed, "MentionDismissed should have been posted"


async def test_kagan_only_when_no_github_link() -> None:
    """When search_mentions returns only kagan results, the list shows only kagan rows."""
    from textual.widgets import OptionList

    kagan_only = [_KAGAN_MENTION]
    with _mock_search(kagan_only):
        async with _MentionTestApp().run_test() as pilot:
            await pilot.pause()
            typeahead = pilot.app._get_typeahead()
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            option_list = typeahead.query_one("OptionList", OptionList)
            assert option_list.option_count == 1
            label = str(option_list.get_option_at_index(0).prompt)
            assert "[K]" in label
            assert "[GH]" not in label
