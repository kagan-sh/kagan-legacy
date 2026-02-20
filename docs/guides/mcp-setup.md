---
title: MCP setup
description: Connect external AI clients to Kagan over MCP
icon: material/server-network
tags:
  - mcp
  - setup
---

# MCP setup

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

---

## Capability profiles

| Profile | Use |
| ------- | --- |
| `viewer` | Read-only. Inspect tasks, flag concerns. |
| `planner` | Read + plan submission. |
| `pair_worker` | Task automation — create, update, annotate. No merge. |
| `operator` | Day-to-day ops — sessions, reviews. |
| `maintainer` | Admin/destructive actions. Trusted pipelines only. |

```bash
kagan mcp --capability pair_worker
kagan mcp --identity kagan_admin --capability maintainer
```

---

## Access profile presets

`--preset` applies a named capability + identity combination. Run `kagan profiles` to list all.

| Preset | Equivalent flags | Use |
| ------ | ---------------- | --- |
| `security-reviewer` | `--capability viewer --identity kagan` | Read-only auditing |
| `test-writer` | `--capability pair_worker --identity kagan` | Scoped test generation |
| `refactoring-agent` | `--capability pair_worker --identity kagan` | Bounded refactors |
| `pair-worker` | `--capability pair_worker --identity kagan` | Interactive PAIR workflow |
| `orchestrator` | `--capability operator --identity kagan_admin` | AUTO pipeline orchestration |
| `maintainer` | `--capability maintainer --identity kagan_admin` | Admin / CI lane |

```bash
kagan mcp --preset orchestrator
kagan mcp --preset security-reviewer --session-id task:abc123
```

Explicit `--capability` / `--identity` flags always override a preset.

---

## Editor configs

=== "Claude Code"

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

=== "VS Code"

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

=== "Cursor"

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

=== "OpenCode"

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

=== "Codex"

    Path: `~/.codex/config.toml`

    ```toml
    [mcp_servers.kagan]
    command = "kagan"
    args = ["mcp", "--capability", "pair_worker"]
    ```

=== "Gemini CLI"

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

=== "Kimi CLI"

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

---

## Multi-repo

**Create:** Kagan → New Project → add repo paths. First repo = active.

**Switch:** `Ctrl+R` → `j`/`k` → `Enter` select · `n` add · `Esc` cancel.

**Branch:** `b` = task-level base branch override. Repo base from checked-out branch.

**Review:** `v` (Task Details) → Workspace Repos → Diff / Merge per repo.

**State:** External to repos — `kagan.db`, `config.toml`, worktrees. No `.kagan/` in repos.

---

## Error recovery

| Code | Action |
| ---- | ------ |
| `AUTH_STALE_TOKEN` | Reconnect client; `kagan core stop` → `start` |
| `CLIENT_OUTDATED` | Restart MCP/TUI session to reload latest runtime |
| `CLIENT_VERSION_REQUIRED` | Update/restart client so it sends runtime version |
| `CLIENT_BUILD_HASH_REQUIRED` | Update/restart client so it sends runtime fingerprint |
| `DISCONNECTED` | Start Kagan or restart core |
| `START_PENDING` | Poll `job_poll(wait=false)` |

[MCP tools reference](../reference/mcp-tools.md)
