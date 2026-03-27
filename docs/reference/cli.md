---
title: CLI Reference
description: Complete command and option reference for the kagan CLI
icon: material/console
tags:
  - cli
  - reference
---

# CLI reference

`kagan` with no subcommand launches the TUI (same as `kagan tui`).

| Command   | Description                                     |
| --------- | ----------------------------------------------- |
| `chat`    | Orchestrator REPL / one-shot prompt             |
| `doctor`  | Environment diagnostics                         |
| `import`  | Import tasks from external sources              |
| `list`    | List projects with task counts                  |
| `mcp`     | Run MCP server (stdio)                          |
| `plugins` | Plugin management (requires opt-in, see below)  |
| `reset`   | Remove local state                              |
| `serve`   | Run HTTP API server (no web UI)                 |
| `tools`   | Stateless utilities and advanced prompt tooling |
| `tui`     | Run TUI explicitly                              |
| `update`  | Check/install updates                           |
| `web`     | Start API server with bundled web UI            |

## Global options

| Option                | Description                                                          |
| --------------------- | -------------------------------------------------------------------- |
| `--version`           | Show version and exit                                                |
| `-v, --verbose`       | Enable verbose stderr logging                                        |
| `--skip-update-check` | Skip startup update check (hidden; also `KAGAN_SKIP_UPDATE_CHECK=1`) |

______________________________________________________________________

## `kagan tui`

Default command. Launches the Kanban TUI.

| Option             | Description                                                |
| ------------------ | ---------------------------------------------------------- |
| `--db TEXT`        | SQLite database path                                       |
| `-s, --session-id` | Pre-attach orchestrator chat to a persisted session        |
| `--skip-preflight` | Skip startup doctor checks (also `KAGAN_SKIP_PREFLIGHT=1`) |

______________________________________________________________________

## `kagan chat`

Interactive orchestrator REPL by default. Use `--prompt` for single-shot mode.

Session lifecycle details: [ACP session lifecycle](../guides/acp-session-lifecycle.md).
Slash commands and usage: [Chat guide](../guides/chat.md).

| Option          | Description                                |
| --------------- | ------------------------------------------ |
| `--prompt TEXT` | Single-shot mode (send once, print, exit)  |
| `--session-id`  | Attach to an existing chat or task session |
| `--agent`       | Override default orchestrator backend      |

______________________________________________________________________

## `kagan doctor`

Runs startup diagnostics (Python, git, agent backend availability, tmux, IDE, DB, project config).

`kagan` runs these checks silently on boot and only surfaces output when critical blockers are detected. Exit code 0 when all pass/warn, exit code 1 on any failure.

| Option                  | Description                                     |
| ----------------------- | ----------------------------------------------- |
| `--verbosity tldr`      | Warnings and failures only                      |
| `--verbosity short`     | Concise guidance + one source pointer (default) |
| `--verbosity technical` | Full rationale, commands, official source links |

______________________________________________________________________

## `kagan import`

| Subcommand | Description                       |
| ---------- | --------------------------------- |
| `github`   | Import GitHub issues as new tasks |

### `kagan import github`

| Option    | Description                                                                  |
| --------- | ---------------------------------------------------------------------------- |
| `--repo`  | Repository in `owner/repo` format (auto-detected from git remote if omitted) |
| `--state` | Issue state filter: `open` (default), `closed`, `all`                        |
| `--label` | Import only issues with this label                                           |
| `--yes`   | Skip confirmation prompt                                                     |

______________________________________________________________________

## `kagan list`

Lists projects with repository paths and per-status task counts (BACKLOG, IN_PROGRESS, REVIEW, DONE). No options.

______________________________________________________________________

## `kagan mcp`

Starts the MCP server on STDIO. Blocks until the host disconnects.

| Option                              | Description                                             |
| ----------------------------------- | ------------------------------------------------------- |
| `--readonly`                        | Read-only tier (read-only tools/resources/prompts only) |
| `--admin`                           | Admin tier (includes destructive/admin tools)           |
| `--session-id TEXT`                 | Bind server context to a session or task                |
| `--role ROLE`                       | Agent role: `WORKER`, `REVIEWER`, or `ORCHESTRATOR`     |
| `--enable-internal-instrumentation` | Expose diagnostics instrumentation tool                 |

`--readonly` and `--admin` are mutually exclusive. Without either flag, the server runs in default tier (read + write, no destructive operations).

### Access tiers

