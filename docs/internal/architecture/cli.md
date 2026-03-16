# CLI Architecture — `kagan.cli`

*Design principles: Click-native, Zen of Python, no cleverness.*

______________________________________________________________________

## References

| Package    | Repo                                              | Use                                                                                                     |
| ---------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Click**  | [pallets/click](https://github.com/pallets/click) | CLI framework: groups, commands, options, `CliRunner` testing patterns.                                 |
| **Loguru** | [Delgan/loguru](https://github.com/Delgan/loguru) | Structured logging. Config and sink setup in core — see `docs/internal/architecture/core.md` § Logging. |

______________________________________________________________________

## Internal Structure

```
                         ┌─────────────────────────────────────────────┐
                         │              pyproject.toml                 │
                         │     kagan = "kagan.cli:cli"                │
                         └─────────────────┬───────────────────────────┘
                                           │
                                           ▼
                         ┌─────────────────────────────────────────────┐
                         │           __init__.py                       │
                         │     re-exports cli for entry_points         │
                         └─────────────────┬───────────────────────────┘
                                           │
                                           ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           main.py  (root group)                            │
 │                                                                             │
 │  Click group with invoke_without_command=True                               │
 │  Eager --version flag                                                       │
 │  Hidden --skip-update-check (envvar: KAGAN_SKIP_UPDATE_CHECK)              │
 │  Default: no subcommand → delegates to tui                                 │
 │                                                                             │
 │  ┌─── _CLIGroup(click.Group) ────────────────────────────────────────────┐  │
 │  │  One error boundary for the entire CLI:                               │  │
 │  │    ClickException → re-raise (Click formats it)                       │  │
 │  │    Abort          → re-raise (Ctrl-C)                                 │  │
 │  │    Exception      → log + wrap as ClickException(str(exc))            │  │
 │  └───────────────────────────────────────────────────────────────────────┘  │
 │                                                                             │
  | Registers 11 commands: tui, chat, doctor, projects, mcp,                      |
  |                         reset-state, update, tools, plugins, import, serve    |
 └──────────────────────────────────┬──────────────────────────────────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │  11 command modules    │  (flat siblings)       │
           │  each one file         │  each one function     │
           │  no base class         │  no shared state       │
           ▼                        ▼                        ▼
 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
 | KaganApp     │  │              │  │              │  │list_projects │
 │              │  │              │  │              │  │   .py        │
 │  │ launches     │  │ --prompt     │  │ --verbosity  │  │ name=        │
│  │ KaganApp     │  │ --session-id │  │   tldr|short │  │ "projects"   │
│  │ (core in     │  │ --agent      │  │   |technical │  │ creates      │
│  │  on_mount)   │  │ creates      │  │  sync only   │  │ client +     │
│  │              │  │ run_chat()   │  │              │  │ lists projects│
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘

 ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   mcp.py     │  │  reset.py    │  │  update.py   │  │  tools.py    │
│              │  │ name=        │  │              │  │  (group)     │
│  │  --readonly  │  │ "reset-state"│  │ --check-only │  │ ┌────────────────┐ │
│  │  --admin     │  │ --project    │  │ --prerelease │  │ │ enhance        │ │
│  │  --session-id│  │  confirm()   │  │ --force      │  │ │ --file         │ │
│              │  │ creates      │  │  pipx/pip    │  │ │ --agent/--tool │ │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘

 ┌──────────────┐
 │  plugins.py   │
 │  (group)      │
 │ ┌────────────────┐ │
 │ │ sync           │ │
 │ │ list           │ │
 │ │ check          │ │
 │ └──────────┘ │
 │              │
 └──────────────┘

           │                    ┌──────────────────────────────────┐
           │ all commands use   │       _bootstrap.py              │
           ├───────────────────►│                                  │
           │                    │  make_client(db_path=None)       │
           │                    │     └─ KaganCore(db_path)          │
           │                    │                                  │
           │                    │  run_async(coro)                 │
           │                    │     └─ asyncio.run(coro)         │
           │                    │                                  │
           │                    │  maybe_check_for_updates()       │
           │                    │  check_and_install_update(...)    │
           │                    └──────────────────────────────────┘
           │
           │ lazy imports       ┌──────────────────────────────────┐
           │ (inside function   │  kagan.core   (in-process SDK)   │
           │  bodies only)      │  kagan.tui    (Textual app)      │
           └───────────────────►│  kagan.mcp    (MCP STDIO server) │
                                │  kagan.chat   (REPL)             │
                                │  kagan.plugins (plugin system)   │
                                └──────────────────────────────────┘


  DEPENDENCY DIRECTION (strictly one-way, no cycles):

    cli modules ──► _bootstrap.py
    cli modules ──► kagan.core / kagan.tui / kagan.mcp / kagan.chat

    kagan.core  ──✘──► kagan.cli    NEVER
    kagan.tui   ──✘──► kagan.cli    NEVER
```

______________________________________________________________________

## Key UX Decisions

- Bare `kagan` launches TUI — most common entry point
- `kagan chat --prompt "..."` is single-shot: prints and exits. No `--prompt` → interactive REPL.
- `kagan chat` sessions persist by default using core settings storage; relaunch resumes the last REPL session.
- `/sessions` is the session control surface in chat REPL (list/attach/new) and mirrors TUI session switching.
- `kagan doctor` output format: `PASS`/`WARN`/`FAIL` per check, with `quick fix` and `verify` hints
- `kagan mcp --help` shows access tiers and common flag configurations inline
- Update hint: one-line `hint: kagan 0.7.0 available...` before normal command output
  (not for eager exits like `--version`)
- CI opt-out: `KAGAN_SKIP_UPDATE_CHECK=1` or `--skip-update-check` (hidden flag)

Behavioral details for every command are in `docs/internal/features/cli.md`.

______________________________________________________________________

## Package Layout

```
src/kagan/cli/
├── __init__.py        # re-export `cli` for entry_points
├── main.py            # root group, version flag, default-to-tui, error boundary
├── _bootstrap.py      # make_client, run_async, update check helpers
├── _env.py            # environment configuration helpers
├── entrypoint.py      # entry point wrapper
├── imports.py         # kagan import github (GitHub issue import group)
├── tui.py             # kagan tui
├── chat.py            # kagan chat [--prompt] [--session-id]
├── doctor.py          # kagan doctor [--verbosity]
├── list_projects.py   # kagan projects       (not list.py — shadows builtin)
├── mcp.py             # kagan mcp [flags]
├── reset.py           # kagan reset-state [--force] [--project]
├── serve.py           # kagan serve [--port] [--host] [--readonly] [--admin]
├── update.py          # kagan update [--check-only] [--prerelease] [--force]
├── tools.py           # kagan tools enhance [prompt]
├── plugins.py         # kagan plugins sync|list|check
└── web.py             # kagan web (web dashboard convenience wrapper)
```

**17 modules.** No sub-packages. Every file has one job.

______________________________________________________________________

## Entry Point

`pyproject.toml` declares `kagan = "kagan.cli:cli"`. The `__init__.py` re-exports
the root Click group.

______________________________________________________________________

## Root Group (`main.py`)

- Custom `_CLIGroup(click.Group)` subclass — one error boundary for the entire CLI.
  Catches unexpected exceptions, logs them, wraps as `ClickException` for clean output.
- Root group with `invoke_without_command=True` — bare `kagan` delegates to `tui`.
- Eager `--version` option exits immediately.
- Hidden `--skip-update-check` flag (also `KAGAN_SKIP_UPDATE_CHECK` envvar).
- Startup update check: silent, never breaks startup, swallows errors.
- All 11 commands registered explicitly via `cli.add_command()`.

______________________________________________________________________

## The Async Bridge (`_bootstrap.py`)

Core is an in-process SDK. Many core calls are async. Click callbacks are sync.
`_bootstrap.py` provides three helpers:

| Helper                          | Purpose                                              |
| ------------------------------- | ---------------------------------------------------- |
| `make_client(db_path=None)`     | Create a `KaganCore`. One per command invocation.    |
| `run_async(coro)`               | Sync → async boundary via `asyncio.run()`.           |
| `maybe_check_for_updates()`     | Silent PyPI version check. Never breaks startup.     |
| `check_and_install_update(...)` | Detect install method (uv/pipx/pip), fetch, install. |

No Click imports in `_bootstrap.py`. No shared state. Pure utility.

______________________________________________________________________

## Error Handling Boundary

| Exception              | Exit Code | When                            |
| ---------------------- | --------- | ------------------------------- |
| `click.UsageError`     | 2         | Bad flag, missing arg, conflict |
| `click.BadParameter`   | 2         | Invalid param value             |
| `click.ClickException` | 1         | Application-level error         |
| `click.Abort`          | 1         | Ctrl-C / EOF                    |

Strategy:

1. **Parameter conflicts** — raise `click.UsageError`.
1. **Domain errors** — raise `click.ClickException(msg)`.
1. **Unexpected errors** — caught by `_CLIGroup.invoke`, logged, surfaced as `ClickException`.

One place, one policy.

______________________________________________________________________

## Command Implementation Notes

Every command follows the same shape: Click decorators, heavy imports inside the function
body, `make_client()` + `run_async()` for async core calls. Behavioral details for each
command are in `docs/internal/features/cli.md`.

Notable exceptions to the standard pattern:

| Command      | Why it's different                                              |
| ------------ | --------------------------------------------------------------- |
| `tui.py`     | No `make_client()` — TUI creates its own client in `on_mount`   |
| `doctor.py`  | Sync only — preflight checks don't need the async boundary      |
| `mcp.py`     | Calls `kagan.mcp.server.serve(opts)`, blocks on STDIO           |
| `tools.py`   | No `KaganCore` — standalone LLM utility, not a domain operation |
| `plugins.py` | Subgroup with 3 subcommands: `sync`, `list`, `check`            |
| `imports.py` | Subgroup for `kagan import github`; interactive GitHub issue import |
| `serve.py`   | Starts HTTP API server; blocks until stopped                    |
| `web.py`     | Convenience wrapper: starts server + opens browser              |

______________________________________________________________________

## How State Flows

```
 shell
  │
  ▼
cli()                          ← Click parses argv, creates Context
  │
  ├─ --version?                ← eager option: print & exit immediately
  │
  ├─ maybe_check_for_updates() ← silent, never breaks startup
  │
  ├─ no subcommand?            ← delegates to tui
  │
  └─ subcommand resolved       ← Click creates child Context, invokes command
       │
       ▼
     command(args)              ← pure function, receives parsed args
       │
       ├─ client = make_client()  ← lazy import, create SDK instance
       │
       ├─ run_async(client.ns.op())  ← namespaced call, cross async boundary
       │
       └─ click.echo(result)    ← output to stdout
```

For `kagan chat`, session metadata and transcript state are persisted in the core settings store,
so `/sessions` and `--session-id` can re-attach to prior conversations without losing context.

No shared mutable state. No `ctx.obj` passing. Each command creates its own short-lived client.

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

No `tests/cli/` directory — CLI is too thin. Behavioral tests flow through `KaganDriver`
in `tests/core/` and `tests/mcp/`.

One carve-out: `tests/core/test_cli_surface.py` validates CLI help text, exit codes,
and command-surface behavior via Click's `CliRunner` (sync tests), run sequentially.

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                  | Why                                                  |
| ------------------------ | ---------------------------------------------------- |
| Daemon / `kagan core`    | Core is an in-process SDK. No process management.    |
| Typer                    | Adds indirection without earning it for ~9 commands. |
| `commands/` subdirectory | Flat is better than nested. 17 files is manageable.  |
| Base command class       | Each command is a function. No inheritance.          |
| `ctx.obj` state passing  | Commands are independent. No hidden coupling.        |
| Lazy-loading group       | Heavy imports deferred to function bodies instead.   |
| Custom help formatting   | Click's default is good enough.                      |
