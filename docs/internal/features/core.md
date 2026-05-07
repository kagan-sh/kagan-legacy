# Core Features

Observable behaviors of `kagan.core`. Each section maps to a test file in `tests/core/`.
Implementation details live in `docs/internal/architecture/core.md`.

______________________________________________________________________

## 1. Client Lifecycle

- Construct with optional `db_path`, defaults to `~/.local/share/kagan/kagan.db`
- Works without an active project (can list/create projects)
- Async context manager disposes cleanly on exit
- Preflight checks return actionable pass/warn/fail results

______________________________________________________________________

## 2. Projects & Repos

- Create a project → persisted, appears in project list
- Link one or more repos to a project by path
- Set a project as active → scopes all subsequent task/workspace/review ops
- Find a project by name or by repo path on disk
- Delete a project → all its tasks, workspaces, sessions, and events are removed

______________________________________________________________________

## 3. Task CRUD

- Create a task with title → appears in BACKLOG with unique ID
- Optional fields: description, priority, execution mode, base branch, acceptance criteria, agent backend
- Update mutable fields on an existing task
- Delete a task → stops active session, removes workspace, cleans up events
- List tasks, optionally filtered by status or execution mode
- Full-text search across title and description
- Add timestamped notes to a task; read them back chronologically

______________________________________________________________________

## 4. Task Lifecycle

- Valid transitions: BACKLOG → IN_PROGRESS → REVIEW → DONE
- REVIEW can also go back to IN_PROGRESS or BACKLOG
- DONE → BACKLOG reopens a task (fresh worktree on next run/pair)
- DONE is only reachable via `review.merge()`, never via direct move
- Invalid transitions raise `InvalidTransitionError`
- Moving away from IN_PROGRESS cancels any active session

______________________________________________________________________

## 5. Worktrees

- Starting a task provisions an isolated git worktree at `$XDG_STATE_HOME/kagan/worktrees/{task_id}` (outside the repo, preventing untracked-file collisions)
- Worktree branches from the repo's default branch (or task's base branch) under `kagan/{task_id}`
- Diff shows all changes in the worktree as unified diff
- Diff stats show files changed, insertions, deletions
- Merging a task squash-merges into the base branch, removes the worktree from disk, deletes the Worktree row, and prunes orphaned `kagan/*` branches
- Deleting a task removes its worktree from disk before removing the DB row
- Orphan worktrees (worktree exists but task was deleted) are detected and removed at TUI startup

______________________________________________________________________

## 6. Managed Runs

- Run a task → provisions worktree, spawns agent subprocess (ACP over STDIO), returns run
- Agent streams progress via ACP session updates (text chunks, tool calls, plans, permission requests)
- Permission requests surface as `CHAT_PERMISSION_REQUEST` events; the CLI resolves them via the inline approval panel (trust tiers: once / tool-for-session / all-for-session / deny), and the web resolves them via `POST /api/chat/sessions/{session_id}/permission/{future_id}`
- Kagan's own MCP tools (`mcp__kagan*`) are auto-approved — no user prompt is raised when the orchestrator calls back into itself
- `_tool_action_key` is keyed on the tool base name (not the full invocation string), so session-level approvals correctly cover repeated calls with different arguments
- Kagan's ACP reader writes events to DB in real-time
- Events stream reactively to any connected client (near-zero latency)
- Client reconnects and picks up full event history from offset 0
- Cancel kills the agent process and moves task to BACKLOG
- Repetition guard detects agents stuck in tool-call loops: if the same tool+arguments hash appears ≥8 times within a 20-call window, the agent is cancelled
- Repetition guard normalizes arguments (dict, JSON string, None) before hashing — different files read via the same tool produce distinct hashes
- On repetition-triggered cancellation, AGENT_FAILED is emitted **before** cancel to guarantee subscribers receive the error before the terminal TASK_STATUS_CHANGED
- ACP UsageUpdate events capture context window usage (size, used) and cumulative cost (amount, currency)
- Usage metrics are persisted on the Session record at session completion (context_window_used, context_window_size, cost_amount, cost_currency)
- Real-time usage updates are emitted as AGENT_STATUS events with a `usage` payload and streamed to all connected surfaces

______________________________________________________________________

## 7. Interactive Launches

- Launch interactive run on a task → provisions worktree, launches interactive environment
- Environment options: tmux session, IDE (vscode/cursor/windsurf/kiro), neovim
- Agent backend and launcher are orthogonal choices
- `.mcp.json` in worktree lets agent and IDE discover kagan's MCP server
- Session status tracked in DB; survives client restart
- Attach interrupts a managed run: if a background agent is active, it is cancelled before the interactive session starts
- TUI resumes and repaints the board after detaching from tmux (`Ctrl+b d`) or exiting neovim

______________________________________________________________________

## 8. Reviews

- Approve a task → records approval (does not move to DONE)
- Reject a task → moves back with feedback
- Merge a task → merges worktree into base branch, moves to DONE, cleans up workspace
- Merge can require prior approval (configurable)
- Rebase a task's worktree onto latest base branch
- Rebase conflicts are reported with affected file list
- Continue a paused rebase after resolving conflicts manually
- Query current conflict files for a task
- Record a pass/fail verdict for each acceptance criterion individually (`set_criterion_verdict`)
- Clear all criterion verdicts to reset review state

