---
title: Configuration Reference
description: Full schema for config.toml, locations, and environment overrides
icon: material/cog
---

# Configuration reference

`config.toml` in Kagan config dir. Paths: `platformdirs` + env overrides.

| Purpose         | Override                  |
| --------------- | ------------------------- |
| Config          | `KAGAN_CONFIG_DIR`        |
| Data            | `KAGAN_DATA_DIR`          |
| Cache           | `KAGAN_CACHE_DIR`         |
| Worktree base   | `KAGAN_WORKTREE_BASE`     |
| Core runtime    | _(derived from data dir)_ |
| TUI mouse input | `KAGAN_TUI_MOUSE`         |

Files: `config.toml`, `kagan.db`, core runtime (`endpoint.json`, `token`, etc.).

## Minimal example

```toml
[general]
default_agent_backend = "claude-code"
auto_skill_discovery = false
review_strictness = "balanced"
additional_instructions = "Use conventional commit format"
attached_launcher = "tmux"
doctor_verbosity = "short"
interaction_verbosity = "short"
max_concurrent_agents = 3
```

## `[general]`

| Key                                 | Type           | Default                          | Notes                                                                                                                                                                                                                            |
| ----------------------------------- | -------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `max_concurrent_agents`             | integer        | `3`                              | Concurrent managed-run cap                                                                                                                                                                                                       |
| `mcp_server_name`                   | string         | `"kagan"`                        | MCP server registration name                                                                                                                                                                                                     |
| `worktree_base_ref_strategy`        | string         | `"local_if_ahead"`               | Base ref preference for worktree add/diff: `remote`, `local_if_ahead`, `local`                                                                                                                                                   |
| `auto_review`                       | boolean        | `true`                           | Run AI review on completion                                                                                                                                                                                                      |
| `auto_approve`                      | boolean        | `true`                           | Skip planner permission prompts                                                                                                                                                                                                  |
| `auto_skill_discovery`              | boolean        | `false`                          | Enable trusted local skill metadata discovery for orchestrator `/skills`                                                                                                                                                         |
| `require_review_approval`           | boolean        | `false`                          | Require review approval before merge                                                                                                                                                                                             |
| `serialize_merges`                  | boolean        | `true`                           | Queue merge actions                                                                                                                                                                                                              |
| `default_agent_backend`             | string         | `"claude-code"`                  | Default worker agent                                                                                                                                                                                                             |
| `use_recommended_backend`           | boolean        | `false`                          | Auto-pick the best-performing backend per task from historical analytics (requires ≥5 prior sessions per backend × role × task-type). See [intelligent backend selection](../guides/analytics.md#intelligent-backend-selection). |
| `additional_instructions`           | string         | `""`                             | Free-text rules appended to every agent prompt                                                                                                                                                                                   |
| `review_strictness`                 | string         | `"balanced"`                     | Review rigor. Allowed: `strict`, `balanced`, `relaxed`                                                                                                                                                                           |
| `planning_depth`                    | string         | `"always"`                       | When to create task plans. Allowed: `always`, `multi_task`, `never`                                                                                                                                                              |
| `auto_confirm_single_tasks`         | boolean        | `false`                          | Skip confirmation for single-task plans                                                                                                                                                                                          |
| `attached_launcher`                 | string         | `"tmux"` (`"vscode"` on Windows) | Preferred launcher for interactive runs                                                                                                                                                                                          |
| `doctor_verbosity`                  | string         | `"short"`                        | Allowed: `tldr`, `short`, `technical` (used by `kagan doctor` and startup blockers)                                                                                                                                              |
| `interaction_verbosity`             | string         | `"short"`                        | Allowed: `tldr`, `short`, `technical` (used for TUI notification/help detail level)                                                                                                                                              |
| `default_model_claude`              | string or null | `null`                           | Default model for Claude-family agents                                                                                                                                                                                           |
| `default_model_openai`              | string or null | `null`                           | Default model for OpenAI-family agents                                                                                                                                                                                           |
| `core_idle_timeout_seconds`         | integer        | `180`                            | Core auto-stop timeout after idle                                                                                                                                                                                                |
| `core_autostart`                    | boolean        | `true`                           | Start core automatically when client connects                                                                                                                                                                                    |
| `core_transport_preference`         | string         | `"auto"`                         | Allowed: `auto`, `socket`, `tcp`                                                                                                                                                                                                 |
| `task_wait_default_timeout_seconds` | integer        | `1800`                           | Default timeout for `task_wait` (30 minutes)                                                                                                                                                                                     |
| `task_wait_max_timeout_seconds`     | integer        | `3600`                           | Max allowed timeout for `task_wait` (60 minutes)                                                                                                                                                                                 |

## `[refinement]`

| Key                 | Type        | Default           | Notes                        |
| ------------------- | ----------- | ----------------- | ---------------------------- |
| `enabled`           | boolean     | `true`            | Enable prompt refinement     |
| `hotkey`            | string      | `"ctrl+e"`        | Hotkey to trigger refinement |
| `skip_length_under` | integer     | `20`              | Skip short inputs            |
| `skip_prefixes`     | string list | `['/', '!', '?']` | Skip command-like inputs     |

## `[ui]`

| Key                                | Type    | Default | Notes                                     |
| ---------------------------------- | ------- | ------- | ----------------------------------------- |
| `skip_attached_instructions_popup` | boolean | `false` | Skip interactive-launch instruction modal |

## Environment variables passed into interactive sessions

| Variable                           | Default | Meaning                                                                                                                                                                                                                   |
| ---------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NO_COLOR`                         | unset   | When set (any value), the chat REPL renders all panels and spinners without ANSI color and uses an ASCII spinner. Honors [no-color.org](https://no-color.org).                                                            |
| `KAGAN_BATCH_APPROVAL_DEBOUNCE_MS` | `100`   | Window (milliseconds) the chat REPL waits to collect concurrent `request_permission` calls into one batched approval panel. Must parse as a non-negative number; falls back to the default otherwise.                     |
| `KAGAN_BATCH_APPROVAL_CAP`         | `20`    | Maximum number of approvals batched into a single panel. Once reached, the panel is shown immediately even if the debounce window has not expired. Must parse as a positive integer; falls back to the default otherwise. |
| `KAGAN_CHAT_SHOW_THOUGHTS`         | unset   | When set to a truthy value (`1`, `true`, `yes`, `on`), the REPL prints agent "thinking" chunks alongside its message output.                                                                                              |

## Web dashboard settings

The web dashboard at `/settings` offers a categorized settings UI that reads and writes the same key-value store as `config.toml`. Changes made in the web UI take effect immediately and are visible in the TUI Settings modal, and vice versa.

| Category        | Controls                                                                    |
| --------------- | --------------------------------------------------------------------------- |
| Preferences     | Default agent backend, theme (system / dark / light)                        |
| Personalization | Custom instructions appended to every agent prompt, dotfile override status |
| Shortcuts       | Keyboard shortcut reference                                                 |
| Automation      | Auto review, require review approval, serialize merges                      |
| Orchestration   | Auto-confirm single tasks, review strictness, planning depth                |
| Git             | Identity mode (managed / system / custom), base branch, worktree strategy   |
| Environment     | Interactive launcher, restore last workspace, show attach guidance          |
| Models          | Default model hints for Claude-family and OpenAI-family agents              |
| Connection      | Server URL, mode, SSE status, version                                       |
| System Checks   | Preflight checks with pass/warn/fail status and fix hints                   |

The settings page uses a left sidebar for category navigation. Toggle rows save immediately on change; text fields save on blur or explicit Save button.

## Prompt override files

Place Markdown files in `.kagan/prompts/` at the root of your project repository to fully replace the built-in prompts:

| File              | Replaces                       | Notes                                                                     |
| ----------------- | ------------------------------ | ------------------------------------------------------------------------- |
| `orchestrator.md` | Orchestrator system prompt     | Full replacement — settings and additional instructions are skipped       |
| `execution.md`    | Task execution prompt template | Supports `{title}`, `{description}`, `{acceptance_criteria}` placeholders |
| `review.md`       | Review prompt                  | Full replacement                                                          |

If a file is absent, the built-in default is used with behavioral settings and additional instructions appended.

The TUI Settings modal and web dashboard show which override files are detected.

| Variable                | Meaning                   |
| ----------------------- | ------------------------- |
| `KAGAN_TASK_ID`         | Current task ID           |
| `KAGAN_TASK_TITLE`      | Current task title        |
| `KAGAN_WORKTREE_PATH`   | Worktree path             |
| `KAGAN_PROJECT_ROOT`    | Project root path         |
| `KAGAN_CWD`             | Current working directory |
| `KAGAN_MCP_SERVER_NAME` | MCP server name override  |

## TUI mouse reporting

`KAGAN_TUI_MOUSE` controls terminal mouse reporting when starting the TUI.

- Default (unset): mouse reporting enabled (click-to-focus on Kanban cards works out of the box)
- Disable: `KAGAN_TUI_MOUSE=0` (also accepts `false`, `no`, `off`)
- Enable explicitly: `KAGAN_TUI_MOUSE=1` (also accepts `true`, `yes`, `on`)
