# MCP Features

Observable behaviors of `kagan.server.mcp`. Each section maps to a test file in `tests/mcp/`.
Implementation details live in `docs/internal/architecture/mcp.md`.

______________________________________________________________________

## 1. Task Tools

- Get a task by ID (summary, full, or context mode)
- List tasks filtered by status, scoped to active project
- Search tasks by query string
- Create a task with title and optional fields
- Batch-create multiple tasks at once (title required, description optional per entry)
- Patch task fields or transition status (lifecycle enforced)
- Delete a task and all associated data
- Add a timestamped note to a task
- Read paginated execution event logs via `task_events`
- Get task counts grouped by status via `task_counts`
- Wait for task status changes or target statuses via event-driven lifecycle signals

______________________________________________________________________

## 2. Managed Run Tools

- Start managed execution → provisions worktree, spawns agent, returns run
- Wait for task lifecycle transitions with `tasks_wait` (event-driven, timeout-bounded)
- Cancel a running run → kills agent, moves task to BACKLOG
- `run_summary` returns token usage metrics per task: context_window_used, context_window_size, cost_amount, cost_currency

______________________________________________________________________

## 3. Interactive Session Tools

- Open an interactive run → provisions worktree, launches environment, returns run
- Read current run status
- Close a run and clean up

______________________________________________________________________

## 4. Project & Repo Tools

- List projects with metadata and task counts
- Create a project, optionally linking repos
- Open a project (set as active for this server run)
- Link a repo to a project; list repos in a project
- Update a repo's default branch

______________________________________________________________________

## 5. Review Tools

- Apply review actions: approve, reject (with feedback), merge, rebase
- Merge enforces lifecycle (REVIEW status required, approval if configured)
- Rebase reports conflicts with affected file list
- Get merge conflict details via `review_conflicts`
- Continue an interrupted rebase via `review_continue_rebase`
- Abort a rebase operation via `review_abort_rebase`
- Set verdict on individual acceptance criteria via `review_set_criterion_verdict`
- Clear all AI review verdicts via `review_clear_verdicts`

______________________________________________________________________

## 6. Settings & Audit Tools

- Read all settings as key-value pairs
- Update settings (validated by core)
- List recent audit events with limit

______________________________________________________________________

## 7. Prompts

- `review_task` — structured code review with diff context
- `plan_tasks_from_description` — natural-language to task breakdown (orchestrator drafts tickets, user reviews before batch-creating)
- `diagnose_failure` — diagnose agent execution failure
- Always available regardless of agent role

______________________________________________________________________

## 8. Diagnostics

- Internal instrumentation tool (opt-in via `--enable-internal-instrumentation`)
- Returns active sessions, DB stats, agent process status

______________________________________________________________________

## 9. Plugin Tools

- `plugins_sync` (ORCHESTRATOR role) — sync issues via MCP, returns created/skipped/errors
  - Accepts plugin name, repo (owner/repo format), optional state and label filters
  - Returns created/skipped/errors counts and community warnings
- `plugins_preflight` (WORKER role) — check if a plugin's external dependencies are satisfied
  - Optional plugin name; checks all plugins if omitted
  - Returns pass/warn/fail checks and readiness status

______________________________________________________________________

## 10. Persona Tools

- `persona_preset_audit` — audit persona presets in a repository
- `persona_preset_import` — import persona presets from a GitHub repository
- `persona_preset_export` — export persona presets to a GitHub repository
- `persona_preset_whitelist_list` — list trusted persona repositories
- `persona_preset_whitelist_add` — add a repository to the trusted list
- `persona_preset_whitelist_remove` — remove a repository from the trusted list

______________________________________________________________________

## 11. Resources

- Read-only data endpoints, always available regardless of access mode
- `kagan://ping` — health check
- `kagan://settings` — settings snapshot
- `kagan://projects` — project list
- `kagan://tasks/{id}` — task detail
- `kagan://runtime` — active sessions and agent processes

______________________________________________________________________

## 12. Access Control

- Three roles: WORKER (board awareness + own-task annotation), REVIEWER (+ verdicts), ORCHESTRATOR (full control)
- `--role` flag sets the agent role; defaults to ORCHESTRATOR
- `--readonly` maps to WORKER, `--admin` maps to ORCHESTRATOR for backward compatibility
- Unregistered tools are invisible — host never knows they exist
- Session binding (`--session-id`) auto-opens project and defaults task_id
- Core wires `--role WORKER` into `.mcp.json` automatically for spawned agents
