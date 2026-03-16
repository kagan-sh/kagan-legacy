# MCP Server Architecture — `kagan.mcp`

*Design principles: python-sdk native, Zen of Python, no cleverness.*

______________________________________________________________________

## References

| Package            | Repo                                                                                  | Use                                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **MCP Python SDK** | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MCP framework: `MCPServer`, tool registration, lifespan, STDIO transport.                               |
| **Loguru**         | [Delgan/loguru](https://github.com/Delgan/loguru)                                     | Structured logging. Config and sink setup in core — see `docs/internal/architecture/core.md` § Logging. |

______________________________________________________________________

## Context

`kagan.mcp` exposes kagan's core SDK as an MCP server. Two consumers:

1. **IDE hosts** (Cursor, VS Code, Windsurf, Kiro, Claude Code) — connect to kagan's MCP server
   to manage tasks, review diffs, and read project state.
1. **PAIR-mode agents** — running inside an IDE, tmux, or neovim, agents discover kagan via
   `.mcp.json` in the worktree and call MCP tools to report progress back to the board.

AUTO executions use ACP (direct STDIO JSON-RPC), not MCP — see `docs/internal/architecture/core.md`
§ Event Streaming. MCP is for PAIR mode and external tool integrations.

Both consumers use the same server code. The `--session-id` flag scopes which tools are
visible and which task context is active.

______________________________________________________________________

## Design Principles

```
Simple is better than complex.
There should be one obvious way to do it.
Namespaces are one honking great idea.
```

1. **One `MCPServer` instance** — created with lifespan that owns a `KaganCore`

1. **Tools are plain functions** — `@mcp.tool()` decorator, type hints drive the schema

1. **Toolsets group by domain** — one file per domain (tasks, projects, reviews, etc.)

1. **Access control is a filter** — tools are registered once, filtered at registration time

1. **python-sdk is the framework** — no wrapper abstractions over `MCPServer`, `ServerContext`, etc.

1. **STDIO transport only** — hosts launch `kagan mcp` as a subprocess

______________________________________________________________________

## Internal Structure

```
                      ┌────────────────────────────────────────────────┐
                      │              CLI entry point                    │
                      │   kagan mcp [--readonly] [--admin]            │
                      │             [--session-id]                     │
                      │             [--enable-internal-...]            │
                      └──────────────────┬─────────────────────────────┘
                                         │
                                         ▼
                      ┌────────────────────────────────────────────────┐
                      │              server.py                         │
                      │                                                │
                      │  create_server(opts) -> MCPServer              │
                      │    ├─ lifespan: create KaganCore               │
                      │    ├─ register_all_toolsets(mcp, opts)         │

│    ├─ lifespan: create KaganCore               │
│    ├─ register_all_toolsets(mcp, opts)         │
                      └──────────────────┬─────────────────────────────┘
                                         │
            ┌────────────────────────────┼──────────────────────────────┐
            │  register_all_toolsets()   │  walks toolset modules       │
            │  applies access filter     │  based on access tier        │
            ▼                            ▼                              ▼
  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │  toolsets/        │  │  toolsets/        │  │  toolsets/        │
  │  tasks.py         │  │  projects.py      │  │  review.py        │
  │                   │  │                   │  │                   │
  │  task_get         │  │  project_list     │  │  review_decide    │

  │  task_list        │  │  project_create   │  │                   │
  │  task_create      │  │  project_set_active│  │                   │
  │  task_update      │  │  ...              │  │                   │
  │  task_events      │  │                   │  │                   │
  │  tasks_wait       │  │                   │  │                   │
│  task_events      │  │                   │  │                   │
  │  ...              │  │                   │  │                   │
  └──────────────────┘  └──────────────────┘  └──────────────────┘

  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │  toolsets/        │  │  toolsets/        │  │  toolsets/        │
  │  sessions.py      │  │  settings.py      │  │  diagnostics.py   │
  │                   │  │                   │  │                   │
  │  run_start        │  │  settings_get     │  │  diagnostics_     │
  │  tasks_wait       │  │  settings_set     │  │  get_             │
  │  run_cancel       │  │  audit_log_list   │  │  instrumentation  │
  └──────────────────┘  └──────────────────┘  └──────────────────┘

  ┌──────────────────┐
  │  toolsets/        │
  │  plugins.py       │
  │                   │
  │  plugins_sync     │
  │  plugins_preflight│
  │                   │
  └──────────────────┘

            │
            │ all tools use          ┌──────────────────────────────┐
            ├───────────────────────►│  _policy.py                  │
            │                        │                              │
            │                        │  3-tier access (read/write/  │
            │                        │  admin) + readonly exclusion │
            │                        │  is_tool_allowed() check     │

            │                        └──────────────────────────────┘
            │
            │ tools read/write       ┌──────────────────────────────┐
├───────────────────────►│  kagan.core (in-process SDK) │
│  via lifespan context  │  ctx → client → client.tasks │
│                        │                 client.projects│
│                        │                 client.reviews │
            │
            │ resources + prompts    ┌──────────────────────────────┐
            └───────────────────────►│  resources.py + prompts.py   │
                                     └──────────────────────────────┘


  DEPENDENCY DIRECTION (strictly one-way):

    kagan.mcp ──► kagan.core     (uses KaganCore)

    kagan.mcp ──✘──► kagan.tui   NEVER
    kagan.mcp ──✘──► kagan.cli   NEVER
    kagan.core ──✘──► kagan.mcp  NEVER
```

______________________________________________________________________

## Package Layout

```
src/kagan/mcp/
├── __init__.py        # re-export create_server
├── server.py          # MCPServer factory, lifespan, STDIO entry point
├── _policy.py         # 3-tier access control (readonly / standard / admin)

├── resources.py       # @mcp.resource() definitions
├── prompts.py         # @mcp.prompt() definitions
└── toolsets/          # one file per domain
    ├── __init__.py    # register_all_toolsets()
    ├── tasks.py       # task_get, task_list, task_create, task_update, ...
    ├── sessions.py    # run_start, run_summary, run_cancel, run_update
    ├── projects.py    # project_list, project_create, project_set_active, ...
    ├── review.py      # review_decide
    ├── settings.py    # settings_get, settings_set, audit_log_list
    ├── plugins.py     # plugins_sync, plugins_preflight
```

8 files + toolsets/ sub-package. The toolsets sub-package earns its nesting — it groups
~27 tools by domain and keeps `server.py` lean.

______________________________________________________________________

## Server Factory

`server.py` exports `create_server(opts)` and `serve(opts)`.

- `create_server` builds an `MCPServer` with name, version, instructions, and a lifespan.
- `serve` calls `create_server` then `mcp.run(transport="stdio")`.
- The lifespan creates a `KaganCore`, yields it as app context, and closes it on shutdown.
  | `readonly` | false | Exclude all mutating tools (read tier) |
  | `admin` | false | Enable destructive tools (admin tier) |
  | `session_id` | None | Bind to a task session |

### Server Options

| Option                   | Default | Description                            |
| ------------------------ | ------- | -------------------------------------- |
| `readonly`               | false   | Exclude all mutating tools (read tier) |
| `readonly`               | false   | Exclude all mutating tools (read tier) |
| `admin`                  | false   | Enable destructive tools (admin tier)  |
| `session_id`             | None    | Bind to a task session                 |
| `session_id`             | None    | Bind to a task session                 |
| `enable_instrumentation` | false   | Enable diagnostics tool                |

______________________________________________________________________

## Lifespan and Context

The lifespan async context manager creates a `KaganCore` and a `ServerContext` dataclass
(containing the client + server options). This context is available to every tool, resource, and prompt via the MCP `Context` parameter.

Every tool function receives `ctx: Context` as a parameter. From it, the tool extracts:

- The `KaganCore` instance
- The `ServerOptions` (to check session binding, etc.)

No globals. No module-level state. Context flows through the framework.

______________________________________________________________________

## Tool Registration Pattern

Each toolset file exports a `register(mcp, opts)` function. Inside, tools are registered
with `@mcp.tool()` decorators. Before registering each tool, `is_tool_allowed()` is called
to check if the tool passes the access control filter for the current opts.
The host never knows they exist. No runtime authorization, no error envelopes.

### Tool Design Rules

1. **Type hints drive the schema** — parameter types become the JSON schema for the tool.
1. **Docstrings become descriptions** — the tool's `description` is its docstring.
1. **Return dicts** — serialized from domain models. No custom serialization framework.
1. **Raise on error** — domain exceptions from core are caught and wrapped as tool errors.
1. **Session-aware defaults** — tools that accept `task_id` make it optional when session-bound.

______________________________________________________________________

## Access Control

Access control is a **static filter at registration time**, not runtime middleware.
Three tiers, mapped to trust level (user presence).

### Three Tiers

| Tier         | Flag         | Trust model                    | Can do                                                                                            |
| ------------ | ------------ | ------------------------------ | ------------------------------------------------------------------------------------------------- |
| **Readonly** | `--readonly` | Observer — no mutations        | Read tasks, projects, settings, audit, logs                                                       |
| **Standard** | *(none)*     | Autonomous agent — safe writes | + create/update/add-note tasks, batch-create tasks, manage runs, start/cancel runs, apply reviews |

Each tier includes all lower tiers. Standard is the common case — task agents get it automatically. Admin is for orchestrators where the user is present and approving each action.

### Who Gets What

| Consumer               | Flags               | Tier     |
| ---------------------- | ------------------- | -------- |
| Task agent (AUTO/PAIR) | `--session-id {id}` | Standard |

| Orchestrator (IDE host) | `--admin` | Admin |
| Reviewer agent | `--readonly --session-id {id}` | Readonly |
| IDE host (browse only) | `--readonly` | Readonly |

Core wires these flags into `.mcp.json` automatically when spawning agents.

### Tool Tier Requirements

| tool                                                       | minimum tier |
| ---------------------------------------------------------- | ------------ |
| task_get, task_list, task_events, tasks_wait               | Readonly     |
| project_list, repo_list, settings_get, audit_log_list      | Readonly     |
| plugins_preflight                                          | Readonly     |
| task_create, task_batch_create, task_update, task_add_note | Standard     |
| run_start, run_cancel, run_update, project_set_active      | Standard     |
| review_decide                                              | Standard     |
| task_delete, project_create, project_delete                | Admin        |
| settings_set                                               | Admin        |
| plugins_sync                                               | Admin        |

### Readonly Mode

`--readonly` excludes all mutating tools. Only read tools, resources, and prompts
are available. `--readonly` and `--admin` are mutually exclusive.

______________________________________________________________________

## Tool Profiles

Tool profiles provide **per-role tool filtering** on top of access tiers. While access tiers control _which tier_ of tools is available, profiles further restrict _which tools_ within that tier an agent can see.

### ToolProfile StrEnum

Defined in `kagan.core.enums`:

| Profile | Intended consumer | Tool count |
|---|---|---|
| `TASK` | Autonomous task agent (AUTO mode) | ~8 |
| `REVIEWER` | Reviewer agent checking acceptance criteria | ~13 |
| `ORCHESTRATOR` | Orchestrator with full visibility | All tools in tier |

### TOOL_PROFILES Dict

`TOOL_PROFILES: dict[ToolProfile, frozenset[str]]` in `kagan.mcp._policy` maps each profile to an explicit allowlist of tool names:

- **TASK**: `task_get`, `task_list`, `task_search`, `task_events`, `task_add_note`, `run_update`, `run_summary`, `settings_get`
- **REVIEWER**: all TASK tools + `review_decide`, `review_set_criterion_verdict`, `review_clear_verdicts`, `review_conflicts`, `tasks_wait`, `task_counts`
- **ORCHESTRATOR**: all tools in `TOOL_TIERS` (no additional restriction — effective tier still applies)

### Composition with Access Tiers

Profile filtering is **additive** — both the tier check AND the profile check must pass:

```python
# Both conditions must be true for a tool to be registered:
effective_tier.value >= required_tier.value   # tier check
AND
(profile is None or tool_name in TOOL_PROFILES[profile])  # profile check
```

`profile=None` (the default) disables profile filtering entirely — all tools for the effective tier are visible. This preserves full backwards compatibility.

### Who Gets What Profile

| Consumer | Tier | Profile | Effect |
|---|---|---|---|
| Task agent (AUTO) | Standard | `TASK` | ~8 task-focused tools |
| Reviewer agent | Standard | `REVIEWER` | ~13 tools including review ops |
| Orchestrator | Admin | `ORCHESTRATOR` | All tools |
| External / manual | Any | `None` (default) | All tools for tier |

Profile is passed via `--profile <name>` CLI flag on `kagan mcp`. `build_mcp_manifest()` in `_agent.py` propagates the profile flag automatically when spawning agents.

### Exhaustiveness Guarantee

A test in `tests/unit/test_tool_profiles.py` (`test_profile_exhaustiveness`) asserts that the union of all `TOOL_PROFILES` values equals `set(TOOL_TIERS.keys())`. This ensures no tool is ever "orphaned" (unassigned to any profile).

______________________________________________________________________

## Session Binding

When `--session-id` is provided:

1. The lifespan auto-opens the project that owns the run's task.

1. Tools that accept `task_id` make it **optional** — defaults to the bound task.

1. The agent doesn't need to discover or pass task IDs.

This is how agents and IDE pair-mode sessions communicate:

- Agent env: `KAGAN_MCP_CMD=kagan mcp --session-id {id}`
- IDE worktree: `.mcp.json` with `args: ["mcp", "--session-id", "{id}"]`

______________________________________________________________________

## When MCP Is Used

**ACP is the primary streaming channel for AUTO executions** — kagan spawns the agent
and speaks ACP over STDIO (see `docs/internal/architecture/core.md` § Event Streaming).

MCP is used in two cases:

1. **PAIR mode** — the agent runs inside an IDE, tmux, or neovim. It discovers
   `.mcp.json` in the worktree and calls MCP tools to report progress back to the board.
1. **External tools** — IDE hosts browse tasks, orchestrators manage projects, or users
   connect custom tools to kagan via `kagan mcp [flags]`.

```
Agent in IDE/tmux (or external tool)   kagan MCP server               Core DB
   │                                       │                             │
   │── discovers .mcp.json ───────────────►│                             │
   │                                       │── KaganCore() ─────────────►│

   │                                       │                             │
   |── task_add_note("found the bug") ────►|── client.tasks.add_note() ──►|
   │                                       │                             │
   |── task_update(status="review") ──────►|── client.tasks.set_status() ─►|
   │                                       │                             │
   |── task_events(write event) ────────►|── client.tasks.events.emit()►|

   | task_update(status="review") ──────►|── client.tasks.set_status() ─►|
|                                       │                             │
| task_events(write event) ────────►|── client.tasks.events.emit()►|
                                                              ◄── task.events.stream()
                                                                  (TUI wakes reactively)
```

The MCP server creates its own `KaganCore` pointing at the same SQLite DB.

Events written via MCP and events written via ACP end up in the same `run_events`
table — consumers can't tell the difference.

______________________________________________________________________

## Resources

Resources are read-only data endpoints. Hosts use them for context without calling tools.

| URI                       | Description                                       |
| ------------------------- | ------------------------------------------------- |
| `kagan://ping`            | Health check                                      |
| `kagan://settings`        | Current settings snapshot                         |
| `kagan://projects`        | Project list with metadata                        |
| `kagan://tasks/{task_id}` | Task detail (full mode)                           |
| `kagan://runtime`         | Runtime status — active sessions, agent processes |

Resources are always available regardless of access tier.

______________________________________________________________________

## Prompts

Prompts are reusable templates that hosts can invoke.

| Prompt        | Parameters | Purpose                                   |
| ------------- | ---------- | ----------------------------------------- |
| `review_task` | task_id    | Structure a code review with diff context |

| `plan_tasks_from_description` | description | Natural-language to task breakdown |
| `diagnose_failure` | task_id, failure_summary | Diagnose agent execution failure |

Prompts are always available regardless of access tier.

______________________________________________________________________

## Error Handling

Tools raise exceptions. The python-sdk catches them and returns error content blocks.

| Exception             | When                                        | MCP Result                               |
| --------------------- | ------------------------------------------- | ---------------------------------------- |
| Tool validation error | Bad input, not found, bad state             | `is_error=true`, text content            |
| Core domain error     | InvalidTransitionError, NotFoundError, etc. | Caught, wrapped as tool error            |
| Unexpected exception  | Bug                                         | Caught by SDK, returned as error content |
| Tool not registered   | Access control filtered it out              | Not in `tools/list` — host can't call it |

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

MCP-specific: no subprocess, no STDIO in tests. `create_server(opts)` returns a testable
`MCPServer` instance; the router driver dispatches tool calls in-process.

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                        | Why                                                                    |
| ------------------------------ | ---------------------------------------------------------------------- |
| HTTP/SSE transport             | Kagan is local-only. STDIO is simplest. Hosts spawn the process.       |
| Auth middleware                | Local process, local user. Access control via 3-tier flags.            |
| Tool wrapper/base class        | `@mcp.tool()` is the abstraction. Adding a layer earns nothing.        |
| Runtime tier switching         | Rebuild the server for different access tier. One process, one config. |
| Custom serialization framework | Standard JSON serialization of model dicts.                            |
