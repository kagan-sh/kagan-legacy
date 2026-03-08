---
title: Configuration reference
description: Full schema for config.toml, locations, and environment overrides
icon: material/cog
---

# Configuration reference

`config.toml` in Kagan config dir. Paths: `platformdirs` + env overrides.

| Purpose         | Override                 |
| --------------- | ------------------------ |
| Config          | `KAGAN_CONFIG_DIR`       |
| Data            | `KAGAN_DATA_DIR`         |
| Cache           | `KAGAN_CACHE_DIR`        |
| Worktree base   | `KAGAN_WORKTREE_BASE`    |
| Core runtime    | `KAGAN_CORE_RUNTIME_DIR` |
| TUI mouse input | `KAGAN_TUI_MOUSE`        |

Files: `config.toml`, `kagan.db`, core runtime (`endpoint.json`, `token`, etc.).

## Minimal example

```toml
[general]
default_worker_agent = "claude"
auto_skill_discovery = false
worker_persona = "Implementer: ship the smallest correct change and verify with tests."
orchestrator_persona = "Orchestrator: plan concrete tasks and communicate concisely."
pr_reviewer_persona = "PR Reviewer: validate requirements, regressions, and test coverage."
default_pair_terminal_backend = "tmux"
doctor_verbosity = "short"
interaction_verbosity = "short"
max_concurrent_agents = 3
```

## `[general]`

| Key                                  | Type           | Default                          | Notes                                                                               |
| ------------------------------------ | -------------- | -------------------------------- | ----------------------------------------------------------------------------------- |
| `max_concurrent_agents`              | integer        | `3`                              | Concurrent AUTO execution cap                                                       |
| `mcp_server_name`                    | string         | `"kagan"`                        | MCP server registration name                                                        |
| `worktree_base_ref_strategy`         | string         | `"local_if_ahead"`               | Base ref preference for worktree add/diff: `remote`, `local_if_ahead`, `local`      |
| `auto_review`                        | boolean        | `true`                           | Run AI review on completion                                                         |
| `auto_approve`                       | boolean        | `true`                           | Skip planner permission prompts                                                     |
| `auto_skill_discovery`               | boolean        | `false`                          | Enable trusted local skill metadata discovery for orchestrator `/skills`            |
| `require_review_approval`            | boolean        | `false`                          | Require review approval before merge                                                |
| `serialize_merges`                   | boolean        | `true`                           | Queue merge actions                                                                 |
| `default_worker_agent`               | string         | `"claude"`                       | Default worker agent                                                                |
| `worker_persona`                     | string         | Built-in implementer preset      | Global AUTO worker persona prompt                                                   |
| `orchestrator_persona`               | string         | Built-in orchestrator preset     | Global orchestrator/planning persona prompt                                         |
| `pr_reviewer_persona`                | string         | Built-in reviewer preset         | Global PR reviewer persona prompt                                                   |
| `default_pair_terminal_backend`      | string         | `"tmux"` (`"vscode"` on Windows) | Allowed: `tmux`, `nvim`, `vscode`, `cursor`, `windsurf`, `kiro`, `antigravity`      |
| `doctor_verbosity`                   | string         | `"short"`                        | Allowed: `tldr`, `short`, `technical` (used by `kagan doctor` and startup blockers) |
| `interaction_verbosity`              | string         | `"short"`                        | Allowed: `tldr`, `short`, `technical` (used for TUI notification/help detail level) |
| `default_model_claude`               | string or null | `null`                           | Optional default model                                                              |
| `default_model_opencode`             | string or null | `null`                           | Optional default model                                                              |
| `default_model_codex`                | string or null | `null`                           | Optional default model                                                              |
| `default_model_gemini`               | string or null | `null`                           | Optional default model                                                              |
| `default_model_kimi`                 | string or null | `null`                           | Optional default model                                                              |
| `default_model_copilot`              | string or null | `null`                           | Optional display preference                                                         |
| `default_model_goose`                | string or null | `null`                           | Optional default model                                                              |
| `default_model_openhands`            | string or null | `null`                           | Optional default model                                                              |
| `default_model_auggie`               | string or null | `null`                           | Optional default model                                                              |
| `default_model_amp`                  | string or null | `null`                           | Optional default model                                                              |
| `default_model_cagent`               | string or null | `null`                           | Optional default model                                                              |
| `default_model_stakpak`              | string or null | `null`                           | Optional default model                                                              |
| `default_model_vibe`                 | string or null | `null`                           | Optional default model                                                              |
| `default_model_vtcode`               | string or null | `null`                           | Optional default model                                                              |
| `core_idle_timeout_seconds`          | integer        | `180`                            | Core auto-stop timeout after idle                                                   |
| `core_autostart`                     | boolean        | `true`                           | Start core automatically when client connects                                       |
| `core_transport_preference`          | string         | `"auto"`                         | Allowed: `auto`, `socket`, `tcp`                                                    |
| `tasks_wait_default_timeout_seconds` | integer        | `1800`                           | Default timeout for `tasks_wait` (30 minutes)                                       |
| `tasks_wait_max_timeout_seconds`     | integer        | `3600`                           | Max allowed timeout for `tasks_wait` (60 minutes)                                   |

## `[agents.<name>]`

Example:

```toml
[agents.claude]
identity = "claude.com"
name = "Claude Code"
short_name = "claude"
protocol = "acp"
active = true
model_env_var = "ANTHROPIC_MODEL"

[agents.claude.run_command]
"*" = "npx claude-code-acp"

[agents.claude.interactive_command]
"*" = "claude"
```

Fields:

| Key                   | Type    | Notes                            |
| --------------------- | ------- | -------------------------------- |
| `identity`            | string  | Unique provider/agent identity   |
| `name`                | string  | Display name                     |
| `short_name`          | string  | Compact label                    |
| `protocol`            | string  | Currently `acp`                  |
| `active`              | boolean | Enable/disable this agent        |
| `model_env_var`       | string  | Env var used for model selection |
| `run_command`         | table   | OS-keyed commands for AUTO mode  |
| `interactive_command` | table   | OS-keyed commands for PAIR mode  |

OS keys for command tables: `macos`, `linux`, `windows`, `*`.

## `[refinement]`

| Key                 | Type        | Default           | Notes                        |
| ------------------- | ----------- | ----------------- | ---------------------------- |
| `enabled`           | boolean     | `true`            | Enable prompt refinement     |
| `hotkey`            | string      | `"ctrl+e"`        | Hotkey to trigger refinement |
| `skip_length_under` | integer     | `20`              | Skip short inputs            |
| `skip_prefixes`     | string list | `['/', '!', '?']` | Skip command-like inputs     |

## `[ui]`

| Key                       | Type        | Default               | Notes                                                      |
| ------------------------- | ----------- | --------------------- | ---------------------------------------------------------- |
| `skip_pair_instructions`  | boolean     | `false`               | Skip PAIR instruction modal                                |
| `tui_plugin_ui_allowlist` | string list | `["official.github"]` | Plugin IDs allowed to contribute declarative UI to the TUI |

## `[plugins]`

| Key         | Type        | Default (GitHub + NoOp) | Notes                   |
| ----------- | ----------- | ----------------------- | ----------------------- |
| `discovery` | string list | GitHub, NoOp plugins    | `module.path:ClassName` |

Third-party: install plugin → add to `discovery` → restart core. No remote fetch; import-based from local packages.

```toml
[plugins]
discovery = [..., "my_company.kagan_plugins.my_plugin:MyPlugin"]
```

## Environment variables passed into PAIR sessions

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
