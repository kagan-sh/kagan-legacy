---
title: MCP tools reference
description: Consolidated tool catalog, contract semantics, and access tiers
icon: material/tools
tags:
  - mcp
  - reference
---

# MCP tools reference

Consolidated MCP toolset reference for Kagan.

## Runtime module path

For embedded/runtime integrations, use `kagan.server.mcp.runtime` as the canonical server module.

## Annotation model

| Annotation    | Meaning                           |
| ------------- | --------------------------------- |
| `read-only`   | Reads state only                  |
| `mutating`    | Modifies state                    |
| `mixed`       | Action-dependent read/write modes |
| `destructive` | Irreversible/high-impact action   |

______________________________________________________________________

## Tool catalog

### Task tools (`toolsets/tasks.py`)

| Tool               | Annotation    | Purpose                                                                           |
| ------------------ | ------------- | --------------------------------------------------------------------------------- |
| `task_get(...)`    | `read-only`   | Read bounded task snapshot (`summary`/`full`) or bounded context (`mode=context`) |
| `task_list(...)`   | `read-only`   | List tasks with optional status/repo filtering and free-text `query` search       |
| `task_create(...)` | `mutating`    | Create one or more tasks (single via `title`, batch via `tasks` list)             |
| `task_update(...)` | `mutating`    | Apply partial task updates, transitions, and metadata adjustments                 |
| `task_delete(...)` | `destructive` | Delete a task permanently                                                         |
| `task_events(...)` | `read-only`   | Read paginated task execution events (newest-first pages)                         |
| `task_wait(...)`   | `read-only`   | Long-poll task status changes                                                     |

### Session tools (`toolsets/sessions.py`)

| Tool                        | Annotation    | Purpose                                                         |
| --------------------------- | ------------- | --------------------------------------------------------------- |
| `run_start(...)`            | `mutating`    | Start a managed run or launch an interactive session for a task |
| `run_cancel(...)`           | `mutating`    | Cancel an active session by session_id and task_id              |
| `run_get(...)`              | `read-only`   | Read the current session status for a task                      |
| `run_detach(...)`           | `mutating`    | Finalize an interactive session and update task status          |
| `run_summary(...)`          | `read-only`   | List running sessions + statuses for active tasks               |
| `verify_step(...)`          | `mutating`    | Record a PASS/FAIL verdict on a plan step during execution      |
| `verification_summary(...)` | `read-only`   | Get all step verdicts for a task's current session              |
| `checkpoint_create(...)`    | `mutating`    | Create a git checkpoint in a task's worktree                    |
| `checkpoint_list(...)`      | `read-only`   | List checkpoints for a task's current session                   |
| `session_rewind(...)`       | `mutating`    | Rewind a task's worktree to a previous checkpoint               |
| `insight_add(...)`          | `mutating`    | Add a categorized insight note to a task                        |
| `insight_list(...)`         | `read-only`   | List insight notes for a task                                   |
| `insight_remove(...)`       | `destructive` | Remove an insight note from a task                              |

### Project tools (`toolsets/projects.py`)

| Tool                  | Annotation  | Purpose                                                        |
| --------------------- | ----------- | -------------------------------------------------------------- |
| `project_list(...)`   | `read-only` | List projects with metadata and task counts                    |
| `project_setup(...)`  | `mutating`  | Create a project and optionally link repos, set as active      |
| `project_update(...)` | `mutating`  | Update project settings, link/unlink repos, set default branch |

### Review tools (`toolsets/review.py`)

| Tool                         | Annotation    | Purpose                                                             |
| ---------------------------- | ------------- | ------------------------------------------------------------------- |
| `review_decide(...)`         | `mutating`    | Approve or reject a task (`verdict="approve"` or `"reject"`)        |
| `review_merge(...)`          | `destructive` | Merge an approved task into its base branch                         |
| `review_rebase(...)`         | `mutating`    | Rebase a task branch (`action="start"`, `"continue"`, or `"abort"`) |
| `review_conflicts(...)`      | `read-only`   | Get merge conflict details                                          |
| `review_verdict(...)`        | `mutating`    | Set verdict on an individual acceptance criterion                   |
| `review_clear_verdicts(...)` | `mutating`    | Clear all AI review verdicts for a task                             |

