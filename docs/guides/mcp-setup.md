---
title: MCP setup
description: Connect external AI clients to Kagan over MCP
icon: material/server-network
---

# MCP setup

**Prerequisites:** Kagan installed, client supports MCP stdio.

## 1. Start server

```bash
kagan mcp
```

Variants: `--readonly`, `--capability pair_worker`, `--session-id task:TASK-123`, `--identity kagan_admin --capability maintainer`

## 2. Add to client

```text
command: kagan
args: ["mcp"]
```

[Editor MCP setup](editor-mcp-setup.md) for per-editor config.

## 3. Verify

`task_list` → tasks returned. `task_get(task_id, include_logs=true)`. If truncated: `task_logs(task_id, offset, limit)`.

## 4. Capability profiles

| Profile       | Use                          |
| ------------- | ---------------------------- |
| `viewer`      | Read-only                    |
| `pair_worker` | Task automation (scoped)      |
| `operator`    | Day-to-day ops               |
| `maintainer`  | Admin/destructive (trusted)   |

## 5. Recovery

| Code              | Action                                      |
| ----------------- | -------------------------------------------- |
| `AUTH_STALE_TOKEN`| Reconnect client; `kagan core stop` + `start`|
| `DISCONNECTED`    | Start Kagan or restart core                  |
| `START_PENDING`   | Poll `job_poll(wait=false)`                   |

[MCP tools reference](../reference/mcp-tools.md)
