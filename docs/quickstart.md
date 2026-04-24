---
title: Quickstart
description: Install Kagan and complete your first task — including the review gate — in under 5 minutes
icon: material/timer
---

# Quickstart

Install. Launch. Run a task. Review and merge. That's the whole flow.

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/getting-started/installation/), `git`, a local repo, and at least one supported agent installed (Claude Code, Codex, or Gemini CLI are good starting points — see [supported agents](concepts/architecture-overview.md#supported-agents)).

## 1. Install

```bash
uv tool install kagan
kagan --version
```

No `uv`? `curl -LsSf https://astral.sh/uv/install.sh | sh`

## 2. Launch

```bash
cd your-project-directory
kagan
```

First run shows a welcome screen. Open or create a project from the current directory. The board appears: BACKLOG → IN_PROGRESS → REVIEW → DONE.

## 3. Create and run a task

Press `n` to create a task. Give it a title and description — include acceptance criteria if you want AI-assisted review. Press `Ctrl+S` to save. The task appears in BACKLOG.

Select the task, press `s` to start a managed run. The agent launches in the background in an isolated git worktree. Your working copy stays untouched. Watch output in the task detail panel (`Enter`).

When the agent finishes, the card moves to REVIEW automatically.

## 4. Review and merge

This is the gate. Open the REVIEW card with `Enter`. You see:

- Diff summary (files changed, lines added/removed)
- Acceptance criteria checklist (if you set them)
- Agent reasoning notes from the run

Press `a` to approve. Press `m` to merge. The worktree branch merges into your base branch. The task moves to DONE.

```
REVIEW → DONE requires your explicit merge. The state machine does not skip this step.
```

That's it. The agent ran in isolation, you reviewed the diff, you approved, the merge fired.

## Shortcuts

`?` Help · `n` New task · `s` Start run · `Enter` Open task · `a` Approve · `m` Merge · `Ctrl+Shift+P` Quick Actions · `Ctrl+,` Settings

## When things break

```bash
kagan doctor
```

Reports which agents are installed and whether the environment is healthy. [Troubleshooting](troubleshooting.md)
