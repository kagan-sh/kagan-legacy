# MCP Server Architecture — `kagan.mcp`

*Design principles: python-sdk native, Zen of Python, no cleverness.*

______________________________________________________________________

## References

| Package            | Repo                                                                                  | Use                                                                       |
| ------------------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **MCP Python SDK** | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MCP framework: `MCPServer`, tool registration, lifespan, STDIO transport. |
| **Loguru**         | [Delgan/loguru](https://github.com/Delgan/loguru)                                     | Structured logging.                                                       |

______________________________________________________________________

## Context

`kagan.mcp` exposes kagan's core SDK as an MCP server for two consumers:

1. **IDE hosts** (Cursor, VS Code, etc.) — manage tasks, review diffs, read project state.
1. **Interactive-run agents** — discover kagan via `.mcp.json` and report progress to the board.

Managed executions use ACP (direct STDIO JSON-RPC), not MCP. The `--session-id` flag scopes tool visibility and task context.

______________________________________________________________________

## Design Principles

```text
Simple is better than complex.
There should be one obvious way to do it.
```

1. **One `MCPServer` instance** — created with lifespan that owns a `KaganCore`
1. **Tools are plain functions** — `@mcp.tool()` decorator, type hints drive the schema
1. **Toolsets group by domain** — one file per domain (tasks, projects, reviews, etc.)
1. **Access control is a filter** — tools registered once, filtered at registration time
1. **python-sdk is the framework** — no wrapper abstractions over `MCPServer`
1. **STDIO transport only** — hosts launch `kagan mcp` as a subprocess

______________________________________________________________________

## Internal Structure

```text
CLI: kagan mcp [--role] [--session-id]
                │
                ▼
server.py: create_server(opts)
    ├─ lifespan: create KaganCore
    └─ register_all_toolsets(mcp, opts)
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
toolsets/   toolsets/   toolsets/
tasks.py    projects.py review.py
  task_get    project_list  review_approve
  task_list   project_create
  task_create
toolsets/   toolsets/   toolsets/
sessions.py settings.py plugins.py
  run_start   settings_get  plugins_sync
  run_cancel  settings_set  plugins_preflight
                │
                ▼ (lifespan context)
        ┌───────────────┐
        │ kagan.core    │
        │ (SDK access)  │
        └───────────────┘

Dependencies: kagan.mcp ──► kagan.core only
```

______________________________________________________________________

## Package Layout

```text
src/kagan/mcp/
├── __init__.py        # re-export create_server
├── server.py          # MCPServer factory, lifespan, STDIO entry point
├── _policy.py         # Role-based access control
├── resources.py       # @mcp.resource() definitions
├── prompts.py         # @mcp.prompt() definitions
└── toolsets/          # one file per domain
    ├── __init__.py    # register_all_toolsets()
    ├── tasks.py       # task_get, task_list, task_create, task_update, ...
    ├── sessions.py    # run_start, run_summary, run_cancel, run_exists, ...
    ├── projects.py    # project_list, project_create, project_set_active, ...
    ├── review.py      # review_approve, review_reject, review_merge, ...
    ├── settings.py    # settings_get, settings_set, audit_log_list
    └── plugins.py     # plugins_sync, plugins_preflight
```

______________________________________________________________________

## Server Factory

`server.py` exports `create_server(opts)` and `serve(opts)`:

- `create_server` builds an `MCPServer` with name, version, instructions, and a lifespan
- `serve` calls `create_server` then `mcp.run(transport="stdio")`
- The lifespan creates a `KaganCore`, yields it as app context, closes on shutdown

### Server Options

| Option                   | Default      | Description                                   |
| ------------------------ | ------------ | --------------------------------------------- |
| `role`                   | ORCHESTRATOR | Agent role: WORKER, REVIEWER, or ORCHESTRATOR |
| `session_id`             | None         | Bind to a task session                        |
| `enable_instrumentation` | false        | Enable diagnostics tool                       |

`--readonly` maps to WORKER and `--admin` maps to ORCHESTRATOR for backward compatibility.

______________________________________________________________________

## Lifespan and Context

The lifespan creates a `KaganCore` and `ServerContext` dataclass. Every tool receives `ctx: Context` containing the `KaganCore` instance and `ServerOptions`. No globals, no module-level state.

______________________________________________________________________

## Tool Registration Pattern

Each toolset exports `register(mcp, opts)`. Tools use `@mcp.tool()` decorators; `is_tool_allowed()` filters by role before registration.

### Tool Design Rules

1. **Type hints drive the schema** — parameters become JSON schema
1. **Docstrings become descriptions**
1. **Return dicts** — serialized from domain models
1. **Raise on error** — domain exceptions are caught and wrapped
1. **Session-aware defaults** — `task_id` optional when session-bound

______________________________________________________________________

## Access Control

Access control is a **static filter at registration time**, not runtime middleware. Higher roles include all tools from lower roles.

| Role             | CLI Flag              | Tools Available                                      |
| ---------------- | --------------------- | ---------------------------------------------------- |
| **WORKER**       | `--role WORKER`       | Board awareness + own-task ops (used by task agents) |
| **REVIEWER**     | `--role REVIEWER`     | WORKER + review verdict tools                        |
| **ORCHESTRATOR** | `--role ORCHESTRATOR` | Everything (default; IDE hosts)                      |

`_policy.py` defines `ROLE_TOOLS: dict[AgentRole, frozenset[str]]`. Core wires `--role WORKER` into `.mcp.json` for spawned agents.

______________________________________________________________________

## Session Binding

When `--session-id` is provided:

1. Lifespan auto-opens the owning project
1. `task_id` becomes **optional** — defaults to bound task
1. Agent doesn't need to discover or pass task IDs

Agent env: `KAGAN_MCP_CMD=kagan mcp --session-id {id}`
IDE worktree: `.mcp.json` with matching args

______________________________________________________________________

## When MCP Is Used

**ACP is the primary streaming channel** for managed executions. MCP is used for:

1. **Interactive launch** — agent in IDE/tmux/neovim discovers `.mcp.json`, reports progress
1. **External tools** — IDE hosts browse tasks, orchestrators manage projects

Both MCP and ACP write to the same SQLite `run_events` table.

______________________________________________________________________

## Resources and Prompts

**Resources** (read-only data endpoints):

| URI                       | Description                |
| ------------------------- | -------------------------- |
| `kagan://ping`            | Health check               |
| `kagan://settings`        | Current settings snapshot  |
| `kagan://projects`        | Project list with metadata |
| `kagan://tasks/{task_id}` | Task detail (full mode)    |
| `kagan://runtime`         | Runtime status             |

**Prompts** (reusable templates):

| Prompt                        | Purpose                                   |
| ----------------------------- | ----------------------------------------- |
| `review_task`                 | Structure a code review with diff context |
| `plan_tasks_from_description` | Natural-language to task breakdown        |
| `diagnose_failure`            | Diagnose agent execution failure          |

Both are always available regardless of role.

______________________________________________________________________

## Error Handling

| Exception             | When                            | MCP Result                    |
| --------------------- | ------------------------------- | ----------------------------- |
| Tool validation error | Bad input, not found, bad state | `is_error=true`, text content |
| Core domain error     | InvalidTransitionError, etc.    | Caught, wrapped as tool error |
| Unexpected exception  | Bug                             | Caught by SDK, error content  |
| Tool not registered   | Access control filtered it out  | Not in `tools/list`           |

______________________________________________________________________

## Testing

See `docs/internal/testing.md`. Tests use `create_server(opts)` for in-process tool calls (no subprocess).

______________________________________________________________________

## What This Architecture Does NOT Have

| Omitted                        | Why                                                              |
| ------------------------------ | ---------------------------------------------------------------- |
| HTTP/SSE transport             | Kagan is local-only. STDIO is simplest. Hosts spawn the process. |
| Auth middleware                | Local process, local user. Access control via role flags.        |
| Tool wrapper/base class        | `@mcp.tool()` is the abstraction.                                |
| Runtime role switching         | Rebuild the server for a different role.                         |
| Custom serialization framework | Standard JSON serialization of model dicts.                      |
