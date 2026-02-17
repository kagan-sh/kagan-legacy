---
title: CLI reference
description: Complete command and option reference for the kagan CLI
icon: material/console
---

# CLI reference

`kagan` with no subcommand → `kagan tui` (default).

| Command  | Description              |
| -------- | ------------------------ |
| `core`   | Manage core process      |
| `doctor` | Environment diagnostics |
| `list`   | List projects and repos  |
| `mcp`    | Run MCP server (stdio)   |
| `reset`  | Remove local state       |
| `tools`  | Stateless utilities      |
| `tui`    | Run TUI explicitly       |
| `update` | Check/install updates    |

## `kagan tui`

| Option                | Description                    |
| --------------------- | ------------------------------ |
| `--db TEXT`           | SQLite database path           |
| `--skip-preflight`    | Skip pre-flight (dev only)     |
| `--skip-update-check` | Skip update check on startup   |

## `kagan doctor`

Checks Python, git, gh CLI, Kagan paths. Run before troubleshooting.

## `kagan list`

No options.

## `kagan core`

| Subcommand | Description              |
| ---------- | ------------------------ |
| `start`   | Start core (if not running) |
| `status`  | Show core status         |
| `stop`    | Stop core                |

`kagan core start`: `--foreground` for foreground run.

## `kagan mcp`

| Option                              | Description                          |
| ----------------------------------- | ------------------------------------ |
| `--readonly`                        | Read-only tools only                 |
| `--session-id TEXT`                 | Bind to session/task                  |
| `--capability TEXT`                 | `viewer` \| `planner` \| `pair_worker` \| `operator` \| `maintainer` |
| `--endpoint TEXT`                   | Override core endpoint               |
| `--identity TEXT`                   | `kagan` \| `kagan_admin`             |
| `--enable-internal-instrumentation` | Enable diagnostics tool             |

## `kagan update`

| Option        | Description                    |
| ------------- | ------------------------------ |
| `-f, --force` | Skip confirmation              |
| `--check`     | Check only, don't install      |
| `--prerelease`| Include pre-releases           |

## `kagan reset`

| Option        | Description                    |
| ------------- | ------------------------------ |
| `-f, --force` | Skip confirmation              |

## `kagan tools`

| Subcommand       | Description                    |
| ---------------- | ------------------------------ |
| `enhance`        | Enhance prompts for AI tools   |
| `plugin-scaffold`| Generate plugin from template  |

### `kagan tools enhance`

`[PROMPT]` or `-f PATH`. `-t, --tool`: `claude` \| `opencode` (auto-detects if omitted).

### `kagan tools plugin-scaffold`

| Option         | Description                          |
| -------------- | ------------------------------------ |
| `--name TEXT`  | Plugin ID (3–64 chars, lowercase)    |
| `--output DIR` | Output dir (default: cwd)            |
