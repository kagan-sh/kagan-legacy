"""kagan.plugins — plugin protocol, lifecycle, and discovery.

Plugins extend kagan without modifying core. Built-in plugins register via
entry points in pyproject.toml; community plugins do the same in their own
packages. Discovery uses importlib.metadata — no central registry to edit.

Built-in plugins (shipped with the ``kagan`` package) are trusted. Community
plugins trigger a provenance warning on load — the user is responsible for
evaluating third-party code.

    from kagan.plugins import PluginManager

    manager = PluginManager(client)
    await manager.load()           # discover & register entry-point plugins
    result = await manager.sync("github", project_id="abc123")
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from importlib.metadata import Distribution, PackageNotFoundError, entry_points, version

from loguru import logger

from kagan.core import KaganCore, PreflightCheckResult
from kagan.core.errors import KaganError

ENTRY_POINT_GROUP = "kagan.plugins"
_BUILTIN_PACKAGE = "kagan"
_BUILTIN_SOURCE_URL = "https://github.com/aorumbayev/kagan"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PluginError(KaganError):
    """Base for all plugin errors."""


class PluginSyncError(PluginError):
    """Raised when a sync operation fails."""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of an idempotent sync operation."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped

    def with_error(self, error: str) -> "ImportResult":
        """Return a new ImportResult with an additional error."""
        return replace(self, errors=(*self.errors, error))


# ---------------------------------------------------------------------------
# Plugin provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PluginInfo:
    """Provenance metadata for a discovered plugin.

        Built-in plugins (package == "kagan") are trusted. Community plugins
    carry their source package, version, and project URL so users can
    evaluate them before use.
    """

    name: str
    cls: type["Plugin"]
    package: str
    version: str
    source_url: str
    builtin: bool


def _extract_source_url(dist: Distribution) -> str:
    """Best-effort extraction of a project URL from distribution metadata."""
    # Try Home-page first
    homepage = dist.metadata.get("Home-page", "")
    if homepage and homepage != "UNKNOWN":
        return homepage

    # Try Project-URL entries (format: "Label, URL")
    for entry in dist.metadata.get_all("Project-URL") or []:
        if "," in entry:
            label, url = entry.split(",", 1)
            label_lower = label.strip().lower()
            if label_lower in ("repository", "source", "homepage", "github"):
                return url.strip()

    return "(unknown)"


_COMMUNITY_DISCLAIMER = """\
⚠  Community plugin '{name}' loaded from package '{package}' v{version}
   Source: {source_url}

   This plugin is NOT maintained by the kagan project.
   Community plugins are loaded at your own risk — review the source code
   and evaluate third-party plugins for security and correctness before use.

   To improve plugin safety, contribute to the kagan project:
   https://github.com/aorumbayev/kagan\
