"""CLIRenderer — Rich-console rendering for chat events.

Phase 5b extracts the rendering side of ``_OrchestratorACPClient.session_update``
into a dedicated class. The legacy ACP client now constructs ``CLIRenderer``
and forwards each ACP update through the granular hooks below. Phase 5c will
wire ``on_event`` directly to ``ChatEngine.stream_assistant``; today
``on_event`` is provided as a forward-compatible dispatcher but the legacy ACP
client uses the granular methods so that ordering subtleties (Markdown
finalize-before-tool-print) match the prior inline implementation byte-for-byte.

This file contains no behaviour change — the printer closures, ``_GroupedToolDisplay``
state, and ``ToolRunTracker`` interactions all match what ``_chat_acp.py`` did
before the split.
"""

from __future__ import annotations

import contextlib
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from loguru import logger
from prompt_toolkit.application.run_in_terminal import run_in_terminal
from rich.markup import escape as _rich_escape

from kagan.cli.chat._streaming import (
    MarkdownStreamingRegion,
    ResponseChunkBuffer,
    _TurnLiveState,
)
from kagan.cli.chat.tool_runs import ToolRunTracker

if TYPE_CHECKING:
    from collections.abc import Callable

    from rich.console import Console

    from kagan.core.chat.events import ChatEvent

# Approval modals (transient prompt_toolkit Applications) need to coexist with
# the long-lived REPL prompt session. While a modal owns the screen, prints
# from the streaming ACP client must be routed via ``run_in_terminal``; outside
# a modal the outer ``patch_stdout(raw=True)`` already routes them above the
# REPL prompt, so direct calls are cheaper and avoid extra redraw cycles.
_MODAL_DEPTH = 0


@contextlib.contextmanager
def _modal_active():
    """Increment the modal-depth counter for the duration of an approval modal.

    Multiple modals can stack (rare); the depth counter handles nesting safely.
    """
    global _MODAL_DEPTH
    _MODAL_DEPTH += 1
    try:
        yield
    finally:
        _MODAL_DEPTH -= 1


def _modal_depth() -> int:
    return _MODAL_DEPTH


def print_via_terminal(fn: Callable[[], None]) -> None:
    """Print safely above any active prompt_toolkit Application.

    When an approval modal (a transient ``Application``) owns the
    terminal, route through ``run_in_terminal`` so the print doesn't
    collide with the modal's redraw. Outside of modals,
    ``patch_stdout(raw=True)`` in the outer REPL loop already routes
    ``_console.print`` above the toolbar — call ``fn`` directly to
    skip the extra redraw cycle.
    """
    if _MODAL_DEPTH > 0:
        try:
            run_in_terminal(fn)
            return
        except Exception:
            logger.debug("run_in_terminal failed, falling back to direct print", exc_info=True)
    fn()


# ---------------------------------------------------------------------------
# Grouped tool-call display
# ---------------------------------------------------------------------------


