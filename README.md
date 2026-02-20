<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/assets/logo-light.svg">
    <img alt="Kagan" src=".github/assets/logo-light.svg" width="480">
  </picture>
</p>

<p align="center">
  <strong>A terminal task board that runs AI agents on your code — you review, you decide, you merge.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/kagan/"><img src="https://img.shields.io/pypi/v/kagan?style=for-the-badge" alt="PyPI"></a>
  <a href="https://pypi.org/project/kagan/"><img src="https://img.shields.io/pypi/pyversions/kagan?style=for-the-badge" alt="Python"></a>
  <a href="https://opensource.org/license/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/aorumbayev/kagan/stargazers"><img src="https://img.shields.io/github/stars/aorumbayev/kagan?style=for-the-badge" alt="Stars"></a>
  <a href="https://discord.gg/dB5AgMwWMy"><img src="https://img.shields.io/badge/discord-join-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
</p>

<p align="center">
  <a href="https://snyk.io/test/github/kagan-sh/kagan?targetFile=pyproject.toml"><img src="https://snyk.io/test/github/kagan-sh/kagan/badge.svg?targetFile=pyproject.toml&style=flat" alt="Snyk"></a>
</p>

<p align="center">
  <a href="https://docs.kagan.sh/">Documentation</a> •
  <a href="https://docs.kagan.sh/quickstart/">Quickstart</a> •
  <a href="https://docs.kagan.sh/guides/mcp-setup/">MCP Setup</a> •
  <a href="https://docs.kagan.sh/reference/cli/">CLI Reference</a> •
  <a href="https://github.com/aorumbayev/kagan/issues">Issues</a>
</p>

---

<p align="center">
  <img src=".github/assets/demo.png" alt="Kagan Demo" width="700">
</p>

Create a task. Pick a mode. The agent works. You review, approve, and merge.

## Install

=== "UV (Recommended)"

```bash
uv tool install kagan
```

=== "Mac / Linux"

```bash
curl -fsSL https://uvget.me/install.sh | bash -s -- kagan
```

=== "Windows (PowerShell)"

```powershell
iwr -useb uvget.me/install.ps1 -OutFile install.ps1; .\install.ps1 kagan
```

=== "pip"

```bash
pip install kagan
```

### Requirements

- Python 3.12 -- 3.13, Git, terminal 80x20+
- tmux (recommended for PAIR sessions on macOS/Linux)
- VS Code or Cursor (PAIR launchers, especially on Windows)

## Usage

```bash
kagan              # Launch TUI (default command)
kagan tui          # Launch TUI explicitly
kagan core status  # Show status of the core process
kagan core stop    # Stop the running core process
kagan mcp          # Run as MCP server (connects to core via IPC)
kagan tools        # Stateless developer utilities (prompt enhancement)
kagan update       # Check for and install updates
kagan list         # List all projects with task counts
kagan reset        # Reset data (interactive)
kagan --help       # Show all options
```

## Ways to Use Kagan

### TUI (interactive)

Run `kagan` -- create tasks, run AUTO/PAIR workflows, review/rebase/merge, switch projects.

### Editor (MCP)

Operate Kagan from Claude Code, Gemini CLI, or any MCP-compatible client -- no TUI required:

```bash
kagan mcp --capability pair_worker
```

Start with `pair_worker`. Escalate to `maintainer` when needed. See [MCP setup](https://docs.kagan.sh/guides/mcp-setup/) for editor configs.

## Features

- Kanban lifecycle: `BACKLOG -> IN_PROGRESS -> REVIEW -> DONE`
- Task CRUD, duplicate, inspect
- Work modes: `AUTO` (background agent) / `PAIR` (interactive session)
- Chat-driven planning with approval flow
- Review: diff, approve/reject/rebase/merge
- Multi-repo: project switching, base-branch controls
- PAIR handoff: tmux / VS Code / Cursor session management
- MCP: 23 tools spanning tasks, sessions, review, planning, projects, audit, settings
- Core daemon management: run, inspect, stop

## Supported Agents

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic)
- [OpenCode](https://opencode.ai/docs) (SST)
- [Codex](https://github.com/openai/codex) (OpenAI)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (Google)
- [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) (Moonshot AI)
- [GitHub Copilot](https://github.com/github/copilot-cli) (GitHub)

## Docs

**[docs.kagan.sh](https://docs.kagan.sh/)** -- [Quickstart](https://docs.kagan.sh/quickstart/) | [MCP Setup](https://docs.kagan.sh/guides/mcp-setup/) | [Editor MCP Setup](https://docs.kagan.sh/guides/editor-mcp-setup/)

## License

[MIT](LICENSE)

---

<p align="center">
  <a href="https://www.star-history.com/#aorumbayev/kagan&type=date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=aorumbayev/kagan&type=date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=aorumbayev/kagan&type=date" />
      <img alt="Star History" src="https://api.star-history.com/svg?repos=aorumbayev/kagan&type=date" width="600" />
    </picture>
  </a>
</p>
