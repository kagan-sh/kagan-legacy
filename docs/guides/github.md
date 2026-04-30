---
title: GitHub integration
description: Two-way metadata sync, create-and-link, and `#`-mention autocomplete for GitHub Issues
icon: material/github
tags:
  - github
  - integration
---

# GitHub integration

Kagan integrates with GitHub Issues at three points:

1. **Import** issues from a repository as Kagan tasks.
2. **Create-and-link** — when creating a Kagan task, optionally link it to an existing issue or create a fresh issue from the task.
3. **`#`-mention autocomplete** — type `#` anywhere in a Kagan text field to insert a link to a Kagan task or a GitHub issue.

The integration uses the GitHub CLI (`gh`) for auth — no token plumbing.

## What you need

- GitHub CLI installed: <https://cli.github.com>
- Signed in: `gh auth login`
- A Kagan project linked to a Git repo whose `origin` points at GitHub

## How sync works

Once a task is linked to a GitHub issue, Kagan keeps the following fields in sync **bidirectionally** on every pull/push:

| Field                     | Direction                                    |
| ------------------------- | -------------------------------------------- |
| Title                     | both ways                                    |
| Body / description        | both ways, **verbatim** — no scaffolding     |
| Priority labels           | both ways (`priority:critical/high/medium/low`) |
| Acceptance criteria       | both ways via a tagged comment (see below)   |

What does **not** sync:

- **Status / lifecycle.** Moving a Kagan task to `DONE` does not close the GitHub issue. Closing an issue on GitHub does not move the Kagan task. They are independent concepts — a Kanban column is not the same as an issue lifecycle state.
- **Comments** other than the Kagan-managed acceptance-criteria comment.
- **Assignees, milestones, projects** — not in scope for this integration.

The body is stored exactly as it appears on GitHub. Kagan does not prepend the URL, inject `[label]` tags, or add any other scaffolding to the description. Round-trips are stable.

## Acceptance criteria

GitHub already has a checklist convention (`- [ ]` / `- [x]`). Kagan uses it in two ways:

1. **First import** — checklist lines in the issue body seed the Kagan task's acceptance criteria. The body is left untouched.
2. **Subsequent edits** — when criteria change in Kagan, Kagan upserts a single comment on the issue tagged with `<!-- kagan:acceptance-criteria -->`. The comment body is a clean checklist. On every pull, if that comment exists Kagan re-derives criteria from it; otherwise it falls back to the body seed.

The issue body is never modified by criteria sync — only the tagged comment is.

## Create and link

When creating a Kagan task on any surface (TUI, web, VS Code, MCP, chat), the `github_issue` field accepts:

- empty / `none` → no link.
- `42` / `#42` → link to the existing issue in the project's linked repo.
- `owner/repo#42` → link to an issue in a specific repo.
- `new` → create a new GitHub issue from the task's title and description, then link.

The link is stored on the task as `<owner>/<repo>#<number>` and is what every later sync operation keys on.

## Import

### CLI

```bash
kagan import github --repo owner/repo
```

Optional flags:

- `--state open|closed|all`
- `--label <label>` (repeatable)
- `--limit <n>` (default 100)
- `--issues 1,2,42` — import specific numbers only

### TUI

Press `.` for Actions → run `github import` → enter repo (auto-detected from `origin`), state, optional labels → preview list with toggles → import.

### Web

Click **Import from GitHub** on the board toolbar. Same fields, same preview, same toggles.

### VS Code

Command palette → **Kagan: Import from GitHub**. Same flow.

### MCP

`github_preview` and `github_sync` tools mirror the HTTP routes 1:1. Useful for orchestrator agents and external MCP clients.

### Chat

Ask the orchestrator: *"import open issues from owner/repo"*. The orchestrator calls `github_sync` via MCP.

## `#`-mention autocomplete

Type `#` in any Kagan text field — task description, acceptance criterion, chat message, code editor (VS Code) — and a typeahead opens listing matches from two sources:

- **Kagan tasks** in the current project (matched by short id and title).
- **GitHub issues** in the linked repo (matched by number and title).

Pick a Kagan task → inserts `kagan#<short_id>`. Pick a GitHub issue → inserts `#<number>`. Both forms are clickable in rendered markdown:

- `kagan#abc12345` → opens the task in-app.
- `#42` → opens the issue on GitHub.

If the project has no linked GitHub repo, the typeahead still works — Kagan-only.

## Cross-client parity

Every capability above is reachable from every client:

| Capability       | CLI | TUI | Web | VS Code | Chat | MCP |
| ---------------- | --- | --- | --- | ------- | ---- | --- |
| Import           | ✓   | ✓   | ✓   | ✓       | ✓    | ✓   |
| Create-and-link  | —   | ✓   | ✓   | ✓       | ✓    | ✓   |
| `#`-mention      | —   | ✓   | ✓   | ✓       | ✓    | ✓   |

(CLI does not have a generic `task create` command today — task creation is via the TUI or any of the API-driven clients.)

## Label mapping

These labels auto-map to Kagan priorities on import and on push-back:

- `priority:critical`, `priority:high`, `priority:medium`, `priority:low`

If the label doesn't exist on the repo when Kagan first sets it, Kagan creates it (`gh label create`) with a sensible default colour.

## Troubleshooting

- `GitHub CLI (gh) not found` → install from <https://cli.github.com>.
- `GitHub CLI not authenticated` → `gh auth login`.
- `repo must be in owner/repo format` → use `owner/repo`, e.g. `octocat/hello-world`.

For a full environment check:

```bash
kagan doctor
```