class _GroupedToolDisplay:
    """Accumulate parallel tool calls and render them as grouped status lines.

    Groups calls by tool name.  Shows: ``tool_name x N -- done D/N . Xs``.
    """

    def __init__(self) -> None:
        # tool_name -> list of (status, started_at, ended_at)
        self._calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._key_to_name: dict[str, str] = {}

    def start(self, tool_key: str, tool_name: str, started_at: float) -> None:
        self._key_to_name[tool_key] = tool_name
        self._calls[tool_name].append(
            {"key": tool_key, "status": "running", "started": started_at, "ended": None}
        )

    def complete(self, tool_key: str, status: str, ended_at: float) -> None:
        name = self._key_to_name.get(tool_key)
        if name is None:
            return
        for entry in self._calls.get(name, []):
            if entry["key"] == tool_key and entry["status"] == "running":
                entry["status"] = status
                entry["ended"] = ended_at
                break

    def render_lines(self) -> list[str]:
        """Return one display line per tool name."""
        lines = []
        now = time.monotonic()
        for name, entries in self._calls.items():
            total = len(entries)
            done = sum(1 for e in entries if e["status"] in ("completed", "failed"))
            error = sum(1 for e in entries if e["status"] == "failed")
            elapsed = max((now - e["started"]) for e in entries if e["started"] is not None)
            elapsed_text = f"{elapsed:.1f}s"

            if total == 1:
                entry = entries[0]
                if entry["status"] == "running":
                    icon = "●"
                    style = "dim"
                elif entry["status"] == "completed":
                    icon = "✓"
                    style = "green"
                else:
                    icon = "✗"
                    style = "red"
                line = f"  [{style}]{icon} {_rich_escape(name)} · {elapsed_text}[/{style}]"
            else:
                if error > 0:
                    status_text = f"done {done}/{total} · {error} err · {elapsed_text}"
                    style = "red"
                elif done == total:
                    status_text = f"done {total}/{total} · {elapsed_text}"
                    style = "green"
                else:
                    status_text = f"done {done}/{total} · {elapsed_text}"
                    style = "dim"
                icon = "✓" if done == total and error == 0 else "●"
                line = f"  [{style}]{icon} {_rich_escape(name)} x{total} -- {status_text}[/{style}]"
            lines.append(line)
        return lines

    def clear(self) -> None:
        self._calls.clear()
        self._key_to_name.clear()


# ---------------------------------------------------------------------------
# CLIRenderer
# ---------------------------------------------------------------------------


def _make_done_printer(
    console: Console,
    title: str,
    key_arg: str | None,
    status: str,
    started_at: float,
    ended_at: float,
) -> Callable[[], None]:
    def _print() -> None:
        arg_part = f" [dim]({_rich_escape(key_arg)})[/dim]" if key_arg else ""
        elapsed = max(0.0, ended_at - started_at)
        duration = f" [dim]{elapsed:.1f}s[/dim]" if elapsed >= 0.1 else ""
        name = _rich_escape(title)
        if status == "completed":
            console.print(
                f"  [green]●[/green] [dim]Used[/dim] [bold]{name}[/bold]{arg_part}{duration}",
                highlight=False,
            )
        else:
            console.print(
                f"  [red]●[/red] [dim]Used[/dim] [bold]{name}[/bold]{arg_part} [red]failed[/red]",
                highlight=False,
            )

    return _print


