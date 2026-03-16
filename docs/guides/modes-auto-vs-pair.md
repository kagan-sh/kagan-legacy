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

`n` → set AUTO → `s` or `Enter` → dedicated Task Output screen in split view with the same `Space` chat split cycle (`Esc` close, `Ctrl+F` fullscreen while open) in the lower pane (live stream) → REVIEW → approve/merge.

Agent runs in the background. Use implementation session follow-ups plus `s` (start) / `Shift+S` (stop)
to steer iterations, then review output in REVIEW.

## Run PAIR

`n` → set PAIR → `Enter` → work in tmux / Neovim / VS Code / Cursor / Windsurf / Kiro / Antigravity → move through REVIEW manually.

You drive. The session is yours. Kagan tracks state and surfaces it at review time.

PAIR `Enter` does not route to AI Panel. It creates/attaches the PAIR session and
redirects into the configured backend (tmux/Neovim suspend attach; VS Code/Cursor/Windsurf/Kiro/Antigravity
external handoff with startup-prompt guidance).
If focus briefly clears during board refresh, `Enter` reuses the last focused task; use `Escape` to
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

`Enter` (open task) → `e` (edit) → change `task_type` → `Ctrl+S` save.

## Orchestrator session lifecycle

If you need precise behavior for ACP session spawn/reuse/cleanup in `kagan chat` and TUI orchestrator chat, see:
[ACP session lifecycle](acp-session-lifecycle.md)

______________________________________________________________________

## Acceptance criteria gate

Acceptance criteria are optional, but they control which review paths are available.

- AUTO and PAIR execution both work without criteria.
- AI-assisted approve and merge actions require at least one acceptance criterion.
- Tasks without criteria require explicit human review before approval or merge.

Set criteria when creating or editing a task (`Enter` → `e` → Acceptance Criteria field).

______________________________________________________________________

## Resume Context panel

When you reopen an `IN_PROGRESS` or `REVIEW` task, the last 500 characters of its scratchpad
notes appear at the top of the task detail view — before description, before criteria.

This is the one screen you read after an interruption. No hunting through tabs or logs.

If the task has no notes yet, the panel shows `(No notes yet)` and stays out of the way.

______________________________________________________________________

## Review Summary panel

When a task enters REVIEW, the review modal surfaces a structured summary tab:

- Task title, status, priority on one line
- Acceptance criteria as a checklist (`□ criterion text`)
- Diff stats once loaded (`N files changed, +X −Y`)

Reviewers read one screen instead of raw `git diff`. Approve, reject, or rebase from there.

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

[:octicons-arrow-right-24: Configuration reference](../reference/configuration.md) · [:octicons-arrow-right-24: Task lifecycle](../concepts/task-lifecycle.md) · [:octicons-arrow-right-24: Troubleshooting](../troubleshooting.md)
