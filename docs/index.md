---
title: Kagan Docs — AI Agent Orchestration
description: 'Documentation for Kagan: orchestrate AI coding agents with a terminal Kanban board, MCP server, and CLI.'
hide:
  - navigation
  - toc
---

# Your agents work. You decide.

14+ AI agents. One board. Every task tracked from backlog to merge -- while you keep your hands on the wheel.

Kagan is a keyboard-first Kanban TUI that orchestrates coding agents across the full task lifecycle. Plan. Run. Review. Merge. No context lost between steps, no state scattered across terminals.

```bash
uvx kagan
```

<div class="collection-cards" markdown>

- [:material-lightning-bolt: **60-second start**](quickstart.md)

- [:material-robot: **Managed runs and interactive attach**](guides/managed-vs-interactive.md)

- [:material-server-network: **Run from your editor**](guides/mcp-setup.md)

- [:material-microsoft-visual-studio-code: **VS Code extension**](guides/vscode-extension.md)

- [:material-source-branch: **Review before merge**](concepts/task-lifecycle.md)

- [:material-chat: **Chat orchestrator**](guides/chat.md)

- :material-monitor-dashboard:{ .lg .middle } **Web dashboard**

  Manage your board from a browser — locally or remotely from any device on your network.

  [:octicons-arrow-right-24: Web dashboard](guides/web-dashboard.md)  ·  [:octicons-arrow-right-24: Remote access](guides/remote-access.md)

</div>

______________________________________________________________________

## Supported agents

Kagan works with the agents you already use. Bring one or bring all — they share the same board, the same state, the same review gate.

**Claude Code** · **OpenCode** · **Codex** · **Gemini CLI** · **Kimi CLI** · **GitHub Copilot** · **Goose** · **OpenHands** · **Auggie** · **Amp** · **Docker cagent** · **Stakpak** · **Mistral Vibe** · **VT Code**

Set `default_worker_agent` in config or pick per task. Kagan detects what's installed automatically.

[:octicons-arrow-right-24: Full agent list with install commands](concepts/architecture-overview.md#supported-agents)

______________________________________________________________________

## Interactive launchers

Interactive sessions open in the tool you already live in: **tmux** · **Neovim** · **VS Code** · **Cursor** · **Windsurf** · **Kiro** · **Antigravity**

[:octicons-arrow-right-24: Backend details](concepts/architecture-overview.md#interactive-launchers)

______________________________________________________________________

## MCP clients

Any editor or tool that speaks MCP can drive Kagan without the TUI. Tested configs ship for:

**Claude Code** -- **VS Code** -- **Cursor** -- **OpenCode** -- **Codex** -- **Gemini CLI** -- **Kimi CLI** -- **GitHub Copilot** -- **Goose** -- **Amp** -- **Auggie**

[:octicons-arrow-right-24: Full MCP setup](guides/mcp-setup.md)

______________________________________________________________________

## Find what you need

| Goal                             | Page                                                       |
| -------------------------------- | ---------------------------------------------------------- |
| First run in under 5 minutes     | [Quickstart](quickstart.md)                                |
| Install the VS Code extension    | [VS Code extension](guides/vscode-extension.md)            |
| Understand the task flow         | [Task lifecycle](concepts/task-lifecycle.md)               |
| Understand start vs attach       | [Managed vs interactive](guides/managed-vs-interactive.md) |
| Use chat REPL or TUI overlay     | [Chat guide](guides/chat.md)                               |
| Understand ACP chat sessions     | [ACP session lifecycle](guides/acp-session-lifecycle.md)   |
| Connect an AI client via MCP     | [MCP setup](guides/mcp-setup.md)                           |
| Work across multiple repos       | [MCP setup — Multi-repo](guides/mcp-setup.md#multi-repo)   |
| Import tasks from GitHub         | [Import from GitHub](guides/github.md)                     |
| Extend with plugins              | [Plugins](reference/plugins.md) (early stage)              |
| Use the web dashboard            | [Web dashboard](guides/web-dashboard.md)                   |
| Control board from any device    | [Remote access](guides/remote-access.md)                   |
| Fix a known issue                | [Troubleshooting](troubleshooting.md)                      |
| All CLI flags                    | [CLI reference](reference/cli.md)                          |
| All MCP tools                    | [MCP tools reference](reference/mcp-tools.md)              |
