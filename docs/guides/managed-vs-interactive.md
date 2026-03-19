---
title: Managed Runs and Interactive Attach
description: Choose how to launch work without turning it into a task mode
icon: material/robot
tags:
  - runs
  - execution
---

# Managed Runs and Interactive Attach

Every task is just a task. When you launch it, choose one of two actions:

| When… | Use |
| --- | --- |
| Requirements are clear and bounded | Start a managed run |
| You want to guide the work live | Launch an interactive session |
| You want background progress and later review | Start a managed run |
| You want tmux / Neovim / editor handoff | Launch an interactive session |

## Start a managed run

`n` → create task → `s` to start → follow progress in the task or session views → REVIEW → approve/merge.

The agent runs in the background. Use follow-ups, notes, and review to steer iterations after launch.

## Launch an interactive session

`n` → create task → `a` (or the Attach button in the web UI) → continue in tmux / Neovim / VS Code / Cursor / Windsurf / Kiro / Antigravity.

Kagan prepares the worktree, writes `.kagan/start_prompt.md`, and opens or hands off to your configured launcher. The task itself does not change mode; the session just uses an interactive launcher.

When `attached_launcher = "nvim"`, Kagan opens `.kagan/start_prompt.md` and attempts to open the first detected Neovim AI chat command:
`CodeCompanionChat` → `AvanteChat` → `CopilotChat` → `ClaudeCode`.
It also preloads startup prompt content into `g:kagan_start_prompt` (and clipboard when available).

When `attached_launcher = "vscode"`, Kagan attempts to auto-start
`code chat --mode agent` when Copilot Chat is installed, preloading `.kagan/start_prompt.md`
as context and asking for first-step acknowledgement.

## Switching later

You do not edit a task to change its run style. Launch managed work with Start, or launch an interactive session with Attach when you need it.

## Acceptance criteria gate

Acceptance criteria are optional, but they control which review paths are available.

- Managed and interactive runs both work without criteria.
- AI-assisted approve and merge actions require at least one acceptance criterion.
- Tasks without criteria require explicit human review before approval or merge.

## Resume Context

Agents append reasoning notes to a task's scratchpad as they run. Task detail views include a **Resume Context** strip (IN_PROGRESS/REVIEW only) that shows the most recent notes, trimmed to the last ~500 characters. If no notes exist, it shows `(No notes yet)`.

You can still fetch the full scratchpad via `task_get(..., include_scratchpad=true)` when you need the complete history.

## Recording agent decisions

During managed runs, agents can append structured reasoning notes mid-task via `task_add_note`:

```text
task_add_note(task_id="abc123", note="Chose approach B over A — A required a schema migration.")
```

Each call appends a timestamped entry. Notes accumulate in the scratchpad and inform the acceptance criteria coverage check when the run completes.

[:octicons-arrow-right-24: Configuration reference](../reference/configuration.md) · [:octicons-arrow-right-24: Task lifecycle](../concepts/task-lifecycle.md) · [:octicons-arrow-right-24: Troubleshooting](../troubleshooting.md)
