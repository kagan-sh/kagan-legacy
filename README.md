<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-light.svg">
    <img alt="Kagan — AI-powered Kanban board for coding agents" src="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg" width="100%">
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
  <a href="https://snyk.io/test/github/kagan-sh/kagan?targetFile=pyproject.toml"><img src="https://snyk.io/test/github/kagan-sh/kagan/badge.svg?targetFile=pyproject.toml&style=flat" alt="Snyk"></a>
  <a href="https://glama.ai/mcp/servers/kagan-sh/kagan"><img src="https://glama.ai/mcp/servers/kagan-sh/kagan/badges/score.svg" alt="Glama"></a>
</p>

<!-- mcp-name: io.github.kagan-sh/kagan -->

<h3 align="center">
  <a href="https://docs.kagan.sh/">Docs</a> ·
  <a href="https://docs.kagan.sh/quickstart/">Quickstart</a> ·
  <a href="https://docs.kagan.sh/guides/mcp-setup/">MCP Setup</a> ·
  <a href="https://docs.kagan.sh/reference/cli/">CLI Reference</a>
</h3>

---

A terminal Kanban board that runs AI coding agents on your code. Create tasks, run agents autonomously or in pair mode. 14 agents supported.

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

Full docs: **[docs.kagan.sh](https://docs.kagan.sh/)**. TUI: `Space` cycles layout, `Esc` closes, `Ctrl+F` fullscreen.

## Web Dashboard

Run `kagan web` (add `--host 0.0.0.0` for network access). See [docs](https://docs.kagan.sh/guides/remote-access/).

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
