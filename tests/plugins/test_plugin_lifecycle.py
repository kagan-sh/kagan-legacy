"""Tests: Plugin system lifecycle — registration, discovery, teardown, provenance."""

from unittest.mock import patch

import pytest

from kagan.core import KaganCore
from kagan.plugins import ImporterPlugin, ImportResult, Plugin, PluginError, PluginManager

pytestmark = [pytest.mark.plugins]


# ---------------------------------------------------------------------------
# Helpers — minimal concrete plugins for testing
# ---------------------------------------------------------------------------


class _StubPlugin(Plugin):
    @property
    def name(self) -> str:
        return "stub"

    async def setup(self, client: KaganCore) -> None:
        self._setup_called = True

    async def teardown(self) -> None:
        self._teardown_called = True


class _StubImport(ImporterPlugin):
    @property
    def name(self) -> str:
        return "stub-import"

    async def setup(self, client: KaganCore) -> None:
        self._client = client

    async def sync(self, project_id: str) -> ImportResult:
        return ImportResult(created=1, skipped=2)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    c = KaganCore(db_path=tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
async def manager(client):
    return PluginManager(client)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


async def test_register_and_get(manager: PluginManager) -> None:
    """Registering a plugin makes it retrievable by name."""
    plugin = _StubPlugin()
    await manager.register(plugin)

    assert "stub" in manager.available
    assert manager.get("stub") is plugin


async def test_register_calls_setup(manager: PluginManager) -> None:
    """Registration calls plugin.setup() with the client."""
    plugin = _StubPlugin()
    await manager.register(plugin)
    assert plugin._setup_called is True


async def test_register_duplicate_raises(manager: PluginManager) -> None:
    """Registering the same plugin name twice raises PluginError."""
    await manager.register(_StubPlugin())
    with pytest.raises(PluginError, match="already registered"):
        await manager.register(_StubPlugin())


async def test_get_unknown_raises(manager: PluginManager) -> None:
    """Getting an unregistered plugin raises PluginError with available list."""
    with pytest.raises(PluginError, match="not found"):
        manager.get("nonexistent")


# ---------------------------------------------------------------------------
# Import plugin typing
# ---------------------------------------------------------------------------


async def test_get_import_returns_import_plugin(manager: PluginManager) -> None:
    """get_import() returns ImportPlugin subclass."""
    await manager.register(_StubImport())
    plugin = manager.get_import("stub-import")
    assert isinstance(plugin, ImporterPlugin)


async def test_get_import_rejects_non_import(manager: PluginManager) -> None:
    """get_import() raises PluginError for non-import plugins."""
    await manager.register(_StubPlugin())
    with pytest.raises(PluginError, match="not an import plugin"):
        manager.get_import("stub")


# ---------------------------------------------------------------------------
# Sync convenience
# ---------------------------------------------------------------------------


async def test_sync_convenience(manager: PluginManager) -> None:
    """manager.sync() delegates to the import plugin."""
    await manager.register(_StubImport())
    # Need a project for sync
    project = await manager._client.projects.create("Test")
    await manager._client.projects.set_active(project.id)

    result = await manager.sync("stub-import", project_id=project.id)
    assert result.created == 1
    assert result.skipped == 2


async def test_load_includes_builtin_github_without_entry_points(
    manager: PluginManager,
) -> None:
    with patch("kagan.plugins._base.entry_points", return_value=[]):
        await manager.load()

    assert "github" in manager.available
    assert manager.is_builtin("github") is True


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


async def test_unregister_calls_teardown(manager: PluginManager) -> None:
    """Unregistering a plugin calls teardown and removes it from available."""
    plugin = _StubPlugin()
    await manager.register(plugin)
    await manager.unregister("stub")

    assert "stub" not in manager.available
    assert plugin._teardown_called is True


async def test_teardown_all(manager: PluginManager) -> None:
    """teardown_all() removes all plugins."""
    await manager.register(_StubPlugin())
    await manager.register(_StubImport())
    assert len(manager.available) == 2

    await manager.teardown_all()
    assert len(manager.available) == 0


# ---------------------------------------------------------------------------
# SyncResult
# ---------------------------------------------------------------------------


def test_sync_result_total() -> None:
    """SyncResult.total sums created + updated + skipped."""
    result = ImportResult(created=3, updated=1, skipped=5)
    assert result.total == 9
