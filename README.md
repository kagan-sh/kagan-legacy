<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/assets/logo-light.svg">
    <img alt="Kagan" src=".github/assets/logo-light.svg" width="480">
  </picture>
</p>

<p align="center">
  <strong>AI-powered Kanban TUI for autonomous development workflows</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/kagan/"><img src="https://img.shields.io/pypi/v/kagan?style=for-the-badge" alt="PyPI"></a>
  <a href="https://pypi.org/project/kagan/"><img src="https://img.shields.io/pypi/pyversions/kagan?style=for-the-badge" alt="Python"></a>
  <a href="https://opensource.org/license/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/aorumbayev/kagan/stargazers"><img src="https://img.shields.io/github/stars/aorumbayev/kagan?style=for-the-badge" alt="Stars"></a>
</p>

<p align="center">
  <a href="https://docs.kagan.sh">Documentation</a> •
  <a href="https://docs.kagan.sh/install">Install</a> •
  <a href="https://docs.kagan.sh/quickstart">Quickstart</a> •
  <a href="https://github.com/aorumbayev/kagan/issues">Issues</a>
</p>

---

<p align="center">
  <img src="https://i.imgur.com/dZRl5V7.png" alt="Kagan Screenshot" width="700">
</p>

Kagan is a terminal-based Kanban board that integrates AI agents to help you complete development tasks autonomously or collaboratively. Review mode highlights merge readiness and conflict resolution guidance to prevent surprise merge failures.

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

- Python 3.12 – 3.13
- Git repository (for worktrees)
- tmux (recommended on macOS/Linux for native PAIR terminal sessions)
- VS Code or Cursor (supported PAIR launchers, especially on Windows)
- Terminal (minimum 80x20 characters)

## Usage

```bash
kagan              # Launch TUI (default command)
kagan tui          # Launch TUI explicitly
kagan mcp          # Run as MCP server
kagan tools        # Stateless developer utilities (prompt enhancement)
kagan update       # Check for and install updates
kagan list         # List all projects with task counts
kagan reset        # Reset data (interactive)
kagan --help       # Show all options
```

## Supported AI CLIs

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (Anthropic)
- [OpenCode](https://opencode.ai/docs) (SST)
- [Codex](https://github.com/openai/codex) (OpenAI)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (Google)
- [Kimi CLI](https://github.com/MoonshotAI/kimi-cli) (Moonshot AI)
- [GitHub Copilot](https://github.com/github/copilot-cli) (GitHub)

## Documentation

**Full documentation available at [docs.kagan.sh](https://docs.kagan.sh)**

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
