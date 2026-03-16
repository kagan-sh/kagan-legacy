# KaganCore — Architecture

## Context

`kagan.core` is an in-process SDK that frontends (TUI, CLI, MCP server) use to manage a kanban
board and run AI coding agents. `KaganCore` owns the DB, enforces the task lifecycle,
provisions git worktrees, spawns agents, and streams progress back to callers.

**The fundamental abstraction is a Task.** A Task is a kanban ticket. When started, it gets an
isolated worktree and an agent session. AUTO sessions run autonomously as detached processes that
survive client exit. PAIR sessions open an editor/terminal for collaborative work. Kagan is
**agent-agnostic** — it supports any CLI-based coding agent (Claude Code, Codex, Gemini CLI,
Goose, etc.) through a backend registry. Agents report progress back via kagan's MCP server.
The core client is the bridge between frontends and this machinery.

______________________________________________________________________

## Design Principles

```
Simple is better than complex.
Flat is better than nested.
There should be one obvious way to do it.
If the implementation is hard to explain, it's a bad idea.
```

1. **One class, one import** — `from kagan.core import KaganCore`
1. **Fluent API by domain** — `client.tasks.create()`, `client.projects.list()`, `client.reviews.merge()`
1. **SQLModel for models + DB** — one class is both validation model and table definition
1. **Unified Session** — no separate AUTO/PAIR models; one `Session` model with a `mode` field
1. **Core owns execution** — backend launch, agent spawning, worktree provisioning all live in core;
   frontends are thin display layers
1. **Agent-agnostic** — any CLI coding agent works. A registry maps names to launch configs.
   Backends with `supports_acp: True` get piped stdio + ACP event streaming; others run
   detached and report via MCP. MCP also serves PAIR mode and external tools.
1. **DB is the durable buffer** — both ACP and MCP paths write to the same table;
   any client reconnects and picks up where it left off
1. **Async public API** — Textual is async, MCP is async, agent spawning is async
1. **Reactive event streaming** — `task.events.stream()` uses `asyncio.Event` signaling, not polling.
   When an event is written to the DB, the signal fires and the stream wakes instantly.
   A 5-second timeout acts as a safety net only, not a polling interval.
1. **No chat logic** — conversational abstractions live in `kagan.chat`, not here.
   Core provides the raw primitives (agent spawn, event streaming) that `kagan.chat` builds on.

______________________________________________________________________

## References

