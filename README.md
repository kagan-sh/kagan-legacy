<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-light.svg">
    <img alt="Kagan — interactive CLI supervision layer for AI coding agents with a structural human review gate" src="https://raw.githubusercontent.com/kagan-sh/kagan/main/.github/assets/hero-dark.svg" width="100%">
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
  <a href="https://docs.kagan.sh/concepts/task-lifecycle/">The review gate</a> ·
  <a href="https://docs.kagan.sh/guides/mcp-setup/">MCP Setup</a> ·
  <a href="https://docs.kagan.sh/reference/cli/">CLI Reference</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</h3>

---

Kagan is an interactive CLI supervision layer for AI coding agents with a structural human review gate. No agent-authored task reaches your main branch without an explicit approval — the harness enforces it.

The agent runs in an isolated git worktree. When it finishes, the task lands in review. You read the diff, adjudicate the findings, and approve. Approve means `ready` — kagan never pushes, merges, or force-pushes; it hands you the exact `git push` / `gh pr create` commands to run yourself. That gate cannot be automated away. It is not a setting.

You invoke `kagan` when you choose: it opens a single interactive session that shows what needs you (or "nothing — go do something else") and exits. There is no always-on dashboard and no live agent-output stream.

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

- An urgency-sorted Inbox that shows only what needs you — quiet by default, invoke-and-exit
- Each task runs in its own git worktree — your working copy stays untouched
- A two-gate flow: intake (input readiness) before the agent runs, review (output quality) before you approve
- Review requires explicit human approval; approve means `ready`, and kagan never pushes or merges for you
- MCP server so Claude Code, Codex, or any MCP-capable client can report into the harness
- A `doctor` preflight checks all required tools on launch

Supported agents: **Claude Code**, **Codex**, and **fake-agent** (tests).

Full docs: **[docs.kagan.sh](https://docs.kagan.sh/)**

## Surfaces

- **CLI** (`kagan`) — the one entrypoint: an interactive session over the Inbox, intake, review, ship, and workspaces views
- **MCP** (`kagan mcp`) — the agent's report channel, spawned by Claude Code, Codex, or any MCP host

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
