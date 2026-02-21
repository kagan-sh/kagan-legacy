from __future__ import annotations

from types import SimpleNamespace

from textual.widgets._select import SelectOverlay

from kagan.tui.textual_compat import apply_textual_compat_workarounds
from kagan.tui.ui.widgets.slash_complete import SlashComplete


def test_select_overlay_page_navigation_recovers_from_stale_index_map() -> None:
    apply_textual_compat_workarounds()
    events: list[str] = []
    overlay_stub = SimpleNamespace(
        _options=[object()],
        highlighted=0,
        _index_to_line={},
        action_first=lambda: events.append("first"),
        action_last=lambda: events.append("last"),
    )

    SelectOverlay._move_page(overlay_stub, 1)

    assert events == ["last"]


def test_select_overlay_compat_patch_is_idempotent() -> None:
    apply_textual_compat_workarounds()
    patched_once = SelectOverlay._move_page

    apply_textual_compat_workarounds()

    assert SelectOverlay._move_page is patched_once


def test_slash_complete_pagedown_falls_back_when_option_list_raises_keyerror() -> None:
    widget = SlashComplete()
    events: list[str] = []

    class _OptionListStub:
        def action_page_down(self) -> None:
            raise KeyError(0)

        def action_last(self) -> None:
            events.append("last")

    option_list = _OptionListStub()
    widget.query_one = lambda *_args, **_kwargs: option_list  # type: ignore[method-assign]

    widget.action_page_down()

    assert events == ["last"]