Review semantics:

- `review_decide(verdict="approve")` records approval state but does **not** move task to `DONE`.
- `DONE` is reached by completion flows (for example `review_merge()` or no-change close flow).

### Settings tools (`toolsets/settings.py`)

| Tool                | Annotation  | Purpose                     |
| ------------------- | ----------- | --------------------------- |
| `settings_get()`    | `read-only` | Read allowlisted settings   |
| `settings_set(...)` | `mutating`  | Update allowlisted settings |

### Persona tools (`toolsets/personas.py`)

| Tool                   | Annotation  | Purpose                                                        |
| ---------------------- | ----------- | -------------------------------------------------------------- |
| `persona_inspect(...)` | `read-only` | Audit and preview a persona preset repo before import          |
| `persona_import(...)`  | `mutating`  | Import persona presets from GitHub                             |
| `persona_export(...)`  | `mutating`  | Export local persona presets to GitHub                         |
| `persona_trust(...)`   | `mixed`     | Manage trusted repos (`action="list"`, `"add"`, or `"remove"`) |

### Diagnostics tools (`toolsets/diagnostics.py`)

| Tool                                | Annotation  | Purpose                                        |
| ----------------------------------- | ----------- | ---------------------------------------------- |
| `audit_list(...)`                   | `read-only` | List recent audit log entries                  |
| `diagnostics_get_instrumentation()` | `read-only` | Return active sessions, DB stats (opt-in only) |

### Integration tools (`toolsets/integrations.py`)

| Tool                         | Annotation    | Purpose                                       |
| ---------------------------- | ------------- | --------------------------------------------- |
| `integration_preview(...)`   | `read-only`   | Preview integration import results            |
| `integration_sync(...)`      | `destructive` | Sync issues via integration, returns counts   |
| `integration_preflight(...)` | `read-only`   | Check integration prerequisites and readiness |

### Analytics tools (`toolsets/analytics.py`)

All analytics tools are read-only, scoped to the active project, and return empty payloads when no project is active.

| Tool                              | Annotation  | Purpose                                                                  |
| --------------------------------- | ----------- | ------------------------------------------------------------------------ |
| `analytics_backend_stats()`       | `read-only` | Per-backend session stats: count, success rate, avg duration, retry rate |
| `analytics_session_timeline(...)` | `read-only` | Daily session counts by status over a trailing window                    |
| `analytics_export(...)`           | `read-only` | Combined backend stats + session timeline snapshot                       |

#### `analytics_backend_stats`

- **Arguments**: none
- **Returns**: `{"backends": [{"agent_backend", "count", "success_rate", "avg_duration_seconds", "retry_rate"}, ...]}`
- **Use case**: Compare agent backends across the active project to choose the most reliable one for a new task.

#### `analytics_session_timeline`

- **Arguments**: `days: int = 30`
- **Returns**: `{"timeline": [{"date", "total", "completed", "failed", "cancelled", "running", "pending"}, ...]}`
- **Use case**: Plot session volume and outcome trends over a trailing window.

#### `analytics_export`

- **Arguments**: `days: int = 30`
- **Returns**: `{"exported_at", "period_days", "backend_stats", "session_timeline"}`
- **Use case**: Snapshot aggregate analytics in a single call for archival, sharing, or offline analysis.

Additional multi-dimensional analytics (by role, by task type, per-task backend recommendation) are exposed over REST at `/api/analytics/...` but are not currently wrapped as MCP tools.

______________________________________________________________________

## `task_get` API

`task_get` supports three modes:

- `summary`: compact task payload
- `full`: expanded bounded task payload
- `context`: full bounded context (workspace + linked tasks)

### Parameters

