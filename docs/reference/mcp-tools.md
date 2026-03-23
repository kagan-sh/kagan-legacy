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

| Tool                       | Annotation    | Purpose                                                                           |
| -------------------------- | ------------- | --------------------------------------------------------------------------------- |
| `task_get(...)`            | `read-only`   | Read bounded task snapshot (`summary`/`full`) or bounded context (`mode=context`) |
| `task_list(...)`           | `read-only`   | List tasks with optional filtering and scratchpad inclusion                       |
| `task_search(...)`         | `read-only`   | Search tasks by query string                                                      |
| `task_events(...)`         | `read-only`   | Read paginated task execution events (newest-first pages)                        |
| `task_counts(...)`         | `read-only`   | Get task counts grouped by status                                                 |
| `tasks_wait(...)`          | `read-only`   | Long-poll task status changes                                                     |
| `task_create(...)`         | `mutating`    | Create a task                                                                     |
| `task_batch_create(...)`   | `mutating`    | Create multiple tasks in a single call                                            |
| `task_update(...)`         | `mutating`    | Apply partial task updates, transitions, and metadata adjustments                 |
| `task_add_note(...)`       | `mutating`    | Append a timestamped reasoning note to a task's scratchpad                        |
| `task_delete(...)`         | `destructive` | Delete a task                                                                     |

### Automation & session tools

| Tool               | Annotation  | Purpose                                                                   |
| ------------------ | ----------- | ------------------------------------------------------------------------- |
| `run_start(...)`   | `mutating`  | Start a managed run or launch an interactive session for a task           |
| `run_exists(...)`  | `read-only` | Check whether a task currently has an interactive session                 |
| `run_create(...)`  | `mutating`  | Provision a workspace and start an interactive session                    |
| `run_get(...)`     | `read-only` | Read the current interactive session status for a task                    |
| `run_kill(...)`    | `mutating`  | Cancel a task run by task id                                              |
| `run_detach(...)`  | `mutating`  | Finalize an interactive session and update task status                    |
| `run_cancel(...)`  | `mutating`  | Cancel an active session                                                  |
| `run_summary(...)` | `read-only` | List running sessions + statuses for active tasks                         |

### Project, review, and admin

| Tool                        | Annotation    | Purpose                                                       |
| --------------------------- | ------------- | ------------------------------------------------------------- |
| `project_list(...)`         | `read-only`   | List recent projects                                          |
| `project_set_active(...)`   | `mutating`    | Set active project                                            |
| `project_create(...)`       | `mutating`    | Create a project                                              |
| `project_add_repo(...)`     | `mutating`    | Link a repo to a project                                      |
| `project_delete(...)`       | `destructive` | Delete a project                                              |
| `repo_list(...)`            | `read-only`   | List repos by project                                         |
| `review_approve(...)`       | `mutating`    | Record approval for a review-ready task                       |
| `review_reject(...)`        | `mutating`    | Reject a review-ready task with explicit feedback             |
| `review_merge(...)`         | `destructive` | Merge an approved task into its base branch                   |
| `review_rebase(...)`        | `mutating`    | Rebase a task branch onto its base branch                     |
| `review_conflicts(...)`     | `read-only`   | Get merge conflict details                                    |
| `review_continue_rebase(...)` | `mutating`  | Continue an interrupted rebase                                |
| `review_abort_rebase(...)`  | `mutating`    | Abort a rebase operation                                      |
| `review_set_criterion_verdict(...)` | `mutating` | Set verdict on an acceptance criterion                   |
| `review_clear_verdicts(...)` | `mutating`   | Clear AI review verdicts                                      |
| `audit_list(...)`           | `read-only`   | List recent audit events                                      |
| `settings_get()`            | `read-only`   | Read allowlisted settings                                     |
| `settings_set(...)`         | `mutating`    | Update allowlisted settings                                   |

### Plugin tools (experimental)

| Tool                     | Annotation    | Purpose                                  |
| ------------------------ | ------------- | ---------------------------------------- |
| `plugins_sync(...)`      | `destructive` | Sync issues via plugin, returns counts   |
| `plugins_preflight(...)` | `read-only`   | Check plugin prerequisites and readiness |

### Persona tools

| Tool                                | Annotation    | Purpose                                |
| ----------------------------------- | ------------- | -------------------------------------- |
| `persona_preset_audit(...)`         | `read-only`   | Audit persona presets in a repo        |
| `persona_preset_import(...)`        | `mutating`    | Import persona presets from GitHub     |
| `persona_preset_export(...)`        | `mutating`    | Export persona presets to GitHub       |
| `persona_preset_whitelist_list(...)` | `read-only`  | List trusted persona repos            |
| `persona_preset_whitelist_add(...)`  | `mutating`   | Trust a persona repo                  |
| `persona_preset_whitelist_remove(...)` | `mutating` | Untrust a persona repo               |

