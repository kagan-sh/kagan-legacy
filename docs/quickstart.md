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

`n` -> title + description -> `Ctrl+S` save. Task appears in BACKLOG.

## 4. Run it

- **Managed run:** Select task -> `s` to start. Use `Shift+S` to stop.
- **Interactive launch:** Select task -> `a` to launch in your configured backend.

[Managed runs and interactive attach](guides/managed-vs-interactive.md)

## 5. Review and merge

Move to REVIEW -> `Enter` -> approve (`a`) / reject (`x`) -> merge (`m`).

## Optional: import existing GitHub issues

Use Quick Actions (`Ctrl+Shift+P`) and run `github import`, or use:

```bash
kagan import github --repo owner/repo
```

## Shortcuts

`?` Help · `Ctrl+Shift+P` Quick Actions · `Ctrl+O` Projects · `Ctrl+R` Repositories · `Ctrl+,` Settings · `Ctrl+I` AI Panel · `Space` Chat split

Press `?` from any screen to open context-aware help. Rare actions (repo sync, GitHub import, AI review) live in Quick Actions.

## AI Panel

`Ctrl+I` toggles the AI Panel. `Space` cycles split layout while open. Press `Esc` to close and `Ctrl+F` to fullscreen it. Or use the standalone REPL:

```bash
kagan chat
```

Type `/help` for slash commands, `/sessions` to manage conversations.

[Chat guide](guides/chat.md) · [ACP session lifecycle](guides/acp-session-lifecycle.md)

## Remote access

Open the web dashboard from any browser:

```bash
kagan web --host 0.0.0.0
```

Open the URL shown in the terminal on any device on your network. The bundled dashboard is served directly by `kagan web`; it does not pair to a separate `kagan serve` instance. [Remote access guide](guides/remote-access.md)

## When things break

Startup runs doctor checks silently. If a critical blocker is found, Kagan prints the report and exits.

```bash
kagan doctor
```

[Troubleshooting](troubleshooting.md)