______________________________________________________________________

## 9. Settings & Audit

- Read and update key-value settings persisted in DB
- Behavioral settings: review strictness, planning depth, auto-confirm
- Additional instructions: single free-text field appended to all agent prompts
- Dotfile overrides: `.kagan/prompts/` files fully replace built-in prompts when present
- Known keys: default agent backend, attached launcher, auto-review, require approval, additional instructions, review strictness, planning depth
- Task mutations are audit-logged automatically (`task.create`, `task.update`, `task.status_change`, `task.delete`).
- Audit trail is queryable with limit

______________________________________________________________________

## 10. Persona Pipeline

- Four built-in personas: `analyst`, `planner`, `implementer`, `reviewer`
- Each persona has a distinct prompt profile tuned to its role
- Activate a persona per session via `run_start(task_id, persona="implementer")`
- Import persona presets from GitHub repos (subject to whitelist)
- Export persona presets to GitHub repos
- Manage an import whitelist of approved persona source repos
- Audit persona repositories for preset structure and validity (`audit_repo`)
- Multi-session sequencing is orchestrator-driven: the orchestrator agent plans and starts sequential persona sessions via MCP tools, not an automated Python-level pipeline

______________________________________________________________________

## 11. Preflight

- Checks: git, configured agent backend executable, tmux, DB writability
- Each check returns pass, warn, or fail with fix hints
- Blocking checks prevent operations; warnings are informational

______________________________________________________________________

## 12. Project Learnings

- Agents save project-wide learnings by calling `insight_add` with a learning category
- Before each managed task run, kagan queries all learning insights across every task in the current project
- Up to 20 unique learnings (newest-first, deduplicated) are injected into the task prompt as a `PROJECT CONTEXT (from prior tasks):` section
- Learnings are strictly scoped to the project — insights from other projects are never included

______________________________________________________________________

## 13. Analytics & Metrics

- Track per-backend performance metrics: session count, success rate, average duration, retry rate
- Session activity timeline aggregates daily counts (total, completed, failed, cancelled) over a configurable window (default 30 days)
- Metrics are computed from session event logs, not external telemetry
- All data stays local — no export to external services
- Export analytics as JSON for external dashboards, compliance, or team reporting
- Three MCP tools expose analytics: `analytics_backend_stats`, `analytics_session_timeline`, `analytics_export`
- Export respects the same project-scoping as other operations (per active project)
- Analytics queries are read-only; no effect on task state or events

______________________________________________________________________

## 14. Orchestrator-chat Foundation

- `client.resolve_active_session(task_id)` returns the most relevant session for
  a task. Priority: active worker → active reviewer → most-recent reviewer →
  most-recent worker → most-recent any → `None`. Pure, total — never raises.
  *Tests:* `tests/unit/core/test_resolve_active_session.py`.
- `client.list_running_agents(project_id=None)` returns active worker / reviewer
  sessions joined with their owning task as `ActiveAgentRow` rows ordered by
  `started_at DESC`; optionally scoped to a project.
  *Tests:* `tests/core/test_running_agents_listing.py`.
- `client.attach_chat(chat_session_id, session_id, agent_role=...)` writes
  `attached_session_id` / `attached_role` on the ChatSession; `session_id=None`
  detaches and clears the role. *Tests:* `tests/core/test_chat_attachment.py`.
- `transition_session` injects an `agent_started` / `agent_finished` /
  `agent_stopped` system message into every project chat session when a
  session enters `RUNNING` or a terminal status. Failures are logged and
  never block the transition.
  *Tests:* `tests/core/test_session_transition_notifies_chat.py`.

______________________________________________________________________

## 15. GitHub Integration

- Import open / closed / all GitHub issues into a project as kagan tasks; idempotent (re-runs skip already-imported issues, update existing ones with newer GitHub `updatedAt`)
- Task ↔ issue link stored on `Task.github_issue` as `<owner>/<repo>#<number>`
- Bidirectional metadata sync: title, body (verbatim — no scaffolding injected into description), priority labels, acceptance criteria
- Acceptance criteria sync via a tagged comment (`<!-- kagan:acceptance-criteria -->`); first import seeds criteria from `- [ ]` / `- [x]` lines in the issue body, subsequent edits read/write the tagged comment instead of rewriting the body
- Status lifecycles are decoupled — moving a task to DONE does not close the issue; closing the issue does not change task status
- Create-and-link at task creation time: `github_issue` accepts `none` / `<number>` / `owner/repo#<number>` / `new` (creates the issue from task title + description)
- `#`-mention autocomplete (dual-source) — typing `#` in any kagan text field opens a typeahead listing matching kagan tasks (local DB) and GitHub issues (`gh issue list --search`); selecting inserts `kagan#<short_id>` or `#<number>`
- Cross-client parity: import + create-and-link + `#`-mention reachable from CLI, TUI, web, VS Code, MCP, chat
- Auth via `gh` CLI — no token plumbing
