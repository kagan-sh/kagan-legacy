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

Pick one surface and ignore the others for now:

- `kagan` - keyboard-first TUI
- `kagan web` - browser dashboard
- VS Code extension - native editor experience
- `kagan mcp` - MCP clients like Claude Code, Cursor, or OpenCode

```bash
cd your-project-directory
kagan
```

On a fresh install with no projects yet, bare `kagan` shows a one-time surface picker so you can choose TUI, web, chat, VS Code, Open VSX, or MCP setup. Runtime picks (`TUI`, `web`, `chat`) become the default for future bare `kagan` launches until you change them in settings.

Welcome screen -> open/create project -> board appears (BACKLOG -> IN_PROGRESS -> REVIEW -> DONE).

## Optional: use VS Code

If you want Kagan inside your editor, install the VS Code extension from the [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode) or [Open VSX](https://open-vsx.org/extension/kagan/kagan-vscode).

If you install the extension, you do **not** need `.vscode/mcp.json` just to use the Kagan sidebar or `@kagan` chat.

Full guide: [VS Code extension](guides/vscode-extension.md)

## 3. Create a task

`n` -> title + description -> `Ctrl+S` save. Task appears in BACKLOG.

## 4. Run it

- **Run in background:** Select task -> `s` to start. Use `Shift+S` to stop.
- **Open in editor or terminal:** Select task -> `a` to launch in your configured backend.

[Managed runs and interactive attach](guides/managed-vs-interactive.md)

## 5. Review and merge

Move to REVIEW -> `Enter` -> approve (`a`) / reject (`x`) -> merge (`m`).

## Optional: import existing GitHub issues

Use Quick Actions (`Ctrl+Shift+P`) and run `github import`, or use:

```bash
kagan import github --repo owner/repo
```

## Shortcuts

`?` Help · `Ctrl+Shift+P` Quick Actions · `Ctrl+O` Projects · `Ctrl+R` Repositories · `Ctrl+,` Settings · `Ctrl+I` AI Panel · `Space` Chat split · `w` Workspace (TUI) · `Cmd/Ctrl+Shift+W` Workspace (web)

Press `?` from any screen to open context-aware help. Rare actions (repo sync, GitHub import, AI review) live in Quick Actions.

## AI Panel

`Ctrl+I` toggles the AI Panel. `Space` cycles split layout while open. Press `Esc` to close and `Ctrl+F` to fullscreen it. Or use the standalone REPL:

```bash
kagan chat
```

Type `/help` for slash commands, `/sessions` to manage conversations.

[Chat guide](guides/chat.md) · [ACP session lifecycle](guides/acp-session-lifecycle.md)

## TUI navigation

In the TUI board, `Enter` is two-step: the first press opens the inspector for the selected card, and the second press opens the full task screen.

Press `w` to switch from the board to the TUI **Workspace** screen. That view is orchestrator-first: the left sidebar lists orchestrator conversations, `n` starts a new session, `/` filters sessions, `x` deletes the selected session, and `Ctrl+I` jumps focus into the chat input. `Esc` steps back cleanly: from chat to the sidebar, then from the sidebar back to Kanban.

## Workspace view

Kagan now has orchestrator-first workspace views in both clients:

- **TUI:** press `w` from the board to switch into Workspace. Press `w` to return directly, or use `Esc` to step back from search/chat to the sidebar and then back to Kanban.
- **Web:** click the Workspace icon in the activity bar or press `Cmd/Ctrl+Shift+W`.

In both clients, the conversation itself is the workspace: you navigate between orchestrator sessions, continue planning in-thread, and treat tasks as outputs of that conversation rather than as separate sidebar chat tabs.

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
