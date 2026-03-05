# CLI Features

Observable behaviors of `kagan.cli`. CLI is a thin shell — no dedicated test domain.
Behavioral tests flow through `tests/core/` and `tests/mcp/` via `KaganDriver`.
CLI surface snapshots (help text, exit codes) live in `tests/core/test_cli_surface.py`.
Implementation details live in `docs/internal/architecture/cli.md`.

______________________________________________________________________

## Commands

### `kagan` (no args)

- Launches the TUI dashboard

### `kagan --version`

- Prints version and exits

### `kagan tui`

- Launches the TUI dashboard (same as bare `kagan`)
- `-s, --session-id ID`: pre-attaches orchestrator chat to a persisted TUI session

### `kagan chat`

- No flags: starts an interactive REPL
- `--prompt "text"`: single-shot mode — runs prompt, prints result, exits
- `--session-id ID`: resumes a previous persisted session
- `--agent NAME`: overrides the default agent backend
- `--prompt` and `--session-id` can be combined
- Sessions are persisted across restarts (conversation mode, rendered transcript, and orchestrator context)
- `/sessions` opens session flow in-REPL:
  - `/sessions` lists persisted sessions
  - `/sessions <number|id-prefix>` attaches to a session
  - `/sessions new` creates and switches to a new session

### `kagan doctor`

- Checks: git, agent backend, tmux, IDE, DB, project config
- Each check: pass, warn, or fail with fix hints
- `--verbosity`: `tldr` (one-line summary), `short` (default, per-check), `technical` (full detail)
- Exit 0 if all pass/warn, exit 1 if any fail

### `kagan projects`

- Table of projects with repo paths and per-status task counts
- Exit 0 always (empty table is not an error)

### `kagan mcp`

- Starts MCP server on STDIO (blocks until host disconnects)
- `--readonly`, `--admin`, `--session-id` (readonly and admin are mutually exclusive)
- `--enable-internal-instrumentation` for diagnostics tool

### `kagan reset-state`

- Wipes all data with confirmation prompt
- `--project NAME`: scope to one project
- `--force`: skip confirmation

### `kagan update`

- Checks PyPI and installs if newer version available
- `--check-only`, `--prerelease`, `--force`
- Auto-detects install method (uv / pipx / pip)

### `kagan tools enhance`

- Enhances a prompt by delegating rewrite to a CLI agent tool
- Input: `--file` > positional arg (if neither is provided, command exits with usage error)
- Optional `--agent NAME` selects the refinement backend explicitly (chat-style backend naming)
- Optional `-t, --tool` legacy shorthand for `claude`/`opencode`; cannot be combined with `--agent`

### `kagan plugins`

Plugin management subgroup.

#### `kagan plugins sync`

- `kagan plugins sync <name> --repo owner/repo` syncs external items into the active project
- `--state`: issue state filter (open, closed, all). Default: open
- `--label`: only sync issues with this label
- Reports created/skipped/errors counts
- Shows community plugin provenance warnings

#### `kagan plugins list`

- Lists installed plugins with built-in/community labels
- Community plugins show package name and version

#### `kagan plugins check`

- `kagan plugins check [name]` runs preflight checks for one or all plugins
- Displays PASS/WARN/FAIL per check with fix hints

______________________________________________________________________

## Startup Behavior

- Silent update check on normal command invocations (never blocks, swallows errors)
  - Eager exits like `--version` skip the root callback and do not run the check
- If newer version available, prints one-line hint before command runs
- Opt-out: `KAGAN_SKIP_UPDATE_CHECK=1` or `--skip-update-check` (hidden)

______________________________________________________________________

## Error Behavior

| Situation                               | Exit Code                       |
| --------------------------------------- | ------------------------------- |
| Success                                 | 0                               |
| Usage error (bad flag, unknown command) | 2                               |
| Application error                       | 1                               |
| Unexpected crash                        | 1 (traceback logged internally) |
| Ctrl-C                                  | 1                               |
