# Plugin Features

Observable behaviors of `kagan.plugins`. Each section maps to a test file in `tests/plugins/`.
Implementation details live in `docs/internal/architecture/plugins.md`.

______________________________________________________________________

## 1. Plugin Lifecycle

- Discover installed plugins via Python entry points (`kagan.plugins` group)
- Load all discovered plugins — setup, register, emit provenance warnings for community plugins
- Entry-point name must match plugin's `name` property — mismatches are skipped with a warning
- Duplicate registration raises `PluginError`
- Get a plugin by name — raises `PluginError` if not found, listing available plugins
- Unregister a plugin — calls teardown, removes from registry
- Tear down all plugins on shutdown

______________________________________________________________________

## 2. Provenance & Trust

- Built-in plugins (package == "kagan") load silently
- Community plugins emit a provenance warning with package name, version, and source URL
- Warnings are accessible via `manager.community_warnings`
- Non-Plugin entry points are skipped with a warning (not a crash)
- Entry points that fail to load are skipped with a logged exception

______________________________________________________________________

## 3. Plugin Health Checks

- Each plugin can report preflight checks as `PreflightCheckResult` objects (pass/warn/fail)

- `PluginManager.preflight()` collects checks from all registered plugins

- Single-plugin check via `manager.get(name).preflight()`

- GitHub plugin checks: `gh` CLI installed, `gh` authenticated

______________________________________________________________________

## 4. GitHub Import

- Configure with owner/repo before sync — raises `PluginError` if not configured
- Fetch issues from GitHub using `gh` CLI (JSON output)
- Supports filtering by state (`open`, `closed`, `all`), labels (multiple), and limit
- Selective import: pass `issue_numbers` to `GitHubImportConfig` to restrict to specific issues
- Create kagan tasks from issues: title, description (body + URL + unmapped labels)
- Map GitHub labels to task properties:
  - `priority:critical` / `priority:high` / `priority:medium` / `priority:low` → Priority
- Unmapped labels appear as `[label]` tags in description
- Sync is idempotent: issue→task mapping persisted in settings table
- Previously-synced issues are skipped
- Deleted tasks are re-imported on next sync
- Issues missing number or title are reported as errors, not crashes
- Per-issue failures are caught and reported in `ImportResult.errors`

______________________________________________________________________

## 5. CLI Commands

- `kagan plugins sync <name> --repo owner/repo` — sync issues into active project
  - `--label <label>` (repeatable) — filter by label
  - `--limit <n>` — cap issue count (default 100)
  - `--issues 1,2,3` — import only specific issue numbers
- `kagan plugins preview <name> --repo owner/repo` — preview matching issues without importing
  - `--label <label>` (repeatable) — filter by label
  - `--limit <n>` — cap issue count (default 100)
- `kagan plugins list` — show installed plugins with built-in/community labels
- `kagan plugins check [name]` — run preflight checks for one or all plugins

______________________________________________________________________

## 6. MCP Tools

- `plugins_sync` (Admin tier) — sync issues via MCP, returns created/skipped/errors
- `plugins_preview` (Readonly tier) — preview issues matching filters, returns list without importing
- `plugins_preflight` (Readonly tier) — check plugin prerequisites, returns checks and readiness

______________________________________________________________________

## 7. GitHub Integration Utilities

- Canonicalize `owner/repo` slugs — strip whitespace, reject malformed values
- Normalize GitHub issue state strings (`open`, `closed`, `all`) — case-insensitive, reject unknown
- Filter preflight check results to blocking (non-pass) entries
- Format actionable setup messages from blocking preflight checks (fix hints, descriptions)
- Parse `owner/repo` slug from git remote URLs (HTTPS, SSH, `git@` forms) — return `None` for unsupported

______________________________________________________________________

## 8. Issue Preview

- `preview_github_issues()` fetches issues matching config and returns `GitHubIssuePreview` dicts
- Each preview includes: `number`, `title`, `state`, `labels`, `url`, `already_synced`
- `already_synced` is `True` if the issue number appears in the persisted sync map
- Preview does not create any tasks — read-only operation
- TUI two-step flow: Phase 1 filters issues via preview, Phase 2 presents a `SelectionList` for selective import
- Already-synced issues are shown with `(synced)` suffix and deselected by default
