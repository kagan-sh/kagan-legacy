<div align="center">
  <a href="https://github.com/kagan-sh/kagan"><img src="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg" width="60%" alt="Kagan" /></a>
  <p>AI-powered Kanban board for orchestrating coding agents on your codebase</p>

  <a href="https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode"><img src="https://img.shields.io/visual-studio-marketplace/v/kagan.kagan-vscode?label=Marketplace&color=0a0a0a&style=flat" alt="VS Marketplace" /></a>
  <a href="https://open-vsx.org/extension/kagan/kagan-vscode"><img src="https://img.shields.io/open-vsx/v/kagan/kagan-vscode?label=Open%20VSX&color=0a0a0a&style=flat" alt="Open VSX" /></a>
  <a href="https://github.com/kagan-sh/kagan"><img src="https://img.shields.io/github/stars/kagan-sh/kagan?color=0a0a0a&style=flat" alt="Stars" /></a>
</div>

---

Manage tasks, stream live agent output, review diffs, and merge -- all through native VS Code APIs. Works with 14 agent backends including Claude Code, Cursor, Windsurf, and more.

## Features

| Feature | VS Code Surface | How to access |
|---------|----------------|---------------|
| Orchestrator chat | Chat Participant | `@kagan <message>` in Chat panel |
| Watch task output | Chat Participant | `@kagan /watch` or click chat icon on task |
| Board status | Chat Participant | `@kagan /status` |
| Kanban board | Sidebar TreeView | Click the Kagan icon in the Activity Bar |
| Task diffs | SCM diff editor | Right-click task > View Diff |
| Review verdicts | Comments panel | Open a task in Review status |
| Agent terminal | Terminal | Right-click running task > Attach Terminal |
| Diagnostic log | Output Channel | Command: Show Agent Output |

## Quick Start

1. Install the extension from the Marketplace or Open VSX.
2. The extension auto-connects to `localhost:8765` and auto-starts the server if needed.
3. Open the Chat panel and type `@kagan` to start.

> **Tip:** Install Kagan with `pip install kagan` or `uv tool install kagan`, then run `kagan serve` to start the API server.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `kagan.serverUrl` | `localhost:8765` | Server host:port |
| `kagan.protocol` | `http` | Connection protocol (http/https) |
| `kagan.authToken` | | Bearer token for authentication |
| `kagan.autoConnect` | `true` | Connect on activation |
| `kagan.autoStartServer` | `true` | Auto-start local server |
| `kagan.serverCommand` | `kagan` | CLI command for auto-start |
| `kagan.autoWatchOnAttach` | `true` | Auto-stream output on IDE attach |

## Requirements

- [Kagan](https://github.com/kagan-sh/kagan) server running locally or remotely
- VS Code 1.96.0+

## Links

- [Documentation](https://kagan.sh)
- [GitHub](https://github.com/kagan-sh/kagan)
- [Issues](https://github.com/kagan-sh/kagan/issues)