"""


# ---------------------------------------------------------------------------
# Plugin ABCs
# ---------------------------------------------------------------------------


class Plugin(ABC):
    """Base class for all kagan plugins.

    Subclass and register via entry points::

        [project.entry-points."kagan.plugins"]
        github = "kagan.plugins._github:GitHubImporter"
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g. 'github')."""

    async def setup(self, client: KaganCore) -> None:  # noqa: B027
        """Called once when the plugin is registered. Store the client reference."""
        ...

    async def teardown(self) -> None:  # noqa: B027
        """Called when the plugin is unregistered."""
        ...

    def preflight(self) -> list[PreflightCheckResult]:
        """Return health checks for this plugin's external dependencies.

        Returns core PreflightCheckResult objects so the existing doctor renderer
        works unchanged. Default: no checks.
        """
        return []


class ImporterPlugin(Plugin, ABC):
    """Plugin that imports external items as kagan tasks."""

    def configure(self, config: object) -> None:
        """Configure the plugin before sync. Subclasses override to accept typed config."""

    @abstractmethod
    async def sync(self, project_id: str) -> ImportResult:
        """Pull external items into the given project. Must be idempotent."""


def _builtin_plugin_classes() -> dict[str, type[Plugin]]:
    from kagan.plugins._github import GitHubImporter

    return {
        "github": GitHubImporter,
    }


def _current_kagan_version() -> str:
    try:
        return version(_BUILTIN_PACKAGE)
    except PackageNotFoundError:
        return "(unknown)"


def _community_plugins_enabled() -> bool:
    value = os.environ.get("KAGAN_ENABLE_COMMUNITY_PLUGINS", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_plugins() -> dict[str, PluginInfo]:
    """Discover installed plugins via entry points.

        Returns a mapping of plugin name -> PluginInfo for all packages
        that declare a ``kagan.plugins`` entry point group. Each entry
    carries provenance info (package name, version, source URL, builtin flag).
    """
    discovered: dict[str, PluginInfo] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
            if not (isinstance(cls, type) and issubclass(cls, Plugin)):
                logger.warning("Entry point {!r} is not a Plugin subclass, skipping", ep.name)
                continue

            # Extract provenance from distribution metadata
            dist = ep.dist
            package = dist.name if dist else "(unknown)"
            version = dist.version if dist else "(unknown)"
            source_url = _extract_source_url(dist) if dist else "(unknown)"
            builtin = package.lower() == _BUILTIN_PACKAGE

            if not builtin and not _community_plugins_enabled():
                logger.info(
                    "Community plugin {!r} discovered from {} but ignored "
                    "(set KAGAN_ENABLE_COMMUNITY_PLUGINS=1 to enable)",
                    ep.name,
                    package,
                )
                continue

            discovered[ep.name] = PluginInfo(
                name=ep.name,
                cls=cls,
                package=package,
                version=version,
                source_url=source_url,
                builtin=builtin,
            )
        except ImportError as exc:
            logger.warning(
                "Failed to import plugin {!r}: {} (missing dependency?)",
                ep.name,
                exc,
            )
        except AttributeError as exc:
            logger.warning(
                "Plugin entry point {!r} references invalid attribute: {}",
                ep.name,
                exc,
            )
        except TypeError as exc:
            logger.warning(
                "Plugin entry point {!r} type error (wrong class signature?): {}",
                ep.name,
                exc,
            )

    builtin_version = _current_kagan_version()
    for name, cls in _builtin_plugin_classes().items():
        if name in discovered:
            continue
        logger.warning(
            "Built-in plugin {!r} missing from entry points; registering fallback.",
            name,
        )
        discovered[name] = PluginInfo(
            name=name,
            cls=cls,
            package=_BUILTIN_PACKAGE,
            version=builtin_version,
            source_url=_BUILTIN_SOURCE_URL,
            builtin=True,
        )
    return discovered


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class PluginManager:
    """Registry and lifecycle manager for plugins.

    Construct with a KaganCore, then call ``load()`` to discover and
    register all installed plugins via entry points::

        manager = PluginManager(client)
        await manager.load()
        result = await manager.sync("github", project_id="...")

    Community plugins (not shipped with kagan) trigger a provenance warning
    on load. The warnings are collected and accessible via ``community_warnings``.
    """

    def __init__(self, client: KaganCore) -> None:
        self._client = client
        self._plugins: dict[str, Plugin] = {}
        self._meta: dict[str, PluginInfo] = {}
        self._community_warnings: list[str] = []

    async def load(self) -> list[str]:
        """Discover and register all entry-point plugins. Returns names loaded."""
        discovered = discover_plugins()
        loaded: list[str] = []
        for name, meta in discovered.items():
            if name in self._plugins:
                continue
            self._meta[name] = meta

            # Emit provenance warning for community plugins
            if not meta.builtin:
                warning = _COMMUNITY_DISCLAIMER.format(
                    name=meta.name,
                    package=meta.package,
                    version=meta.version,
                    source_url=meta.source_url,
                )
                self._community_warnings.append(warning)
                logger.warning(warning)

            plugin = meta.cls()
            if plugin.name != name:
                logger.warning(
                    "Plugin class {!r} reports name {!r} but entry point is {!r}, skipping",
                    meta.cls.__name__,
                    plugin.name,
                    name,
                )
                continue
            await self.register(plugin)
            loaded.append(name)
        if loaded:
            logger.info("Plugins loaded: {}", ", ".join(loaded))
        return loaded

    async def register(self, plugin: Plugin) -> None:
        """Register and set up a single plugin instance."""
        name = plugin.name
        if name in self._plugins:
            raise PluginError(f"Plugin {name!r} is already registered")
        await plugin.setup(self._client)
        self._plugins[name] = plugin
        logger.debug("Plugin registered: {}", name)

    async def unregister(self, name: str) -> None:
        """Tear down and remove a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin is not None:
            await plugin.teardown()
            self._meta.pop(name, None)
            logger.debug("Plugin unregistered: {}", name)

    def get(self, name: str) -> Plugin:
        """Get a registered plugin by name. Raises PluginError if not found."""
        plugin = self._plugins.get(name)
        if plugin is None:
            available = ", ".join(sorted(self._plugins)) or "(none)"
            raise PluginError(f"Plugin {name!r} not found. Installed: {available}")
        return plugin

    def get_import(self, name: str) -> ImporterPlugin:
        """Get a registered import plugin by name. Raises PluginError if wrong type."""
        plugin = self.get(name)
        if not isinstance(plugin, ImporterPlugin):
            raise PluginError(f"Plugin {name!r} is not an import plugin")
        return plugin

    def get_meta(self, name: str) -> PluginInfo | None:
        """Get provenance metadata for a plugin, if available."""
        return self._meta.get(name)

    def is_builtin(self, name: str) -> bool:
        """Return True if the plugin ships with kagan."""
        meta = self._meta.get(name)
        return meta.builtin if meta else False

    @property
    def available(self) -> list[str]:
        """Sorted list of registered plugin names."""
        return sorted(self._plugins)

    @property
    def community_warnings(self) -> list[str]:
        """Provenance warnings emitted during load for community plugins."""
        return list(self._community_warnings)

    def preflight(self) -> list[PreflightCheckResult]:
        """Collect health checks from all registered plugins."""
        checks: list[PreflightCheckResult] = []
        for plugin in self._plugins.values():
            checks.extend(plugin.preflight())
        return checks

    async def sync(self, name: str, *, project_id: str) -> ImportResult:
        """Run an import sync for the named plugin. Convenience wrapper."""
        plugin = self.get_import(name)
        return await plugin.sync(project_id)

    async def teardown_all(self) -> None:
        """Tear down all registered plugins."""
        for name in list(self._plugins):
            await self.unregister(name)


__all__ = [
    "ENTRY_POINT_GROUP",
    "ImportResult",
    "ImporterPlugin",
    "Plugin",
    "PluginError",
    "PluginInfo",
    "PluginManager",
    "PluginSyncError",
    "discover_plugins",
]
