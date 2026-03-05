from typing import TYPE_CHECKING

from kagan.runtime_env import sanitize_startup_environment

if TYPE_CHECKING:
    from collections.abc import Callable


def main() -> int | None:
    sanitize_startup_environment()

    from kagan.cli.main import cli

    cli_callable: Callable[[], int | None] = cli
    return cli_callable()
