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

- Starting a task (AUTO or PAIR) provisions an isolated git worktree at `$XDG_STATE_HOME/kagan/worktrees/{task_id}` (outside the repo, preventing untracked-file collisions)
- Worktree branches from the repo's default branch (or task's base branch) under `kagan/{task_id}`
- Diff shows all changes in the worktree as unified diff
- Diff stats show files changed, insertions, deletions
- Merging a task squash-merges into the base branch, removes the worktree from disk, deletes the Worktree row, and prunes orphaned `kagan/*` branches
- Deleting a task removes its worktree from disk before removing the DB row
- Orphan worktrees (worktree exists but task was deleted) are detected and removed at TUI startup

______________________________________________________________________

## 6. AUTO Execution

- Run a task → provisions worktree, spawns agent subprocess (ACP over STDIO), returns run
- Agent streams progress via ACP session updates (text chunks, tool calls, plans, permissions)
- Kagan's ACP reader writes events to DB in real-time
- Events stream reactively to any connected client (near-zero latency)
- Client reconnects and picks up full event history from offset 0
- Cancel kills the agent process and moves task to BACKLOG

______________________________________________________________________

## 7. PAIR Sessions

- Pair on a task → provisions worktree, launches interactive environment
- Environment options: tmux session, IDE (vscode/cursor/windsurf/kiro), neovim
- Agent backend and launcher are orthogonal choices
- `.mcp.json` in worktree lets agent and IDE discover kagan's MCP server
- Session status tracked in DB; survives client restart

______________________________________________________________________

## 8. Reviews

- Approve a task → records approval (does not move to DONE)
- Reject a task → moves back with feedback
- Merge a task → merges worktree into base branch, moves to DONE, cleans up workspace
- Merge can require prior approval (configurable)
- Rebase a task's worktree onto latest base branch
- Rebase conflicts are reported with affected file list

______________________________________________________________________

## 9. Settings & Audit

- Read and update key-value settings persisted in DB
- Known keys: default agent backend, default launcher, auto-review, require approval
- All mutations are audit-logged automatically (who, what, when)
- Audit trail is queryable with limit

______________________________________________________________________

## 10. Preflight

- Checks: git, configured agent backend executable, tmux, DB writability
- Each check returns pass, warn, or fail with fix hints
- Blocking checks prevent operations; warnings are informational
