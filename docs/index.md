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

  [:octicons-arrow-right-24: Architecture](concepts/architecture-overview.md)

</div>

______________________________________________________________________

## Supported agents

Kagan works with the agents you already use. Bring one or bring all -- they share the same board, the same state, the same review gate.

| Agent              | Author       | Description                                 |
| ------------------ | ------------ | ------------------------------------------- |
| **Claude Code**    | Anthropic    | Agentic coding from the terminal            |
| **OpenCode**       | SST          | Multi-model CLI with TUI                    |
| **Codex**          | OpenAI       | OpenAI CLI coding agent                     |
| **Gemini CLI**     | Google       | Google Gemini CLI agent                     |
| **Kimi CLI**       | Moonshot AI  | Kimi CLI coding agent                       |
| **GitHub Copilot** | GitHub       | GitHub Copilot CLI agent                    |
| **Goose**          | Block        | Open-source, extensible AI agent            |
| **OpenHands**      | OpenHands    | Cloud coding agent platform                 |
| **Auggie**         | Augment Code | Terminal and editor AI agent                |
| **Amp**            | Sourcegraph  | Frontier coding agent for the terminal      |
| **Docker cagent**  | Docker       | Agent builder and runtime with MCP/ACP      |
| **Stakpak**        | Stakpak      | Terminal-native DevOps agent                |
| **Mistral Vibe**   | Mistral      | Open-source CLI backed by Devstral          |
| **VT Code**        | Vinh Nguyen  | Rust-based agent with semantic intelligence |

Set `default_worker_agent` in config or pick per task. Kagan detects what's installed and falls through the priority list automatically.

______________________________________________________________________

## PAIR backends

Interactive sessions open in the tool you already live in.

| Backend       | Editor / Terminal                            |
| ------------- | -------------------------------------------- |
| `tmux`        | Terminal multiplexer (default on Unix/macOS) |
| `nvim`        | Neovim with AI chat plugin support           |
| `vscode`      | Visual Studio Code                           |
| `cursor`      | Cursor                                       |
| `windsurf`    | Windsurf                                     |
| `kiro`        | Kiro                                         |
| `antigravity` | Antigravity                                  |

______________________________________________________________________

## MCP clients

Any editor or tool that speaks MCP can drive Kagan without the TUI. Tested configs ship for:

**Claude Code** -- **VS Code** -- **Cursor** -- **OpenCode** -- **Codex** -- **Gemini CLI** -- **Kimi CLI** -- **GitHub Copilot** -- **Goose** -- **Amp** -- **Auggie**

[:octicons-arrow-right-24: Full MCP setup](guides/mcp-setup.md)

______________________________________________________________________

## Find what you need

| Goal                          | Page                                                     |
| ----------------------------- | -------------------------------------------------------- |
| First run in under 5 minutes  | [Quickstart](quickstart.md)                              |
| Understand AUTO vs PAIR       | [AUTO vs PAIR](guides/modes-auto-vs-pair.md)             |
| Connect an AI client via MCP  | [MCP setup](guides/mcp-setup.md)                         |
| Work across multiple repos    | [MCP setup - Multi-repo](guides/mcp-setup.md#multi-repo) |
| Connect GitHub issues and PRs | [GitHub plugin](guides/github.md)                        |
| Fix a known issue             | [Troubleshooting](troubleshooting.md)                    |
| All CLI flags                 | [CLI reference](reference/cli.md)                        |
| All MCP tools                 | [MCP tools reference](reference/mcp-tools.md)            |
