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
kagan --version
```

## 2. Launch

```bash
cd your-project-directory
kagan
```

Welcome screen -> open/create project -> board appears (BACKLOG -> IN_PROGRESS -> REVIEW -> DONE).

## 3. Create a task

`n` -> title + description -> AUTO or PAIR -> `Ctrl+S` save. Task appears in BACKLOG.

## 4. Run it

- **AUTO:** Select task -> `s` (or `Enter` when focused) to start. Use `Shift+S` to stop.
- **PAIR:** Select task -> `Enter` -> continue in your configured PAIR backend.

[AUTO vs PAIR](guides/modes-auto-vs-pair.md)

## 5. Review and merge

Move to REVIEW -> `Enter` -> approve (`a`) / reject (`x`) -> merge (`m`).

## Optional: import existing GitHub issues

Use Command Palette (`Ctrl+P`) and run `github import`, or use:

```bash
kagan import github --repo owner/repo
```

## Shortcuts

`?` Help · `Ctrl+P` Command Palette · `Ctrl+O` Projects · `Ctrl+R` Repositories · `Ctrl+,` Settings · `Ctrl+T` Chat

Press `?` from any screen to open context-aware help. Rare actions (repo sync, GitHub import, AI review) live in the command palette.

## Chat

`Ctrl+T` toggles the AI chat overlay on any screen. Or use the standalone REPL:

```bash
kagan chat
```

Type `/help` for slash commands, `/sessions` to manage conversations.

[Chat guide](guides/chat.md) · [ACP session lifecycle](guides/acp-session-lifecycle.md)

## When things break

Startup runs doctor checks silently. If a critical blocker is found, Kagan prints the report and exits.

```bash
kagan doctor
```

[Troubleshooting](troubleshooting.md)
