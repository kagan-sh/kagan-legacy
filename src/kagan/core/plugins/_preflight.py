"""Plugin preflight collection helper.

Exposes a single ``collect_plugin_checks`` function that loads all plugins
via PluginManager and returns their combined preflight results.  Kept in its
own module so it can be imported without pulling in the full plugin lifecycle.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from kagan.core.errors import KaganError

if TYPE_CHECKING:
    from kagan.core._preflight import PreflightCheckResult


async def _load_and_collect(manager: object) -> list[PreflightCheckResult]:
    """Load plugins on *manager* then return their preflight results."""
    import asyncio
    from collections.abc import Coroutine

    load = getattr(manager, "load", None)
    preflight = getattr(manager, "preflight", None)
    if callable(load):
        result = load()
        if isinstance(result, Coroutine) or asyncio.isfuture(result):
            await result
    if callable(preflight):
        checks = preflight()
        if isinstance(checks, list):
            return checks  # type: ignore[return-value]
    return []


def collect_plugin_checks(client: object) -> list[PreflightCheckResult]:
    """Synchronously load plugins and collect their preflight results.

    Constructs a fresh :class:`~kagan.core.plugins.PluginManager` from
    *client*, loads all entry-point plugins, and returns the combined list of
    :class:`~kagan.core._preflight.PreflightCheckResult` objects.

    Any import, runtime, or kagan error is caught and logged at DEBUG level so
    plugin failures never block the doctor command.
    """
    from kagan.core.plugins._base import PluginManager

    try:
        manager = PluginManager(client)
        return asyncio.run(_load_and_collect(manager))
    except (ImportError, KaganError, RuntimeError):
        logger.opt(exception=True).debug("Plugin preflight collection failed")
        return []
