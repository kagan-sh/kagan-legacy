# KaganCore — Architecture

## Context

`kagan.core` is an in-process SDK that frontends use to manage a kanban board and run AI coding
agents. `KaganCore` owns the DB, enforces the task lifecycle, provisions git worktrees, spawns
agents, and streams progress back to callers.

**The fundamental abstraction is a Task.** A Task is a kanban ticket. When started, it gets an
isolated worktree and an agent session. Managed runs execute autonomously as detached processes that
survive client exit. Interactive launches open an editor or terminal for collaborative work.
Kagan is backend-agnostic, but the contract is capability-based: `codex` and `claude-code` are the
reference backends that exercise the shared launch, stream, and review paths. Other CLI-based
coding agents remain supported when they conform to the same interface.

## Design Principles

```text
Simple is better than complex.
Flat is better than nested.
There should be one obvious way to do it.
```

1. **One class, one import** — `from kagan.core import KaganCore`
1. **Fluent API by domain** — `client.tasks.create()`, `client.projects.list()`, `client.reviews.merge()`
1. **SQLModel for models + DB** — one class is both validation model and table definition
1. **Unified Session** — one `Session` model; interactive launches identified by launcher metadata
1. **Core owns execution** — backend launch, agent spawning, worktree provisioning all live in core
1. **Capability-based backends** — vendor names are data; launch behavior follows declared capabilities
1. **DB is the durable buffer** — ACP and MCP paths write to the same table; clients reconnect seamlessly
1. **Async public API** — Textual is async, MCP is async, agent spawning is async
1. **Reactive event streaming** — `task.events.stream()` uses `asyncio.Event` signaling, not polling
1. **No chat logic** — conversational abstractions live in `kagan.cli.chat`, not here

## References

