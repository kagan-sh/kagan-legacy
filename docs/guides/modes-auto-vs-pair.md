---
title: AUTO vs PAIR
description: Choose and run the right execution mode for each task
icon: material/robot
tags:
  - modes
  - execution
---

# AUTO vs PAIR

| When…                            | Use  |
| -------------------------------- | ---- |
| Requirements clear, bounded      | AUTO |
| Evolving, exploratory            | PAIR |
| Async background progress        | AUTO |
| Direct interactive collaboration | PAIR |

## Run AUTO

`n` → set AUTO → `a` (start) or `o` (open Task Output) → dedicated Task Output screen in split view with the same `Ctrl+O` chat overlay in the lower pane (live stream) → REVIEW → approve/merge.

Agent runs in the background. Use implementation session follow-ups plus `a`/`s`
to steer iterations, then review output in REVIEW.

## Run PAIR

`n` → set PAIR → `o` → work in tmux / Neovim / VS Code / Cursor / Windsurf / Kiro / Antigravity → move through REVIEW manually.

You drive. The session is yours. Kagan tracks state and surfaces it at review time.

On the board, `Enter` opens task details.
PAIR `o` does not route to AI Assistant chat overlay. It creates/attaches the PAIR session and
redirects into the configured backend (tmux/Neovim suspend attach; VS Code/Cursor/Windsurf/Kiro/Antigravity
external handoff with startup-prompt guidance).
If focus briefly clears during board refresh, `o` reuses the last focused task; use `Escape` to
clear selection explicitly.

When `default_pair_terminal_backend = "nvim"`, Kagan opens `.kagan/start_prompt.md` and attempts
to open the first detected Neovim AI chat command:
`CodeCompanionChat` → `AvanteChat` → `CopilotChat` → `ClaudeCode`.
It also preloads startup prompt content into `g:kagan_start_prompt` (and clipboard when available).
For CopilotChat, Kagan auto-sends that prompt; for ClaudeCode, it auto-adds `.kagan/start_prompt.md`
to context.

When `default_pair_terminal_backend = "vscode"`, Kagan attempts to auto-start
`code chat --mode agent` when Copilot Chat is installed, preloading `.kagan/start_prompt.md`
as context and asking for first-step acknowledgement.

## Switch mode

`v` (details) → `e` (edit) → change `task_type` → ++ctrl+s++ save.

______________________________________________________________________

## Acceptance criteria gate

When a task has acceptance criteria defined, Kagan checks coverage when the agent completes.
If any criteria appear unaddressed in the agent's run notes, a warning is appended to the
task scratchpad before the task enters REVIEW:

```
[CRITERIA REVIEW NOTE] The following acceptance criteria may need verification:
  1. All API endpoints return 4xx on invalid input
  2. Migration is reversible
Please confirm these are addressed before approving.
```

This is a **soft gate** — the transition to REVIEW always proceeds. The warning is informational,
surfaced at review time. It never blocks an agent mid-run.

Set criteria when creating or editing a task (`v` → `e` → Acceptance Criteria field).

______________________________________________________________________

## Resume Context panel

When you reopen an `IN_PROGRESS` or `REVIEW` task, the last 500 characters of its scratchpad
notes appear at the top of the task detail view — before description, before criteria.

This is the one screen you read after an interruption. No hunting through tabs or logs.

If the task has no notes yet, the panel shows `(No notes yet)` and stays out of the way.

______________________________________________________________________

## Review Summary panel

When a task enters REVIEW, the Task Output screen surfaces the same structured context:

- Task title, status, priority on one line
- Acceptance criteria as a checklist (`□ criterion text`)
- Diff stats once loaded (`N files changed, +X −Y`)

Reviewers read one screen instead of raw `git diff`, with the AI Assistant chat overlay available.

______________________________________________________________________

## Recording agent decisions

During AUTO runs, agents can append structured reasoning notes mid-task via `task_annotate`:

```
task_annotate(task_id="abc123", note="Chose approach B over A — A required a schema migration.")
```

Each call appends a timestamped entry. Notes accumulate in the scratchpad and appear in the
Resume Context panel when you reopen the task. They also inform the acceptance criteria coverage
check when the run completes.

______________________________________________________________________

## Config

```toml
[general]
default_worker_agent = "claude"
default_pair_terminal_backend = "tmux"
max_concurrent_agents = 3
```

[Configuration](../reference/configuration.md) · [Troubleshooting](../troubleshooting.md) · [MCP tools](../reference/mcp-tools.md)
