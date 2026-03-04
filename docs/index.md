---
title: Kagan
description: AI-powered Kanban TUI for autonomous development workflows
hide:
  - navigation
  - toc
---

# Your agents work. You decide.

Fourteen AI agents. One board. Every task tracked from backlog to merge -- while you keep your hands on the wheel.

Kagan is a keyboard-first Kanban TUI that orchestrates coding agents across the full task lifecycle. Plan. Run. Review. Merge. No context lost between steps, no state scattered across terminals.

```bash
uvx kagan
```

<div class="grid cards" markdown>

- :material-lightning-bolt:{ .lg .middle } **60-second start**

  ______________________________________________________________________

  One command. Any repo. Board up, first task running.

  [:octicons-arrow-right-24: Quickstart](quickstart.md)

- :material-robot:{ .lg .middle } **AUTO vs PAIR**

  ______________________________________________________________________

  Background agents or interactive sessions. Switch per task, not per project.

  [:octicons-arrow-right-24: Choose your mode](guides/modes-auto-vs-pair.md)

- :material-server-network:{ .lg .middle } **Run from your editor**

  ______________________________________________________________________

  Claude Code, VS Code, Cursor, Gemini CLI, or any MCP client. The TUI is optional.

  [:octicons-arrow-right-24: MCP setup](guides/mcp-setup.md)

- :material-source-branch:{ .lg .middle } **Review before merge**

  ______________________________________________________________________

  Structured review: diff summary, acceptance criteria checklist, your call.

  [:octicons-arrow-right-24: Task lifecycle](concepts/task-lifecycle.md)

</div>

______________________________________________________________________

## Supported agents

Kagan works with the agents you already use. Bring one or bring all — they share the same board, the same state, the same review gate.

**Claude Code** · **OpenCode** · **Codex** · **Gemini CLI** · **Kimi CLI** · **GitHub Copilot** · **Goose** · **OpenHands** · **Auggie** · **Amp** · **Docker cagent** · **Stakpak** · **Mistral Vibe** · **VT Code**

Set `default_worker_agent` in config or pick per task. Kagan detects what's installed automatically.

[:octicons-arrow-right-24: Full agent list with install commands](concepts/architecture-overview.md#supported-agents)

______________________________________________________________________

## PAIR backends

Interactive sessions open in the tool you already live in: **tmux** · **Neovim** · **VS Code** · **Cursor** · **Windsurf** · **Kiro** · **Antigravity**

[:octicons-arrow-right-24: Backend details](concepts/architecture-overview.md#pair-backends)

______________________________________________________________________

## MCP clients

Any editor or tool that speaks MCP can drive Kagan without the TUI. Tested configs ship for:

**Claude Code** -- **VS Code** -- **Cursor** -- **OpenCode** -- **Codex** -- **Gemini CLI** -- **Kimi CLI** -- **GitHub Copilot** -- **Goose** -- **Amp** -- **Auggie**

[:octicons-arrow-right-24: Full MCP setup](guides/mcp-setup.md)

______________________________________________________________________

## Find what you need

| Goal                         | Page                                                     |
| ---------------------------- | -------------------------------------------------------- |
| First run in under 5 minutes | [Quickstart](quickstart.md)                              |
| Understand the task flow     | [Task lifecycle](concepts/task-lifecycle.md)             |
| Understand AUTO vs PAIR      | [AUTO vs PAIR](guides/modes-auto-vs-pair.md)             |
| Understand ACP chat sessions | [ACP session lifecycle](guides/acp-session-lifecycle.md) |
| Connect an AI client via MCP | [MCP setup](guides/mcp-setup.md)                         |
| Work across multiple repos   | [MCP setup — Multi-repo](guides/mcp-setup.md#multi-repo) |
| Import tasks from GitHub     | [Import from GitHub](guides/github.md)                   |
| Fix a known issue            | [Troubleshooting](troubleshooting.md)                    |
| All CLI flags                | [CLI reference](reference/cli.md)                        |
| All MCP tools                | [MCP tools reference](reference/mcp-tools.md)            |
