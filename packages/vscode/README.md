# Kagan VS Code Extension

Native VS Code client for Kagan. Board, agent output, diffs, reviews -- all through platform-native APIs.

## Quick Start

1. Install the extension (`.vsix` or marketplace).
1. The extension auto-connects to `http://localhost:8765` and auto-starts the server if needed.
1. Open the Chat panel (`Cmd+Shift+I`) and type `@kagan` to watch agent output.

## Features

| Feature         | VS Code Surface  | How to access                              |
| --------------- | ---------------- | ------------------------------------------ |
| Orchestrator    | Chat Participant | `Cmd+Shift+I` then `@kagan <message>`      |
| Watch task      | Chat Participant | `@kagan /watch` or chat icon on task       |
| Board status    | Chat Participant | `@kagan /status`                           |
| Kanban board    | Sidebar TreeView | Click the Kagan icon in the activity bar   |
| Task diffs      | SCM diff editor  | Right-click task > View Diff               |
| Review verdicts | Comments         | Open a task in Review status               |
| Agent terminal  | Terminal         | Right-click running task > Attach Terminal |
| Diagnostic log  | Output Channel   | Command: Show Agent Output                 |

## Connection

- **Auto-connect** on startup (disable with `kagan.autoConnect: false`).
- **Auto-start** local server when `serverUrl` is localhost and nothing is listening.
- **Status bar** shows connection state and task counts.

The extension does not auto-start remote servers.

## Settings

| Setting                   | Default                 | Description                |
| ------------------------- | ----------------------- | -------------------------- |
| `kagan.serverUrl`         | `http://localhost:8765` | Kagan server URL           |
| `kagan.autoConnect`       | `true`                  | Connect on activation      |
| `kagan.autoStartServer`   | `true`                  | Auto-start local server    |
| `kagan.serverCommand`     | `kagan`                 | CLI command for auto-start |
| `kagan.autoWatchOnAttach` | `true`                  | Auto-open Chat on attach   |

## Development

```bash
pnpm run compile        # Type-check + bundle
pnpm run watch          # Dev mode (esbuild + tsc watch)
pnpm run test:unit      # Vitest
pnpm run test:integration # Extension host tests
pnpm run test:e2e       # WDIO real VS Code
pnpm run vsix           # Package .vsix
```
