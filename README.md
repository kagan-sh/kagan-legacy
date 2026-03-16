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

<h3 align="center">
  <a href="https://docs.kagan.sh/">Docs</a> ·
  <a href="https://docs.kagan.sh/quickstart/">Quickstart</a> ·
  <a href="https://docs.kagan.sh/guides/mcp-setup/">MCP Setup</a> ·
  <a href="https://docs.kagan.sh/reference/cli/">CLI Reference</a>
</h3>

---

A terminal Kanban board that runs AI coding agents on your code. Create a task, pick a mode — let the agent run autonomously or keep your hands on the wheel with the agent as co-pilot. Review and merge. 14 agents supported.

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

## Docs

**[docs.kagan.sh](https://docs.kagan.sh/)** — everything else lives there.

## TUI Controls

On Kanban and Task screens, press `Space` to cycle AI chat split layout (`vertical -> horizontal -> vertical`), `Esc` to close the overlay, and `Ctrl+F` to expand the open overlay fullscreen.

## Web Dashboard

Run the bundled web UI locally:

```bash
kagan web
```

To access from another device on your network:

```bash
kagan web --host 0.0.0.0
```

See [Remote access](https://docs.kagan.sh/guides/remote-access/) for network setup.

## License

[MIT](LICENSE)
