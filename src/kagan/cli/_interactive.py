"""Thin prompt-toolkit helpers — the ONLY module that imports prompt_toolkit.

Rich renders into ANSI strings (``render_to_ansi``); prompt-toolkit consumes
them as ``ANSI`` formatted text. They never both own stdout, and ``rich.Live``
is never used (it deadlocks against prompt-toolkit's stdout lock — DESIGN 3.2).

Every helper degrades when stdin is not a TTY (or under tests with a scripted
pipe input) instead of blocking, so the session is testable with a piped input.
"""

import asyncio
import re
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    HorizontalAlign,
    HSplit,
    VerticalAlign,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.patch_stdout import patch_stdout

from kagan.format._console import render_to_str
from kagan.format.shell import FrameGeometry, RenderedFrame, frame_geometry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from prompt_toolkit.input import Input
    from prompt_toolkit.output import Output
    from rich.console import RenderableType


def render_to_ansi(renderable: RenderableType, *, columns: int = 80) -> str:
    """Render a Rich renderable to an ANSI string for prompt-toolkit to consume.

    Goes through the single ``make_console`` factory (the prod / colorful path) so
    the theme'd semantic styles resolve and the test harness shares the construction.
    """
    return render_to_str(renderable, width=columns, no_color=False)


class Cancelled(Exception):
    """Raised when the user cancels a prompt (esc / ctrl-c / EOF)."""


async def navigate(
    render: Callable[[FrameGeometry], RenderedFrame],
    handlers: dict[str, Callable[..., None]],
    *,
    input: Input | None = None,
    output: Output | None = None,
) -> None:
    """Run a full-screen frame loop: ``render()`` paints the ANSI frame, ``handlers``
    maps a key to a callback that may mutate caller state and call ``event.app.exit()``.

    Used by the inbox navigator. The caller owns its cursor/result state in the
    closures it passes as handlers (so this primitive stays presentation-free)."""
    bindings = KeyBindings()
    for key, handler in handlers.items():
        bindings.add(key)(handler)

    app: Application[None] = Application(
        layout=Layout(_centered_frame(render)),
        key_bindings=bindings,
        full_screen=True,
        input=input,
        output=output,
    )
    with patch_stdout():
        await app.run_async()


async def wait_in_frame(
    render: Callable[[FrameGeometry], RenderedFrame],
    awaitable: Awaitable[object],
    *,
    input: Input | None = None,
    output: Output | None = None,
) -> object:
    """Show a read-only frame while an awaitable runs, then return its result.

    Lets the scheduled awaitable run one tick first so an awaitable that settles
    (or raises) immediately — fast results, and piped-input test runs — propagates
    without ever painting a frame, matching the module's non-blocking contract."""
    task = asyncio.ensure_future(awaitable)
    await asyncio.sleep(0)
    if task.done():
        return await task
    bindings = KeyBindings()
    app: Application[None] = Application(
        layout=Layout(_centered_frame(render)),
        key_bindings=bindings,
        full_screen=True,
        input=input,
        output=output,
    )

    def _done(_task) -> None:
        app.invalidate()
        app.exit()

    task.add_done_callback(_done)
    try:
        with patch_stdout():
            await app.run_async()
        return await task
    finally:
        task.remove_done_callback(_done)


async def show_until_dismiss(
    render: Callable[[FrameGeometry], RenderedFrame],
    *,
    keys: Sequence[str] = ("q", "escape", "enter"),
    input: Input | None = None,
    output: Output | None = None,
) -> None:
    """Hold a read-only Rich frame on the alternate screen until a dismiss key.

    The fix for the navigator repaint (DESIGN §1.2 keystone): stats / help / bare
    workspaces are one-shot prints that the navigator's next ``full_screen``
    repaint paints over before the user can read them. This runs the SAME
    ``run_async`` ``full_screen`` Application the navigator uses, so the frame
    owns the screen until dismissed — it is not a print between full-screen apps.
    """
    bindings = KeyBindings()

    def _dismiss(event) -> None:
        event.app.exit()

    for key in keys:
        bindings.add(key)(_dismiss)
    bindings.add("c-c")(_dismiss)

    app: Application[None] = Application(
        layout=Layout(_centered_frame(render)),
        key_bindings=bindings,
        full_screen=True,
        input=input,
        output=output,
    )
    with patch_stdout():
        await app.run_async()


def _open_editor(text: str) -> str | None:
    """Open $EDITOR on ``text`` for a long answer. Called BETWEEN full-screen apps so
    prompt_toolkit has released the terminal. Returns the edited text, or None when no
    editor is available / the edit was aborted. Factored out so tests monkeypatch it
    instead of launching a real editor."""
    try:
        import click

        # click.edit is typed over AnyStr; narrow the result back to str (or None).
        edited = click.edit(text)  # pyrefly: ignore[bad-argument-type]
    except Exception:
        return None
    return edited if isinstance(edited, str) else None


