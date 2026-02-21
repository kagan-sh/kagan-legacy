---
title: GitHub plugin
description: Connect Kagan to GitHub for issue sync, PR workflows, and board automation
icon: material/github
tags:
  - github
  - plugins
---

# GitHub plugin

Bundled by default (`official.github`). Repos start disconnected — run connect first.

**Prerequisites:** `gh` CLI + `gh auth login`, Kagan project with repo.

## Setup

1. **Verify:** `gh auth status`
1. **Connect:** TUI palette (`.`) → `github connect`, or MCP `kagan_github_connect_repo`
1. **Sync:** `Shift+G` or palette → `repo sync`, or MCP `kagan_github_sync_issues`

Single-repo: `project_id` auto-resolves. Multi-repo: add `repo_id`.

## Review PR automation

- When a connected task moves to `REVIEW`, Kagan auto-creates a draft PR for the task workspace branch.
- This now applies even when no GitHub issue is linked, as long as the task workspace matches a connected repo.
- PR creation auto-pushes the task branch (`origin/<task-branch>`) before calling `gh pr create`.
- For tasks already linked to a PR, subsequent AUTO completions push new commits to the remote branch automatically.

## Issue ↔ Task mapping

| GitHub   | Kagan   |
| -------- | ------- |
| `OPEN`   | BACKLOG |
| `CLOSED` | DONE    |

Titles: `[GH-123] Original Title`

## AUTO/PAIR labels

| Label             | Type |
| ----------------- | ---- |
| `kagan:mode:auto` | AUTO |
| `kagan:mode:pair` | PAIR |

Order: labels → repo default → **PAIR**. Conflict → PAIR wins.

Repo default: `kagan.github.default_mode: "AUTO"` in repo scripts.

## Lease coordination

One instance per issue. `kagan:locked` label; 1h duration, 2h stale → auto-takeover. Disable: `kagan.github.lease_enforcement: false`.

## Error codes

| Code                       | Fix                              |
| -------------------------- | -------------------------------- |
| `GH_CLI_NOT_AVAILABLE`     | `brew install gh`                |
| `GH_AUTH_REQUIRED`         | `gh auth login`                  |
| `GH_REPO_ACCESS_DENIED`    | Check permissions                |
| `GH_REPO_METADATA_INVALID` | Reconnect (use canonical `repo`) |
| `GH_PROJECT_REQUIRED`      | Provide `project_id`             |
| `GH_REPO_REQUIRED`         | Multi-repo: add `repo_id`        |
| `GH_NOT_CONNECTED`         | Run connect first                |
| `GH_SYNC_FAILED`           | Check gh access, inspect stats   |

## MCP tools

**V1 (frozen):** `kagan_github_contract_probe`, `kagan_github_connect_repo`, `kagan_github_sync_issues` — all MAINTAINER.

**Extended:** `acquire_lease`, `release_lease`, `get_lease_state`, `create_pr_for_task`, `link_pr_to_task`, `reconcile_pr_status`, `check_ci_status`, `merge_pr`, `get_pr_review_comments`, `sync_task_status`.

______________________________________________________________________

## Operations

### Initial setup checklist

- [ ] `gh --version` installed, `gh auth login` completed
- [ ] `gh repo view <owner>/<repo>` succeeds
- [ ] Kagan project created with repository attached
- [ ] `kagan_github_connect_repo` → response `code: "CONNECTED"`
- [ ] Confirm `connection` metadata: canonical `repo`, correct `owner` and `default_branch`
- [ ] `kagan_github_sync_issues` → tasks appear on board with `[GH-N]` prefix

### Routine sync

```json
{
  "tool": "kagan_github_sync_issues",
  "arguments": { "project_id": "<project_id>" }
}
```

Post-sync: check `stats.errors == 0`, compare `stats.total` with GitHub issue count.

### Recovery

**Mapping drift:** Re-run `kagan_github_sync_issues`. Sync reconciles by issue number.

**Connection reset:** `kagan_github_connect_repo` is idempotent — returns `ALREADY_CONNECTED` if valid, refreshes if metadata changed.

### Rate limits

~5000 req/h via `gh`. Batch sync (once, not per-issue). Monitor: `gh api rate_limit`.

### Scheduling sync

Kagan has no `--call` mode. To schedule:

- Trigger from TUI (`Shift+G`)
- Use any MCP client to call `kagan_github_sync_issues` against a running Kagan MCP server

### Monitoring

| Cadence | Check                                         |
| ------- | --------------------------------------------- |
| Daily   | `stats.errors` from sync is 0                 |
| Weekly  | GitHub issue count matches task count         |
| Weekly  | Closed issues not stuck in BACKLOG            |
| Weekly  | `kagan:locked` labels match active workspaces |
