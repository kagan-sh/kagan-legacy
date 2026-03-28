---
title: Troubleshooting
description: Symptom-first fixes for common Kagan issues
icon: material/bug
---

# Troubleshooting

`kagan` runs doctor checks automatically on startup and shows them only when
critical blockers are detected. Run doctor directly any time for full diagnostics:

```bash
kagan doctor
```

Match symptom text below.

## Core / MCP

| Symptom                        | Fix                                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Runtime metadata incomplete    | Restart the client, then run `kagan doctor`                                                            |
| `AUTH_STALE_TOKEN`             | Reconnect MCP client and restart `kagan serve` / `kagan web` if needed                                |
| `CLIENT_OUTDATED`              | Restart MCP/TUI client session to reload latest runtime                                                |
| `CLIENT_VERSION_REQUIRED`      | Update/restart MCP/TUI client to send runtime version                                                  |
| `CLIENT_BUILD_HASH_REQUIRED`   | Update/restart MCP/TUI client to send runtime fingerprint                                              |
| `Unknown session origin 'tui'` | Close any other running Kagan instance, then relaunch from your intended directory                     |
| `DISCONNECTED`                 | Run `kagan` first, then `kagan mcp`                                                                    |
| `START_PENDING`                | Wait a few seconds, then retry or restart `kagan serve` / `kagan web`                                 |
| Logs cut off mid-output        | Use `task_logs` with `offset` and `limit` to page through; follow `next_offset`                        |

## Interactive launch / terminal

| Symptom                          | Fix                                                                                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| tmux not found                   | `brew install tmux` (macOS) / `apt install tmux` (Debian) / `dnf install tmux` (Fedora)                                                           |
| nvim not found                   | `brew install neovim` (macOS) / `apt install neovim` (Debian) / `dnf install neovim` (Fedora)                                                     |
| VS Code chat did not auto-open   | Ensure `GitHub.copilot-chat` is installed (`code --list-extensions`), then relaunch the interactive session; fallback is `.kagan/start_prompt.md` |
| Unsupported interactive launcher | Set `attached_launcher = "tmux"` \| `"nvim"` \| `"vscode"` \| `"cursor"` \| `"windsurf"` \| `"kiro"` \| `"antigravity"`                           |

## Git

| Symptom                     | Fix                                                        |
| --------------------------- | ---------------------------------------------------------- |
| Git not found               | `brew install git` / `apt install git` / `dnf install git` |
| Git identity not configured | `git config --global user.name "…"` and `user.email "…"`   |

## Other

| Symptom                            | Fix                                                                                                                                                                            |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Another instance running           | Close other instance; if stale: `kagan reset`                                                                                                                                  |
| Chat context missing after a crash | Only persisted checkpoints are recoverable; see [ACP session lifecycle](guides/acp-session-lifecycle.md)                                                                       |
| UI rendering issues                | Resize ≥80×20; truecolor terminal; check logs in `kagan.log` (platformdirs log directory)                                                                                      |
| Mouse copy inconsistent            | Set `KAGAN_TUI_MOUSE=0` for keyboard-first mode. With mouse enabled (default or `KAGAN_TUI_MOUSE=1`): use `Option`-select (iTerm) or `Shift`-select (GNOME / Windows Terminal) |

## Prompt safety / privacy

| Symptom                                      | Fix                                                                                                                                                       |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Escaped tags like `&lt;input&gt;` in prompts | Expected. Kagan escapes control-tag syntax to reduce prompt-injection risk.                                                                               |
| `[REDACTED]` in logs or agent output         | Expected. Kagan redacts high-confidence secrets before prompt send/log persistence. Use placeholders; inject credentials through secure runtime channels. |

## GitHub plugin

| Code                               | Fix                                                                        |
| ---------------------------------- | -------------------------------------------------------------------------- |
| `GH_CLI_NOT_AVAILABLE`             | `brew install gh` / `apt install gh` / `dnf install gh`                    |
| `GH_AUTH_REQUIRED`                 | `gh auth login`                                                            |
| `GH_NOT_CONNECTED`                 | TUI: `.` → Connect GitHub, or CLI: `kagan import github --repo owner/repo` |
| `LEASE_HELD_BY_OTHER`              | `force_takeover: true` if holder gone; 2h+ lease → auto-takeover           |
| Sync shows 0 but GitHub has issues | `gh issue list --repo owner/repo`; re-auth `gh auth login`                 |

## Updates

```bash
kagan update --check-only   # check only
kagan update            # install
kagan update --force    # skip confirmation
kagan update --prerelease
```

Skip startup check: `KAGAN_SKIP_UPDATE_CHECK=1`

## Nuclear cleanup

```bash
kagan reset --force
```

Permanently removes all config, data, and worktrees. All tasks and project state will be lost. Before running: stop any active sessions and export any logs you want to keep. After: run `kagan` to start fresh.
