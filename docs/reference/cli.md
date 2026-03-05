---
title: CLI reference
description: Complete command and option reference for the kagan CLI
icon: material/console
tags:
  - cli
  - reference
---

# CLI reference

`kagan` with no subcommand → `kagan tui` (default).

| Command    | Description                         |
| ---------- | ----------------------------------- |
| `chat`     | Orchestrator REPL / one-shot prompt |
| `core`     | Manage core process                 |
| `doctor`   | Environment diagnostics             |
| `import`   | Import tasks from tools             |
| `list`     | List projects and repos             |
| `mcp`      | Run MCP server (stdio)              |
| `profiles` | List MCP access profiles            |
| `reset`    | Remove local state                  |
| `tools`    | Stateless utilities                 |
| `tui`      | Run TUI explicitly                  |
| `update`   | Check/install updates               |

## Machine-readable output guarantees

- Most CLI commands are currently human-first text output (`kagan list`, `kagan core status`, `kagan profiles`, etc.).
- User-tunable schema flags are not GA today (`--output-schema`, schema overlays, repair-policy controls).
- For stable machine contracts today, prefer MCP/SDK integrations over parsing CLI text output.

### Need custom schema validation?

[Open a feature request](https://github.com/aorumbayev/kagan/issues/new?template=feature_request.md) with your CI/CD use case and expected contract behavior.

## `kagan tui`

| Option                | Description                           |
| --------------------- | ------------------------------------- |
| `--db TEXT`           | SQLite database path                  |
| `--skip-preflight`    | Skip startup doctor checks (dev only) |
| `--skip-update-check` | Skip update check on startup          |

## `kagan doctor`

Runs startup diagnostics (Python, git, agent backend availability, tooling).
`kagan` runs these checks silently on boot and only surfaces output when critical blockers are detected.

| Option                  | Description                                     |
| ----------------------- | ----------------------------------------------- |
| `--verbosity tldr`      | Warnings and failures only                      |
| `--verbosity short`     | Concise guidance + one source pointer (default) |
| `--verbosity technical` | Full rationale, commands, official source links |

## `kagan chat`

Interactive orchestrator REPL by default. Use `--prompt` for single-shot mode.
Session lifecycle details: [ACP session lifecycle](../guides/acp-session-lifecycle.md)

| Option          | Description                                |
| --------------- | ------------------------------------------ |
| `--prompt TEXT` | Single-shot mode (send once, print, exit)  |
| `--session-id`  | Attach to an existing chat or task session |
| `--agent`       | Override default orchestrator backend      |

## `kagan import`

| Subcommand | Description                       |
| ---------- | --------------------------------- |
| `github`   | Import GitHub issues as new tasks |

### `kagan import github`

| Option    | Description                                 |
| --------- | ------------------------------------------- |
| `--repo`  | Repository in `owner/repo` format           |
| `--state` | Issue state filter: `open`, `closed`, `all` |
| `--label` | Import only issues with this label          |
| `--yes`   | Skip confirmation prompt                    |

## `kagan list`

No options.

## `kagan core`

| Subcommand | Description                 |
| ---------- | --------------------------- |
| `start`    | Start core (if not running) |
| `status`   | Show core status            |
| `stop`     | Stop core                   |

`kagan core start`: `--foreground` for foreground run.

## `kagan mcp`

| Option                              | Description                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------------ |
| `--readonly`                        | Read-only tools only                                                           |
| `--session-id TEXT`                 | Bind to session/task                                                           |
| `--capability TEXT`                 | `viewer` \| `planner` \| `pair_worker` \| `operator` \| `maintainer`           |
| `--identity TEXT`                   | `kagan` \| `kagan_admin`                                                       |
| `--preset TEXT`                     | Named profile (see below). Overridden by explicit `--capability`/`--identity`. |
| `--endpoint TEXT`                   | Override core endpoint                                                         |
| `--enable-internal-instrumentation` | Enable diagnostics tool                                                        |

### Presets

`--preset` applies a pre-built `--capability` + `--identity` combination.

| Preset              | capability    | identity      | Use                                |
| ------------------- | ------------- | ------------- | ---------------------------------- |
| `security-reviewer` | `viewer`      | `kagan`       | Read-only auditing                 |
| `test-writer`       | `pair_worker` | `kagan`       | Scoped test generation             |
| `refactoring-agent` | `pair_worker` | `kagan`       | Bounded refactors with review gate |
| `pair-worker`       | `pair_worker` | `kagan`       | Interactive PAIR workflow          |
| `orchestrator`      | `operator`    | `kagan_admin` | AUTO pipeline orchestration        |
| `maintainer`        | `maintainer`  | `kagan_admin` | Admin / CI lane                    |

```bash
kagan mcp --preset orchestrator
kagan mcp --preset security-reviewer --session-id task:abc123
```

Run `kagan profiles` to list all presets with descriptions and equivalent manual flags.

## `kagan profiles`

Lists all built-in MCP access profiles with their `--capability`, `--identity`, and a description. No options.

```bash
kagan profiles
```

## `kagan update`

| Option         | Description               |
| -------------- | ------------------------- |
| `-f, --force`  | Skip confirmation         |
| `--check`      | Check only, don't install |
| `--prerelease` | Include pre-releases      |

## `kagan reset`

| Option        | Description       |
| ------------- | ----------------- |
| `-f, --force` | Skip confirmation |

## `kagan tools`

| Subcommand | Description                  |
| ---------- | ---------------------------- |
| `enhance`  | Enhance prompts for AI tools |

### `kagan tools enhance`

`[PROMPT]` or `-f PATH`. `-t, --tool`: `claude` | `opencode` (auto-detects if omitted).