Review semantics:

- `review_approve()` records approval state but does **not** move task to `DONE`.
- `DONE` is reached by completion flows (for example `review_merge()` or no-change close flow).

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

| Parameter           | Type     | Default  | Description                                |
| ------------------- | -------- | -------- | ------------------------------------------ |
| `task_id`           | `string` | required | Target task                                |
| `limit`             | `int`    | `20`     | Events per page (1–200)                    |
| `offset`            | `int`    | `0`      | Chronological offset                       |
| `include_payload`   | `bool`   | `false`  | Include full event payloads                |
| `max_payload_bytes` | `int`    | `16384`  | Max bytes per individual payload (256–128K)|
| `max_total_bytes`   | `int`    | `262144` | Total byte budget for response (4K–1M)     |

### Response fields

| Field                      | Type     | Description                                  |
| -------------------------- | -------- | -------------------------------------------- |
| `task_id`                  | `string` | The task these events belong to              |
| `offset`                   | `int`    | Offset used for this page                    |
| `limit`                    | `int`    | Limit used for this page                     |
| `returned`                 | `int`    | Number of events returned                    |
| `truncated_by_total_bytes` | `bool`   | Whether response was truncated by byte budget|
| `logs`                     | `list`   | Returned event entries                       |

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

```text
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

`run_start` provisions a workspace and launches a task run. Omit `launcher` for a managed background run; provide a launcher for an interactive launch.

### Parameters

| Parameter       | Type             | Description                                             |
| --------------- | ---------------- | ------------------------------------------------------- |
| `task_id`       | `string`         | Target task                                             |
| `agent_backend` | `string \| null` | Override default agent backend                          |
| `launcher`      | `string \| null` | Optional launcher for interactive runs                  |
| `persona`       | `string \| null` | Optional persona name to seed agent conversation        |

### Response

- `session_id` — identifier of the run
- `task_id`, `status`, `agent_backend`, `persona`, and optional `launcher`

Use `run_start()` for managed execution or `run_start(launcher="tmux")` (or another launcher) for an interactive launch.

______________________________________________________________________

## Attached run APIs

The attached-run lifecycle now uses one explicit tool per action.

### Parameters

| Tool              | Parameter | Type     | Description                                                |
| ----------------- | --------- | -------- | ---------------------------------------------------------- |
| `run_exists(...)` | `task_id` | `string` | Returns `{"exists": bool, "task_id": ...}`             |
| `run_create(...)` | `task_id` | `string` | Provisions a workspace and starts an interactive session   |
| `run_get(...)`    | `task_id` | `string` | Reads the current interactive session status for the task  |
| `run_kill(...)`   | `task_id` | `string` | Cancels the task run via `client.tasks.cancel`             |
| `run_detach(...)` | `task_id` | `string` | Finalizes an interactive session via `client.tasks.detach` |

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

- `general.tasks_wait_default_timeout_seconds`
- `general.tasks_wait_max_timeout_seconds`

______________________________________________________________________

## Access tiers

Tool visibility is controlled by the MCP server's access tier (set via `--readonly` / `--admin` flags).

| Tier       | Visible tools                                                                                                                |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `readonly` | Worker-scope tools (`task_get`, `task_list`, `task_search`, `task_events`, `task_counts`, `task_add_note`, `tasks_wait`, `run_summary`, `run_exists`, `run_create`, `run_get`, `run_kill`, `run_detach`, `settings_get`, `review_conflicts`, `plugins_preflight`) |
| `default`  | Read-only + `task_create`, `task_batch_create`, `task_update`, `task_add_note`, `run_start`, `run_exists`, `run_create`, `run_get`, `run_kill`, `run_detach`, `run_cancel`, `review_approve`, `review_reject`, `review_merge`, `review_rebase` |
| `admin`    | `default` + `task_delete`, `settings_set`, `plugins_sync`, review flows, persona management                                 |

Unregistered tools are invisible to the host — it never knows they exist.

______________________________________________________________________

## Task field semantics

- `status` is Kanban state: `BACKLOG`, `IN_PROGRESS`, `REVIEW`, `DONE`.
- `status` only accepts Kanban states such as `BACKLOG`, `IN_PROGRESS`, `REVIEW`, and `DONE`.
- Do not set `status=DONE` via generic task patch/move workflows.
  Use review completion flows to reach `DONE`.
- `acceptance_criteria` accepts either a single string or a list of strings.

______________________________________________________________________