| Package      | Repo                                                                      | Use                                            |
| ------------ | ------------------------------------------------------------------------- | ---------------------------------------------- |
| **ACP**      | [anthropics/agent-protocol](https://github.com/anthropics/agent-protocol) | Agent Client Protocol for ACP-capable agents   |
| **SQLModel** | [fastapi/sqlmodel](https://github.com/fastapi/sqlmodel)                   | Models + DB: one class as table and validation |
| **Loguru**   | [Delgan/loguru](https://github.com/Delgan/loguru)                         | Structured logging                             |

## Module Layout

```text
kagan/core/
├── __init__.py            # re-exports KaganCore, models, enums, errors
├── client.py              # KaganCore + domain namespace classes
├── models.py              # SQLModel table classes
├── enums.py               # TaskStatus, SessionStatus, Priority, SessionEventType
├── errors.py              # KaganError hierarchy
│
├── git.py                 # git operations wrapper (public module)
├── _acp.py                # ACP adapter: KaganACPClient + event mapping
├── _agent.py              # agent backend registry + launcher
├── _asyncio_compat.py     # asyncio compatibility shims
├── _audit.py              # audit log repository
├── _config.py             # TOML read/write
├── _db.py                 # engine factory and session management
├── _db_helpers.py         # sqlite-specific pragmas and helpers
├── _events.py             # session event repository
├── _launchers.py          # interactive environment launchers
├── _logging.py            # loguru configure_logging()
├── _attached_backends.py  # interactive backend availability helpers
├── _persona.py            # persona pipeline definitions
├── _preflight.py          # system health checks
├── _projects.py           # project repository
├── _prompts/              # three-layer prompt resolution and packaged prompt text
├── _repetition_guard.py   # loop detection for tool calls
├── _reviews.py            # review repository
├── _sessions.py           # agent session repository
├── _settings.py           # settings repository
├── _tasks.py              # task repository
├── transitions.py         # task lifecycle state machine (public — no underscore)
├── _utils.py              # utility functions
├── _watcher.py            # DBWatcher: filesystem DB change watcher
├── _worktrees.py          # worktree management logic
│
├── _agent_monitor.py      # post-agent evaluation and rebase helpers
├── _checkpoints.py        # task execution checkpoints (create, list, rewind, cleanup)
├── _compaction.py         # database compaction
├── _event_rendering.py    # event display rendering helpers
├── _hooks.py              # guard functions for repeated and dangerous tool calls
├── _insights.py           # project insight extraction with decay and relevance
├── _prompt_export.py      # prompt export functionality
├── _security.py           # security helpers
├── _session_helpers.py    # session utility functions
├── _verification.py       # step-level verification tracking for acceptance criteria
│
└── adapters/              # adapter sub-package
    ├── __init__.py
    ├── pi_rpc.py          # JSONL-framed RPC adapter for pi-coding-agent
    ├── pi_rpc_messages.py # Typed message models for pi RPC protocol
    └── db/                # database adapters
```

~42 files. Flat structure with private modules (underscore prefix) and adapters sub-package.

## Integrations

Native integrations live in `kagan.core.integrations`. Today GitHub is the only native
integration, exposed through the module-level `github` singleton and `all_enabled()`.
There is no protocol, ABC, metaclass, or entry-point discovery layer around it.

The old entry-point plugin system (ABC hierarchy, dynamic discovery, community-plugin env flag)
was removed in the `refactor/native-integrations` branch. There are no backwards-compat shims.

The GitHub integration stores the canonical task-to-issue link on `Task.github_issue` as
`<owner>/<repo>#<number>`. Body / title / priority / acceptance-criteria sync bidirectionally;
status lifecycles (kanban column ↔ issue open/closed) are intentionally decoupled. Acceptance
criteria sync via a comment tagged `<!-- kagan:acceptance-criteria -->` rather than rewriting
the issue body. A separate `kagan.core.integrations.mentions` module powers `#`-mention
autocomplete with dual-source results (kagan tasks from the local DB + GitHub issues from `gh`).

## Frontend Construction

Every frontend creates a `KaganCore` the same way. The constructor takes only `db_path`
(optional, defaults to `~/.local/share/kagan/kagan.db`). No `project_path` — repo paths are
stored in the `Repository` table and loaded when a project is opened.

| Frontend | Construction                                            |
| -------- | ------------------------------------------------------- |
| TUI      | Creates client in `on_mount`, passes to screens         |
| CLI      | `_bootstrap.make_client()` helper, used in each command |
| MCP      | Lifespan context creates client at startup              |

One obvious way: `KaganCore()`. No factories, no DI frameworks.

## Surface Hierarchy

Kagan has one core model and three primary shells:

| Surface | Role                                                                            |
| ------- | ------------------------------------------------------------------------------- |
| TUI     | Primary operator surface for creating tasks, running agents, and reviewing work |
| Web     | Remote companion surface for supervising the same workflow from another device  |
| VS Code | Embedded companion surface for watching, attaching, and reviewing in-editor     |

The CLI remains the lowest-friction entry point for setup and automation. MCP is a transport and
tool surface for external clients, not a separate product model.

## Data Models

### Tables

| Table            | Key Fields                                                                                                                       | Purpose                                |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| **Project**      | id, name, created_at                                                                                                             | Top-level grouping                     |
| **Repository**   | id, project_id, path, default_branch                                                                                             | Git repo linked to project             |
| **Task**         | id, project_id, title, description, status, priority, base_branch, review_approved, acceptance_criteria, agent_backend, launcher | The core abstraction — a kanban ticket |
| **Worktree**     | id, task_id, repo_id, worktree_path, branch_name                                                                                 | Git worktree for a task                |
| **Session**      | id, task_id, agent_backend, status, launcher, pid, input_tokens, output_tokens, cost_amount                                      | Agent execution record                 |
| **SessionEvent** | id, task_id, run_id, event_type, payload (JSON), created_at                                                                      | Agent progress stream                  |
| **TaskNote**     | id, task_id, content, created_at                                                                                                 | Timestamped notes on a task            |
| **Setting**      | key (PK), value                                                                                                                  | Key-value settings                     |
| **AuditEntry**   | id, action, entity_type, entity_id, detail (JSON), created_at                                                                    | Audit trail                            |

### Done Tasks

When a task reaches DONE (via `review.merge()`), the worktree is merged into the base branch
and the Worktree row is removed. Task, Session, and SessionEvent rows remain for history.
Reopening (DONE → BACKLOG) leaves the task without a worktree until the next `run()`.

## Enums

| Enum                  | Values                                                                                                                                                                           |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **TaskStatus**        | BACKLOG, IN_PROGRESS, REVIEW, DONE                                                                                                                                               |
| **SessionStatus**     | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED                                                                                                                                   |
| **Priority**          | LOW, MEDIUM, HIGH, CRITICAL                                                                                                                                                      |
| **SessionEventType**  | OUTPUT_CHUNK, AGENT_STATUS, TOOL_CALL_START, TOOL_CALL_UPDATE, AGENT_COMPLETED, AGENT_FAILED, PLAN_UPDATE, TASK_STATUS_CHANGED, MERGE_COMPLETED, MERGE_FAILED, CRITERION_VERDICT |
| **BranchRefStrategy** | LOCAL, REMOTE, LOCAL_IF_AHEAD                                                                                                                                                    |

## Error Hierarchy

| Error                                                 | When                                            |
| ----------------------------------------------------- | ----------------------------------------------- |
| **KaganError**                                        | Base for all kagan errors                       |
| **NotFoundError**                                     | Entity not found                                |
| **InvalidTransitionError**                            | Illegal status move                             |
| **WorktreeError**                                     | Git worktree operation failed                   |
| **MergeConflictError** (extends WorktreeError)        | Merge produced conflicts                        |
| **AgentError**                                        | Agent spawn or communication failure            |
| **PreflightError**                                    | Blocking preflight issue prevents operation     |
| **ValidationError**                                   | Input validation failures                       |
| **ConfigurationError**                                | Configuration or state issues                   |
| **SessionError**                                      | Session operation failures                      |
| **MultiRepoUnsupportedError** (extends WorktreeError) | Task execution attempted against multiple repos |

## Fluent API

The client is a composition root. Each domain is a namespace object with focused methods.
**Principle:** The namespace is the subject — don't repeat it in method names.
`client.tasks.get(id)` not `client.tasks.get_task(id)`; `client.projects.list()` not `client.projects.list_projects()`.

### KaganCore (composition root)

| Member                   | Type                                  |
| ------------------------ | ------------------------------------- |
| `client.tasks`           | Tasks                                 |
| `client.tasks.events`    | Events                                |
| `client.projects`        | Projects                              |
| `client.worktrees`       | Worktrees                             |
| `client.reviews`         | Reviews                               |
| `client.settings`        | Settings                              |
| `client.audit_log`       | AuditLog                              |
| `client.persona_presets` | PersonaPresetOps                      |
| `client.aclose()`        | Dispose engine, await agent cleanup   |
| `client.close()`         | Sync best-effort wrapper around close |
| `client.preflight()`     | Check system requirements             |
| `client.reset()`         | Wipe all data                         |
| `client.db_version()`    | Current Alembic migration revision    |

Supports async context manager (`async with KaganCore() as client`). Async owners
(TUI, server, MCP lifespan) must call `await client.aclose()` on shutdown so
spawned subprocess transports are drained before the event loop closes.

### Namespace Methods Overview

| Namespace           | Key Methods                                                                                                                                   |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **tasks**           | `create()`, `get()`, `list()`, `update()`, `set_status()`, `delete()`, `search()`, `run()`, `cancel()`, `add_note()`, `wait_for_completion()` |
| **tasks.events**    | `list()`, `list_recent()`, `latest()`, `emit()`, `stream()`, `stream_all()`, `stream_board()`                                                 |
| **projects**        | `create()`, `get()`, `list()`, `set_active()`, `delete()`, `add_repo()`, `repos()`, `resolve_repo_path()`                                     |
| **worktrees**       | `create()`, `get()`, `diff()`, `diff_stats()`, `cleanup()`, `cleanup_orphans()`                                                               |
| **reviews**         | `approve()`, `reject()`, `merge()`, `rebase()`, `abort_rebase()`, `continue_rebase()`, `conflicts()`, `set_criterion_verdict()`               |
| **settings**        | `get()`, `set()`                                                                                                                              |
| **audit_log**       | `list()`, `record()`                                                                                                                          |
| **persona_presets** | `audit_repo()`, `import_from_github()`, `export_to_github()`, `list_whitelist()`, `add_to_whitelist()`, `remove_from_whitelist()`             |

### Prompt Resolution

Three-layer hierarchy:

| Layer       | Mechanism                           | Effect                                    |
| ----------- | ----------------------------------- | ----------------------------------------- |
| **Layer 0** | Code defaults + behavioral settings | Compiles settings into prompt clauses     |
| **Layer 1** | `additional_instructions` setting   | Single text field appended to all prompts |
| **Layer 2** | `.kagan/prompts/*.md` dotfiles      | Full replacement; bypasses Layers 0 and 1 |

Key functions in `_prompts`: `resolve_orchestrator_prompt()`, `resolve_task_prompt()`, `resolve_review_prompt()`.

`execution.md` dotfiles may include template placeholders (`{title}`, `{description}`, `{acceptance_criteria}`). If rendering fails, Kagan falls back to default compiled prompt.

#### Project Learnings Injection

`resolve_task_prompt()` accepts optional `learnings: list[str]`. When provided, a `PROJECT CONTEXT` section is appended. Learnings are sourced from `TaskNote` rows starting with `[LEARNING]`, filtered by `project_id`, ordered newest-first, deduplicated, and capped at 20.

## Persona Pipeline

Built-in personas: `analyst` (reads codebase), `planner` (breaks work into subtasks), `implementer` (executes changes), `reviewer` (checks diffs against criteria).

A task can be executed across multiple sessions with different personas in sequence (analyst → planner → implementer → reviewer).

## DBWatcher

`DBWatcher` provides reactive board change detection for consumers that need to track the full board state (e.g., chat integration, web dashboard sync).

- Polls the DB at a configurable interval and compares snapshots
- Detects: task creation, deletion, status changes, execution mode changes
- Emits structured change events to registered listeners
- Used by `kagan.cli.chat` to provide context updates when the board changes
- Distinct from `tasks.events.stream()` (streams agent progress for single task)

## Event Streaming

`tasks.events.stream()` is an async generator yielding `SessionEvent` rows reactively using `asyncio.Event` signaling (not polling). When `emit()` inserts a row, it signals waiting streams. A 5-second safety timeout ensures liveness.

### Three Streaming Paths

|                   | ACP (managed)                     | MCP (interactive / external)         | Pi RPC (pi-coding-agent)            |
| ----------------- | --------------------------------- | ------------------------------------ | ----------------------------------- |
| **When**          | ACP-capable backends              | Interactive launches, IDE hosts      | `pi-coding-agent` backend           |
| **Transport**     | Direct STDIO JSON-RPC (ACP)       | Agent spawns kagan MCP as subprocess | JSONL over subprocess stdin/stdout  |
| **Bidirectional** | Yes — kagan sends prompts, cancel | No — caller invokes tools            | Yes — kagan sends commands, abort   |
| **Process**       | Kagan owns (can terminate)        | Agent runs in external environment   | Kagan owns (long-lived per session) |

**Path A — ACP:** Backends with `ACP_STREAMING` capability use piped stdin/stdout. Events flow through `KaganACPClient.session_update()` → `map_acp_update_to_event()` → `Events.emit()`. A repetition guard hashes tool calls and cancels stuck agents (≥4 identical calls in last 10).

**Path B — MCP:** Agent discovers `.mcp.json` in worktree and spawns `kagan mcp --session-id {id}`. MCP tool calls write events to the DB.

**Path C — Pi RPC:** `pi-coding-agent` uses `adapters/pi_rpc.PiRpcClient`. The process is spawned once per session and kept alive across prompts. `translate_pi_rpc_message()` converts pi JSONL frames to `AgentEvent` instances. See the Pi RPC adapter section below.

All three converge at `tasks.events.stream()`.

### Secret Scrubbing

`Events.emit()` calls `_scrub_secrets(payload)` before persisting. Deep-traverses dicts, pattern-matches AWS keys, GitHub tokens, OpenAI keys, private keys, and keys named `password`, `secret`, `token`, `api_key`, etc. Non-mutating — returns a new dict.

## Agent Persistence

```
Managed (ACP):
  kagan --spawns--> Agent subprocess (piped stdio)
  ├─ events via ACP session/update
  └─ kagan exit/cancel → agent terminates and is awaited before loop shutdown

Interactive (MCP):
  kagan --launches--> IDE/tmux/neovim
  ├─ agent discovers .mcp.json
  ├─ reports via MCP tool calls
  └─ survives kagan exit; reconnect resumes from DB
```

Key points: **DB is the durable buffer** — both paths write to the same table. Session status updates to COMPLETED/FAILED when done.

### Agent Environment Variables

| Var                | Purpose                                                    |
| ------------------ | ---------------------------------------------------------- |
| `KAGAN_TASK_ID`    | Which task this agent is working on                        |
| `KAGAN_SESSION_ID` | Which session to report progress to                        |
| `KAGAN_DB_PATH`    | Path to SQLite database                                    |
| `KAGAN_WORKTREE`   | Working directory (the git worktree)                       |
| `KAGAN_MCP_CMD`    | Command to start kagan's MCP server scoped to this session |

## Internal Modules

### `_db.py` — Engine Factory

Provides `create_db_engine(db_path)` and `default_db_path()`. Sync SQLModel engine with WAL mode and FK enforcement. Creates all tables on first use.

### `transitions.py` — Task Lifecycle State Machine

Valid transitions:

```
BACKLOG ────► IN_PROGRESS
IN_PROGRESS ─► REVIEW
IN_PROGRESS ─► BACKLOG
REVIEW ──────► DONE (only via review.merge)
REVIEW ──────► IN_PROGRESS
REVIEW ──────► BACKLOG
DONE ───────► BACKLOG (via task.set_status)
```

Direct DONE from `task.set_status()` is blocked; only `review.merge()` can transition to DONE.

### `git.py` — Git Operations

Created per-repo via `client._git_for_task()`. Operations: `worktree_add`, `worktree_remove`, `diff`, `merge`, `rebase`, etc.

### `_agent.py` — Agent Backend Registry and Launcher

Kagan supports any CLI-based coding agent through a backend registry.

| Backend           | CLI Executable | Notes                                           |
| ----------------- | -------------- | ----------------------------------------------- |
| `claude-code`     | `claude`       | Anthropic                                       |
| `codex`           | `codex`        | OpenAI                                          |
| `gemini-cli`      | `gemini`       | Google                                          |
| `kimi-cli`        | `kimi`         | Moonshot                                        |
| `github-copilot`  | `copilot`      | GitHub                                          |
| `goose`           | `goose`        | Block                                           |
| `openhands`       | `openhands`    | Open-source                                     |
| `opencode`        | `opencode`     | Open-source                                     |
| `auggie`          | `auggie`       | Augment                                         |
| `amp`             | `amp`          | Sourcegraph                                     |
| `docker-cagent`   | `cagent`       | Docker                                          |
| `stakpak`         | `stakpak`      | Infrastructure                                  |
| `mistral-vibe`    | `vibe`         | Mistral                                         |
| `vt-code`         | `vtcode`       | VT Code                                         |
| `pi-coding-agent` | `npx`          | Pi (Mariozechner) — JSONL-RPC, not CLI-launched |

**Backend aliases:** `claude` → `claude-code`; `gemini` → `gemini-cli`; `kimi` → `kimi-cli`; `pi` → `pi-coding-agent`.

**Launch sequence:**

1. Look up backend in registry → get executable + args template
1. Write `.mcp.json` into worktree
1. Set env vars (`KAGAN_TASK_ID`, `KAGAN_SESSION_ID`, `KAGAN_MCP_CMD`, etc.)
1. Spawn as **detached OS process** (new process session)
1. Return Session

**MCP flag wiring per consumer:**

| Consumer       | `.mcp.json` args                   | Access tier             |
| -------------- | ---------------------------------- | ----------------------- |
| Task agent     | `mcp --session-id {id}`            | Standard (read + write) |
| Orchestrator   | `mcp --admin`                      | Admin (+ destructive)   |
| Reviewer agent | `mcp --readonly --session-id {id}` | Readonly                |

### `_launchers.py` — Interactive Environment Launchers

| Launcher                                    | Environment               |
| ------------------------------------------- | ------------------------- |
| **tmux**                                    | Detached tmux session     |
| **ide** (vscode / cursor / windsurf / kiro) | IDE opens worktree folder |
| **neovim**                                  | Neovim at worktree        |

The `.mcp.json` file tells the environment to discover kagan's MCP server scoped to this session.

### `adapters/pi_rpc.py` — Pi RPC Adapter

`pi-coding-agent` does not accept a prompt as a CLI argument. Instead, it exposes a JSONL-framed
RPC protocol over subprocess stdin/stdout. `PiRpcClient` in `adapters/pi_rpc.py` wraps that
protocol so the rest of the system interacts with a familiar async interface.

**Wire framing.** Commands to the agent are JSON objects written one per line to stdin. Events
from the agent arrive as JSON objects one per line on stdout (`AgentSessionEvent` shape from the
pi protocol). Neither direction uses length prefixes or delimiters beyond the newline.

**Byte guards (CWE-770).** Two limits cap runaway output: 10 MB per JSONL line
(`_PI_RPC_MAX_LINE_BYTES`) and 500 MB cumulative per prompt invocation
(`_PI_RPC_MAX_CUMULATIVE_BYTES`). The cumulative counter resets at the start of each `prompt()`
call, so a long-lived client across many prompts does not accumulate the budget.

**Lifecycle.** `PiRpcClient` is an async context manager. On `__aenter__`, it spawns
`npx @mariozechner/pi-coding-agent --mode rpc` via `asyncio.create_subprocess_exec`. Pi's process
does not auto-exit after completing a prompt, so the caller is responsible for termination.
`aclose()` sends `SIGTERM`, waits up to 2 seconds (`_KILL_GRACE_SECONDS`), then sends `SIGKILL`
if the process has not exited.

**Event translation.** `translate_pi_rpc_message()` converts a single parsed pi frame into an
`AgentEvent`. The mapping:

| Pi frame type           | `AgentEvent` variant  | Notes                                          |
| ----------------------- | --------------------- | ---------------------------------------------- |
| `agent_start`           | `AgentStart`          |                                                |
| `agent_end`             | `AgentEnd`            | Also sets `done = True` to end the read loop   |
| `turn_start`            | `TurnStart`           | turn_index supplied by caller counter          |
| `turn_end`              | `TurnEnd`             |                                                |
| `message_start`         | `MessageStart`        | Assistant messages only; user messages skipped |
| `message_update`        | `MessageUpdate`       | `text_delta` and `thinking_delta` only         |
| `message_end`           | `MessageEnd`          | Assistant messages only                        |
| `tool_execution_start`  | `ToolExecutionStart`  |                                                |
| `tool_execution_update` | `ToolExecutionUpdate` |                                                |
| `tool_execution_end`    | `ToolExecutionEnd`    |                                                |
| `compaction_start`      | `CompactionOccurred`  | `compaction_end` is ignored (start suffices)   |
| `response`              | `None`                | RPC ack frames                                 |
| `extension_ui_request`  | `None`                | UI frames not applicable in headless mode      |
| anything else           | `None`                | Silently discarded                             |

**Cancellation.** `prompt()` accepts an `asyncio.Event cancel_event`. When set, a background
task sends `{"type": "abort"}` to stdin. The read loop still drains remaining output until EOF
or `agent_end`.

**Backend registry hook.** `_agent.py` registers `pi-coding-agent` with
`BackendCapability.PI_RPC_STREAMING`. The capability is distinct from `ACP_STREAMING` because
the transport and launch model differ: pi is not a detached process and does not report through
MCP. The `_sessions.py` run path currently routes all non-ACP backends through the detached
launcher (`spawn_agent`); wiring `PI_RPC_STREAMING` to call `PiRpcClient.prompt()` instead is
a pending integration step.

**Message models.** `adapters/pi_rpc_messages.py` contains typed dataclass models
(`PiAgentStart`, `PiMessageUpdate`, `PiToolCallStart`, etc.) and `parse_pi_rpc_message()`, which
validates raw dicts against those models. `translate_pi_rpc_message()` pattern-matches on those
typed instances, not on raw dicts, so unknown future pi frame types are safely discarded rather
than raising.

### `_config.py` — Bootstrap Config

Reads/writes TOML from `~/.config/kagan/config.toml`. **Bootstrap-only** — settings needed before the DB exists: `db_path`, `log_level`. Runtime preferences live in the DB `Setting` table.

### `_preflight.py` — System Health Checks

Checks: Python, git, uv, tmux, nvim, configured editor, configured agent backend executable. Each check reports pass, warn, or fail with fix hints. `PreflightCheckResult` and `CheckStatus` are re-exported as public API.

## Agent Integration Flow

### Managed run: `client.tasks.run(task_id)`

```
Frontend → KaganCore → Agent CLI (detached)
   │          │              │
   │── task.run(id) ────────►│
   │          │── worktrees.create()
   │          │── write .mcp.json
   │          │── spawn (detached)
   │◄─ Session ──────────────│
   │          │              │── discovers .mcp.json
   │◄─ events via ACP ───────│── session/update notification
   │          │◄─ emit event + signal
   │◄─ tasks.events.stream(id)
   │          │
╳ (client exits)            │── keeps working
                            │── writes via MCP
```

### Interactive launch: `client.tasks.run(task_id, launcher="tmux")`

```
Frontend → KaganCore → Launcher (tmux/IDE/nvim)
   │          │              │
   │── task.run(id, launcher)►│
   │          │── worktrees.create()
   │          │── write .mcp.json
   │          │── LAUNCHERS[launcher]
   │◄─ Session ──────────────│ start agent + env
   │          │              │── user works with agent
   │◄─ events via MCP ───────│── agent uses kagan MCP
```

## Session Attach + Replay

`kagan.core` exposes a small foundation for the orchestrator-chat overlay shipped
across the TUI, web, VS Code, and CLI. The goal is for any frontend to (a) list
the agents currently running across a project, (b) resolve "the most relevant"
session for a task, (c) attach a chat to that session, and (d) replay or live-tail
its event history.

### `_sessions_query.resolve_active_session(sessions)`

Pure, total function in `src/kagan/core/_sessions_query.py`. Takes the full
session history for a single task and returns the session a UI should focus by
default. Priority:

1. Worker session whose status is in `{PENDING, RUNNING}` (most recent wins on ties)
1. Reviewer session whose status is in `{PENDING, RUNNING}`
1. Most-recent reviewer session (any status)
1. Most-recent worker session (any status)
1. Otherwise, the most-recent session regardless of role; `None` if the list is
   empty.

The function never raises. Frontends consume it via
`client.resolve_active_session(task_id)`, which loads the history through
`list_task_sessions` first.

### `_sessions_query.list_running_agents(project_id=None)`

Cross-task joined query that returns all sessions currently in
`{PENDING, RUNNING}` paired with their owning task. Optionally scoped to a
single project. Results are sorted by `started_at DESC`. Each row is an
`ActiveAgentRow` (frozen `dataclass`):

| Field                           | Type             |
| ------------------------------- | ---------------- |
| `task_id`, `task_title`         | `str`            |
| `task_status`                   | `str`            |
| `session_id`, `agent_backend`   | `str`            |
| `agent_role`                    | `str \| None`    |
| `session_status`                | `str`            |
| `started_at`, `last_event_at`   | `datetime` (UTC) |
| `input_tokens`, `output_tokens` | `int \| None`    |

`ActiveAgentRow` is JSON-safe — server routes serialise it directly into
`ActiveAgentRowResponse` (see `kagan.server.responses`).

### `ChatSession.attached_session_id`

`models.ChatSession` stores the durable routing target for the agent session a
chat is tracking:

- `attached_session_id: str | None` — `None` means orchestrator mode (default).

Migration `migrations/versions/25420575c1aa_chat_session_attach_target.py` adds
the column and the `attached_session_id` index. Migration
`migrations/versions/7b1f4d96c2e1_drop_chat_sessions_attached_role.py` removes
the former duplicate `attached_role` column; callers derive role from
`Session.agent_role`. There is intentionally no SQLite FK constraint on
`attached_session_id`: the `sessions` table is sometimes recreated via
rename-and-recreate migrations, which corrupts SQLite's trigger-based FK
enforcement. Referential integrity is enforced at the application layer.

### `kagan.core.chat._attach`

| Function                         | Purpose                                                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `attach_chat_to_session()`       | Set or clear `attached_session_id` on a ChatSession; passing `session_id=None` detaches.                      |
| `record_agent_lifecycle_event()` | Append an `agent_lifecycle` `SessionEvent` for replay and UI surfaces without polluting chat message history. |
| `notify_project_chat_sessions()` | Iterate every chat session in a project and record a lifecycle event for each one.                            |

### Lifecycle hook in `transitions.transition_session`

After the DB commit succeeds, `transition_session` calls
`_notify_chat_on_session_transition`. Notifications are best-effort — failures
are logged at warning level and never block the transition. Fires:

| Source → target                                 | Notification kind |
| ----------------------------------------------- | ----------------- |
| anything → `RUNNING` (when not already RUNNING) | `agent_started`   |
| anything → `COMPLETED`                          | `agent_finished`  |
| anything → `FAILED` / `CANCELLED`               | `agent_stopped`   |

The summary string includes the task title and (when present) the agent role,
e.g. `"Implement /attach (worker) finished"`.

### Public `KaganCore` surface

| Method                                                                  | Purpose                                                           |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `await client.list_running_agents(project_id=None)`                     | List active sessions across the project as `ActiveAgentRow` rows. |
| `await client.resolve_active_session(task_id)`                          | Pick "the most relevant" session for `task_id` (or `None`).       |
| `await client.attach_chat(chat_session_id, session_id, agent_role=...)` | Attach (or, with `session_id=None`, detach) a chat from an agent. |

Internal cross-cutting helpers `db_async`, `db_sync`, `sa_col`, and
`list_running_agents` are also re-exported from `kagan.core` so server route
modules don't need to import private modules directly.

______________________________________________________________________

## Logging

All packages use [Loguru](https://github.com/Delgan/loguru). One sink, one file, one configuration point.

| Aspect   | Value                                                                                |
| -------- | ------------------------------------------------------------------------------------ |
| Library  | `loguru.logger` (no stdlib `logging`)                                                |
| Sink     | Single file: `$XDG_STATE_HOME/kagan/kagan.log`                                       |
| Rotation | 10 MB, 3 retained files                                                              |
| Format   | `{time:YYYY-MM-DD HH:mm:ss.SSS} \| {level} \| {name}:{function}:{line} \| {message}` |
| Levels   | `DEBUG` in dev, `INFO` in production (controlled by `KAGAN_LOG_LEVEL`)               |
| Console  | No console sink by default. `--verbose` / `-v` adds stderr sink                      |

**Rules:** One `logger.configure()` call in `kagan.core` init. No stdlib logging. Use `logger.bind(task_id=..., session_id=...)` for context. Loguru's `enqueue=True` on the file sink for async safety.

### XDG Compliance

| XDG variable      | Default          | Kagan uses for                      |
| ----------------- | ---------------- | ----------------------------------- |
| `XDG_STATE_HOME`  | `~/.local/state` | `kagan.log` (log file)              |
| `XDG_DATA_HOME`   | `~/.local/share` | `kagan.db` (SQLite database)        |
| `XDG_CONFIG_HOME` | `~/.config`      | `kagan/config.toml` (user settings) |

On macOS, these defaults apply unless the env vars are explicitly set.

## Ownership Boundaries

**Core owns execution** — frontends call `tasks.run()` and optionally supply a launcher.
They never launch agents, provision worktrees, or write `.mcp.json` directly.

**Core does not own chat** — conversational abstractions live in `kagan.cli.chat`. Both TUI and CLI import it; core never does.

```
kagan.cli.chat ──► kagan.core (agent spawning, event streaming, task ops)
kagan.tui ──► kagan.cli.chat (ChatSession, slash commands)
kagan.cli ──► kagan.cli.chat (run_chat for REPL)
kagan.core ──✘► kagan.cli.chat NEVER
```

## Testing

See `docs/internal/testing.md` for the full testing guide. Core-specific: internal helpers are unit-tested separately, not through the DSL.