class CLIRenderer:
    """Translate ACP/ChatEvent updates into Rich console output for the CLI.

    Phase 5b lifts the rendering side of ``_OrchestratorACPClient.session_update``
    here. Phase 5c will wire this directly to ``engine.stream_assistant()``.
    Today the legacy ACP client constructs ``CLIRenderer`` and forwards each
    update through the granular hooks below; ``on_event`` is the forward-
    compatible dispatcher used by phase 5c.
    """

    def __init__(self, console: Console, *, show_thoughts: bool = False) -> None:
        self._console = console
        self._tool_runs = ToolRunTracker()
        self._grouped_tools = _GroupedToolDisplay()
        self._response_chunks = ResponseChunkBuffer()
        self._md_region = MarkdownStreamingRegion(console, show_thoughts=show_thoughts)
        self.last_usage: Any = None

    # ------------------------------------------------------------------
    # Turn lifecycle
    # ------------------------------------------------------------------

    def start_turn(self, live_state: _TurnLiveState | None = None) -> None:
        self._md_region.discard()
        self._md_region.set_live_state(live_state)
        self._response_chunks.clear()
        self._tool_runs.start_turn()
        self._grouped_tools.clear()
        self.last_usage = None

    def finish_turn(self) -> str:
        self._md_region.finalize()
        return self._response_chunks.get_all().strip()

    def finalize_pending_markdown(self) -> None:
        self._md_region.finalize()

    # ------------------------------------------------------------------
    # Tool report (used by the controller's `/show tool` slash command)
    # ------------------------------------------------------------------

    def tool_report(self, query: str | None) -> tuple[str, bool]:
        return self._tool_runs.tool_report(query)

    # ------------------------------------------------------------------
    # Granular hooks called by the legacy ACP client (phase 5b path)
    # ------------------------------------------------------------------

    def on_assistant_chunk(self, text: str, *, thought: bool = False) -> None:
        if not text:
            return
        if not thought:
            self._response_chunks.append(text)

        def _do_append() -> None:
            self._md_region.append(text, thought=thought)

        print_via_terminal(_do_append)

    def on_tool_call_start(self, update: Any) -> None:
        self._md_region.finalize()
        title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
        tool_key = self._tool_runs.tool_key(update)
        if self._tool_runs.status_for(tool_key) == "started":
            return
        self._tool_runs.set_status(tool_key, "started")
        key_arg = self._tool_runs.extract_tool_key_arg(update)
        run = self._tool_runs.ensure_tool_run(update=update, title=title, key_arg=key_arg)
        run.status = "running"
        run.args = self._tool_runs.serialize_payload(self._tool_runs.extract_tool_args(update))
        self._grouped_tools.start(tool_key, title, run.started_at)

        def _print_start() -> None:
            arg_part = f" [dim]({_rich_escape(key_arg)})[/dim]" if key_arg else ""
            self._console.print(
                f"\n  [dim]●[/dim] [dim]Using[/dim] [bold]{_rich_escape(title)}[/bold]{arg_part}",
                highlight=False,
            )

        print_via_terminal(_print_start)

    def on_tool_call_progress(self, update: Any) -> None:
        self._md_region.finalize()
        status = getattr(update, "status", None)
        tool_key = self._tool_runs.tool_key(update)
        if status and self._tool_runs.status_for(tool_key) == status:
            return
        # ToolCallProgress carries no title/args — fall back to what was stored at start
        existing = self._tool_runs.get_run(tool_key)
        title = (
            getattr(update, "title", None)
            or (existing.title if existing else None)
            or "tool"
        )
        key_arg = self._tool_runs.extract_tool_key_arg(update) or (
            existing.key_arg if existing else None
        )
        run = self._tool_runs.ensure_tool_run(update=update, title=title, key_arg=key_arg)
        if status:
            run.status = str(status)
        args = self._tool_runs.serialize_payload(self._tool_runs.extract_tool_args(update))
        if args:
            run.args = args
        result = self._tool_runs.serialize_payload(self._tool_runs.extract_tool_result(update))
        if result:
            run.result = result
        if status not in ("completed", "failed"):
            return
        self._tool_runs.set_status(tool_key, status)
        run.ended_at = run.ended_at or time.monotonic()
        self._grouped_tools.complete(tool_key, status, run.ended_at)
        print_via_terminal(
            _make_done_printer(self._console, title, key_arg, status, run.started_at, run.ended_at)
        )

    def on_usage_update(self, update: Any) -> None:
        self.last_usage = update

    # ------------------------------------------------------------------
    # ChatEvent dispatcher (phase 5c entry point)
    # ------------------------------------------------------------------

    def on_event(self, event: ChatEvent) -> None:
        """Dispatch a typed ChatEvent through the granular hooks.

        Phase 5b: not yet wired. Phase 5c will route engine.stream_assistant()
        through this. Kept here so the seam is visible and so phase 5c is a
        small wiring change rather than a rewrite.
        """
        match event.kind:
            case "assistant_chunk":
                self.on_assistant_chunk(event.text, thought=event.thought)
            case "tool_call_start":
                self.on_tool_call_start(event)
            case "tool_call_progress":
                self.on_tool_call_progress(event)
            case "usage":
                self.on_usage_update(event)
            case "done":
                # finish_turn() is the controller's responsibility; here we just
                # ensure pending Markdown is flushed.
                self.finalize_pending_markdown()
            case "turn_cancelled" | "error" | "assistant_message":
                self.finalize_pending_markdown()
            case _:
                pass


__all__ = [
    "CLIRenderer",
    "_GroupedToolDisplay",
    "_make_done_printer",
    "_modal_active",
    "_modal_depth",
    "print_via_terminal",
]
