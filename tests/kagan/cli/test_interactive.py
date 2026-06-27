"""In-frame input primitives (Phase 3): prompt/choose/confirm captured INSIDE the
centered control-plane frame, driven via the pipe-input test seam (no raw PromptSession
below the box). These pin that the box never breaks and the editing keys work."""

import asyncio

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.text import Text

from kagan.cli import _interactive
from kagan.format.shell import RenderedFrame, render_frame, render_input_line


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _text_render(geometry, text: str) -> RenderedFrame:
    return render_frame(render_input_line("Answer", text), geometry)


def _choice_render(geometry, index: int) -> RenderedFrame:
    return render_frame(Text(f"index={index}"), geometry)


def _confirm_render(geometry) -> RenderedFrame:
    return render_frame(Text("Proceed?"), geometry)


def test_prompt_in_frame_submits_typed_text() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("hello\r")
        result = _run(_interactive.prompt_in_frame(_text_render, input=pipe, output=DummyOutput()))
    assert result == "hello"


def test_prompt_in_frame_backspace_edits() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("hel\x7flo\r")  # type hel, backspace -> he, type lo -> helo
        result = _run(_interactive.prompt_in_frame(_text_render, input=pipe, output=DummyOutput()))
    assert result == "helo"


def test_prompt_in_frame_accepts_default_on_enter() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("\r")
        result = _run(
            _interactive.prompt_in_frame(
                _text_render,
                default="existing answer",
                input=pipe,
                output=DummyOutput(),
            )
        )
    assert result == "existing answer"


def test_prompt_in_frame_typing_replaces_default() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("replacement answer\r")
        result = _run(
            _interactive.prompt_in_frame(
                _text_render,
                default="old answer",
                input=pipe,
                output=DummyOutput(),
            )
        )
    assert result == "replacement answer"


def test_prompt_in_frame_ctrl_c_cancels_to_none() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("hi\x03")  # ctrl-c cancels
        result = _run(_interactive.prompt_in_frame(_text_render, input=pipe, output=DummyOutput()))
    assert result is None


def test_prompt_in_frame_ctrl_o_opens_editor(monkeypatch) -> None:
    monkeypatch.setattr(_interactive, "_open_editor", lambda t: t + " [edited]")
    with create_pipe_input() as pipe:
        pipe.send_text("draft\x0f\r")  # type draft, ctrl-o -> editor, then enter submits
        result = _run(_interactive.prompt_in_frame(_text_render, input=pipe, output=DummyOutput()))
    assert result == "draft [edited]"


def test_choose_in_frame_moves_and_selects() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("j\r")  # down to index 1, enter selects
        result = _run(
            _interactive.choose_in_frame(_choice_render, 3, input=pipe, output=DummyOutput())
        )
    assert result == 1


def test_choose_in_frame_ctrl_c_cancels() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("\x03")
        result = _run(
            _interactive.choose_in_frame(_choice_render, 3, input=pipe, output=DummyOutput())
        )
    assert result is None


def test_confirm_in_frame_yes_no_and_default() -> None:
    with create_pipe_input() as pipe:
        pipe.send_text("y")
        assert _run(
            _interactive.confirm_in_frame(_confirm_render, input=pipe, output=DummyOutput())
        )
    with create_pipe_input() as pipe:
        pipe.send_text("n")
        assert not _run(
            _interactive.confirm_in_frame(_confirm_render, input=pipe, output=DummyOutput())
        )
    with create_pipe_input() as pipe:
        pipe.send_text("\r")  # enter takes the default
        assert _run(
            _interactive.confirm_in_frame(
                _confirm_render, default=True, input=pipe, output=DummyOutput()
            )
        )
