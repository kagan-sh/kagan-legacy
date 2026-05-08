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

| Command  | Description                                     |
| -------- | ----------------------------------------------- |
| `chat`   | Orchestrator REPL / one-shot prompt             |
| `doctor` | Environment diagnostics                         |
| `import` | Import tasks from external sources              |
| `list`   | List projects with task counts                  |
| `mcp`    | Run MCP server (stdio)                          |
| `reset`  | Remove local state                              |
| `serve`  | Run HTTP API server (no web UI)                 |
| `tools`  | Stateless utilities and advanced prompt tooling |
| `tui`    | Run TUI explicitly                              |
| `update` | Check/install updates                           |
| `web`    | Start API server with bundled web UI            |

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

`--yolo` has been removed. Use the permission panel's session trust options when a tool asks for approval.

______________________________________________________________________

## `kagan doctor`

Runs startup diagnostics (Python, git, agent backend availability, tmux, IDE, DB, project config).

`kagan` runs these checks silently on boot and only surfaces output when critical blockers are detected. Exit code 0 when all pass/warn, exit code 1 on any failure.

| Option                  | Description                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| `--verbosity tldr`      | Warnings and failures only                                               |
| `--verbosity short`     | Rich summary, required checks, backend panel, and action table (default) |
| `--verbosity technical` | Full rationale, commands, official source links                          |

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

Prefer `--role` when configuring MCP clients. `--readonly` and `--admin` are compatibility flags; `--admin` currently exposes the same MCP tool surface as the default role-driven server.

### Access tiers

| Tier       | Scope                                                                                                                                                                                                                                                                                                                                                   |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `readonly` | Worker-scope operations (`task_get`, `task_list`, `task_events`, `task_wait`, `run_get`, `run_cancel`, `run_detach`, `run_summary`, `review_conflicts`, `settings_get`, `integration_preflight`, `integration_preview`, `verify_step`, `verification_summary`, `checkpoint_create`, `checkpoint_list`, `session_rewind`, `insight_add`, `insight_list`) |
| `default`  | Orchestrator-scope access (worker tools plus task creation/mutation/deletion, run orchestration, review decisions/merge/rebase, projects, settings, audit, integrations, personas, and insight removal)                                                                                                                                                 |
| `admin`    | Alias of `default` for MCP; currently exposes the same tool surface                                                                                                                                                                                                                                                                                     |

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

| Option           | Description                                 |
| ---------------- | ------------------------------------------- |
| `--project NAME` | Reset a single project by name              |
| `-f, --force`    | Skip confirmation                           |
| `--dry-run`      | Show what would be deleted without deleting |

Without `--project`, resets all data (config, DB, worktrees).

______________________________________________________________________

## `kagan serve`

Starts the HTTP API server for local integrations. REST and SSE endpoints are served from the same local process.

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

`--readonly` and `--admin` are mutually exclusive. Without either flag, `kagan web` runs with standard access.

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

This is advanced tooling for prompt export and evaluation workflows.

### `kagan tools prompts persona`

Persona preset import, export, and trust management.

| Subcommand  | Description                               |
| ----------- | ----------------------------------------- |
| `import`    | Import persona presets from a GitHub repo |
| `export`    | Export persona presets to a GitHub repo   |
| `audit`     | Audit a persona repo without importing    |
| `whitelist` | List trusted persona repos                |
| `trust`     | Add a repo to persona trust list          |
| `untrust`   | Remove a repo from persona trust list     |

#### `kagan tools prompts persona import`

| Option               | Description                                         |
| -------------------- | --------------------------------------------------- |
| `REPO`               | Repository in `owner/repo` format                   |
| `--path`             | Persona file path (default: `.kagan/personas.json`) |
| `--ref`              | Git ref to import from                              |
| `-y, --yes`          | Skip confirmation                                   |
| `--preview`          | Show personas without importing                     |
| `--acknowledge-risk` | Acknowledge risks of third-party presets            |

#### `kagan tools prompts persona export`

| Option   | Description                       |
| -------- | --------------------------------- |
| `REPO`   | Repository in `owner/repo` format |
| `--path` | Persona file path                 |
| `--ref`  | Git ref to export to              |

#### `kagan tools prompts persona audit`

| Option   | Description                       |
| -------- | --------------------------------- |
| `REPO`   | Repository in `owner/repo` format |
| `--path` | Persona file path                 |
| `--ref`  | Git ref to audit                  |

#### `kagan tools prompts persona trust` / `untrust`

| Option | Description                       |
| ------ | --------------------------------- |
| `REPO` | Repository in `owner/repo` format |

______________________________________________________________________

## Machine-readable output

Most CLI commands produce human-first text output. For stable machine contracts, prefer MCP integrations over parsing CLI text output.
