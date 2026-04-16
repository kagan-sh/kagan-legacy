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

```
- [VS Code extension guide](vscode-extension.md)
- [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode)
- [Open VSX](https://open-vsx.org/extension/kagan/kagan-vscode)
```

**Prerequisites:** Kagan installed, client supports MCP stdio.

## 1. Pick the right integration path

- **Using the Kagan VS Code extension?** Install the extension and skip `.vscode/mcp.json`.
- **Using Claude Code, Cursor, OpenCode, Codex, or another MCP client?** Add Kagan as an MCP server there.

The MCP client starts `kagan mcp` for you when it connects. You usually do **not** run `kagan mcp` manually first.

## 2. Add to client

Start with an explicit role. `WORKER` is the safest default for coding agents; `ORCHESTRATOR` is the full project-control role.

```bash
kagan mcp --role WORKER
```

Example for Claude Code:

```json
{
  "mcpServers": {
    "kagan": {
      "command": "kagan",
      "args": ["mcp", "--role", "WORKER"]
    }
  }
}
```

## 3. Verify

```text
task_list → tasks returned
task_get(task_id, include_logs=true) → task detail
task_logs(task_id, offset, limit)   → if truncated
```

______________________________________________________________________

## Roles and compatibility flags

Prefer `--role` when configuring MCP clients:

| Role           | When to use it                                                |
| -------------- | ------------------------------------------------------------- |
| `WORKER`       | Task-scoped coding agents that should stay within one task    |
| `REVIEWER`     | Review-only agents that should inspect and give verdicts      |
| `ORCHESTRATOR` | Full project control for planning, task creation, and routing |

Compatibility flags still work:

- `--readonly` narrows the server to the worker-style read-focused surface.
- `--admin` is currently an alias of the default MCP tool surface.
- `--readonly` and `--admin` are mutually exclusive.

```bash
kagan mcp --role WORKER                 # safest default for agents
kagan mcp --role REVIEWER               # review verdict tools
kagan mcp --role ORCHESTRATOR           # full project control
kagan mcp --readonly                    # compatibility shortcut for read-focused access
kagan mcp --admin                       # currently same MCP tool surface as default
kagan mcp --session-id task:abc123      # task-scoped session
```

______________________________________________________________________

## Editor configs

For fresh setups, add `"--role", "WORKER"` (or the role you want) to the `args` array in these examples.

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

!!! tip "Roles and compatibility flags"
Add `"--role", "WORKER"`, `"--role", "REVIEWER"`, or `"--role", "ORCHESTRATOR"` to the `args` array to control tool visibility. `"--readonly"` and `"--admin"` still work as compatibility flags. For task-scoped sessions, add `"--session-id", "task:abc123"`.

______________________________________________________________________

## Analytics tools

Kagan exposes its analytics data over MCP so external clients (Claude Desktop, Cursor, Claude Code, etc.) can query agent performance and session activity programmatically. These tools are available to every role (`WORKER`, `REVIEWER`, `ORCHESTRATOR`) and operate on the currently active project — open a project in Kagan first, otherwise they return empty results.

| Tool                         | What it returns                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `analytics_backend_stats`    | Per-backend session count, success rate, average duration, and retry rate.       |
| `analytics_session_timeline` | Daily session counts by status. Accepts `days` (default `30`).                   |
| `analytics_export`           | Combined backend stats + session timeline, ready for dashboards. Accepts `days`. |

See the [Analytics guide](analytics.md) for the full list of metrics, UI surfaces, and export workflows.

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
