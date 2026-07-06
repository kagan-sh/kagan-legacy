<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-light.svg">
    <img alt="Kagan — Kanban TUI for AI coding agents with a structural human review gate" src="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg" width="100%">
  </picture>
</p>
<p align="center">
  <a href="https://pypi.org/project/kagan/"><img src="https://img.shields.io/pypi/v/kagan?style=for-the-badge" alt="PyPI"></a>
  <a href="https://pypi.org/project/kagan/"><img src="https://img.shields.io/pypi/pyversions/kagan?style=for-the-badge" alt="Python"></a>
  <a href="https://opensource.org/license/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/kagan-sh/kagan/stargazers"><img src="https://img.shields.io/github/stars/kagan-sh/kagan?style=for-the-badge" alt="Stars"></a>
  <a href="https://discord.gg/dB5AgMwMy"><img src="https://img.shields.io/badge/discord-join-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  <a href="https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode"><img src="https://img.shields.io/visual-studio-marketplace/v/kagan.kagan-vscode?label=VS%20Marketplace&style=flat" alt="VS Marketplace"></a>
  <a href="https://open-vsx.org/extension/kagan/kagan-vscode"><img src="https://img.shields.io/open-vsx/v/kagan/kagan-vscode?label=Open%20VSX&style=flat" alt="Open VSX"></a>
  <a href="https://snyk.io/test/github/kagan-sh/kagan?targetFile=pyproject.toml"><img src="https://snyk.io/test/github/kagan-sh/kagan/badge.svg?targetFile=pyproject.toml&style=flat" alt="Snyk"></a>
  <a href="https://glama.ai/mcp/servers/kagan-sh/kagan"><img src="https://glama.ai/mcp/servers/kagan-sh/kagan/badges/score.svg" alt="Glama"></a>
</p>

<!-- mcp-name: io.github.kagan-sh/kagan -->

<h3 align="center">
  <a href="https://docs.kagan.sh/">Docs</a> ·
  <a href="https://docs.kagan.sh/quickstart/">Quickstart</a> ·
  <a href="https://docs.kagan.sh/concepts/task-lifecycle/">The review gate</a> ·
  <a href="https://docs.kagan.sh/guides/mcp-setup/">MCP Setup</a> ·
  <a href="https://docs.kagan.sh/reference/cli/">CLI Reference</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</h3>

---

Kagan is a Kanban TUI for AI coding agents with a structural human review gate. No agent-authored task reaches your main branch without an explicit approval — the state machine enforces it.

The agent runs in an isolated git worktree. When it finishes, the task card moves to REVIEW. You read the diff, check the acceptance criteria, and press approve. Then merge fires. That transition — REVIEW to DONE — cannot be automated away. It is not a setting.

> This repository and experiemental python version of kagan harness are **DEPRECATED** see https://github.com/kagan-sh/kagan for latest iteration of the tool - now leveraging OpenCode ecosystem and available as a native OpenCode plugin.

## Install

```bash
uv tool install kagan     # or: uvx kagan
```

<details>
<summary>Mac / Linux (no uv)</summary>

```bash
curl -fsSL https://uvget.me/install.sh | bash -s -- kagan
```
</details>

<details>
<summary>Windows (PowerShell)</summary>

```powershell
iwr -useb uvget.me/install.ps1 -OutFile install.ps1; .\install.ps1 kagan
```
</details>

## What you get

- Kanban board (BACKLOG → IN_PROGRESS → REVIEW → DONE) enforced by a state machine
- Each task runs in its own git worktree — your working copy stays untouched
- Managed runs (background agent) or interactive attach (you + agent in tmux/editor)
- REVIEW stage requires explicit human approval before merge; no path around it
- MCP server so Claude Code, Codex, or any MCP-capable client can drive the board
- `kagan doctor` preflight checks all required tools before first run

Tested agents: **Claude Code** · **Codex** · **Gemini CLI** · 11 more — see [docs/backends](https://docs.kagan.sh/concepts/architecture-overview/#supported-agents).

Full docs: **[docs.kagan.sh](https://docs.kagan.sh/)**

## Companion surfaces

The TUI (`kagan`) is the primary operator surface. Two companion surfaces exist for specific workflows:

- **Web dashboard** (`kagan web`) — browser-based board, useful for remote access or a second monitor
- **VS Code extension** — sidebar panel and `@kagan` chat participant inside VS Code

Both companions share the same state as the TUI via the same API server. Neither is required.

## License

[MIT](LICENSE)

---

<p align="center">
  <a href="https://www.star-history.com/#kagan-sh/kagan&type=date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=kagan-sh/kagan&type=date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=kagan-sh/kagan&type=date" />
      <img alt="Star History" src="https://api.star-history.com/svg?repos=kagan-sh/kagan&type=date" width="600" />
    </picture>
  </a>
</p>
