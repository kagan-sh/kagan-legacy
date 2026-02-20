from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import TYPE_CHECKING, Any

type AsyncCommandHandler = Callable[..., Awaitable[dict[str, Any]]]
type ExceptionResponseBuilder = Callable[
    [Exception, tuple[Any, ...], dict[str, Any]],
    dict[str, Any],
]
type ExceptionMappingFactory = Callable[[], Mapping[type[Exception], ExceptionResponseBuilder]]

if TYPE_CHECKING:
    import logging


def map_command_exceptions(
    mapping: Mapping[type[Exception], ExceptionResponseBuilder] | ExceptionMappingFactory,
    *,
    logger: logging.Logger | None = None,
    log_message: str | None = None,
) -> Callable[[AsyncCommandHandler], AsyncCommandHandler]:
    """Map expected command-boundary exceptions into structured response payloads.

    Unknown exceptions are re-raised so failures remain loud.
    """

    def decorator(fn: AsyncCommandHandler) -> AsyncCommandHandler:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            try:
                return await fn(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # quality-allow-broad-except: explicit boundary mapper
                resolved = mapping() if callable(mapping) else mapping
                for exc_type, build_response in resolved.items():
                    if isinstance(exc, exc_type):
                        if logger is not None and log_message:
                            logger.warning("%s: %s", log_message, exc)
                        return build_response(exc, args, kwargs)
                raise

        return wrapper

    return decorator


__all__ = ["map_command_exceptions"]
