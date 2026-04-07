---
title: Import from GitHub
description: Bring GitHub issues into Kagan as tasks in a few steps
icon: material/github
tags:
  - github
  - import
---

# Import from GitHub

Kagan has built-in GitHub issue import. Bring existing issues onto your board in a few steps.

## What you need

- GitHub CLI installed: <https://cli.github.com>
- Signed in on your machine: `gh auth login`
- A Kagan project already created

## Import in the TUI

GitHub import uses a two-step flow:

**Step 1 — Filter:**

1. Open your project board in `kagan`
1. Open Actions with `.`
1. Run `github import`
1. Enter your repository in `owner/repo` format
1. Choose issue state (`open`, `closed`, or `all`)
1. Optionally enter comma-separated labels to filter by (e.g. `bug, feature`)
1. Optionally set a limit (default 100)
1. Press `Enter` to preview matching issues

**Step 2 — Select:**

1. Review the list of matching issues — already-synced ones are shown with `(synced)` and deselected by default
1. Use `Space` to toggle individual issues, `a` to select all, `n` to deselect all
1. Press `Enter` to import selected issues, or `Esc` to go back and adjust filters

Kagan shows a summary with created, skipped, and error counts.

## Preview before import

See what issues match your filters before committing to the import:

```bash
kagan plugins preview github --repo octocat/hello-world
```

Optional flags:

- `--state open|closed|all`
- `--label <label>` (repeatable) — filter by one or more labels
- `--limit <n>` — cap the number of issues returned (default 100)

Output shows issue number, title, state, labels, and whether the issue is already synced.

## Import from CLI

```bash
kagan plugins sync github --repo octocat/hello-world
```

Optional flags:

- `--state open|closed|all`
- `--label <label>` (repeatable) — filter by one or more labels
- `--limit <n>` — max issues to fetch (default 100)
- `--issues 1,2,42` — import only specific issue numbers

Examples:

```bash
# Import only bug issues
kagan plugins sync github --repo octocat/hello-world --label bug

# Import multiple label filters
kagan plugins sync github --repo octocat/hello-world --label bug --label priority:high

# Import specific issues by number
kagan plugins sync github --repo octocat/hello-world --issues 12,34,56
```

## Label mapping

These labels map automatically when importing:

- `priority:critical`, `priority:high`, `priority:medium`, `priority:low`

Other labels are kept in the task description as tags.

## Troubleshooting

- `GitHub CLI (gh) not found` -> install from <https://cli.github.com>
- `GitHub CLI not authenticated` -> run `gh auth login`
- `repo must be in owner/repo format` -> use `owner/repo`, for example `octocat/hello-world`

For a full environment check, run:

```bash
kagan doctor
```
