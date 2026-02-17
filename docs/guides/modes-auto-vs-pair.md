---
title: AUTO vs PAIR
description: Choose and run the right execution mode for each task
icon: material/robot
---

# AUTO vs PAIR

| When…                          | Use    |
| ------------------------------ | ------ |
| Requirements clear, bounded    | AUTO   |
| Evolving, exploratory          | PAIR   |
| Async background progress      | AUTO   |
| Direct interactive collaboration | PAIR |

## Run AUTO

`n` → set AUTO → `a` or `Enter` → Task Output (`Enter`) → REVIEW → approve/merge.

## Run PAIR

`n` → set PAIR → `Enter` → work in tmux/VS Code/Cursor → move through REVIEW manually.

## Switch mode

`v` (details) → `e` (edit) → change `task_type` → `F2` save.

## Config

```toml
[general]
default_worker_agent = "claude"
default_pair_terminal_backend = "tmux"
max_concurrent_agents = 3
```

[Configuration](../reference/configuration.md) · [Troubleshooting](../troubleshooting.md) · [MCP tools](../reference/mcp-tools.md)
