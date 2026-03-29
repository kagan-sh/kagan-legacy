<div align="center">
  <img src="https://raw.githubusercontent.com/kagan-sh/kagan/main/packages/vscode/media/kagan-icon.png" width="128" alt="Kagan" />
  <h1>Kagan for VS Code</h1>
  <p>AI-powered Kanban board for orchestrating coding agents on your codebase</p>

<a href="https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode"><img src="https://img.shields.io/visual-studio-marketplace/v/kagan.kagan-vscode?label=Marketplace&color=0a0a0a&style=flat" alt="VS Marketplace" /></a>
<a href="https://open-vsx.org/extension/kagan/kagan-vscode"><img src="https://img.shields.io/open-vsx/v/kagan/kagan-vscode?label=Open%20VSX&color=0a0a0a&style=flat" alt="Open VSX" /></a>
<a href="https://github.com/kagan-sh/kagan"><img src="https://img.shields.io/github/stars/kagan-sh/kagan?color=0a0a0a&style=flat" alt="Stars" /></a>

</div>

______________________________________________________________________

Manage tasks, stream live agent output, send follow-ups to a watched task, review diffs, and merge -- all through native VS Code APIs. Works with 14 agent backends including Claude Code, Cursor, Windsurf, and more.

## Features

| Feature           | VS Code Surface  | How to access                              |
| ----------------- | ---------------- | ------------------------------------------ |
| Orchestrator chat | Chat Participant | `@kagan <message>` in Chat panel           |
| Watch task output | Chat Participant | `@kagan /watch` or click chat icon on task |
| Board status      | Chat Participant | `@kagan /status`                           |
| Kanban board      | Sidebar TreeView | Click the Kagan icon in the Activity Bar   |
| Task diffs        | SCM diff editor  | Right-click task > View Diff               |
| Review verdicts   | Comments panel   | Open a task in Review status               |
| Agent terminal    | Terminal         | Right-click running task > Attach Terminal |
| Diagnostic log    | Output Channel   | Command: Show Agent Output                 |
| Settings commands | Command Palette  | Cmd/Ctrl+Shift+P → type "Kagan"            |

## Install

### Visual Studio Marketplace

- Browser: <https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode>

- CLI:

  ```bash
  code --install-extension kagan.kagan-vscode
  ```

### Open VSX

- Browser: <https://open-vsx.org/extension/kagan/kagan-vscode>

Use the Marketplace build for standard VS Code. Use Open VSX for VSCodium and other Open VSX-compatible editors.

## Quick start

1. Install Kagan locally:

   ```bash
   uv tool install kagan
   ```

1. Install the extension from the Marketplace or Open VSX.

1. Open a repository in VS Code.

1. Open the Chat panel and run `@kagan /status`.

1. Open the **Kagan** icon in the Activity Bar to access the board.

The extension connects to `http://localhost:8765` by default and auto-starts `kagan serve` when `kagan` is available on your `PATH`.

> **Important:** You do not need a `.vscode/mcp.json` file just to use the Kagan extension. MCP setup is a separate integration path for generic MCP clients.

Full docs: <https://docs.kagan.sh/guides/vscode-extension/>

## Settings

| Setting                   | Default          | Description                      |
| ------------------------- | ---------------- | -------------------------------- |
| `kagan.serverUrl`         | `localhost:8765` | Server host:port                 |
| `kagan.protocol`          | `http`           | Connection protocol (http/https) |
| `kagan.authToken`         |                  | Bearer token for authentication  |
| `kagan.autoConnect`       | `true`           | Connect on activation            |
| `kagan.autoStartServer`   | `true`           | Auto-start local server          |
| `kagan.serverCommand`     | `kagan`          | CLI command for auto-start       |
| `kagan.autoWatchOnAttach` | `true`           | Auto-stream output on IDE attach |

## Commands

Access settings commands via the Command Palette (Cmd/Ctrl+Shift+P) and type "Kagan":

| Command                     | Description                                          | When to use                                              |
| --------------------------- | ---------------------------------------------------- | -------------------------------------------------------- |
| `kagan.settings.agentBackend`   | Set the default agent backend (claude-code, codex, etc.) | Switch between agent backends without editing config files |
| `kagan.settings.reviewStrictness` | Configure review strictness level                    | Adjust how thorough code reviews should be               |
| `kagan.settings.planningDepth`  | Adjust planning depth for orchestrator sessions      | Control how deeply the orchestrator plans before execution |

## Requirements

- [Kagan](https://github.com/kagan-sh/kagan) server running locally or remotely
- VS Code 1.96.0+

## Links

- [Documentation](https://docs.kagan.sh/guides/vscode-extension/)
- [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode)
- [Open VSX](https://open-vsx.org/extension/kagan/kagan-vscode)
- [GitHub](https://github.com/kagan-sh/kagan)
- [Issues](https://github.com/kagan-sh/kagan/issues)
