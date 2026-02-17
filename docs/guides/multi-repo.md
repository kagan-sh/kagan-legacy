---
title: Multi-repo
description: Run one Kagan project across multiple repositories
icon: material/source-repository-multiple
---

# Multi-repo

## Create

Kagan → New Project → add repo paths. First repo = active.

## Switch repo

`Ctrl+R` → navigate (`j`/`k`) → `Enter` select, `n` add, `Esc` cancel.

## Branch targets

`b` = task-level base branch. Repo base from checked-out branch. Task branch overrides.

## Review per repo

`v` (Task Details) → Workspace Repos → Diff / Merge per repo.

## State location

External to repos: `kagan.db`, `config.toml`, worktrees. No `.kagan/` in repos.
