---
title: Quickstart
description: Install Kagan and complete your first task in under 5 minutes
icon: material/timer
---

# Quickstart

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/getting-started/installation/), `git`, a local repo.

## 1. Install

```bash
# Don't have uv? One line:
curl -LsSf https://astral.sh/uv/install.sh | sh

uv tool install kagan
kagan --version   # e.g. 0.5.0
```

## 2. Launch

```bash
cd your-project-directory
kagan
```

Welcome screen --> open/create project --> board appears (BACKLOG --> IN_PROGRESS --> REVIEW --> DONE).

## 3. Create a task

`n` → title + description → AUTO or PAIR → `Ctrl+S` save. Task appears in BACKLOG.

## 4. Run it

- **AUTO:** Select task → `a` or `Enter`.
  `Enter` opens a dedicated Task Output screen in split view: task/diff details on top, the same chat overlay UI as `Ctrl+O` in the lower half.
  `Ctrl+P` toggles fullscreen for that task overlay; `Ctrl+O` toggles docked overlay for that task.
  Use follow-up chat plus `a` (start) and `s` (stop) to steer iterations.
- **PAIR:** Select task → `Enter` → work in tmux/Neovim/VS Code/Cursor.

PAIR launch does not open the orchestrator chat overlay; it opens or redirects to your configured PAIR backend.

[AUTO vs PAIR](guides/modes-auto-vs-pair.md)

## 5. Review and merge

Move to REVIEW --> `Enter` (Task Output) --> approve/reject --> merge.

## Shortcuts

`?` Help · `.` Actions · `,` Settings · `F12` Debug

## When things break

Startup runs doctor checks silently. If a critical blocker is found,
Kagan prints the report and exits.

```bash
kagan doctor
```

[Troubleshooting](troubleshooting.md)
