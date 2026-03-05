---
title: MCP setup
description: Connect external AI clients to Kagan over MCP
icon: material/server-network
tags:
  - mcp
  - setup
---

# MCP setup

Kagan exposes its full task lifecycle over MCP. Any editor or CLI that speaks the protocol becomes a first-class client -- no TUI required.

**Prerequisites:** Kagan installed, client supports MCP stdio.

## 1. Start server

```bash
kagan mcp
```

## 2. Add to client

Start with read-only access:

```text
command: kagan
args: ["mcp", "--readonly", "--capability", "viewer"]
```

Switch to elevated profiles only when needed.

## 3. Verify

```
task_list → tasks returned
task_get(task_id, include_logs=true) → task detail
task_logs(task_id, offset, limit)   → if truncated
```

______________________________________________________________________

## Capability profiles

| Profile       | Use                                                   |
| ------------- | ----------------------------------------------------- |
| `viewer`      | Read-only. Inspect tasks, flag concerns.              |
| `planner`     | Read + plan submission.                               |
| `pair_worker` | Task automation — create, update, annotate. No merge. |
| `operator`    | Day-to-day ops — sessions, reviews.                   |
| `maintainer`  | Admin/destructive actions. Trusted pipelines only.    |

```bash
kagan mcp --capability pair_worker
kagan mcp --identity kagan_admin --capability maintainer
```

______________________________________________________________________

## Access profile presets

`--preset` applies a named capability + identity combination. Run `kagan profiles` to list all.

| Preset              | Equivalent flags                                 | Use                         |
| ------------------- | ------------------------------------------------ | --------------------------- |
| `security-reviewer` | `--capability viewer --identity kagan`           | Read-only auditing          |
| `test-writer`       | `--capability pair_worker --identity kagan`      | Scoped test generation      |
| `refactoring-agent` | `--capability pair_worker --identity kagan`      | Bounded refactors           |
| `pair-worker`       | `--capability pair_worker --identity kagan`      | Interactive PAIR workflow   |
| `orchestrator`      | `--capability operator --identity kagan_admin`   | AUTO pipeline orchestration |
| `maintainer`        | `--capability maintainer --identity kagan_admin` | Admin / CI lane             |

```bash
kagan mcp --preset orchestrator
kagan mcp --preset security-reviewer --session-id task:abc123
```

Explicit `--capability` / `--identity` flags always override a preset.

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
      "args": ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
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
args = ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
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
      - --capability
      - pair_worker
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
      "args": ["mcp", "--capability", "pair_worker"]
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
      "args": ["mcp", "--capability", "pair_worker"]
    }
  }
}
```
````

______________________________________________________________________

## Multi-repo

**Create:** Kagan → New Project → add repo paths. First repo = active.

**Switch:** `Ctrl+R` → `j`/`k` → `Enter` select · `n` add · `Esc` cancel.

**Branch:** `b` = task-level base branch override. Repo base from checked-out branch.

**Review:** `v` (Task Details) → Workspace Repos → Diff / Merge per repo.

**State:** External to repos — `kagan.db`, `config.toml`, worktrees. No `.kagan/` in repos.

______________________________________________________________________

## Error recovery

See [Troubleshooting](../troubleshooting.md) for MCP error codes and fixes.

[MCP tools reference](../reference/mcp-tools.md)
