"""Pinned-footer Live region that wraps the entire agent reply turn.

A turn (the period from when the user submits a prompt until the agent's
final chunk lands) renders many distinct things: a wave animation while
the agent is "thinking", streamed Markdown chunks, grouped tool-call
status lines, errors, and yolo banners.  Historically each of those paths
printed directly to ``_console`` (or via ``run_in_terminal``) and only
``StreamingMarkdownRegion`` opened a Rich ``Live`` while it had buffered
text.  That meant the bottom toolbar (footer) was only pinned during
markdown streaming and disappeared in between sub-phases.

``TurnLiveRegion`` opens **one** Rich ``Live`` for the whole turn whose
renderable is ``Group(tail, Rule, footer)``.  ``tail`` is the
currently-streaming "live" content (wave frame or in-progress markdown
buffer); committed output (completed tool calls, finalized markdown) is
sent via ``console.print`` while the Live is active — Rich automatically
routes those prints to the scrollback area above the live region, so the
footer stays pinned at the bottom of the terminal for the whole turn.

Approval modals run a separate ``prompt_toolkit`` Application that needs
exclusive control of the screen.  Use :meth:`pause` / :meth:`resume`
around those prompts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger
from rich.console import Group
from rich.live import Live
from rich.rule import Rule
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import ConsoleRenderable

# 4fps so the footer's `◐ ◓ ◑ ◒` thinking-dot keeps spinning between text
# chunks.  Rich coalesces redraws internally so this stays cheap.
_REFRESH_PER_SECOND = 4

_EMPTY_TAIL: Text = Text("")


class TurnLiveRegion:
    """A single Rich Live for one full agent reply turn."""

    def __init__(self, console: Any) -> None:
        self._console = console
        self._live: Live | None = None
        self._tail: ConsoleRenderable = _EMPTY_TAIL
        self._paused_for_modal = False

    # ---- lifecycle ---------------------------------------------------
    def start(self) -> None:
        if self._live is not None:
            return
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=_REFRESH_PER_SECOND,
            transient=True,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live is None:
            return
        try:
            self._live.stop()
        except Exception:  # pragma: no cover — defensive
            logger.opt(exception=True).debug("TurnLiveRegion.stop failed")
        finally:
            self._live = None
            self._tail = _EMPTY_TAIL

    def pause(self) -> None:
        """Stop the Live so a prompt_toolkit modal can take over the screen."""
        if self._live is None:
            return
        self._paused_for_modal = True
        try:
            self._live.stop()
        except Exception:  # pragma: no cover — defensive
            logger.opt(exception=True).debug("TurnLiveRegion.pause failed")
        finally:
            self._live = None

    def resume(self) -> None:
        """Restart the Live after a paused modal returns."""
        if not self._paused_for_modal:
            return
        self._paused_for_modal = False
        self.start()

    # ---- tail content ------------------------------------------------
    def set_tail(self, renderable: ConsoleRenderable | None) -> None:
        """Replace the live tail (wave frame, streaming markdown, …)."""
        self._tail = renderable if renderable is not None else _EMPTY_TAIL
        self._refresh()

    def clear_tail(self) -> None:
        self.set_tail(None)

    # ---- committed output -------------------------------------------
    def print(self, *args: Any, **kwargs: Any) -> None:
        """Commit a renderable above the live region.

        While Live is active Rich routes ``console.print`` calls to the
        scrollback area above the live tail, so this is just a
        delegating helper that keeps callers from importing the console
        directly.
        """
        self._console.print(*args, **kwargs)

    # ---- internals --------------------------------------------------
    def _render(self) -> ConsoleRenderable:
        try:
            from kagan.cli.chat.repl import _build_rich_footer

            footer: ConsoleRenderable | None = _build_rich_footer()
        except Exception:  # pragma: no cover — never let footer break a turn
            logger.opt(exception=True).debug("Failed to build Rich footer")
            footer = None

        parts: list[ConsoleRenderable] = []
        if self._tail is not None and self._tail is not _EMPTY_TAIL:
            parts.append(self._tail)
        if footer is not None:
            if parts:
                parts.append(Rule(style="dim"))
            parts.append(footer)
        if not parts:
            return _EMPTY_TAIL
        return Group(*parts)

    def _refresh(self) -> None:
        if self._live is None:
            return
        try:
            self._live.update(self._render())
        except Exception:  # pragma: no cover — defensive
            logger.opt(exception=True).debug("TurnLiveRegion.update failed")

    @property
    def is_active(self) -> bool:
        return self._live is not None
