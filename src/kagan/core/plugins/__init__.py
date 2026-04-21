"""kagan.core.plugins — plugin system for extending kagan.

Public API re-exports. Import everything you need from here::

    from kagan.core.plugins import PluginManager, ImporterPlugin, ImportResult
    from kagan.core.plugins import collect_plugin_checks
"""

from kagan.core.plugins._base import (
    ENTRY_POINT_GROUP,
    ImporterPlugin,
    ImportResult,
    Plugin,
    PluginError,
    PluginInfo,
    PluginManager,
    PluginSyncError,
    discover_plugins,
)
from kagan.core.plugins._preflight import collect_plugin_checks

__all__ = [
    "ENTRY_POINT_GROUP",
    "ImportResult",
    "ImporterPlugin",
    "Plugin",
    "PluginError",
    "PluginInfo",
    "PluginManager",
    "PluginSyncError",
    "collect_plugin_checks",
    "discover_plugins",
]
