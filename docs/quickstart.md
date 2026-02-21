---
title: Quickstart
description: Install Kagan and complete your first task in under 5 minutes
icon: material/timer
---

# Quickstart

Board up. First task running. Under five minutes.

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/getting-started/installation/), `git`, a local repo, and at least one [supported agent](concepts/architecture-overview.md#supported-agents) installed.

## 1. Install

```bash
# Don't have uv? One line:
curl -LsSf https://astral.sh/uv/install.sh | sh

uv tool install kagan
kagan --version   # e.g. 0.5.0
kg --version
```

## 2. Launch

```bash
cd your-project-directory
kagan
# or
kg
```

Welcome screen --> open/create project --> board appears (BACKLOG --> IN_PROGRESS --> REVIEW --> DONE).

## 3. Create a task

`n` → title + description → AUTO or PAIR → `Ctrl+S` save. Task appears in BACKLOG.

## 4. Run it

- **AUTO:** Select task → `a` (start) or `o` (open Task Output).
  `o` opens a dedicated Task Output screen in split view: task/diff details on top, the same chat overlay UI as `Ctrl+O` in the lower half.
  `Ctrl+P` toggles fullscreen for that task overlay; `Ctrl+O` toggles docked overlay for that task.
  Docked height behavior matches the Kanban docked overlay sizing model.
  Use follow-up chat plus `a` (start) and `s` (stop) to steer iterations.
- **PAIR:** Select task → `o` → work in your configured backend (tmux, Neovim, VS Code, Cursor, Windsurf, Kiro, or Antigravity).

From the board, `Enter` opens task details.
PAIR launch does not open the AI Assistant chat overlay; it opens or redirects to your configured PAIR backend.

[AUTO vs PAIR](guides/modes-auto-vs-pair.md)

## 5. Review and merge

Move to REVIEW --> `o` (Task Output) to inspect stats + chat context --> merge from board actions.

## Shortcuts

`?` Help · `.` Actions · `,` Settings · `F12` Debug
In Help, press `Ctrl+F` to search keybindings instantly; `Esc` clears search first, then closes.

When AI Assistant is open, the input rail is intentionally minimal: prompt and input.
Use `Ctrl+P`/`Ctrl+O` to switch fullscreen and docked layouts.
Docked mode keeps the board on the top half and chat on the bottom half; the lower panel
prioritizes output area (~80%) with the input/footer controls at the bottom.
Session switching (`Tab` / `Ctrl+K`) clears unsent input so drafts never leak between sessions.

## When things break

Startup runs doctor checks silently. If a critical blocker is found,
Kagan prints the report and exits.

```bash
kagan doctor
```

[Troubleshooting](troubleshooting.md)
