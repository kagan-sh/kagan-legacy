"""Unit tests for the OSC 8 hyperlink probe and helper.

These test:
- Capability probe: env-driven on/off/override/NO_COLOR logic.
- link(): escape framing, fallback, control-char rejection.
- file_link(): URI construction fallback.
- ToolCallView._header_line(): OSC 8 present/absent based on capability.

These are unit tests (not behavioral integration tests) because they
validate a platform-dependent seam (terminal capability detection via
environment) that acceptance tests cannot reach without patching env.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_osc8_cache() -> None:
    """Clear the functools.cache on is_osc8_supported between tests."""
    from kagan.tui._osc8 import is_osc8_supported

    is_osc8_supported.cache_clear()


# ---------------------------------------------------------------------------
# Probe: KAGAN_OSC8 override
# ---------------------------------------------------------------------------


def test_probe_force_on_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    _clear_osc8_cache()
    monkeypatch.setenv("KAGAN_OSC8", "1")
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    _clear_osc8_cache()

    assert is_osc8_supported() is True


def test_probe_force_off_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    _clear_osc8_cache()
    monkeypatch.setenv("KAGAN_OSC8", "0")
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    _clear_osc8_cache()

    assert is_osc8_supported() is False


# ---------------------------------------------------------------------------
# Probe: NO_COLOR
# ---------------------------------------------------------------------------


def test_probe_no_color_disables_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    monkeypatch.delenv("KAGAN_OSC8", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    _clear_osc8_cache()

    assert is_osc8_supported() is False


def test_probe_kagan_osc8_beats_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    monkeypatch.setenv("KAGAN_OSC8", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    _clear_osc8_cache()

    assert is_osc8_supported() is True


# ---------------------------------------------------------------------------
# Probe: TERM_PROGRAM allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "term_program",
    ["iTerm.app", "WezTerm", "vscode", "ghostty", "Apple_Terminal"],
)
def test_probe_known_term_programs_are_capable(
    monkeypatch: pytest.MonkeyPatch, term_program: str
) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    monkeypatch.delenv("KAGAN_OSC8", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM_PROGRAM", term_program)
    monkeypatch.delenv("TERM", raising=False)
    _clear_osc8_cache()

    assert is_osc8_supported() is True


# ---------------------------------------------------------------------------
# Probe: TERM allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "term",
    ["xterm-kitty", "xterm-ghostty", "wezterm", "alacritty"],
)
def test_probe_known_term_values_are_capable(
    monkeypatch: pytest.MonkeyPatch, term: str
) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    monkeypatch.delenv("KAGAN_OSC8", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    monkeypatch.setenv("TERM", term)
    _clear_osc8_cache()

    assert is_osc8_supported() is True


def test_probe_unknown_env_is_not_capable(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import is_osc8_supported

    monkeypatch.delenv("KAGAN_OSC8", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM_PROGRAM", "some-unknown-terminal")
    monkeypatch.setenv("TERM", "xterm-256color")
    _clear_osc8_cache()

    assert is_osc8_supported() is False


# ---------------------------------------------------------------------------
# link(): escape framing
# ---------------------------------------------------------------------------


def test_link_returns_plain_text_when_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import link

    monkeypatch.setenv("KAGAN_OSC8", "0")
    _clear_osc8_cache()

    result = link("https://example.com", "click me")
    assert result == "click me"


def test_link_returns_osc8_framing_when_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import link

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    result = link("https://example.com", "click me")
    assert "\x1b]8;;https://example.com\x1b\\" in result
    assert "click me" in result
    # Sequence must close after text.
    assert result.endswith("\x1b]8;;\x1b\\")


def test_link_rejects_escape_char_in_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from kagan.tui._osc8 import link

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    with pytest.raises(ValueError, match="illegal control character"):
        link("https://evil\x1b]8;;malicious\x1b\\", "trap")


@pytest.mark.parametrize("bad_char", ["\x07", "\n", "\r"])
def test_link_rejects_other_control_chars_in_url(
    monkeypatch: pytest.MonkeyPatch, bad_char: str
) -> None:
    from kagan.tui._osc8 import link

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    with pytest.raises(ValueError, match="illegal control character"):
        link(f"https://example.com{bad_char}injection", "label")


# ---------------------------------------------------------------------------
# file_link(): URI construction
# ---------------------------------------------------------------------------


def test_file_link_returns_label_when_unsupported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from kagan.tui._osc8 import file_link

    monkeypatch.setenv("KAGAN_OSC8", "0")
    _clear_osc8_cache()

    path = str(tmp_path / "foo.py")
    result = file_link(path)
    assert result == path


def test_file_link_returns_osc8_uri_when_supported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from kagan.tui._osc8 import file_link

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    path = str(tmp_path / "foo.py")
    result = file_link(path)
    expected_uri = (tmp_path / "foo.py").resolve().as_uri()
    assert expected_uri in result
    assert "foo.py" in result


def test_file_link_uses_custom_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from kagan.tui._osc8 import file_link

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    path = str(tmp_path / "bar.py")
    result = file_link(path, "bar.py")
    assert "bar.py" in result


# ---------------------------------------------------------------------------
# ToolCallView._header_line(): OSC 8 integration
# ---------------------------------------------------------------------------


def _make_tool_call_view(title: str, args: dict) -> object:
    """Instantiate ToolCallView without a running Textual app.

    Uses the real constructor so Textual reactives initialise correctly.
    ToolCallView.__init__ calls super().__init__() which seeds the _id and
    reactive infrastructure that var.__set__ requires.
    """
    from kagan.tui.widgets.streaming import ToolCallView

    return ToolCallView(title, status="completed", args=json.dumps(args), tool_id="test-tool")


def test_header_line_contains_osc8_for_path_arg_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui.widgets.streaming import ToolCallView

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    view = _make_tool_call_view("Read", {"path": "src/kagan/tui/app.py"})
    assert isinstance(view, ToolCallView)
    header = view._header_line()
    # OSC 8 open sequence must appear in the header.
    assert "\x1b]8;;" in header
    assert "src/kagan/tui/app.py" in header


def test_header_line_contains_plain_path_when_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui.widgets.streaming import ToolCallView

    monkeypatch.setenv("KAGAN_OSC8", "0")
    _clear_osc8_cache()

    view = _make_tool_call_view("Edit", {"path": "src/kagan/tui/app.py"})
    assert isinstance(view, ToolCallView)
    header = view._header_line()
    assert "\x1b]8;;" not in header
    assert "src/kagan/tui/app.py" in header


def test_header_line_non_path_key_never_linkified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui.widgets.streaming import ToolCallView

    monkeypatch.setenv("KAGAN_OSC8", "1")
    _clear_osc8_cache()

    view = _make_tool_call_view("Bash", {"command": "ls -la"})
    assert isinstance(view, ToolCallView)
    header = view._header_line()
    # Non-path keys must never be wrapped in OSC 8 sequences.
    assert "\x1b]8;;" not in header
    assert "ls -la" in header