async def prompt_in_frame(
    render: Callable[[FrameGeometry, str], RenderedFrame],
    *,
    default: str = "",
    input: Input | None = None,
    output: Output | None = None,
) -> str | None:
    """Capture a single line of text INSIDE the centered control-plane frame.

    ``render(geometry, text)`` returns the framed `RenderedFrame` with the live input
    drawn in it (compose with `format.shell.render_input_line`). Enter submits,
    esc/ctrl-c cancel (→ None), backspace / ctrl-w / ctrl-u edit, ctrl-o opens $EDITOR.
    Runs the SAME `full_screen` Application as `navigate()`, so the rounded box never
    breaks and the test seam (`input`/`output`) is preserved."""
    text = [default]
    replace_on_type = [bool(default)]
    outcome: dict[str, object] = {"result": None, "edit": False}
    while True:
        outcome["result"] = None
        outcome["edit"] = False
        bindings = KeyBindings()

        @bindings.add(Keys.Any)
        def _type(event) -> None:
            if event.data and event.data.isprintable():
                if replace_on_type[0]:
                    text[0] = event.data
                    replace_on_type[0] = False
                else:
                    text[0] += event.data

        @bindings.add("backspace")
        def _backspace(event) -> None:
            text[0] = text[0][:-1]
            replace_on_type[0] = False

        @bindings.add("c-w")
        def _delete_word(event) -> None:
            text[0] = re.sub(r"\s*\S+\s*$", "", text[0])
            replace_on_type[0] = False

        @bindings.add("c-u")
        def _clear(event) -> None:
            text[0] = ""
            replace_on_type[0] = False

        @bindings.add("enter")
        def _submit(event) -> None:
            outcome["result"] = text[0]
            event.app.exit()

        @bindings.add("c-o")
        def _editor(event) -> None:
            outcome["edit"] = True
            event.app.exit()

        @bindings.add("escape")
        @bindings.add("c-c")
        def _cancel(event) -> None:
            event.app.exit()

        app: Application[None] = Application(
            layout=Layout(_centered_frame(lambda g: render(g, text[0]))),
            key_bindings=bindings,
            full_screen=True,
            input=input,
            output=output,
        )
        with patch_stdout():
            await app.run_async()
        if outcome["edit"]:
            edited = _open_editor(text[0])
            if edited is not None:
                text[0] = edited.rstrip("\n")
                replace_on_type[0] = False
            continue
        return outcome["result"]  # type: ignore[return-value]


async def choose_in_frame(
    render: Callable[[FrameGeometry, int], RenderedFrame],
    count: int,
    *,
    default: int = 0,
    input: Input | None = None,
    output: Output | None = None,
) -> int | None:
    """List selection INSIDE the frame. ``render(geometry, index)`` draws the options
    with the cursor at ``index``. ↑↓/j/k move, enter selects (→ index), esc/ctrl-c
    cancel (→ None)."""
    if count <= 0:
        return None
    state: dict[str, int | None] = {"index": max(0, min(default, count - 1)), "result": None}
    bindings = KeyBindings()

    @bindings.add("up")
    @bindings.add("k")
    def _up(event) -> None:
        state["index"] = (state["index"] - 1) % count  # type: ignore[operator]

    @bindings.add("down")
    @bindings.add("j")
    def _down(event) -> None:
        state["index"] = (state["index"] + 1) % count  # type: ignore[operator]

    @bindings.add("enter")
    def _accept(event) -> None:
        state["result"] = state["index"]
        event.app.exit()

    @bindings.add("escape")
    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit()

    app: Application[None] = Application(
        layout=Layout(_centered_frame(lambda g: render(g, state["index"]))),  # type: ignore[arg-type]
        key_bindings=bindings,
        full_screen=True,
        input=input,
        output=output,
    )
    with patch_stdout():
        await app.run_async()
    return state["result"]


async def confirm_in_frame(
    render: Callable[[FrameGeometry], RenderedFrame],
    *,
    default: bool = True,
    input: Input | None = None,
    output: Output | None = None,
) -> bool:
    """Yes/no INSIDE the frame. ``render(geometry)`` draws the question; y/n decide,
    enter takes ``default``, esc/ctrl-c → ``default``."""
    state = {"result": default}
    bindings = KeyBindings()

    @bindings.add("y")
    @bindings.add("Y")
    def _yes(event) -> None:
        state["result"] = True
        event.app.exit()

    @bindings.add("n")
    @bindings.add("N")
    def _no(event) -> None:
        state["result"] = False
        event.app.exit()

    @bindings.add("enter")
    @bindings.add("escape")
    @bindings.add("c-c")
    def _default(event) -> None:
        state["result"] = default
        event.app.exit()

    app: Application[None] = Application(
        layout=Layout(_centered_frame(render)),
        key_bindings=bindings,
        full_screen=True,
        input=input,
        output=output,
    )
    with patch_stdout():
        await app.run_async()
    return state["result"]


def _live_geometry() -> FrameGeometry:
    size = get_app().output.get_size()
    return frame_geometry(size.columns, size.rows)


def _centered_frame(render: Callable[[FrameGeometry], RenderedFrame]) -> HSplit:
    """A dynamically-sized frame centered by prompt-toolkit on every repaint."""

    def _rendered() -> RenderedFrame:
        return render(_live_geometry())

    frame = Window(
        FormattedTextControl(
            lambda: ANSI(_rendered().text),
            show_cursor=False,
            get_cursor_position=lambda: Point(x=0, y=0),
        ),
        width=lambda: Dimension.exact(_rendered().width),
        height=lambda: Dimension.exact(_rendered().height),
        dont_extend_width=True,
        dont_extend_height=True,
        always_hide_cursor=True,
    )
    row = VSplit([frame], align=HorizontalAlign.CENTER)
    return HSplit([row], align=VerticalAlign.CENTER)


def copy_to_clipboard(value: str) -> bool:
    """Best-effort OS clipboard copy via prompt-toolkit's clipboard. Fails soft.

    Returns True when the copy was attempted via a real clipboard backend; the
    caller prints the command regardless so a failed copy is never silent."""
    try:
        from prompt_toolkit.clipboard.pyperclip import PyperclipClipboard

        PyperclipClipboard().set_text(value)
        return True
    except Exception:
        return False


__all__ = [
    "Cancelled",
    "choose_in_frame",
    "confirm_in_frame",
    "copy_to_clipboard",
    "navigate",
    "patch_stdout",
    "prompt_in_frame",
    "render_to_ansi",
    "show_until_dismiss",
    "wait_in_frame",
]