| Parameter            | Type           | Description                               |
| -------------------- | -------------- | ----------------------------------------- |
| `task_id`            | `string`       | Target task                               |
| `mode`               | `string`       | `summary`, `full`, or `context`           |
| `include_scratchpad` | `bool \| null` | Include scratchpad (summary/full modes)   |
| `include_logs`       | `bool \| null` | Include bounded logs (summary/full modes) |
| `include_review`     | `bool \| null` | Include review payload when available     |

### Notes

- Scratchpad/log payloads are transport-bounded by default for reliability.
- When optional payloads are reduced due transport safety, response may include:
  - `scratchpad_truncated: true`
  - `logs_truncated: true`
- When `include_logs=true`, pagination hints may be included:
  - `logs_total_runs`, `logs_returned_runs`
  - `logs_has_more`, `logs_next_offset`

______________________________________________________________________

## `task_events` API

Use this tool to fetch execution event history for a task, with pagination support.

### Parameters

| Parameter         | Type     | Default  | Description                 |
| ----------------- | -------- | -------- | --------------------------- |
| `task_id`         | `string` | required | Target task                 |
| `limit`           | `int`    | `20`     | Events per page (1-200)     |
| `offset`          | `int`    | `0`      | Chronological offset        |
| `include_payload` | `bool`   | `false`  | Include full event payloads |

### Response fields

| Field      | Type     | Description                     |
| ---------- | -------- | ------------------------------- |
| `task_id`  | `string` | The task these events belong to |
| `offset`   | `int`    | Offset used for this page       |
| `limit`    | `int`    | Limit used for this page        |
| `returned` | `int`    | Number of events returned       |
| `logs`     | `list`   | Returned event entries          |

______________________________________________________________________

## `task_update` API

`task_update` is the single task mutation endpoint for incremental updates.

### Parameters

| Parameter             | Type                   | Description                                         |
| --------------------- | ---------------------- | --------------------------------------------------- |
| `task_id`             | `string \| null`       | Target task (defaults to context-bound task)        |
| `title`               | `string \| null`       | New title                                           |
| `description`         | `string \| null`       | New description                                     |
| `priority`            | `string \| int`        | `LOW`, `MEDIUM`, `HIGH`, or priority index          |
| `base_branch`         | `string \| null`       | Base branch override                                |
| `acceptance_criteria` | `list[string] \| null` | New acceptance criteria list                        |
| `agent_backend`       | `string \| null`       | Preferred agent backend                             |
| `launcher`            | `string \| null`       | Preferred interactive launcher                      |
| `status`              | `string \| null`       | Force status transition (set_status under the hood) |

______________________________________________________________________

## `task_wait` long-poll API

`task_wait` blocks until task status changes or timeout is reached.

### Parameters

| Parameter          | Type              | Default                | Description                                            |
| ------------------ | ----------------- | ---------------------- | ------------------------------------------------------ |
| `task_ids`         | `list[string]`    | required               | Task ids to watch (one or many)                        |
| `timeout_seconds`  | `float \| string` | server default (1800s) | Maximum wait duration                                  |
| `wait_for_status`  | `list \| string`  | `null`                 | Optional status filter (empty list/string = no filter) |
| `resolve_when_any` | `bool`            | `false`                | Return when first watched task resolves                |

### Response codes

| Code                   | Meaning                                                                  |
| ---------------------- | ------------------------------------------------------------------------ |
| `TASK_CHANGED`         | Task status changed                                                      |
| `ALREADY_AT_STATUS`    | Task already matches filter                                              |
| `CHANGED_SINCE_CURSOR` | Task changed after supplied cursor                                       |
| `WAIT_WINDOW`          | Window elapsed; re-poll with `remaining_seconds` and `changed_at` cursor |
| `WAIT_TIMEOUT`         | Timeout reached without status change                                    |
| `WAIT_INTERRUPTED`     | Wait cancelled/interrupted                                               |
| `TASK_DELETED`         | Task deleted while waiting                                               |
| `INVALID_TIMEOUT`      | Invalid timeout value                                                    |
| `INVALID_PARAMS`       | Invalid parameter payload                                                |

