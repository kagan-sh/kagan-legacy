---
title: Architecture overview
description: High-level system view for Kagan users
icon: material/source-branch
---

# Architecture overview

## Components

| Component        | Purpose                          |
| ---------------- | -------------------------------- |
| TUI              | Keyboard-first UI                |
| MCP server       | AI tools read/mutate state       |
| Core process     | Coordinates ops and state        |
| SQLite           | Projects, tasks, reviews         |
| Git worktrees    | Isolated task workspaces         |

## Flow

```mermaid
flowchart LR
  TUI[TUI client] --> CORE[Core process]
  MCP[MCP client] --> CORE
  CLI[CLI commands] --> CORE
  CORE --> DB[(SQLite)]
  CORE --> WT[Git worktrees]
```

All interfaces share the same state. MCP task → appears in TUI. TUI review → visible to MCP.

## Plugins

Core = single mutable authority. TUI/MCP/CLI never mutate directly. Plugin actions: `capability.method` via registry. GitHub bundled, repos start disconnected. Third-party: local entrypoints in config (no remote fetch).

## Data

State outside repo: `config.toml`, `kagan.db`, core runtime files, worktrees. No `.kagan/` in repos.

## Troubleshooting

`kagan core status` when connectivity fails. MCP: use capability profiles. [Troubleshooting](../troubleshooting.md) for metadata/token/lock issues.
