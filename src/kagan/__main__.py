"""CLI entry point for Kagan."""

from __future__ import annotations

import sys

if sys.version_info < (3, 12):  # noqa: UP036
    print("Error: Kagan requires Python 3.12 or higher.")
    print(
        "You are running Python {}.{}".format(  # noqa: UP032
            sys.version_info.major, sys.version_info.minor
        )
    )
    print("Please upgrade Python: https://www.python.org/downloads/")
    sys.exit(1)

_original_unraisablehook = sys.unraisablehook


def _suppress_event_loop_closed(unraisable: sys.UnraisableHookArgs) -> None:
    """Suppress 'Event loop is closed' errors from asyncio cleanup."""
    if isinstance(unraisable.exc_value, RuntimeError) and "Event loop is closed" in str(
        unraisable.exc_value
    ):
        return
    _original_unraisablehook(unraisable)


sys.unraisablehook = _suppress_event_loop_closed

from kagan.cli.commands.root import cli  # noqa: E402
from kagan.cli.commands.tui import tui  # noqa: E402

__all__ = ["cli", "tui"]


if __name__ == "__main__":
    cli()
