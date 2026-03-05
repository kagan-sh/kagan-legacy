from typing import TYPE_CHECKING, Any

from kagan.runtime_env import sanitize_startup_environment

if TYPE_CHECKING:
    from collections.abc import Callable

sanitize_startup_environment()


def cli(*args: Any, **kwargs: Any) -> Any:
    from kagan.cli.main import cli as _cli

    _cli_callable: Callable[..., Any] = _cli
    return _cli_callable(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "cli":
        return cli
    raise AttributeError(name)


__all__ = ["cli"]
