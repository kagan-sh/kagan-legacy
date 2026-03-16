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

For embedded/runtime integrations, use `kagan.mcp.runtime` as the canonical server module.

## Annotation model

| Annotation    | Meaning                           |
| ------------- | --------------------------------- |
| `read-only`   | Reads state only                  |
| `mutating`    | Modifies state                    |
| `mixed`       | Action-dependent read/write modes |
| `destructive` | Irreversible/high-impact action   |

______________________________________________________________________

## Tool catalog

### Core task workflow

| Tool                 | Annotation    | Purpose                                                                           |
| -------------------- | ------------- | --------------------------------------------------------------------------------- |
| `task_get(...)`      | `read-only`   | Read bounded task snapshot (`summary`/`full`) or bounded context (`mode=context`) |
| `task_logs(...)`     | `read-only`   | Read paginated task execution logs (newest-first pages)                           |
| `task_list(...)`     | `read-only`   | List tasks with optional filtering and scratchpad inclusion                       |
| `tasks_wait(...)`    | `read-only`   | Long-poll task status changes                                                     |
| `task_create(...)`   | `mutating`    | Create a task                                                                     |
| `task_update(...)`   | `mutating`    | Apply partial task updates, transitions, and metadata adjustments                 |
| `task_add_note(...)` | `mutating`    | Append a timestamped reasoning note to a task's scratchpad                        |
| `task_delete(...)`   | `destructive` | Delete a task                                                                     |

### Automation & session tools

| Tool               | Annotation  | Purpose                                                                   |
| ------------------ | ----------- | ------------------------------------------------------------------------- |
| `run_start(...)`   | `mutating`  | Start AUTO or PAIR execution (provisions worktree, launches agent stream) |
| `run_update(...)`  | `mixed`     | Manage PAIR session lifecycle (exists/create/get/kill/finish)             |
| `run_cancel(...)`  | `mutating`  | Cancel an active session                                                  |
| `run_summary(...)` | `read-only` | List running sessions + statuses for active tasks                         |

### Project, review, and admin

| Tool                 | Annotation    | Purpose                                                      |
| -------------------- | ------------- | ------------------------------------------------------------ |
| `project_list(...)`  | `read-only`   | List recent projects                                         |
| `project_open(...)`  | `mutating`    | Open/switch project                                          |
| `repo_list(...)`     | `read-only`   | List repos by project                                        |
| `review_decide(...)` | `destructive` | Apply review action (`approve`, `reject`, `merge`, `rebase`) |
| `audit_list(...)`    | `read-only`   | List recent audit events                                     |
| `settings_get()`     | `read-only`   | Read allowlisted settings                                    |
| `settings_set(...)`  | `mutating`    | Update allowlisted settings                                  |
| `plan_submit(...)`   | `mutating`    | Submit planner proposal payload                              |

### Plugin tools (experimental)

| Tool                     | Annotation    | Purpose                                  |
| ------------------------ | ------------- | ---------------------------------------- |
| `plugins_sync(...)`      | `destructive` | Sync issues via plugin, returns counts   |
| `plugins_preflight(...)` | `read-only`   | Check plugin prerequisites and readiness |

Review semantics:

- `review_decide(action="approve")` records approval state but does **not** move task to `DONE`.
- `DONE` is reached by completion flows (for example `review_decide(action="merge")` or no-change close flow).

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

## `task_logs` API

Use this tool to fetch additional log history when `task_get(..., include_logs=true)` is truncated
or indicates more pages are available.

### Parameters

| Parameter | Type     | Default  | Description         |
| --------- | -------- | -------- | ------------------- |
| `task_id` | `string` | required | Target task         |
| `limit`   | `int`    | `5`      | Runs per page       |
| `offset`  | `int`    | `0`      | Newest-first offset |

### Response fields

| Field           | Type          | Description                            |
| --------------- | ------------- | -------------------------------------- |
| `logs`          | `list`        | Returned run log entries               |
| `total_runs`    | `int`         | Total runs available                   |
| `returned_runs` | `int`         | Runs returned in this response         |
| `has_more`      | `bool`        | Whether another page is available      |
| `next_offset`   | `int \| null` | Offset to fetch the next older page    |
| `truncated`     | `bool`        | Whether content was reduced for safety |

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
| `execution_mode`      | `string \| null`       | `AUTO` or `PAIR`                                    |
| `base_branch`         | `string \| null`       | Base branch override                                |
| `acceptance_criteria` | `list[string] \| null` | New acceptance criteria list                        |
| `agent_backend`       | `string \| null`       | Preferred agent backend                             |
| `launcher`            | `string \| null`       | Preferred pair launcher                             |
| `status`              | `string \| null`       | Force status transition (set_status under the hood) |

______________________________________________________________________

## `task_add_note` API

`task_add_note` appends a structured, timestamped reasoning note to a task's scratchpad.
Use this during agent execution to record decisions, tradeoffs, and observations.
Each call appends a new entry — it never overwrites prior notes.

