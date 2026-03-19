---
title: Task lifecycle
description: How tasks move from idea to merged code
icon: material/state-machine
---

# Task lifecycle

Every task follows the same four-column flow. The board enforces it.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> BACKLOG
    BACKLOG --> IN_PROGRESS
    IN_PROGRESS --> REVIEW
    IN_PROGRESS --> BACKLOG : paused / descoped
    REVIEW --> IN_PROGRESS : rejected
    REVIEW --> BACKLOG : rejected to backlog
    REVIEW --> DONE : merge only
    DONE --> BACKLOG : reopen
    DONE --> [*]
```

## Statuses

| Status          | Meaning                                     |
| --------------- | ------------------------------------------- |
| **BACKLOG**     | Planned but not started                     |
| **IN_PROGRESS** | Managed run active or interactive session open |
| **REVIEW**      | Work complete, awaiting human review        |
| **DONE**        | Reviewed and merged                         |

Moving between columns is constrained. You can drag tasks left or right within the allowed transitions above — but **REVIEW → DONE requires a merge**. No shortcut.

## Worktrees

When a task starts, Kagan creates a **git worktree** — an isolated branch copy of your repo. The agent works there. Your main branch stays untouched.

```text
your-repo/
  .git/
  src/                     ← your working copy (unchanged)

~/.local/share/kagan/worktrees/
  task-abc123/             ← agent workspace (isolated branch)
    src/
```

- One worktree per task, per repo.
- Multi-repo projects get one worktree per repo per task.
- Worktrees are cleaned up after merge.
- State lives outside your repo — no `.kagan/` directory in your codebase.

## Launch styles

Each task is just a task. When you launch it, choose between a managed run or an interactive launcher handoff.

| Style | Who drives  | Where it happens                                       |
| ----- | ----------- | ------------------------------------------------------ |
| Managed run | Agent | Background process; follow progress in the task or session views |
| Interactive launch | You + agent | tmux, Neovim, VS Code, Cursor, Windsurf, Kiro, etc. |

[:octicons-arrow-right-24: Managed vs interactive guide](../guides/managed-vs-interactive.md)

## Review

When work finishes — the managed run completes or you detach/finish the interactive session — it enters REVIEW.

### What you see

- Diff summary (files changed, lines added/removed)
- Acceptance criteria checklist (if defined)
- Agent reasoning notes (from `task_add_note` scratchpad entries during the run)

### What you can do

| Action  | Effect                                         |
| ------- | ---------------------------------------------- |
| Approve | Records approval; task stays in REVIEW         |
| Reject  | Sends task back to IN_PROGRESS (with notes)    |
| Merge   | Merges worktree branch → base; task → DONE     |
| Rebase  | Rebases worktree onto latest base before merge |

Approve records intent but does not move the task. **Only merge transitions to DONE.**

## Acceptance criteria

Optional. Kagan stores acceptance criteria with the task and shows them during review.

- Tasks with criteria can use AI-assisted review and approval flows.
- Tasks without criteria still run normally, but automated approve/merge actions stay blocked.
- Human review remains available either way.

## Scratchpad and resume

Each task accumulates notes — agent decisions, status changes, your annotations. When you reopen an `IN_PROGRESS` or `REVIEW` task, the Resume Context strip shows the most recent ~500 characters at the top of the detail view. The full scratchpad remains available through `task_get(..., include_scratchpad=true)` or `task_events`.

______________________________________________________________________

[:octicons-arrow-right-24: Architecture overview](architecture-overview.md) · [:octicons-arrow-right-24: Configuration](../reference/configuration.md) · [:octicons-arrow-right-24: Troubleshooting](../troubleshooting.md)