______________________________________________________________________

## `run_start` API

`run_start` provisions a workspace and launches a task run. Omit `launcher` for a managed background run; provide a launcher for an interactive launch.

### Parameters

| Parameter       | Type             | Description                                      |
| --------------- | ---------------- | ------------------------------------------------ |
| `task_id`       | `string`         | Target task                                      |
| `agent_backend` | `string \| null` | Override default agent backend                   |
| `launcher`      | `string \| null` | Optional launcher for interactive runs           |
| `persona`       | `string \| null` | Optional persona name to seed agent conversation |

### Response

- `session_id` — identifier of the run
- `task_id`, `status`, `agent_backend`, `persona`, and optional `launcher`

Use `run_start()` for managed execution or `run_start(launcher="tmux")` (or another launcher) for an interactive launch.

______________________________________________________________________

## `run_cancel` API

`run_cancel` cancels an active session.

### Parameters

| Parameter    | Type     | Description                |
| ------------ | -------- | -------------------------- |
| `session_id` | `string` | Running session identifier |
| `task_id`    | `string` | Task owning the session    |

### Response

- `cancelled: true`
- Echoed `session_id` and `task_id`.

______________________________________________________________________

## `run_summary` API

`run_summary` lists tasks with active runs, useful for dashboards.

### Parameters

| Parameter  | Type                   | Description                                    |
| ---------- | ---------------------- | ---------------------------------------------- |
| `task_ids` | `list[string] \| None` | Optional filter, defaults to all running tasks |

### Response

- `rows`: list of `{task_id, status, agent_backend, session_id, session_backend}`

______________________________________________________________________

## Scope and isolation

- Task mutations are enforced against task-scoped sessions (`task:<task_id>`).
- Interactive workers use task-scoped MCP sessions.
- Managed workers use task-scoped MCP sessions resolved from runtime permission policy.
- Scoped task sessions cannot mutate other task IDs.
- Global MCP access does not override task-scoped worker isolation.

### Timeout configuration

Default and max timeouts are server-side configurable via settings:

- `general.task_wait_default_timeout_seconds`
- `general.task_wait_max_timeout_seconds`

______________________________________________________________________

## Access tiers

Tool visibility is controlled by the MCP server's role tier. `--readonly` maps to the
worker-scoped surface, while the default and `--admin` modes both expose the
same orchestrator-scoped MCP tool set.

| Tier       | Visible tools                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `readonly` | Worker-scope tools (`task_get`, `task_list`, `task_events`, `task_wait`, `run_get`, `run_cancel`, `run_detach`, `run_summary`, `review_conflicts`, `settings_get`, `integration_preflight`, `integration_preview`, `verify_step`, `verification_summary`, `checkpoint_create`, `checkpoint_list`, `session_rewind`, `insight_add`, `insight_list`, `analytics_backend_stats`, `analytics_session_timeline`, `analytics_export`) |
| `default`  | Orchestrator-scope tools (worker tools plus `task_create`, `task_update`, `task_delete`, `run_start`, `review_decide`, `review_merge`, `review_rebase`, `review_verdict`, `review_clear_verdicts`, `project_list`, `project_setup`, `project_update`, `settings_set`, `audit_list`, `integration_sync`, `persona_inspect`, `persona_import`, `persona_export`, `persona_trust`, `insight_remove`)                               |
| `admin`    | Alias of `default` for MCP; currently exposes the same tool surface                                                                                                                                                                                                                                                                                                                                                             |

Unregistered tools are invisible to the host — it never knows they exist.

______________________________________________________________________

## Task field semantics

- `status` is Kanban state: `BACKLOG`, `IN_PROGRESS`, `REVIEW`, `DONE`.
- `status` only accepts Kanban states such as `BACKLOG`, `IN_PROGRESS`, `REVIEW`, and `DONE`.
- Do not set `status=DONE` via generic task patch/move workflows.
  Use review completion flows to reach `DONE`.
- `acceptance_criteria` accepts either a single string or a list of strings.

______________________________________________________________________
