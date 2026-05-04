---
title: Kagan Docs — Kanban TUI with structural human review gate
description: 'Documentation for Kagan: a Kanban TUI for AI coding agents with a structural human review gate enforced by the state machine.'
hide:
  - navigation
  - toc
---

# Your agents work. You decide.

Kagan is a Kanban TUI for AI coding agents with a structural human review gate. No agent-authored task reaches your main branch without an explicit approval — the state machine enforces it.

The agent runs in an isolated git worktree. When it finishes, the task card moves to REVIEW. You read the diff, check the acceptance criteria, press approve. Then merge fires. REVIEW → DONE cannot be automated away. It is not a setting.

```bash
uvx kagan
```

<div class="collection-cards" markdown>

- [:material-source-branch: **The review gate**](concepts/task-lifecycle.md)

- [:material-lightning-bolt: **60-second start**](quickstart.md)

- [:material-robot: **Managed runs and interactive attach**](guides/managed-vs-interactive.md)

- [:material-server-network: **Run from your editor (MCP)**](guides/mcp-setup.md)

- [:material-chat: **Chat orchestrator**](guides/chat.md)

- [:material-chart-line: **Analytics & metrics**](guides/analytics.md)

</div>

______________________________________________________________________

## Supported agents

Tested and documented: **Claude Code** · **Codex** · **Gemini CLI**

11 more backends supported — see [`concepts/architecture-overview.md`](concepts/architecture-overview.md#supported-agents).

Set `default_agent_backend` in config or pick per task. Kagan detects what's installed automatically.

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

## Companion surfaces

The TUI is the primary operator surface. Two companions exist for specific workflows:

- **Web dashboard** (`kagan web`) — browser-based board; useful for remote access or a second monitor
- **VS Code extension** — sidebar panel and `@kagan` chat participant inside VS Code

Both share the same state as the TUI via the same API server.

______________________________________________________________________

## Find what you need

| Goal                          | Page                                                       |
| ----------------------------- | ---------------------------------------------------------- |
| First run in under 5 minutes  | [Quickstart](quickstart.md)                                |
| Understand the review gate    | [Task lifecycle](concepts/task-lifecycle.md)               |
| Understand start vs attach    | [Managed vs interactive](guides/managed-vs-interactive.md) |
| Connect an AI client via MCP  | [MCP setup](guides/mcp-setup.md)                           |
| Use chat REPL or TUI overlay  | [Chat guide](guides/chat.md)                               |
| Understand ACP chat sessions  | [ACP session lifecycle](guides/acp-session-lifecycle.md)   |
| Work across multiple repos    | [MCP setup — Multi-repo](guides/mcp-setup.md#multi-repo)   |
| Sync tasks with GitHub Issues | [GitHub integration](guides/github.md)                     |
| Use the web dashboard         | [Web dashboard](guides/web-dashboard.md)                   |
| Install the VS Code extension | [VS Code extension](guides/vscode-extension.md)            |
| View analytics & metrics      | [Analytics](guides/analytics.md)                           |
| Fix a known issue             | [Troubleshooting](troubleshooting.md)                      |
| All CLI flags                 | [CLI reference](reference/cli.md)                          |
| All MCP tools                 | [MCP tools reference](reference/mcp-tools.md)              |
