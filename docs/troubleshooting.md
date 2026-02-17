---
title: Troubleshooting
description: Symptom-first fixes for common Kagan issues
icon: material/bug
---

# Troubleshooting

```bash
kagan doctor
```

Match symptom text below.

## Core / MCP

| Symptom | Fix |
| ------- | --- |
| Runtime metadata incomplete | `kagan core stop` → `start` → `status` |
| `AUTH_STALE_TOKEN` | Reconnect MCP client; `kagan core stop` → `start` |
| `DISCONNECTED` | Run `kagan` once, then `kagan mcp` |
| `START_PENDING` | Poll `job_poll(wait=false)` until running/terminal |
| `logs_truncated` / `logs_has_more` | `task_logs(task_id, offset, limit)`; use `next_offset` |

## PAIR / terminal

| Symptom | Fix |
| ------- | --- |
| tmux not found | `brew install tmux` (macOS) / `apt install tmux` (Debian) / `dnf install tmux` (Fedora) |
| Unsupported PAIR launcher | `default_pair_terminal_backend = "tmux"` \| `"vscode"` \| `"cursor"` in config |

## Git

| Symptom | Fix |
| ------- | --- |
| Git not found | `brew install git` / `apt install git` / `dnf install git` |
| Git identity not configured | `git config --global user.name "…"` and `user.email "…"` |

## Other

| Symptom | Fix |
| ------- | --- |
| Another instance running | Close other instance; if stale: `kagan reset` |
| UI rendering issues | Resize ≥80×20; truecolor terminal; `F12` debug log |

## GitHub plugin

| Code | Fix |
| ---- | --- |
| `GH_CLI_NOT_AVAILABLE` | `brew install gh` / `apt install gh` / `dnf install gh` |
| `GH_AUTH_REQUIRED` | `gh auth login` |
| `GH_NOT_CONNECTED` | MCP `kagan_github_connect_repo` or TUI `.` → Connect GitHub |
| `LEASE_HELD_BY_OTHER` | `force_takeover: true` if holder gone; 2h+ lease → auto takeover |
| Sync shows 0 but GitHub has issues | `gh issue list --repo owner/repo`; re-auth `gh auth login` |

## Nuclear cleanup

```bash
kagan reset --force
```

Permanently removes local state. Last resort.