!!! tip "When to use `task_add_note` vs `task_update`"
Use `task_add_note` for mid-run agent notes (decision log, tradeoff record).
Use `task_update()` for structured state transitions and status updates.

### Parameters

| Parameter | Type     | Description                                              |
| --------- | -------- | -------------------------------------------------------- |
| `task_id` | `string` | Target task                                              |
| `note`    | `string` | Note content. Stored as `[YYYY-MM-DDTHH:MM:SSZ] <note>`. |

### Scratchpad format

```
---
[2026-02-20T14:31:00Z] Chose approach B over A — A required a schema migration.
---
[2026-02-20T14:45:12Z] Added retry logic; upstream API returns 503 intermittently.
```

Notes live in the scratchpad (retrievable via `task_get(..., include_scratchpad=true)`)
and feed the acceptance criteria coverage check at REVIEW transition time.

______________________________________________________________________

## `tasks_wait` long-poll API

`tasks_wait` blocks until task status changes or timeout is reached.

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

`run_start` provisions a workspace and launches an AUTO or PAIR session for the task.

### Parameters

| Parameter       | Type             | Description                                             |
| --------------- | ---------------- | ------------------------------------------------------- |
| `task_id`       | `string`         | Target task                                             |
| `action`        | `string`         | `run` (AUTO) or `pair` session mode                     |
| `agent_backend` | `string \| null` | Override default agent backend                          |
| `launcher`      | `string \| null` | Override pair launcher (applies only for `action=pair`) |
| `persona`       | `string \| null` | Optional persona name to seed agent conversation        |

### Response

- `session_id` — identifier of the AUTO/PAIR session
- `task_id`, `status`, `action`, `mode`, `agent_backend`, and `persona`

Use `run_start(action="run")` to trigger an AUTO execution loop and `run_start(action="pair")` to attach a PAIR session (creates a `tasks.pair` session).

______________________________________________________________________

## `run_update` API

`run_update` controls PAIR session lifecycle via discrete actions.

### Parameters

| Parameter | Type     | Description                                        |
| --------- | -------- | -------------------------------------------------- |
| `action`  | `string` | One of `exists`, `create`, `get`, `kill`, `finish` |
| `task_id` | `string` | Target task (pair session is scoped to the task)   |

### Actions

- `exists`: Returns `{"exists": bool, "task_id": ...}` without mutating state.
- `create`: Provisions a workspace and starts a PAIR session, mirroring the `run_start(action="pair")` flow.
- `get`: Reads the current PAIR session status (`"STARTED"`, `"ENDED"`, etc.)
- `kill`: Cancels the task run via `client.tasks.cancel`.
- `finish`: Signals the server to end pairing via `client.tasks.end_pairing`.

______________________________________________________________________

## `run_cancel` API

`run_cancel` is the safe knob that cancels an active session when you already know the `session_id`.

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

`run_summary` lists tasks with active AUTO or PAIR sessions, useful for dashboards.

### Parameters

| Parameter  | Type                   | Description                                    |
| ---------- | ---------------------- | ---------------------------------------------- |
| `task_ids` | `list[string] \| None` | Optional filter, defaults to all running tasks |

### Response

- `rows`: list of `{task_id, status, execution_mode, agent_backend, session_id, session_backend}`

______________________________________________________________________

## Scope and isolation

- Task mutations are enforced against task-scoped sessions (`task:<task_id>`).
- PAIR workers use task-scoped MCP sessions.
- AUTO workers use task-scoped MCP sessions resolved from runtime permission policy.
- Scoped task sessions cannot mutate other task IDs.
- Global MCP access does not override task-scoped worker isolation.

### Timeout configuration

Default and max timeouts are server-side configurable via settings:

- `general.tasks_wait_default_timeout_seconds`
- `general.tasks_wait_max_timeout_seconds`

______________________________________________________________________

## Access tiers

Tool visibility is controlled by the MCP server's access tier (set via `--readonly` / `--admin` flags).

| Tier       | Visible tools                                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------------------------------- |
| `readonly` | Read-only operations (`task_get`, `task_list`, `task_events`, `tasks_wait`, `run_summary`, etc.)                    |
| `default`  | Read-only + `task_create`, `task_update`, `task_add_note`, `run_start`, `run_update`, `run_cancel`, `review_decide` |
| `admin`    | `default` + `task_delete`, `settings_set`, `plugins_sync`, destructive review flows                                 |

Unregistered tools are invisible to the host — it never knows they exist.

______________________________________________________________________

## Task field semantics

- `status` is Kanban state: `BACKLOG`, `IN_PROGRESS`, `REVIEW`, `DONE`.
- `status=AUTO` and `status=PAIR` are rejected with `TASK_TYPE_VALUE_IN_STATUS`.
- Do not set `status=DONE` via generic task patch/move workflows.
  Use review completion flows to reach `DONE`.
- `task_type` is execution mode: `AUTO`, `PAIR`.
- `acceptance_criteria` accepts either a single string or a list of strings.

______________________________________________________________________
