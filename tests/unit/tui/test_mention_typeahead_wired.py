"""Tests for MentionTypeahead wired into the TaskEditor description and
acceptance-criteria TextArea fields.

search_mentions is mocked at the module boundary — no ``gh`` CLI calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import TextArea

pytestmark = [pytest.mark.tui, pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mention(source: str, id_: str, title: str, state: str | None = None):
    from kagan.core.integrations.mentions import Mention

    return Mention(source=source, id=id_, title=title, state=state)


_KAGAN_MENTION = _mention("kagan", "kagan#aabbccdd", "Implement login", "BACKLOG")
_GITHUB_MENTION = _mention("github", "#42", "Fix bug", "open")


def _mock_search(results):
    return patch(
        "kagan.core.integrations.mentions.search_mentions",
        AsyncMock(return_value=results),
    )


# ---------------------------------------------------------------------------
# Minimal host app that wraps TaskEditor with a fake client/project_id
# ---------------------------------------------------------------------------


class _FakeClient:
    """Minimal stand-in for KaganCore that satisfies type hints."""


class _EditorApp(App):
    """Minimal app that mounts a TaskEditor with typeahead support."""

    def __init__(self) -> None:
        super().__init__()
        self._fake_client = _FakeClient()
        self._project_id = "proj-test-1"

    def compose(self) -> ComposeResult:
        from kagan.tui.widgets.task_editor import TaskEditor

        yield TaskEditor(
            client=self._fake_client,  # type: ignore[arg-type]
            project_id=self._project_id,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _get_desc_typeahead(app):
    """Return the MentionTypeahead bound to task-description, with debounce zeroed."""
    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    typeaheads = list(app.query(MentionTypeahead))
    ta = next((t for t in typeaheads if t._host_id == "task-description"), None)
    if ta is not None:
        ta._debounce_seconds = 0  # disable debounce in tests
    return ta


async def test_typeahead_fires_on_hash_in_description_text_area() -> None:
    """Typing '#' in the description TextArea opens the typeahead popup."""
    with _mock_search([_KAGAN_MENTION]):
        async with _EditorApp().run_test(size=(80, 30)) as pilot:
            await pilot.pause()

            typeahead = _get_desc_typeahead(pilot.app)
            assert typeahead is not None, "No typeahead found for task-description"
            assert not typeahead.display, "typeahead should start hidden"

            # Simulate '#' typed at word-start
            typeahead.notify_text_changed("#", 1)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            assert typeahead.display, "typeahead should be visible after '#' typed"


async def test_typeahead_inserts_kagan_short_id_into_text_area() -> None:
    """Selecting a kagan row inserts 'kagan#<id>' text into the description TextArea."""
    from kagan.tui.widgets.task_editor import TaskEditor

    with _mock_search([_KAGAN_MENTION]):
        async with _EditorApp().run_test(size=(80, 30)) as pilot:
            await pilot.pause()

            desc_typeahead = _get_desc_typeahead(pilot.app)
            assert desc_typeahead is not None

            editor = pilot.app.query_one(TaskEditor)
            ta = pilot.app.query_one("#task-description", TextArea)

            # Directly notify typeahead as if '#' was typed at position 1.
            # Also pre-populate the editor's position snapshot so the
            # MentionSelected handler has the hash_pos available
            # (in real usage on_key() populates this; here we simulate it).
            desc_typeahead.notify_text_changed("#", 1)
            for _ in range(6):
                await pilot.pause()

            assert desc_typeahead.display, "typeahead must be visible before accepting"

            # Snapshot positions as on_key() would — before notify_key clears them.
            host_id = "task-description"
            editor._typeahead_hash_positions[host_id] = desc_typeahead._hash_position
            editor._typeahead_cursor_positions[host_id] = 1

            # Accept the selection
            desc_typeahead.notify_key("enter")
            for _ in range(4):
                await pilot.pause()

            content = ta.text
            assert "kagan#" in content, (
                f"TextArea should contain 'kagan#' after accepting, got: {content!r}"
            )


async def test_typeahead_also_wired_to_acceptance_criteria() -> None:
    """A separate typeahead instance exists for the acceptance-criteria TextArea."""
    from kagan.tui.widgets._mention_typeahead import MentionTypeahead

    with _mock_search([_KAGAN_MENTION]):
        async with _EditorApp().run_test(size=(80, 30)) as pilot:
            await pilot.pause()

            typeaheads = list(pilot.app.query(MentionTypeahead))
            host_ids = {t._host_id for t in typeaheads}
            assert "task-acceptance-criteria" in host_ids, (
                "A typeahead must be wired to task-acceptance-criteria"
            )


async def test_no_typeahead_without_client() -> None:
    """When client=None, no MentionTypeahead is mounted in the editor."""
    from kagan.tui.widgets._mention_typeahead import MentionTypeahead
    from kagan.tui.widgets.task_editor import TaskEditor

    class _NoClientApp(App):
        def compose(self) -> ComposeResult:
            yield TaskEditor()  # no client / project_id

    async with _NoClientApp().run_test(size=(80, 30)) as pilot:
        await pilot.pause()
        typeaheads = list(pilot.app.query(MentionTypeahead))
        assert len(typeaheads) == 0, "No typeahead should be mounted when client is None"
