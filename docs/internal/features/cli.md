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
- `--verbosity`: `tldr` (one-line summary), `short` (default, Rich summary/actions view), `technical` (full per-check detail)
- Exit 0 if all pass/warn, exit 1 if any fail

### `kagan projects`

- Table of projects with repo paths and per-status task counts
- Exit 0 always (empty table is not an error)

### `kagan mcp`

- Starts MCP server on STDIO (blocks until host disconnects)
- `--readonly`, `--admin`, `--session-id` (readonly and admin are mutually exclusive)
- `--role ROLE`: agent role (`WORKER`, `REVIEWER`, `ORCHESTRATOR`) controls tool visibility
- `--enable-internal-instrumentation` for diagnostics tool

### `kagan reset`

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

### `kagan import github`

- Interactive GitHub issue import into the active project
- `--repo owner/repo`: target repository (prompted if omitted)
- `--state open|closed|all`: filter by issue state (default: open)
- `--label <label>`: only import issues with this label
- `--yes`: skip confirmation prompt
- Reports created/skipped/errors counts

### `kagan serve`

- Starts the HTTP API server (blocks until stopped)
- `--port PORT`: listen port (default: 8765)
- `--host HOST`: bind address (default: 127.0.0.1)
- `--readonly`, `--admin`: mutually exclusive access tiers
- `--tls`: enable HTTPS with self-signed certificate

### `kagan web`

- Launches the web dashboard (starts server + opens browser)
- Accepts same `--host` and `--port` flags as `kagan serve`
- `--no-open`: suppress automatic browser launch
- `--readonly`, `--admin`: mutually exclusive access tiers

### `kagan import github`

Import GitHub issues into the active project.

- `kagan import github --repo owner/repo` syncs issues as kagan tasks
- `--state`: issue state filter (open, closed, all). Default: open
- `--label`: only sync issues with this label
- Reports created/skipped/errors counts
- Idempotent — re-running skips already-imported issues

### `kagan tools prompts`

Prompt inspection and export subgroup.

#### `kagan tools prompts export`

- `--type orchestrator|execution|review` (required): which prompt to resolve and export
- `--output/-o PATH`: write to file; prints to stdout when omitted
- `--format yml|text`: output format (default: `yml`)
- `--model ID`: model ID for the `.prompt.yml` header (default: `openai/gpt-4.1`)
- Resolves through the three-layer pipeline (dotfile → defaults + behavioral → additional instructions)
- `yml` format: GitHub Models `.prompt.yml` (also compatible with promptfoo)
- `text` format: raw resolved prompt text, no wrapper

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
