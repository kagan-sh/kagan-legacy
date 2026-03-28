"""SIGINT signal handling for cancellation and cooperative shutdown."""

import asyncio
import signal
from typing import Any


def install_sigint_handler(
    prompt_task: asyncio.Task[Any],
) -> Any:
    """Install SIGINT handler that cancels the prompt task.

    Args:
        prompt_task: The task to cancel on SIGINT

    Returns:
        The original SIGINT signal handler (for restoration)
    """
    original_handler = signal.getsignal(signal.SIGINT)
    loop = asyncio.get_running_loop()

    def _handle_sigint(*_: Any) -> None:
        loop.call_soon_threadsafe(prompt_task.cancel)

    signal.signal(signal.SIGINT, _handle_sigint)
    return original_handler


def restore_sigint_handler(original_handler: Any) -> None:
    """Restore the original SIGINT handler.

    Args:
        original_handler: The handler returned by install_sigint_handler()
    """
    signal.signal(signal.SIGINT, original_handler)
