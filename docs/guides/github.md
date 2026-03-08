---
title: Import from GitHub
description: Bring GitHub issues into Kagan as tasks in a few steps
icon: material/github
tags:
  - github
  - import
---

# Import from GitHub

Use this guide to import GitHub issues into your board. GitHub support is bundled with Kagan.

## What you need

- GitHub CLI installed: <https://cli.github.com>
- Signed in on your machine: `gh auth login`
- A Kagan project already created

## Import in the TUI

1. Open your project board in `kagan`
1. Open Actions with `.`
1. Run `github import`
1. Enter your repository in `owner/repo` format
1. Choose issue state (`open`, `closed`, or `all`)
1. Press `Enter` to import

Kagan shows a summary with created, skipped, and error counts.

## Import from CLI

```bash
kagan import github --repo octocat/hello-world
```

Optional flags:

- `--state open|closed|all`
- `--label <label>` to import only matching issues
- `--yes` to skip confirmation

If you omit `--repo`, Kagan prompts for it interactively.

## Label mapping

These labels map automatically when importing:

- `priority:critical`, `priority:high`, `priority:medium`, `priority:low`
- `kagan:auto`, `kagan:pair`

If an issue has no mode label, Kagan imports it as `AUTO` by default.

Other labels are kept in the task description as tags.

## Troubleshooting

- `GitHub CLI (gh) not found` -> install from <https://cli.github.com>
- `GitHub CLI not authenticated` -> run `gh auth login`
- `repo must be in owner/repo format` -> use `owner/repo`, for example `octocat/hello-world`

For a full environment check, run:

```bash
kagan doctor
```
