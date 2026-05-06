---
title: Web Dashboard
description: Board view, workspace view, and settings in the browser
icon: material/monitor-dashboard
---

# Web Dashboard

The web dashboard is a React SPA bundled into the `kagan web` command. It is the browser companion surface for the same task lifecycle that the TUI drives locally.

```bash
kagan web                    # localhost only
kagan web --host 0.0.0.0    # LAN access
```

## Activity bar

The left-edge activity bar has four icons:

| Icon      | Route        | Purpose                               |
| --------- | ------------ | ------------------------------------- |
| Board     | `/board`     | Kanban board with drag-and-drop       |
| Workspace | `/workspace` | Orchestrator-first conversation view  |
| Analytics | `/analytics` | Agent performance and session metrics |
| Settings  | `/settings`  | Categorized settings with sidebar     |

Toggle between Board and Workspace with `Cmd/Ctrl+Shift+W`.

## Board view

Four-lane kanban: BACKLOG, IN_PROGRESS, REVIEW, DONE. This is the main operator view in the browser. Drag cards between lanes, click to inspect, double-click to open the full task detail page. The right rail hosts an AI panel (toggle with `Cmd/Ctrl+.`) for orchestrator or task-scoped chat.

The header repository selector never stays empty when repositories are available. If the active project has repos, Kagan selects the active repo or the first available repo; if the project has no repos yet, the Add Repository dialog opens as the next required setup step.

**Import from GitHub** auto-fills the repository field from the active git remote when possible. The repo detection is independent from the GitHub CLI readiness check, so the field can still prefill while Kagan prompts you to install or authenticate `gh`.

## Workspace view

A conversation-first companion to the board, modeled after ChatGPT / Codex Desktop.

### Layout

- **Left sidebar** (desktop): orchestrator conversation list with search, create, and delete actions.
- **Main area**: renders the selected orchestrator session full-width.
- **Mobile**: a top selector switches conversations; the bottom nav includes a dedicated Workspace tab.

### Interaction model

- A workspace conversation is the primary object in this route.
- Tasks are created and managed from the orchestrator conversation, not exposed as separate sidebar threads.
- On first visit, if no conversations exist, Kagan creates a blank orchestrator session automatically.
- The global AI rail does not open on `/workspace`; this route already is the AI surface.

## Analytics

Added in v0.18.0. The `/analytics` page surfaces multi-dimensional metrics across your agent runs, with four tabs:

| Tab              | Content                                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Backend**      | KPI cards (Total Sessions, Success Rate, Avg Duration, Retry Rate), backend performance table, duration chart, session timeline |
| **By Role**      | Per-role success rates (Worker / Orchestrator / Reviewer) and a role comparison chart                                           |
| **By Task Type** | Per-task-type success rates and a Backend x Task Type matrix                                                                    |
| **Combined**     | 3D table of Backend x Role x Task Type combinations                                                                             |

Top-of-page controls:

- **Time range dropdown**: 7 / 14 / 30 days.
- **Export**: downloads the current dataset as JSON.
- **Glossary**: help icon that explains each metric.

See [Analytics & Metrics](./analytics.md) for the full metric definitions, task-type classifier, and access across other surfaces (TUI, CLI, VS Code, MCP).

## Settings

The settings page uses a left sidebar for category navigation. See [Configuration reference -- Web dashboard settings](../reference/configuration.md#web-dashboard-settings) for the full category list.

Changes save immediately for toggles and dropdowns. Text fields save on blur or when you click the Save button.

## Keyboard shortcuts

| Key                | Action                                          |
| ------------------ | ----------------------------------------------- |
| `Cmd/Ctrl+Shift+W` | Toggle Board / Workspace                        |
| `Cmd/Ctrl+Shift+P` | Quick Actions                                   |
| `Cmd/Ctrl+.`       | Cycle AI panel on Board / Task routes           |
| `Cmd/Ctrl+Shift+F` | Toggle AI panel fullscreen off-workspace        |
| `Cmd/Ctrl+K`       | Session switcher                                |
| `?` / `F1`         | Help overlay                                    |
| `Esc`              | Close AI panel off-workspace or dismiss overlay |

Full list: [Keybindings reference](../reference/keybindings.md#web-dashboard)

## Server folder label

The Settings page shows a "Server folder" field. This is the working directory where `kagan web` was launched — not a folder you configure. It tells you which project root the server is serving. If it shows the wrong directory, stop the server and restart it from the correct project root.

## Real-time sync

The dashboard maintains a Server-Sent Events connection to the Kagan server. Task updates from the TUI, CLI, or MCP agents appear within seconds. If the connection drops, the dashboard falls back to HTTP polling every 10 seconds and reconnects automatically.
