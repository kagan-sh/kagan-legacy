# MCP Features

Observable behaviors of `kagan.server.mcp`. Each section maps to a test file in `tests/mcp/`.
Implementation details live in `docs/internal/architecture/mcp.md`.

______________________________________________________________________

## 1. Task Tools

- Get a task by ID (summary, full, or context mode)
- List tasks filtered by status or repo, with optional free-text `query` search
- Create one or more tasks (single via `title`, batch via `tasks` list)
- Patch task fields or transition status (lifecycle enforced)
- Delete a task and all associated data
- Read paginated execution event logs via `task_events`
- Wait for task status changes or target statuses via `task_wait` (event-driven, timeout-bounded)

______________________________________________________________________

## 2. Managed Run Tools

- Start managed execution → provisions worktree, spawns agent, returns run
- Wait for task lifecycle transitions with `task_wait` (event-driven, timeout-bounded)
- Cancel a running run → kills agent, moves task to BACKLOG
- `run_summary` returns token usage metrics per task: context_window_used, context_window_size, cost_amount, cost_currency

______________________________________________________________________

## 3. Interactive Session Tools

- Open an interactive run → provisions worktree, launches environment, returns run
- Read current run status
- Close a run and clean up

______________________________________________________________________

## 4. Project Tools

- List projects with metadata and task counts
- Set up a project, optionally linking repos and setting as active
- Update project settings, link/unlink repos, set default branch

______________________________________________________________________

## 5. Review Tools

- Decide on a task: approve or reject via `review_decide(verdict=...)`
- Merge an approved task into its base branch
- Rebase a task branch via `review_rebase(action="start"|"continue"|"abort")`
- Get merge conflict details via `review_conflicts`
- Set verdict on individual acceptance criteria via `review_verdict`
- Clear all AI review verdicts via `review_clear_verdicts`

______________________________________________________________________

## 6. Settings & Diagnostics Tools

- Read all settings as key-value pairs
- Update settings (validated by core)
- List recent audit events with limit

______________________________________________________________________

## 7. Verification, Checkpoints & Insights (in sessions toolset)

- Record a PASS/FAIL verdict on a plan step via `verify_step`
- Get all step verdicts for a session via `verification_summary`
- Create git checkpoints in a task worktree via `checkpoint_create`
- List checkpoints via `checkpoint_list`
- Rewind a task worktree to a checkpoint via `session_rewind`
- Add categorized insight notes via `insight_add`
- List insights via `insight_list`
- Remove insights via `insight_remove`

______________________________________________________________________

## 8. Prompts

- `review_task` — structured code review with diff context
- `plan_tasks_from_description` — natural-language to task breakdown (orchestrator drafts tickets, user reviews before creating)
- `diagnose_failure` — diagnose agent execution failure
- Always available regardless of agent role

______________________________________________________________________

## 9. Diagnostics

- Internal instrumentation tool (opt-in via `--enable-internal-instrumentation`)
- Returns active sessions, DB stats, agent process status

______________________________________________________________________

## 10. Integration Tools

- `integration_sync` (ORCHESTRATOR role) — sync issues via MCP, returns created/skipped/errors
  - Accepts integration name, repo (owner/repo format), optional state and label filters
  - Returns created/skipped/errors counts
- `integration_preflight` (WORKER role) — check if an integration's external dependencies are satisfied
  - Optional integration name; checks all integrations if omitted
  - Returns pass/warn/fail checks and readiness status
- `integration_preview` (WORKER role) — preview integration import results without applying

______________________________________________________________________

## 11. Persona Tools

- `persona_inspect` — audit and preview persona presets in a repository before import
- `persona_import` — import persona presets from a GitHub repository
- `persona_export` — export local persona presets to a GitHub repository
- `persona_trust` — manage trusted persona repositories (list, add, remove)

______________________________________________________________________

## 12. Analytics Tools

Read-only wrappers around `Analytics` in `kagan.core._analytics`, scoped to the active project. All three tools are registered in the WORKER tier so any agent role can query them; they return empty payloads when no project is active.

- `analytics_backend_stats` — per-backend aggregates (count, success rate, avg duration, retry rate) for choosing an agent backend
- `analytics_session_timeline(days=30)` — daily session counts bucketed by status (completed/failed/cancelled/running/pending) for trend charts
- `analytics_export(days=30)` — combined `{exported_at, period_days, backend_stats, session_timeline}` snapshot for archival or offline analysis

The richer multi-dimensional analytics (by agent role, by task type, per-task backend recommendation) live only on the REST surface under `/api/analytics/*` (see `src/kagan/server/_analytics_routes.py`). They are intentionally not exposed as MCP tools yet — add them to `toolsets/analytics.py` and register in `_policy.py` if a use case emerges.

______________________________________________________________________

## 13. Resources

- Read-only data endpoints, always available regardless of access mode
- `kagan://ping` — health check
- `kagan://settings` — settings snapshot
- `kagan://projects` — project list
- `kagan://tasks/{id}` — task detail
- `kagan://runtime` — active sessions and agent processes

______________________________________________________________________

## 14. Access Control

- Three roles: WORKER (board awareness + own-task annotation), REVIEWER (+ verdicts), ORCHESTRATOR (full control)
- `--role` flag sets the agent role; defaults to ORCHESTRATOR
- `--readonly` maps to WORKER, `--admin` maps to ORCHESTRATOR for backward compatibility
- Unregistered tools are invisible — host never knows they exist
- Session binding (`--session-id`) auto-opens project and defaults task_id
- Core wires `--role WORKER` into `.mcp.json` automatically for spawned agents