| Package      | Repo                                                                      | Use                                                                                                  |
| ------------ | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **ACP**      | [anthropics/agent-protocol](https://github.com/anthropics/agent-protocol) | Agent Client Protocol: ACP-specific adapter for agents that support it (e.g., Claude Code).          |
| **SQLModel** | [fastapi/sqlmodel](https://github.com/fastapi/sqlmodel)                   | Models + DB: one class as table and validation. Engine/session, migrations, SQLAlchemy 2.0 patterns. |
| **Loguru**   | [Delgan/loguru](https://github.com/Delgan/loguru)                         | Structured logging. Core owns the single `logger.configure()` call — see § Logging below.            |

______________________________________________________________________

## Module Layout

```
kagan/core/
├── __init__.py            # re-exports KaganCore, models, enums, errors, PreflightCheckResult, CheckStatus
├── client.py              # KaganCore + domain namespace classes
├── models.py              # SQLModel table classes (uses # type: ignore[assignment] for __tablename__)
├── enums.py               # TaskStatus, WorkMode, SessionStatus, Priority, SessionEventType
├── errors.py              # KaganError hierarchy
├── git.py                 # git operations wrapper
│
├── _acp.py                # ACP adapter: KaganACPClient + event mapping
├── _agent.py              # agent backend registry + launcher (detached + ACP modes)
├── _audit.py              # audit log repository
├── _config.py             # TOML read/write
├── _db.py                 # engine factory and session management
├── _db_helpers.py         # sqlite-specific pragmas and helpers
├── _events.py             # session event repository
├── _launchers.py          # PAIR environment launchers (tmux, IDE, neovim)
├── _logging.py            # loguru configure_logging() — single sink setup
├── _pair_backends.py      # PAIR-specific agent backend logic
├── _persona.py            # persona pipeline definitions
├── _preflight.py          # system health checks
├── _projects.py           # project repository
├── _prompts.py            # three-layer prompt resolution (defaults, behavioral compilation, dotfile overrides)
├── _reviews.py            # review repository
├── _sessions.py           # agent session repository
├── _settings.py           # settings repository
├── _tasks.py              # task repository
├── _transitions.py        # task lifecycle state machine
└── _worktrees.py          # worktree management logic

~27 files. No sub-packages. Flat.

______________________________________________________________________

## Frontend Construction

Every frontend creates a `KaganCore` the same way. The constructor takes only `db_path`
(optional, defaults to `~/.local/share/kagan/kagan.db`). No `project_path` — repo paths are
stored in the `Repository` table and loaded when a project is opened.

This matters for the TUI: the WelcomeScreen lists projects before the user selects one.
The client works without an active project for `projects.list()` and `projects.create()`.

| Frontend | Construction                                            |
| -------- | ------------------------------------------------------- |
| TUI      | Creates client in `on_mount`, passes to screens         |
| CLI      | `_bootstrap.make_client()` helper, used in each command |
| MCP      | Lifespan context creates client at startup              |

One obvious way: `KaganCore()`. No factories, no DI frameworks.

______________________________________________________________________

## Data Models

### Tables

| Table          | Key Fields                                                                                         | Purpose                                  |
| -------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **Project**    | id, name, created_at                                                                               | Top-level grouping                       |
| **Repository** | id, project_id, path, default_branch                                                               | Git repo linked to project               |
| **Task**       | id, project_id, title, description, status, execution_mode, priority, base_branch, review_approved, acceptance_criteria, agent_backend | The core abstraction — a kanban ticket   |
| **Worktree**   | id, task_id, repo_id, worktree_path, branch_name | Git worktree for a task. Stored at `$XDG_STATE_HOME/kagan/worktrees/{task_id}` (override: `KAGAN_WORKTREE_BASE` env). Removed on merge, task delete, or orphan scan. |
| **Session**    | id, task_id, mode (AUTO\|PAIR), agent_backend, status, launcher, pid, input_tokens, output_tokens, context_window_used, context_window_size | Agent execution — unified for both modes. Token fields populated from ACP `UsageUpdate` on session completion; nullable until available. |
| **SessionEvent**   | id, task_id, run_id, event_type, payload (JSON), created_at                                    | Agent progress stream                    |
| **TaskNote**   | id, task_id, content, created_at                                                                   | Timestamped notes on a task              |
| **Setting**    | key (PK), value                                                                                    | Key-value settings                       |
| **AuditEntry** | id, action, entity_type, entity_id, detail (JSON), created_at                                      | Audit trail                              |

### Why Unified Session

A "Session" in AUTO mode and a "Session" in PAIR mode are the same thing:
**an agent working on a task.**
The difference is just the `mode` field. One model, one table, one concept.

### Done Tasks

When a task reaches DONE (via `review.merge()`), the worktree is merged into the base branch
and the Worktree row is removed. Task, Session, and SessionEvent rows remain for history.
Reopening (DONE → BACKLOG) leaves the task without a worktree until the next `run()` or `pair()`.

______________________________________________________________________

## Enums

| Enum              | Values                                                                                                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **TaskStatus**    | BACKLOG, IN_PROGRESS, REVIEW, DONE                                                                                                                            |
| **WorkMode**      | AUTO, PAIR                                                                                                                                              |
| **SessionStatus**     | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED                                                                                                                |
| **Priority**      | LOW, MEDIUM, HIGH, CRITICAL                                                                                                                                   |
| **SessionEventType**  | OUTPUT_CHUNK, AGENT_STATUS, TOOL_CALL_START, TOOL_CALL_UPDATE, AGENT_COMPLETED, AGENT_FAILED, PLAN_UPDATE, TASK_STATUS_CHANGED, MERGE_COMPLETED, MERGE_FAILED, CRITERION_VERDICT |
| **BranchRefStrategy** | LOCAL, REMOTE, LOCAL_IF_AHEAD — git ref resolution strategy for worktree operations |

______________________________________________________________________

## Error Hierarchy

| Error                                           | When                                                    |
| ----------------------------------------------- | ------------------------------------------------------- |
| **KaganError**                                  | Base for all kagan errors                               |
| **NotFoundError**                               | Entity not found                                        |
| **InvalidTransitionError**                      | Illegal status move (e.g., BACKLOG → DONE)              |
| **WorktreeError**                               | Git worktree operation failed                           |
| **MergeConflictError** (extends WorktreeError)  | Merge produced conflicts; carries `conflict_files` list |
| **AgentError**                                  | Agent spawn or communication failure                    |
| **PreflightError**                              | Blocking preflight issue prevents operation             |
| **ValidationError**                             | Input validation failures                               |
| **ConfigurationError**                          | Configuration or state issues                           |
| **SessionError**                                | Session operation failures                              |
| **MultiRepoUnsupportedError** (extends WorktreeError) | Task execution attempted against multiple repos   |

______________________________________________________________________

## Fluent API

The client is a composition root. Each domain is a namespace object with focused methods.

**Fluent principle:** The namespace is the subject — don't repeat it in method names.
`client.tasks.get(id)` not `client.tasks.get_task(id)`; `client.projects.list()` not `client.projects.list_projects()`.
Use `list` consistently for "list all" operations across namespaces. Avoid other builtin shadows (`open`, `filter`, etc.).

### KaganCore (composition root)

| Member                  | Type                                  |
| ----------------------- | ------------------------------------- |
| `client.tasks`          | Tasks                                 |
| `client.tasks.events`   | Events                                |
| `client.projects`       | Projects                              |
| `client.worktrees`      | Worktrees                             |
| `client.reviews`        | Reviews                               |
| `client.settings`       | Settings                              |
| `client.audit_log`      | AuditLog                              |
| `client.persona_presets` | PersonaPresetOps                     |
| `client.close()`        | Dispose engine, cancel running agents |
| `client.preflight()`    | Check system requirements             |
| `client.reset()`        | Wipe all data                         |
| `client.db_version()`   | Current Alembic migration revision    |

Supports async context manager (`async with KaganCore() as client`).

### Tasks — `client.tasks`

| Method                                                                                                   | Description                                                                                                                 |
| -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `create(title, *, description=None, priority=None, execution_mode=None, base_branch=None, acceptance_criteria=None, agent_backend=None)` | Create task                                                                                                                 |
| `get(task_id)`                                                                                           | Get task by ID                                                                                                              |
| `list(*, status=None, execution_mode=None)`                                                              | List tasks with optional filters                                                                                            |
| `update(task_id, *, title=None, description=None, priority=None, execution_mode=None, base_branch=None, acceptance_criteria=None, agent_backend=None)` | Update task fields (explicit params)                                                                                        |
`set_status(task_id, status)`                                                                          | Transition task status (validated by state machine). Use for DONE→BACKLOG too; fresh worktree provisioned on next run/pair. |

| `delete(task_id)`                                                                                        | Delete task and associated data                                                                                             |
| `search(query)`                                                                                          | Full-text search                                                                                                            |
`build_context(task_id)`                                                                                       | Rich context: task + worktree + recent events                                                                              |

| `counts(*, project_id=None)`                                                                             | Per-status task counts                                                                                                      |
`wait_for_completion(task_id, *, timeout)`                                                                              | Block until status changes                                                                                                  |

`add_note(task_id, content)`                                                                             | Add note to task                                                                                                            |
| `list_notes(task_id)`                                                                                         | List notes                                                                                                                  |
| `list_notes(task_id)`                                                                                         | List notes                                                                                                                  |
| `run(task_id, *, agent_backend)`                                                                         | Start AUTO: provision worktree, spawn detached agent, return Session                                                      |
| `pair(task_id, *, agent_backend, launcher)`                                                              | Start PAIR: provision worktree, launch environment, return Session                                                               |
| `cancel(task_id)`                                                                                        | Cancel active run, kill process, move to BACKLOG                                                        |
| `end_pairing(task_id)`                                                                                   | End an active PAIR session                                                                              |
| `runtime_summary(task_id)`                                                                               | Execution time summary for a single task                                                                |
| `runtime_summaries(task_ids)`                                                                            | Execution time summaries for multiple tasks                                                             |

**`client.tasks.events`** — event sub-namespace:

| Method                                          | Description                                                      |
| ----------------------------------------------- | ---------------------------------------------------------------- |
| `list(task_id, *, offset=0, limit=20)`          | Paginated event history                                          |
| `list_all(*, offset, limit)`                    | Paginated events across all tasks                                |
| `list_recent(task_id, *, limit)`                | Most recent N events for a task                                  |
| `list_before(task_id, *, before_id, limit)`     | Events before a given event ID (cursor pagination)               |
| `latest(task_id)`                               | Single most recent event for a task                              |
| `emit(task_id, event_type, payload)`            | Insert event row AND signal waiting streams                      |
| `stream(task_id)`                               | Async generator yielding events reactively (see Event Streaming) |
| `stream_all(*, replay)`                         | Async generator yielding events across all tasks; `replay=True` replays history first |
| `stream_board()`                                | Async generator yielding board-level events (task creation, deletion, status changes) |

### Projects — `client.projects`

| Method                             | Description                                                    |
| ---------------------------------- | -------------------------------------------------------------- |
| `create(name, *, repo_paths=None)` | Create project, optionally link repos                          |
| `get(project_id)`                  | Get project by ID                                              |
| `list()`                           | List all projects                                              |
`set_active(project_id)`           | Set active project (required before task/worktree/review ops) |
| `delete(project_id)`               | Delete project and all its data                                |
| `add_repo(project_id, repo_path)`  | Link repo to project                                           |
| `find_by_repo(repo_path)`                              | Find project containing a repo path                            |
| `find_by_name(name)`                                   | Find project by name                                           |
| `repos(project_id)`                                    | List repos linked to a project                                 |
| `set_repo_default_branch(project_id, repo_id, branch)` | Update the default branch for a repo                           |
| `resolve_repo(project_id, repo_path)`                  | Resolve a repo by path within a project                        |
| `resolve_repo_path(project_id)`                        | Resolve the primary repo path for a project                    |

### Worktrees — `client.worktrees`

Done tasks have no worktree (worktree removed on merge). After reopen (DONE → BACKLOG),
a fresh worktree is provisioned when the user next calls `tasks.run()` or `tasks.pair()`.

| Method                | Description                                          |
| --------------------- | ---------------------------------------------------- |
| `create(task_id)`   | Create git worktree for task                         |
| `get(task_id)`        | Get worktree for task                                |
| `diff(task_id)`       | Unified diff of worktree changes                     |
| `diff_stats(task_id)` | Summary stats (files changed, insertions, deletions) |
| `cleanup(task_id)`    | Remove worktree                                      |
| `cleanup_orphans()`   | Remove worktrees (disk + DB) with no matching task; called at startup |
| `prune_kagan_branches()` | Prune orphaned `kagan/*` branches in the repo |

`cleanup_orphans()` runs at TUI startup as a non-blocking background worker. It removes both the git worktree directory from disk and the Worktree DB row for any worktree whose task no longer exists.
### Reviews — `client.reviews`

| Method                         | Description                                |
| ------------------------------ | ------------------------------------------ |
| `approve(task_id)`             | Mark task as review-approved               |
| `reject(task_id, *, feedback)` | Move to BACKLOG/IN_PROGRESS with feedback  |
| `merge(task_id)`               | Merge worktree → base branch, move to DONE |
| `rebase(task_id)`                                              | Rebase worktree on base branch                                  |
| `abort_rebase(task_id)`                                        | Abort in-progress rebase                                        |
| `continue_rebase(task_id)`                                     | Continue a paused rebase after conflict resolution              |
| `conflicts(task_id)`                                           | List current conflict files for a task                          |
| `set_criterion_verdict(task_id, criterion_index, verdict, reason)` | Record pass/fail verdict for a single acceptance criterion  |
| `clear_verdicts(task_id)`                                      | Clear all criterion verdicts for a task                         |

### Settings — `client.settings`

| Method                               | Description                                  |
| ------------------------------------ | -------------------------------------------- |
| `get()`                              | Read all settings as key-value dict          |
| `set(updates: Mapping[str, str])`  | Update settings (explicit key-value mapping) |
### AuditLog — `client.audit_log`

| Method                                                    | Description                                      |
| --------------------------------------------------------- | ------------------------------------------------ |
| `list(*, limit=None)`                                     | Recent audit entries                             |
| `record(action, entity_type, entity_id, detail)`          | Insert an audit entry manually                   |

#### Prompt Resolution

Prompt resolution follows a three-layer hierarchy:

| Layer | Mechanism | Effect |
|-------|-----------|--------|
| **Layer 0** | Code defaults + behavioral settings | Invisible; compiles `default_execution_mode`, `review_strictness`, `planning_depth`, `auto_confirm_single_tasks` into prompt clauses |
| **Layer 1** | `additional_instructions` setting | Single text field appended to all prompts; additive, never replaces |
| **Layer 2** | `.kagan/prompts/*.md` dotfiles | Full replacement; bypasses Layer 0 and Layer 1 |

Key functions in `_prompts.py`: `resolve_orchestrator_prompt()`, `resolve_task_prompt()`, `resolve_review_prompt()`, `detect_dotfile_overrides()`.

`execution.md` dotfile overrides may include template placeholders such as `{task_title}` and `{task_description}`. If template rendering fails, Kagan falls back to the default compiled prompt and logs a warning rather than emitting a broken execution prompt.

#### Project Learnings Injection

`resolve_task_prompt()` accepts an optional `learnings: list[str] | None` keyword argument. When provided and non-empty, a `PROJECT CONTEXT (from prior tasks):` section is appended to the base prompt (after `_build_auto_run_prompt`, before behavioral settings layers).

Learnings are sourced from `TaskNote` rows whose `content` starts with `[LEARNING]`. The query JOINs `TaskNote` with `Task` on `task_id` and filters by `Task.project_id`, ensuring **strict project isolation** — no learning from a different project is ever injected. Results are ordered newest-first, deduplicated by content (after stripping the `[LEARNING]` prefix), and capped at 20 items.

The call site is `Sessions._fetch_project_learnings()` in `_sessions.py`, invoked just before `resolve_task_prompt()` in the AUTO run path. To save a learning for future tasks, an agent simply calls `task_add_note` with content starting with `[LEARNING] `.
______________________________________________________________________

## Persona Pipeline

`client.persona_presets` — namespace for persona preset management.

### Built-in Personas

| Persona         | Role                                                  |
| --------------- | ----------------------------------------------------- |
| `analyst`       | Reads codebase, produces structured analysis          |
| `planner`       | Breaks work into subtasks, produces a plan            |
| `implementer`   | Executes code changes against a plan                  |
| `reviewer`      | Reviews diffs, checks acceptance criteria             |

### PersonaPresetOps — `client.persona_presets`

| Method                                              | Description                                                  |
| --------------------------------------------------- | ------------------------------------------------------------ |
| `audit_repo(project_id, *, persona)`                | Run a persona against the repo for analysis                  |
| `import_from_github(url, *, token=None)`            | Import a persona preset from a GitHub repo                   |
| `export_to_github(preset_id, url, *, token=None)`   | Export a persona preset to a GitHub repo                     |
| `list_whitelist()`                                  | List approved persona source repos                           |
| `add_to_whitelist(repo_url)`                        | Add a repo to the persona import whitelist                   |
| `remove_from_whitelist(repo_url)`                   | Remove a repo from the whitelist                             |

### Multi-Session Execution

A task can be executed across multiple sessions with different personas in sequence. Each session runs with its own persona prompt, and the output of one session can feed the next. This enables analyst → planner → implementer → reviewer pipelines without manual handoff.

______________________________________________________________________

## DBWatcher

`DBWatcher` provides reactive board change detection for consumers that need to track the full board state (e.g., chat integration, web dashboard sync).

- Polls the DB at a configurable interval and compares snapshots
- Detects: task creation, task deletion, status changes, execution mode changes
- Emits structured change events to registered listeners
- Used by `kagan.chat` to provide context updates when the board changes while a chat session is active
- Distinct from `tasks.events.stream()` (which streams agent progress for a single task); DBWatcher tracks board-level structural changes

______________________________________________________________________

## Event Streaming (Reactive)

`tasks.events.stream()` is an async generator that yields `SessionEvent` rows as they arrive.
It uses **`asyncio.Event` signaling**, not polling.

### How it works

1. `tasks.events.emit()` inserts a `SessionEvent` row into the DB, then calls `signal.set()` on the
   per-task `asyncio.Event`.
1. `tasks.events.stream()` holds the corresponding `asyncio.Event`. When signaled, it reads new
   rows from the DB and yields them.
1. If no signal arrives within 5 seconds, the stream re-checks anyway (safety net for missed
   signals — not a polling interval).
1. The stream self-terminates when: no new events AND no active run for the task.

### Why not polling

|               | Polling                  | Signal                                       |
| ------------- | ------------------------ | -------------------------------------------- |
| Latency       | 0–300ms                  | Near-zero (event loop tick)                  |
| Idle cost     | 3.3 qps per stream       | Zero (blocked on `await`)                    |
| Magic numbers | `sleep(0.3)` — arbitrary | `timeout=5.0` — safety net only              |
| Failure mode  | Works but wastes         | Works, falls back to 5s check if signal lost |

### Two Streaming Paths

Events reach the DB via two distinct paths:

**Path A — ACP (primary, ACP-capable AUTO agents).** Backends that set `supports_acp: True`
in the agent registry (currently only `claude-code`) use the `agent-client-protocol` PyPI
package. Kagan spawns the agent with piped stdin/stdout and uses `acp.connect_to_agent()`
to establish a `ClientSideConnection`. The handshake (`initialize` → `new_session` → `prompt`)
starts the agent. Session updates (`session/update` notifications) flow through
`KaganACPClient.session_update()` which maps them via `map_acp_update_to_event()` and calls
`Events.emit()` to write `SessionEvent` rows to the DB.

Backends without ACP support fall back to the detached process path (Path B via MCP).

```

Agent subprocess (stdout piped to kagan)
│ ACP session/update {AgentMessageChunk, "Hello World"}
▼
KaganACPClient.session_update() → map_acp_update_to_event() → emit() → signal.set()

```

**Path B — MCP (PAIR mode and external tools).** Used in two cases:

1. **PAIR mode** — the agent runs inside an IDE, tmux, or neovim. It discovers
   `.mcp.json` in the worktree, spawns `kagan mcp --session-id {id}`, and calls
   MCP tools to report progress back to the board.
1. **External/manual use** — a user connects their preferred tool to kagan's MCP
   server directly (e.g., an IDE host browsing tasks, or a custom script).

```

Agent in IDE/tmux (or external tool)
MCP tool call: task_events("Hello World")
▼
kagan mcp subprocess → INSERT run_event → signal.set()

```

**Both converge here:** `tasks.events.stream()` wakes on the signal, yields the row,
and the TUI/CLI renders it. The consumer doesn't know which path wrote the event.

|               | ACP (AUTO)                                             | MCP (PAIR / external)                     |
| ------------- | ------------------------------------------------------ | ----------------------------------------- |
| When          | All AUTO executions                                    | PAIR mode, IDE hosts, manual hookup       |
| Transport     | Direct STDIO JSON-RPC, kagan owns subprocess           | Agent/tool spawns kagan MCP as subprocess |
Accumulated text via `task_events`          |
| Bidirectional | Yes — kagan sends prompts, cancel, set_mode            | No — caller invokes tools, kagan reads DB |
| Process model | Kagan owns (can terminate)                             | Agent runs in external environment        |

### Secret Scrubbing

`Events.emit()` calls `_scrub_secrets(payload)` before constructing `SessionEvent`, ensuring **both persisted events and live-streamed events** contain no secrets.

`_scrub_secrets()` deep-traverses the payload dict and applies two complementary rules:

1. **Pattern matching** — string values are scanned against six compiled `re.Pattern` objects:
   - `AKIA[A-Z0-9]{16}` — AWS access key IDs
   - `ghp_[a-zA-Z0-9]{36}` / `ghu_[a-zA-Z0-9]{36}` — GitHub PAT / user tokens
   - `sk-[a-zA-Z0-9]{20,}` — OpenAI API keys
   - `-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----` — private key PEM blocks
   - `Bearer [a-zA-Z0-9._\-]{20,}` — bearer tokens in authorization headers

2. **Sensitive key names** — dict keys matching `password`, `secret`, `token`, `api_key`, `apikey`, `authorization` (case-insensitive) have their values replaced regardless of pattern match.

Patterns have minimum-length requirements to avoid false positives (e.g., `sk-short` is not scrubbed). The function is **non-mutating** — it always returns a new dict; the caller's original dict is unchanged.

______________________________________________________________________

## Agent Persistence

**AUTO agents are subprocesses owned by kagan. PAIR agents are detached.**

```

AUTO (ACP):

kagan (client) Agent subprocess
│ │
├── task.run(id) │
│ └─ spawn (piped stdio) ────►│
│ │── works in worktree
├── task.events.stream(id) │
│ ◄── event 1 (via ACP) │── session/update notification
│ ◄── event 2 (via ACP) │── session/update notification
│ ... │
╳ (kagan exits → agent terminates)

PAIR (MCP):

kagan (client) Agent in IDE/tmux kagan reconnects
│ │ │
├── task.pair(id) │ │
│ └─ launch env ──────────────►│ │
│ │── discovers .mcp.json │
├── task.events.stream(id) │ │
◄── event 1 │── task_events via MCP │
│ │ │
╳ (kagan exits) │── task_events via MCP │

│ │ │
╳ (kagan exits) │── task_events via MCP │
│── done │
│ │
│ task.events.stream()─┤
│ ◄── all events │

```

1. **ACP subprocess** — in AUTO mode, kagan owns the agent process (piped stdin/stdout).
   If kagan exits, it can terminate the agent. Reconnection resumes from DB offset.
1. **PAIR is detached** — agent runs inside an external environment (IDE, tmux, neovim).
   It survives client exit and reports via MCP.
1. **DB is the durable buffer** — both ACP and MCP paths write to the same `run_events` table.
   `tasks.events.stream()` reads with offset. Any client, any time, gets the full history.
1. **Session status** — agent updates Session to COMPLETED or FAILED when done.

### Agent Environment Variables

| Var                | Purpose                                                    |
| ------------------ | ---------------------------------------------------------- |
| `KAGAN_TASK_ID`    | Which task this agent is working on                        |
| `KAGAN_SESSION_ID` | Which session to report progress to                        |
| `KAGAN_DB_PATH`    | Path to SQLite database                                    |
| `KAGAN_WORKTREE`   | Working directory (the git worktree)                       |
| `KAGAN_MCP_CMD`    | Command to start kagan's MCP server scoped to this session |

______________________________________________________________________

## Internal Modules

### `_db.py` — Engine Factory

- Provides `create_db_engine(db_path)` and `default_db_path()`.
- Sync SQLModel engine with WAL mode and FK enforcement.
- Creates all tables on first use.
- Async methods on the client are async because of agent/terminal ops, not DB access.
- Testing: in-memory SQLite via `"sqlite://"`.

### `_transitions.py` — Task Lifecycle State Machine

Valid transitions:

```

BACKLOG ────► IN_PROGRESS
IN_PROGRESS ─► REVIEW
IN_PROGRESS ─► BACKLOG
REVIEW ──────► DONE (only via review.merge)
REVIEW ──────► IN_PROGRESS
REVIEW ──────► BACKLOG
DONE ───────► BACKLOG (via task.set_status; fresh worktree on next run/pair)

```

Direct DONE from `task.set_status()` is blocked; only `review.merge()` can transition to DONE.
`task.set_status(task_id, BACKLOG)` moves DONE → BACKLOG for iteration.

### `_git.py` — Git Operations

- Created per-repo via `client._git_for_task()`, not per-client.
- Operations: `worktree_add`, `worktree_remove`, `worktree_list`, `diff`, `diff_stats`,
  `merge`, `rebase`, `abort_rebase`.
- Multiple repos per project, each with its own path from the Repository table.

### `_agent.py` — Agent Backend Registry and Launcher

Kagan supports any CLI-based coding agent through a backend registry.

**Supported agent backends:**

| Backend          | CLI Executable   | Notes           |
| ---------------- | ---------------- | --------------- |
| `claude-code`    | `claude`         | Anthropic.      |
| `codex`          | `codex`          | OpenAI.         |
| `gemini-cli`     | `gemini`         | Google.         |
| `kimi-cli`       | `kimi`           | Moonshot.       |
| `github-copilot` | `copilot`        | GitHub.         |
| `goose`          | `goose`          | Block.          |
| `openhands`      | `openhands`      | Open-source.    |
| `opencode`       | `opencode`       | Open-source.    |
| `auggie`         | `auggie`         | Augment.        |
| `amp`            | `amp`            | Sourcegraph.    |
| `docker-cagent`  | `cagent`         | Docker.         |
| `stakpak`        | `stakpak`        | Infrastructure. |
| `mistral-vibe`   | `vibe`           | Mistral.        |
| `vt-code`        | `vtcode`         | VT Code.        |

Each backend entry in the registry specifies: executable name, how to pass the prompt
(flag or stdin), how to pass the working directory, and any agent-specific environment
variables. New backends are added by extending the registry dict — no code changes
to the launcher.

**Backend aliases:** `claude` resolves to `claude-code`; `gemini` resolves to `gemini-cli`; `kimi` resolves to `kimi-cli`. Aliases are accepted anywhere a backend name is accepted.

**Launch sequence (agent-agnostic):**

1. Look up backend in registry → get executable + args template
1. Write `.mcp.json` into worktree with appropriate MCP flags (see below)
1. Set env vars (`KAGAN_TASK_ID`, `KAGAN_SESSION_ID`, `KAGAN_MCP_CMD`, etc.)
1. Spawn as **detached OS process** (new process session)
1. Return Session

**MCP flag wiring per consumer:**

| Consumer               | `.mcp.json` args                   | Access tier            |
| ---------------------- | ---------------------------------- | ---------------------- |
| Task agent (AUTO/PAIR) | `mcp --session-id {id}`            | Standard (read + write) |
| Orchestrator           | `mcp --admin`                      | Admin (+ destructive)  |
| Reviewer agent         | `mcp --readonly --session-id {id}` | Readonly               |

Core wires these flags automatically — frontends never construct MCP args.

**Communication (see § Event Streaming above):**

All backends speak ACP. In AUTO mode, step 4 spawns with piped stdin/stdout. Kagan
performs the ACP handshake (`initialize` → `session/new`) and starts a reader loop
that receives `session/update` notifications and writes them to DB. Kagan can send
prompts, cancel, and set_mode back to the agent.

`.mcp.json` is always written to the worktree — it's the communication channel for
PAIR mode (agent in IDE/tmux/neovim reports back via MCP) and for external tools.

### `_launchers.py` — PAIR Environment Launchers

PAIR mode has two orthogonal choices: **agent backend** (which AI agent) and **launcher**
(which interactive environment). The agent backend comes from `_agent.py`'s registry.
The launcher sets up the environment where the user and agent collaborate.

Three launch strategies, one dict:

| Launcher                                    | Environment               | How agent runs                               |
| ------------------------------------------- | ------------------------- | -------------------------------------------- |
| **tmux**                                    | Detached tmux session     | Agent CLI started inside the tmux session    |
| **ide** (vscode / cursor / windsurf / kiro) | IDE opens worktree folder | IDE discovers agent via `.mcp.json`          |
| **neovim**                                  | Neovim at worktree        | Neovim plugin discovers agent via MCP config |

The `.mcp.json` file written into the worktree tells the environment to discover kagan's
MCP server scoped to this session (`kagan mcp --session-id {id}`).

The `LAUNCHERS` dict maps launcher name → launch function. `task.pair()` does a dict lookup.
Default launcher comes from settings (`pair_launcher` key). Default agent backend comes from
settings (`default_agent_backend` key).

### `_config.py` — Bootstrap Config

- Reads/writes TOML config from `~/.config/kagan/config.toml`.
- **Bootstrap-only** — settings needed before the DB exists: `db_path` override, `log_level`.
- Runtime preferences (`default_agent_backend`, `pair_launcher`) live in the DB `Setting` table
  and are managed via `client.settings`. One obvious place for each kind of setting.

### `_preflight.py` — System Health Checks

- Checks: Python, git, uv, tmux, nvim, configured editor, configured agent backend executable.
- Each check reports pass, warn, or fail with fix hints.
- Agent check verifies the configured `default_agent_backend` executable is on PATH.
- `PreflightCheckResult` and `CheckStatus` are re-exported from `kagan.core.__init__` as public API.
  Plugins use these to report their own health checks via `Plugin.preflight()`.

______________________________________________________________________

## Agent Integration Flow

### AUTO: `client.task.run(task_id)`

```

Frontend KaganCore Agent CLI (detached)
| | |
|-- task.run(id) ------------>| |
| |-- worktrees.create() --->|
| |-- write .mcp.json ------->|
| |-- spawn (detached) ------>|
|\<-- Session ----------------------| |
| | |-- discovers .mcp.json
| | |-- works in worktree
| | |
| |◄--- events via MCP -------|-- task_add_note()
| | emit event + signal |-- task_update()
|\<- tasks.events.stream(id) ---| |
| (async for event) | |
| |◄--- events via MCP -------|-- task_add_note()
| | emit event + signal |-- task_update()

╳ (client exits) | |-- keeps working
| | |-- writes via MCP
| | |-- updates Session

```

All agents use the same flow. The only variable is the executable and args template
from the backend registry.

### PAIR: `client.task.pair(task_id)`

```

Frontend KaganCore Launcher (tmux/IDE/nvim)
| | |
|-- task.pair(id) ----------->| |
| |-- worktrees.create() --->|
| |-- write .mcp.json ------->|
| |-- LAUNCHERS[launcher](<>) ->|
|\<-- Session --------------------| start agent + env |-- user works
| | | with agent
| (TUI/CLI displays: | |-- agent uses
| launcher-specific hint) | | kagan MCP
| | | to report
| |◄-- events via MCP --------| progress

```

______________________________________________________________________

## Logging

All packages (`kagan.core`, `kagan.tui`, `kagan.mcp`, `kagan.cli`, `kagan.chat`, `kagan.plugins`) use
[Loguru](https://github.com/Delgan/loguru). One sink, one file, one configuration point.

| Aspect   | Value                                                                                     |
| -------- | ----------------------------------------------------------------------------------------- |
| Library  | `loguru.logger` (no stdlib `logging`)                                                     |
| Sink     | Single file: `$XDG_STATE_HOME/kagan/kagan.log` (default `~/.local/state/kagan/kagan.log`) |
| Rotation | 10 MB, 3 retained files                                                                   |
| Format   | \`{time:YYYY-MM-DD HH:mm:ss.SSS}                                                          |
| Levels   | `DEBUG` in dev, `INFO` in production (controlled by `KAGAN_LOG_LEVEL` env var)            |
| Console  | No console sink by default. `--verbose` / `-v` on CLI commands adds stderr sink.          |

### Rules

1. **One `logger.configure()` call** — in `kagan.core` init, before anything else runs. TUI,
   MCP, CLI, and chat import `loguru.logger` and use it directly. They never call `configure()`.
1. **No stdlib logging** — Loguru only. No `logging.getLogger()`, no handler wiring.
1. **Structured context** — use `logger.bind(task_id=..., session_id=...)` for request-scoped context.
1. **Async-safe** — Loguru's `enqueue=True` on the file sink. Safe from Textual workers,
   async core methods, and MCP tool handlers.
1. **Tests** — no log sink by default. Tests that need to assert log output use `loguru.logger.add()`
   with a `StringIO` sink in a fixture.

### XDG Compliance

Kagan follows the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/):

| XDG variable      | Default          | Kagan uses for                      |
| ----------------- | ---------------- | ----------------------------------- |
| `XDG_STATE_HOME`  | `~/.local/state` | `kagan.log` (log file)              |
| `XDG_DATA_HOME`   | `~/.local/share` | `kagan.db` (SQLite database)        |
| `XDG_CONFIG_HOME` | `~/.config`      | `kagan/config.toml` (user settings) |

On macOS, these defaults apply unless the env vars are explicitly set. Kagan does not
use `~/Library/` paths — XDG is cross-platform and simpler.

______________________________________________________________________

## Ownership Boundaries

**Core owns execution** — frontends call `tasks.run()` or `tasks.pair()` and get back a Session.
They never launch agents, provision worktrees, or write `.mcp.json` directly.

**Core does not own chat** — conversational abstractions (slash commands, message
history) live in `kagan.chat`. Both TUI and CLI import it; core never does.

```

kagan.chat ──► kagan.core (agent spawning, event streaming, task ops)
kagan.tui ──► kagan.chat (ChatSession, slash commands)
kagan.cli ──► kagan.chat (run_chat for REPL)
kagan.core ──✘► kagan.chat NEVER

```

______________________________________________________________________

## Testing

See `docs/internal/testing.md` for the full testing guide.

Core-specific: internal helpers are unit-tested separately, not through the DSL.
Agent prompt quality is evaluation, not testing.
```
