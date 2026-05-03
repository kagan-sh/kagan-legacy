# CLI Architecture — `kagan.cli`

*Design principles: Click-native, Zen of Python, no cleverness.*

## References

| Package    | Repo                                              | Use                                      |
| ---------- | ------------------------------------------------- | ---------------------------------------- |
| **Click**  | [pallets/click](https://github.com/pallets/click) | CLI framework: groups, commands, options |
| **Loguru** | [Delgan/loguru](https://github.com/Delgan/loguru) | Structured logging (configured in core)  |

## Package Layout

```text
src/kagan/cli/
├── __init__.py        # re-export `cli` for entry_points
├── main.py            # root group, version flag, default-to-tui, error boundary
├── _bootstrap.py      # make_client, run_async, update check helpers
├── _env.py            # environment configuration helpers
├── entrypoint.py      # entry point wrapper
├── tui.py             # kagan tui
├── chat.py            # kagan chat [--prompt] [--session-id]
├── doctor.py          # kagan doctor [--verbosity]
├── list_projects.py   # kagan projects
├── mcp.py             # kagan mcp [flags]
├── reset.py           # kagan reset [--force] [--project]
├── serve.py           # kagan serve [--port] [--host] [--readonly]
├── update.py          # kagan update [--check-only] [--prerelease]
├── tools.py           # kagan tools enhance [prompt]
├── imports.py         # kagan import github (subgroup)
└── web.py             # kagan web (dashboard wrapper)
```

**17 modules.** No sub-packages. Every file has one job.

## Entry Point

`pyproject.toml` declares `kagan = "kagan.cli:cli"`. The `__init__.py` re-exports the root Click group.

## Root Group (`main.py`)

- Custom `_CLIGroup(click.Group)` — one error boundary for the entire CLI
- `invoke_without_command=True` — bare `kagan` delegates to `tui`
- Eager `--version` exits immediately
- Hidden `--skip-update-check` flag (also `KAGAN_SKIP_UPDATE_CHECK` envvar)
- Silent update check on startup (never breaks startup)
- 11 commands registered via `cli.add_command()`

## Commands

| Command    | Purpose                                      | Notes                                    |
| ---------- | -------------------------------------------- | ---------------------------------------- |
| `tui`      | Launch Textual interface                     | Default when no subcommand given         |
| `chat`     | Interactive REPL or single-shot (`--prompt`) | Sessions persist automatically           |
| `doctor`   | System health checks                         | Sync only, no async boundary needed      |
| `projects` | List projects                                | Thin wrapper around core                 |
| `mcp`      | Start MCP STDIO server                       | Blocks on STDIO; `--readonly`, `--admin` |
| `reset`    | Reset database/state                         | `--force` to skip confirmation           |
| `update`   | Self-update via pipx/pip                     | `--check-only`, `--prerelease`           |
| `tools`    | LLM tool utilities                           | Subgroup: `enhance`                      |

| `import` | Import from external sources | Subgroup: `github` |
| `serve` | Start HTTP API server | Blocks until stopped |
| `web` | Start server + open browser | Convenience wrapper around `serve` |

## The Async Bridge (`_bootstrap.py`)

Core is async; Click callbacks are sync. `_bootstrap.py` bridges the gap:

| Helper                          | Purpose                                   |
| ------------------------------- | ----------------------------------------- |
| `make_client(db_path=None)`     | Create a `KaganCore` instance per command |
| `run_async(coro)`               | Sync → async via `asyncio.run()`          |
| `maybe_check_for_updates()`     | Silent PyPI version check                 |
| `check_and_install_update(...)` | Detect install method, fetch, install     |

No Click imports. No shared state. Pure utility.

## Error Handling Boundary

| Exception              | Exit Code | When                            |
| ---------------------- | --------- | ------------------------------- |
| `click.UsageError`     | 2         | Bad flag, missing arg, conflict |
| `click.BadParameter`   | 2         | Invalid param value             |
| `click.ClickException` | 1         | Application-level error         |
| `click.Abort`          | 1         | Ctrl-C / EOF                    |

Strategy:

1. **Parameter conflicts** → `click.UsageError`
1. **Domain errors** → `click.ClickException(msg)`
1. **Unexpected errors** → caught by `_CLIGroup.invoke`, logged, surfaced as `ClickException`

## State Flow

```
shell → cli() → Click parses argv
  ├─ --version? → print & exit
  ├─ maybe_check_for_updates() → silent, non-blocking
  ├─ no subcommand? → delegate to tui
  └─ subcommand → command(args)
       ├─ client = make_client()       # lazy import
       ├─ run_async(client.ns.op())    # async boundary
       └─ click.echo(result)           # output
```

No shared mutable state. No `ctx.obj` passing. Each command creates its own short-lived client.

## Key UX Decisions

- Bare `kagan` launches TUI (most common entry point)
- `kagan chat --prompt "..."` is single-shot; no `--prompt` → interactive REPL
- Sessions persist automatically; relaunch resumes last REPL session
- `kagan doctor` output: `PASS`/`WARN`/`FAIL` with `quick fix` hints
- Update hint: one-line before normal output (not for `--version`)
- CI opt-out: `KAGAN_SKIP_UPDATE_CHECK=1` or `--skip-update-check`

Behavioral details in `docs/internal/features/cli.md`.

## Testing

No `tests/cli/` — CLI is too thin. Behavioral tests flow through `KaganDriver` in `tests/core/` and `tests/mcp/`.

One carve-out: `tests/core/test_cli_surface.py` validates help text, exit codes, and command-surface behavior via Click's `CliRunner`.

## What This Architecture Does NOT Have

| Omitted                  | Why                                               |
| ------------------------ | ------------------------------------------------- |
| Daemon / `kagan core`    | Core is an in-process SDK. No process management. |
| Typer                    | Adds indirection without earning it.              |
| `commands/` subdirectory | Flat is better than nested.                       |
| Base command class       | Each command is a function. No inheritance.       |
| `ctx.obj` state passing  | Commands are independent. No hidden coupling.     |
| Custom help formatting   | Click's default is good enough.                   |