| Tier       | Scope                                                                                                                                                                                                                                                                  |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `readonly` | Worker-scope operations (`task_get`, `task_list`, `task_search`, `task_events`, `task_counts`, `task_add_note`, `tasks_wait`, `run_summary`, `run_exists`, `run_create`, `run_get`, `run_kill`, `run_detach`, `settings_get`, `review_conflicts`, `plugins_preflight`) |
| `default`  | Orchestrator-scope access (worker tools plus task creation, task mutation, run orchestration, review actions, projects, settings, plugins, and persona management)                                                                                                     |
| `admin`    | Alias of `default` for MCP; currently exposes the same tool surface                                                                                                                                                                                                    |

```bash
kagan mcp --readonly                    # worker-scope access
kagan mcp                               # orchestrator-scope access
kagan mcp --admin                       # same MCP tool surface as default
kagan mcp --session-id task:abc123      # task-scoped session
```

______________________________________________________________________

## `kagan update`

| Option         | Description                           |
| -------------- | ------------------------------------- |
| `--check-only` | Check for updates only, don't install |
| `--prerelease` | Include pre-release versions          |
| `--force`      | Force reinstall even when current     |

______________________________________________________________________

## `kagan reset`

| Option           | Description                    |
| ---------------- | ------------------------------ |
| `--project NAME` | Reset a single project by name |
| `--force`        | Skip confirmation              |

Without `--project`, resets all data (config, DB, worktrees).

______________________________________________________________________

## `kagan serve`

Starts the HTTP API server for local integrations. REST + SSE endpoints are served from the same local process.

| Option       | Description                               |
| ------------ | ----------------------------------------- |
| `--host`     | Bind address (default: `127.0.0.1`)       |
| `--port`     | Bind port (default: `8765`)               |
| `--readonly` | Read-only access tier                     |
| `--admin`    | Admin access tier                         |
| `--tls`      | Enable HTTPS with self-signed certificate |

`--readonly` and `--admin` are mutually exclusive. Use `--host 0.0.0.0` to allow connections from other devices on the network.

```bash
kagan serve                             # localhost only
kagan serve --host 0.0.0.0             # accept remote connections
kagan serve --host 0.0.0.0 --readonly  # read-only for remote viewers
```

See [Remote access guide](../guides/remote-access.md) for full setup instructions.

______________________________________________________________________

## `kagan web`

Starts the bundled web dashboard and opens your browser.

| Option       | Description                         |
| ------------ | ----------------------------------- |
| `--host`     | Bind address (default: `127.0.0.1`) |
| `--port`     | Bind port (default: `8765`)         |
| `--no-open`  | Do not auto-open a browser window   |
| `--readonly` | Read-only access tier               |
| `--admin`    | Admin access tier                   |

`--readonly` and `--admin` are mutually exclusive.

```bash
kagan web
kagan web --host 0.0.0.0
kagan web --host 0.0.0.0 --no-open
```

The bundled dashboard always talks to the same `kagan web` instance that serves it. It does not pair to a separate `kagan serve` instance. See [Remote access guide](../guides/remote-access.md) for network exposure guidance.

______________________________________________________________________

## `kagan tools`

| Subcommand | Description                  |
| ---------- | ---------------------------- |
| `enhance`  | Enhance prompts for AI tools |
| `prompts`  | Export resolved prompts      |

### `kagan tools enhance`

Rewrites a prompt for clarity and actionability using an AI backend.

`[PROMPT]` positional argument or `-f PATH` for file input. At least one is required.

| Option         | Description                                                              |
| -------------- | ------------------------------------------------------------------------ |
| `--agent NAME` | Refinement agent backend (auto-detects if omitted)                       |
| `-t, --tool`   | Legacy shorthand: `claude` or `opencode` (cannot combine with `--agent`) |
| `-f, --file`   | Read prompt from file                                                    |

### `kagan tools prompts export`

| Option         | Description                                    |
| -------------- | ---------------------------------------------- |
| `--type`       | `orchestrator`, `execution`, or `review`       |
| `--output, -o` | Output path; prints to stdout when omitted     |
| `--format`     | `yml` or `text` output format                  |
| `--model`      | Model ID written into the `.prompt.yml` header |

This is advanced tooling for prompt export and evaluation workflows. Persona management remains under `kagan tools prompts persona ...`.

______________________________________________________________________

## `kagan plugins`

!!! note "Experimental — opt-in only"
Requires `KAGAN_ENABLE_PLUGIN_CLI=1`. The plugin system is early-stage. See [Plugins](plugins.md) for details.

______________________________________________________________________

## Machine-readable output

Most CLI commands produce human-first text output. For stable machine contracts, prefer MCP integrations over parsing CLI text output.
