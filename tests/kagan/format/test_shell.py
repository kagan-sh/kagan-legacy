"""Responsive shell geometry and fitted frame rendering."""

from rich.text import Text

from kagan.format.shell import frame_geometry, render_frame


def _plain(ansi: str) -> str:
    return Text.from_ansi(ansi).plain


def test_small_terminal_uses_full_screen_compact_geometry():
    geometry = frame_geometry(80, 24)

    assert geometry.compact is True
    assert (geometry.width, geometry.height) == (80, 24)
    assert geometry.content_width == 80
    assert geometry.content_height == 24


def test_large_terminal_keeps_centerable_maximum_geometry():
    geometry = frame_geometry(140, 50)

    assert geometry.compact is False
    assert (geometry.width, geometry.height) == (100, 41)
    assert geometry.width < geometry.terminal_columns
    assert geometry.height < geometry.terminal_rows


def test_short_view_fits_content_instead_of_using_maximum_height():
    geometry = frame_geometry(140, 50)
    frame = render_frame(Text("body"), geometry, minimum_height=12)

    assert (frame.width, frame.height) == (100, 12)
    assert _plain(frame.text).splitlines()[0].startswith("╭")
    assert _plain(frame.text).splitlines()[-1].startswith("╰")


def test_long_view_clamps_to_the_proportional_maximum():
    geometry = frame_geometry(140, 50)
    body = Text("\n".join(f"row {i}" for i in range(100)))
    frame = render_frame(body, geometry)

    assert frame.height == geometry.height


def test_compact_view_is_borderless_and_uses_the_full_terminal():
    geometry = frame_geometry(80, 24)
    frame = render_frame(Text("body"), geometry)
    plain = _plain(frame.text)

    assert (frame.width, frame.height) == (80, 24)
    assert "╭" not in plain
    assert "╰" not in plain
    assert "body" in plain


def test_pinned_footer_survives_an_overflowing_body():
    # B5: when the body is taller than the frame, the pinned footer (the action keys)
    # must NOT be cropped — the overflowing body is clipped instead. The intake decision
    # walk lost its whole controls line this way when 10 decisions filled the frame.
    geometry = frame_geometry(120, 30)
    body = Text("\n".join(f"decision {i}" for i in range(200)))
    footer = Text("⏎ answer · a approve · x reject · A approve-all · r run · q quit")
    frame = render_frame(body, geometry, header=Text("intake"), footer=footer)
    plain = _plain(frame.text)
    assert frame.height == geometry.height
    assert "a approve" in plain  # the footer survived; the body was clipped, not it
    assert "intake" in plain  # the header survived too


def test_header_and_footer_are_pinned_with_symmetric_separators():
    geometry = frame_geometry(140, 50)
    frame = render_frame(
        Text("body"),
        geometry,
        minimum_height=17,
        header=Text("header"),
        footer=Text("footer"),
    )
    lines = _plain(frame.text).splitlines()
    header_row = next(i for i, line in enumerate(lines) if "header" in line)
    body_row = next(i for i, line in enumerate(lines) if "body" in line)
    footer_row = next(i for i, line in enumerate(lines) if "footer" in line)
    rule_rows = [
        i for i, line in enumerate(lines) if "─" * 20 in line and i not in (0, len(lines) - 1)
    ]

    assert header_row == 2
    assert rule_rows == [3, footer_row - 1]
    assert rule_rows[0] < body_row < rule_rows[1]
    assert footer_row == len(lines) - 3
