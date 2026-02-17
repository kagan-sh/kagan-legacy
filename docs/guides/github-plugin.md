---
title: GitHub Plugin V1
description: Connect Kagan to GitHub for issue sync, PR workflows, and board automation
icon: material/github
---

# GitHub Plugin V1

Bundled by default (`official.github`). Repos start disconnected—run connect first.

**Prerequisites:** `gh` CLI + `gh auth login`, Kagan project with repo.

## Setup

1. **Verify:** `gh auth status`
2. **Connect:** TUI palette (`.`) → `github connect`, or MCP `kagan_github_connect_repo`
3. **Sync:** `Shift+G` or palette → `repo sync`, or MCP `kagan_github_sync_issues`

Single-repo: `project_id` auto-resolves. Multi-repo: add `repo_id`.

TUI flow is schema-driven via [Plugin UI Schema](plugin-ui-schema.md).

## Issue ↔ Task mapping

| GitHub | Kagan   |
| ------ | ------- |
| `OPEN` | BACKLOG |
| `CLOSED` | DONE   |

Titles: `[GH-123] Original Title`

## AUTO/PAIR labels

| Label             | Type |
| ----------------- | ---- |
| `kagan:mode:auto` | AUTO |
| `kagan:mode:pair` | PAIR |

Order: labels → repo default → **PAIR**. Conflict → PAIR wins.

Repo default: `kagan.github.default_mode: "AUTO"` in repo scripts.

## Lease coordination

One instance per issue. `kagan:locked` label; 1h duration, 2h stale → takeover. Disable: `kagan.github.lease_enforcement: false`.

Lease/PR MCP tools exist but aren’t in frozen V1 contract (see Extended tools below).

## Limits

- Polling only (no webhooks). ~5000 req/h via gh.
- Single PR per task. Labels: `kagan:locked`, `kagan:mode:*`.

## Error codes

| Code                       | Fix                          |
| -------------------------- | ---------------------------- |
| `GH_CLI_NOT_AVAILABLE`     | `brew install gh`            |
| `GH_AUTH_REQUIRED`         | `gh auth login`              |
| `GH_REPO_ACCESS_DENIED`    | Check permissions            |
| `GH_REPO_METADATA_INVALID` | Reconnect (use canonical `repo`) |
| `GH_PROJECT_REQUIRED`      | Provide `project_id`         |
| `GH_REPO_REQUIRED`         | Multi-repo: add `repo_id`    |
| `GH_NOT_CONNECTED`         | Run connect first            |
| `GH_SYNC_FAILED`            | Check gh access, inspect stats |

## MCP tools

**V1 (frozen):** `kagan_github_contract_probe`, `kagan_github_connect_repo`, `kagan_github_sync_issues` — all MAINTAINER.

**Extended:** `acquire_lease`, `release_lease`, `get_lease_state`, `create_pr_for_task`, `link_pr_to_task`, `reconcile_pr_status`
