---
title: MCP Setup — Connect Editors to Kagan
description: Connect external AI clients to Kagan over MCP
icon: material/server-network
tags:
  - mcp
  - setup
---

# MCP setup

Kagan exposes its full task lifecycle over MCP. Any editor or CLI that speaks the protocol becomes a first-class client -- no TUI required.

!!! note "Using the native VS Code extension?"
    If you want the Kagan sidebar, `@kagan` chat participant, native diffs, and reviews inside VS Code, install the extension instead of adding `.vscode/mcp.json`.

    - [VS Code extension guide](vscode-extension.md)
    - [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode)
    - [Open VSX](https://open-vsx.org/extension/kagan/kagan-vscode)

**Prerequisites:** Kagan installed, client supports MCP stdio.

## 1. Start server

```bash
kagan mcp
```

## 2. Add to client

Start with read-only access:

```bash
kagan mcp --readonly
```

Switch to default (read+write) or admin tier only when needed.

## 3. Verify

```text
task_list → tasks returned
task_get(task_id, include_logs=true) → task detail
task_logs(task_id, offset, limit)   → if truncated
```

______________________________________________________________________

## Access tiers

Kagan uses three access tiers, controlled by CLI flags:

| Tier       | Flag         | Scope                                                              |
| ---------- | ------------ | ------------------------------------------------------------------ |
| `readonly` | `--readonly` | Read-only. Inspect tasks, list projects, view logs.                |
| `default`  | *(no flag)*  | Read + write. Create, update, annotate tasks. Run jobs.            |
| `admin`    | `--admin`    | Default + destructive. Delete tasks, modify settings, plugin sync. |

`--readonly` and `--admin` are mutually exclusive.

```bash
kagan mcp --readonly                    # read-only auditing
kagan mcp                               # default read+write
kagan mcp --admin                       # full admin access
kagan mcp --session-id task:abc123      # task-scoped session
```

______________________________________________________________________

## Editor configs

=== "Claude Code"

````
Path: `~/.claude.json` (global) or `.mcp.json` (project)

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "VS Code"

````
Path: `.vscode/mcp.json`

```json
{
  "servers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "Cursor"

````
Path: `.cursor/mcp.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "OpenCode"

````
Path: `~/.config/opencode/opencode.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "Codex"

````
Path: `~/.codex/config.toml`

```toml
[mcp_servers.kagan]
command = "kagan"
args = ["mcp"]
```
````

=== "Gemini CLI"

````
Path: `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "Kimi CLI"

````
Path: `~/.kimi/mcp.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "GitHub Copilot"

````
Path: `.github/copilot/mcp.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "Goose"

````
Path: `~/.config/goose/config.yaml`

```yaml
extensions:
  kagan:
    type: stdio
    name: kagan
    cmd: kagan
    args:
      - mcp
```
````

=== "Amp"

````
Path: `~/.config/amp/settings.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

=== "Auggie"

````
Path: `~/.augment/mcp.json`

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp"]
    }
  }
}
```
````

!!! tip "Read-only or admin access"
Add `"--readonly"` or `"--admin"` to the `args` array to change the access tier. For task-scoped sessions, add `"--session-id", "task:abc123"`.

______________________________________________________________________

## Multi-repo

**Create:** Kagan → New Project → add repo paths. First repo = active.

**Switch:** `Ctrl+R` -> `j`/`k` -> `Enter` select · `Ctrl+Shift+P` Quick Actions · `Esc` cancel.

**Branch:** `b` = task-level base branch override. Repo base from checked-out branch.

**Review:** `Enter` (open task) → `2` (Diff tab) → `a` approve / `x` reject / `m` merge / `b` rebase.

**State:** External to repos — `kagan.db`, `config.toml`, worktrees. No `.kagan/` in repos.

______________________________________________________________________

## Error recovery

See [Troubleshooting](../troubleshooting.md) for MCP error codes and fixes.

[MCP tools reference](../reference/mcp-tools.md)
