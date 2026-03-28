# Plugin System Architecture — `kagan.plugins`

*Entry-point discovery, provenance-aware, Zen of Python.*

______________________________________________________________________

## References

| Package                | Use                                                          |
| ---------------------- | ------------------------------------------------------------ |
| **importlib.metadata** | Entry-point discovery: `entry_points(group="kagan.plugins")` |

______________________________________________________________________

## Context

`kagan.plugins` extends kagan without modifying core. Plugins register via Python entry points
in `pyproject.toml` — no central registry. Discovery uses `importlib.metadata`.

Two trust levels: **built-in** (shipped with kagan) and **community** (third-party).
Community plugins trigger a provenance warning on load.

______________________________________________________________________

## Design Principles

1. **Entry-point discovery** — plugins declare `[project.entry-points."kagan.plugins"]` in
   `pyproject.toml`. No registry to maintain.
1. **ABC hierarchy** — `Plugin` → `ImporterPlugin`. Clear contracts.
1. **Provenance-aware** — `PluginInfo` carries package, version, source URL, builtin flag.
1. **Configure before sync** — `configure()` sets options before `sync()`. No constructor args.
1. **Idempotent sync** — `ImportResult` tracks created/updated/skipped/errors.
1. **Health checks reuse core** — plugins return `PreflightCheckResult` for doctor rendering.
1. **Lazy integration** — MCP and CLI import `kagan.plugins` inside function bodies.

______________________________________________________________________

## Module Layout

```text
kagan/plugins/
├── __init__.py       # public API re-exports
├── _base.py          # Plugin ABCs, PluginManager, discovery, errors
└── _github.py        # GitHubImporter — GitHub Issues → kagan tasks
```

______________________________________________________________________

## Class Hierarchy

```text
Plugin (ABC)
├── name: str (abstract property)
├── setup(client) — on register
├── teardown()    — on unregister
└── preflight() → list[PreflightCheckResult]

ImporterPlugin(Plugin, ABC)
├── configure(config) — set options
└── sync(project_id) → ImportResult

GitHubImporter(ImporterPlugin)
├── name = "github"
├── configure(config: GitHubImportConfig)
├── preflight() → [gh_cli, gh_auth]
└── sync(project_id) → ImportResult
```

______________________________________________________________________

## PluginManager

| Method                     | Description                                   |
| -------------------------- | --------------------------------------------- |
| `load()`                   | Discover and register all plugins             |
| `register(plugin)`         | Set up and register a plugin                  |
| `unregister(name)`         | Tear down and remove                          |
| `get(name)`                | Get plugin. Raises `PluginError` if missing   |
| `get_import(name)`         | Get as `ImporterPlugin`. Raises if wrong type |
| `get_meta(name)`           | Provenance metadata (`PluginInfo`)            |
| `is_builtin(name)`         | True if plugin ships with kagan               |
| `available`                | Sorted list of registered plugin names        |
| `community_warnings`       | Warnings emitted during `load()`              |
| `preflight()`              | Collect health checks from all plugins        |
| `sync(name, project_id=…)` | Convenience wrapper                           |
| `teardown_all()`           | Tear down all plugins                         |

______________________________________________________________________

## Discovery Flow

```text
pyproject.toml → entry_points(group="kagan.plugins")
                      ↓
               discover_plugins()
                 ├── Load entry point classes
                 ├── Verify issubclass(cls, Plugin)
                 └── Extract provenance metadata
                      ↓
               PluginManager.load()
                 ├── Register plugins
                 └── Emit warnings for community plugins
```

______________________________________________________________________

## Provenance

`PluginInfo` (frozen dataclass):

| Field        | Source                       |
| ------------ | ---------------------------- |
| `name`       | Entry-point name             |
| `package`    | Distribution package         |
| `version`    | Distribution version         |
| `source_url` | Project URL from metadata    |
| `builtin`    | `package.lower() == "kagan"` |

Community plugins emit a warning with package, version, and source URL.

______________________________________________________________________

## Error Hierarchy

```text
KaganError
├── PluginError         — base plugin error
│   └── PluginSyncError — sync operation failure
```

______________________________________________________________________

## GitHub Import Plugin

Imports GitHub issues as kagan tasks via `gh` CLI. Label conventions auto-map:

| GitHub Label        | Kagan Field         |
| ------------------- | ------------------- |
| `priority:critical` | `Priority.CRITICAL` |
| `priority:high`     | `Priority.HIGH`     |
| `priority:medium`   | `Priority.MEDIUM`   |
| `priority:low`      | `Priority.LOW`      |

**Sync Map**: Issue→task mapping persists in settings under
`plugin.github.{owner}/{repo}.sync_map`. Re-running skips imported issues.
Deleted tasks are re-imported.

**Preflight Checks**:

- `gh_cli` — PASS if `gh` on PATH, else WARN
- `gh_auth` — PASS if `gh auth token` succeeds, else WARN

______________________________________________________________________

## Integration Points

**CLI** (`kagan.cli.plugins`):

- `kagan plugins sync` — sync from plugin source
- `kagan plugins list` — list installed plugins
- `kagan plugins check` — run preflight checks

**MCP** (`kagan.mcp.toolsets.plugins`):

- `plugins_sync` — sync issues (Admin tier)
- `plugins_preflight` — check prerequisites (Readonly tier)

**Doctor**: Calls `PluginManager.preflight()` to include plugin health checks.

______________________________________________________________________

## Dependency Direction

```text
kagan.plugins ──► kagan.core
kagan.cli     ──► kagan.plugins  (lazy)
kagan.mcp     ──► kagan.plugins  (lazy)
kagan.core    ──✘──► kagan.plugins
kagan.tui     ──✘──► kagan.plugins
```

______________________________________________________________________

## Testing

Tests in `tests/plugins/`:

- `test_plugin_lifecycle.py` — Manager, discovery, errors
- `test_github_import.py` — sync, skip, re-import, labels

Uses `FakeGitHubPlugin` and `FakeGhCli`. No real API calls.

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted               | Why                                              |
| --------------------- | ------------------------------------------------ |
| Plugin config files   | `configure()` API + settings table is sufficient |
| Hot reload            | Discover once per `load()`. Restart required.    |
| TUI integration       | No UI surface needed yet                         |
| Plugin marketplace    | Entry points + pip install is sufficient         |
| Dependency resolution | Each plugin manages own external deps            |
