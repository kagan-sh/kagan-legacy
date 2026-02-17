---
title: Quickstart
description: Install Kagan and complete your first task in under 5 minutes
icon: material/timer
---

# Quickstart

**Prerequisites:** `uv`, `git`, local repo.

## 1. Install

```bash
uv tool install kagan
kagan --version   # e.g. 0.5.0
```

## 2. Launch

```bash
cd /path/to/your-repo
kagan
```

Welcome screen → open/create project → board (BACKLOG, IN_PROGRESS, REVIEW, DONE).

## 3. Create task

`n` → title + description → AUTO or PAIR → `F2` save. Task appears in BACKLOG.

## 4. Run task

- **AUTO:** Select task → `a` or `Enter` → `Enter` for Task Output.
- **PAIR:** Select task → `Enter` → work in tmux/VS Code/Cursor.

[AUTO vs PAIR](guides/modes-auto-vs-pair.md)

## 5. Review

Move to REVIEW → `Enter` (Task Output) → approve/reject → merge.

## Keys

`?` Help · `.` Actions · `,` Settings · `F12` Debug

## Failures

```bash
kagan doctor
```

[Troubleshooting](troubleshooting.md)
