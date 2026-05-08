"""`kagan chat` — interactive REPL or single-shot agent prompt.

Thin Click adapter; logic lives in `kagan.cli.chat`.
"""

import importlib

import click
from loguru import logger

from kagan.cli._bootstrap import run_async

_RICH_COMMAND_CLS: type[click.Command] = click.Command
try:
    _rich_click_module = importlib.import_module("rich_click")
    _RICH_COMMAND_CLS = getattr(_rich_click_module, "RichCommand", click.Command)
except ModuleNotFoundError:
    _RICH_COMMAND_CLS = click.Command


@click.command(
    name="chat",
    cls=_RICH_COMMAND_CLS,
    epilog=(
        "Examples:\n"
        "  kagan chat                         Interactive REPL\n"
        "  kagan chat 'fix the bug'           Single-shot prompt\n"
        "  kagan chat --prompt 'fix the bug'  Single-shot prompt\n"
        "  kagan chat --session-id abc123     Resume a session\n\n"
        "Note: --yolo has been removed; use the approval panel's session trust options."
    ),
)
@click.argument("prompt_argument", metavar="PROMPT", required=False)
@click.option(
    "--prompt",
    "prompt_text",
    type=str,
    default=None,
    help="Single-shot mode: run prompt, print result, exit.",
)
@click.option(
    "--session-id",
    "session_id",
    type=str,
    default=None,
    help="Attach to a chat or task session.",
)
@click.option(
    "--agent", "agent", type=str, default=None, help="Override the default agent backend."
)
def chat(
    prompt_argument: str | None,
    prompt_text: str | None,
    session_id: str | None,
    agent: str | None,
) -> None:
    """Start an interactive chat or run a single prompt."""
    logger.debug("Chat command invoked")
    if prompt_argument is not None and prompt_text is not None:
        raise click.UsageError("Use either PROMPT or --prompt, not both.")

    from kagan.cli.chat import run_chat_async

    try:
        run_async(
            run_chat_async(
                prompt=prompt_text if prompt_text is not None else prompt_argument,
                session_id=session_id,
                agent=agent,
            )
        )
    except KeyboardInterrupt:
        raise click.Abort() from None
