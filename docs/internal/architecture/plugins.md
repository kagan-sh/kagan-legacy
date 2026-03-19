# Plugin System Architecture — `kagan.plugins`

*Design principles: entry-point discovery, provenance-aware, Zen of Python.*

______________________________________________________________________

## References

| Package                | Repo                                                                | Use                                                                                      |
| ---------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **importlib.metadata** | [stdlib](https://docs.python.org/3/library/importlib.metadata.html) | Entry-point discovery: `entry_points(group="kagan.plugins")`.                            |
| **Loguru**             | [Delgan/loguru](https://github.com/Delgan/loguru)                   | Structured logging. Config in core — see `docs/internal/architecture/core.md` § Logging. |

______________________________________________________________________

## Context

`kagan.plugins` extends kagan without modifying core. Plugins register via Python entry points
in `pyproject.toml` — no central registry to edit. Discovery uses `importlib.metadata`.

Two trust levels: **built-in** (shipped with the `kagan` package) and **community** (third-party
packages). Community plugins trigger a provenance warning on load — the user must evaluate
third-party code.

The first built-in plugin imports GitHub issues as kagan tasks using the `gh` CLI.

______________________________________________________________________

## Design Principles

```text
Simple is better than complex.
There should be one obvious way to do it.
Explicit is better than implicit.
```

1. **Entry-point discovery** — plugins declare `[project.entry-points."kagan.plugins"]` in their
   `pyproject.toml`. No plugin registry to maintain.

1. **ABC hierarchy** — `Plugin` → `ImporterPlugin`. Each type has a clear contract.

1. **PluginInfo** carries package name, version, source URL, and builtin flag.

1. **Provenance-aware** — `PluginInfo` carries package name, version, source URL, and builtin flag.
   Community plugins get a visible warning.

1. **Configure before sync** — `ImporterPlugin.configure(config)` sets options before `sync()`.

   No constructor arguments required (entry-point discovery instantiates with no args).

1. **Idempotent sync** — `ImportResult` tracks created/updated/skipped/errors. Re-running is safe.

1. **Health checks reuse core** — plugins return `PreflightCheckResult` objects, so the doctor renderer works unchanged.

1. **Health checks reuse core** — plugins return `PreflightCheckResult` objects, so the doctor renderer works unchanged.

1. **Lazy integration** — MCP and CLI import `kagan.plugins` inside function bodies, not at module top-level.

______________________________________________________________________

## Module Layout

```text
kagan/plugins/
├── __init__.py       # re-exports public API
├── _base.py          # Plugin ABCs, PluginManager, discovery, errors, result types
└── _github.py        # GitHubImporter — GitHub Issues → kagan tasks

└── _github.py        # GitHubImporter — GitHub Issues → kagan tasks
```

3 files. Flat. One ABC module, one concrete plugin. (Entry-point name must match plugin.name)

______________________________________________________________________

## Class Hierarchy

```text
Plugin (ABC)
├── name: str (abstract property)
├── setup(client)           — called once on register
├── teardown()              — called on unregister
└── preflight() → list[PreflightCheckResult]  — health checks (default: [])

ImporterPlugin(Plugin, ABC)
├── configure(config)  — set options before sync
└── sync(project_id) → ImportResult  (abstract)

GitHubImporter(ImporterPlugin)
├── name = "github"
├── configure(config: GitHubImportConfig)
├── preflight() → [gh_cli check, gh_auth check]
└── sync(project_id) → ImportResult


ImporterPlugin(Plugin, ABC)
├── configure(config)  — set options before sync
└── sync(project_id) → ImportResult  (abstract)

GitHubImporter(ImporterPlugin)
├── name = "github"
├── configure(config: GitHubImportConfig)
├── preflight() → [gh_cli check, gh_auth check]
└── sync(project_id) → ImportResult
```

______________________________________________________________________

## PluginManager

Lifecycle manager and registry. One per use site (MCP lifespan, CLI command).

| Method             | Description                                              |
| ------------------ | -------------------------------------------------------- |
| `load()`           | Discover entry-point plugins, register all, return names |
| `register(plugin)` | Set up and register a single plugin instance             |
| `unregister(name)` | Tear down and remove a plugin                            |
| `get(name)`        | Get registered plugin. Raises `PluginError` if missing   |
| `get_import(name)` | Get as `ImporterPlugin`. Raises if wrong type            |
| `get_meta(name)`   | Provenance metadata (`PluginInfo`)                       |

| `get_meta(name)` | Provenance metadata (`PluginInfo`) |
| `is_builtin(name)` | True if plugin ships with kagan |
| `available` | Sorted list of registered plugin names |
| `community_warnings` | Provenance warnings emitted during `load()` |
| `preflight()` | Collect health checks from all plugins |
| `sync(name, project_id=…)` | Convenience: `get_import(name).sync(project_id)` |
| `teardown_all()` | Tear down all registered plugins |
| `get_meta(name)` | Provenance metadata (`PluginInfo`) |
| `is_builtin(name)` | True if plugin ships with kagan |
| `available` | Sorted list of registered plugin names |
| `community_warnings` | Provenance warnings emitted during `load()` |
| `preflight()` | Collect health checks from all plugins |
| `sync(name, project_id=…)` | Convenience: `get_import(name).sync(project_id)` |
| `teardown_all()` | Tear down all registered plugins |

______________________________________________________________________

## Discovery Flow

```text
pyproject.toml
  [project.entry-points."kagan.plugins"]
  github = "kagan.plugins._github:GitHubImporter"

     │
     ▼
importlib.metadata.entry_points(group="kagan.plugins")
     │
     ▼
discover_plugins()
  ├── Load each entry point class
  ├── Verify issubclass(cls, Plugin)
  ├── Extract provenance from distribution metadata
  └── Return dict[name → PluginInfo]

     │
     ▼
PluginManager.load()
  ├── Call discover_plugins()
  ├── Verify plugin.name matches entry-point name
  ├── Emit provenance warning for community plugins
  ├── Register each plugin (setup + store)
  └── Return loaded names
```

______________________________________________________________________

## Provenance

`PluginInfo` is a frozen dataclass carrying trust metadata:

| Field        | Type   | Source                                |
| ------------ | ------ | ------------------------------------- |
| `name`       | `str`  | Entry-point name                      |
| `cls`        | `type` | Plugin class                          |
| `package`    | `str`  | Distribution package name             |
| `version`    | `str`  | Distribution version                  |
| `source_url` | `str`  | Best-effort project URL from metadata |
| `builtin`    | `bool` | True if `package.lower() == "kagan"`  |

Community plugins (not built-in) emit a formatted warning including package, version,
and source URL. The warning is visible in CLI output and stored in `manager.community_warnings`.

______________________________________________________________________

## Error Hierarchy

```text
KaganError
├── PluginError        — base for all plugin errors
│   └── PluginSyncError — sync operation failure (gh CLI error, JSON parse, etc.)

```

______________________________________________________________________

## GitHub Import Plugin

### What It Does

Imports open GitHub issues as kagan tasks. Uses `gh` CLI for authentication — no token
management. Label conventions auto-map to task properties:

| GitHub Label        | Kagan Field         |
| ------------------- | ------------------- |
| `priority:critical` | `Priority.CRITICAL` |
| `priority:high`     | `Priority.HIGH`     |
| `priority:medium`   | `Priority.MEDIUM`   |
| `priority:low`      | `Priority.LOW`      |
| `kagan:auto`        | ignored legacy label |
| `kagan:pair`        | ignored legacy label |

### Sync Map Persistence

Issue → task mapping is persisted in the kagan settings table under
`plugin.github.{owner}/{repo}.sync_map` as JSON. Re-running sync skips already-imported
issues. If a previously-synced task was deleted, it is re-imported.

### Preflight Checks

| Check     | Status | When                     | Fix Hint                         |
| --------- | ------ | ------------------------ | -------------------------------- |
| `gh_cli`  | PASS   | `gh` found on PATH       |                                  |
| `gh_cli`  | WARN   | `gh` not found           | Install → https://cli.github.com |
| `gh_auth` | PASS   | `gh auth token` succeeds |                                  |
| `gh_auth` | WARN   | Not authenticated        | Run → `gh auth login`            |

______________________________________________________________________

## Integration Points

### CLI (`kagan.cli.plugins`)

| Command               | Description                                    |
| --------------------- | ---------------------------------------------- |
| `kagan plugins sync`  | Sync issues from a plugin source               |
| `kagan plugins list`  | List installed plugins (built-in vs community) |
| `kagan plugins check` | Run plugin preflight checks                    |

See `docs/internal/features/cli.md` § Plugins.

### MCP (`kagan.mcp.toolsets.plugins`)

| Tool                | Tier     | Description                |
| ------------------- | -------- | -------------------------- |
| `plugins_sync`      | Admin    | Sync issues from a plugin  |
| `plugins_preflight` | Readonly | Check plugin prerequisites |

See `docs/internal/features/mcp.md` § Plugin Tools.

### Doctor (`kagan.cli.doctor`)

`doctor` calls `PluginManager.preflight()` to collect plugin health checks alongside
core preflight results. Plugin checks appear in the doctor output with the same
PASS/WARN/FAIL format.

______________________________________________________________________

## Dependency Direction

```text
kagan.plugins ──► kagan.core       (KaganCore, PreflightCheckResult, CheckStatus, errors, enums)

kagan.cli     ──► kagan.plugins    (lazy import inside function bodies)
kagan.mcp     ──► kagan.plugins    (lazy import inside tool handlers)

kagan.core    ──✘──► kagan.plugins  NEVER
kagan.tui     ──✘──► kagan.plugins  NEVER (no TUI integration — plugins are CLI/MCP only)
```

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

Plugin tests live in `tests/plugins/`:

| File                       | What it tests                                       |
| -------------------------- | --------------------------------------------------- |
| `test_plugin_lifecycle.py` | Manager load/register/unregister, discovery, errors |
| `test_github_import.py`    | GitHub sync: create, skip, re-import, label mapping |

Tests use a `FakeGitHubPlugin` and `FakeGhCli` to simulate `gh` CLI responses.
No real GitHub API calls in tests.

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                      | Why                                                               |
| ---------------------------- | ----------------------------------------------------------------- |
| Plugin config files          | `configure()` API is explicit. Settings table persists sync maps. |
| Hot reload                   | Plugins are discovered once per `load()`. Restart to pick up new. |
| TUI integration              | Plugins are data importers. No UI surface needed yet.             |
| Plugin marketplace           | YAGNI. Entry points + pip install is sufficient.                  |
| Plugin dependency resolution | Each plugin manages its own external deps (e.g. `gh` CLI).        |
