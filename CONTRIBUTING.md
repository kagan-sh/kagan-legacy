# Contributing to Kagan

## Prerequisites

| Tool                             | Install                                            | Why                           |
| -------------------------------- | -------------------------------------------------- | ----------------------------- |
| Python 3.12+                     | [python.org](https://www.python.org/downloads/)    | Runtime                       |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager + task runner |
| Git                              | system package manager                             | Version control               |

`uv run poe` is the single entry point for all dev commands. [Poe the Poet](https://poethepoet.natn.io/) is installed automatically by `uv sync`.

## Quick start

```bash
git clone https://github.com/kagan-sh/kagan.git && cd kagan
uv sync --dev              # install all dependencies
pre-commit install          # install git hooks
uv run poe dev-setup       # install CLI + reset DB
uv run poe check           # lint + typecheck + deadcode + test
```

## Key commands

```bash
uv run poe dev             # launch TUI in dev mode
uv run poe test            # run all Python tests
uv run poe fix             # auto-fix lint + format
uv run poe check           # all quality gates
uv run poe eval            # run prompt evaluation suite
```

Run `uv run poe --help` for the full task list.

## Where to look

| Task              | Location                            | Notes                                                                  |
| ----------------- | ----------------------------------- | ---------------------------------------------------------------------- |
| Add CLI command   | `src/kagan/cli/`                    | Click group, lazy-loaded                                               |
| Add MCP tool      | `src/kagan/mcp/toolsets/`           | One file per domain                                                    |
| Add TUI screen    | `src/kagan/tui/screens/`            | Register in `app.py` SCREENS dict (see below)                          |
| Add agent backend | `src/kagan/core/agents/registry.py` | Add backend spec; update `SUPPORTED_AGENT_BACKENDS` if it ships in 1.0 |
| Modify prompts    | `src/kagan/core/prompts/`           | Run `uv run poe eval` after                                            |

## Module ownership

Each package under `src/kagan/core/` owns a specific concern. Patch the right layer:

| Module / package           | Owns                                                                     | Go elsewhere if…                                               |
| -------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------- |
| `core/tasks/service.py`    | Task CRUD, worktree coordination                                         | Adding session/ACP logic → `sessions/service.py`               |
| `core/sessions/service.py` | Session lifecycle, ACP streaming                                         | Adding task-level features → `tasks/service.py`                |
| `core/agents/registry.py`  | Agent backend registry + launcher                                        | Adding session features → `sessions/service.py`                |
| `core/transitions.py`      | Status state machine — the only place to add valid (from→to) transitions | You want to bypass the funnel — don't                          |
| `core/prompts/`            | Three-layer prompt resolution                                            | Changing behavioral defaults → settings layer, not prompt code |
| `core/board/events.py`     | DB-persisted task/session event streams                                  | Adding in-memory signals → wire frames                         |

Surfaces (`cli`, `tui`, `mcp`) should import domain behavior through **`kagan.core.api`** plus stable submodules (`models`, `enums`, `errors`, `chat`, `doctor_checks`, `git`, `format`).

Do not use `from __future__ import annotations` anywhere in the repo (`src/`, `scripts/`, `evals/`, `tests/`).

## Package boundaries

Internal packages (`persistence`, `tasks`, `sessions`, `agents`, `board`, etc.) are not importable from surfaces. This is enforced by `import-linter` (see `[tool.importlinter]` in `pyproject.toml`).

If you need a new cross-package capability, expose it through `kagan.core.api` — do not import internal modules from `kagan.tui`, `kagan.cli`, or `kagan.mcp`.

You will see this failure as `ERROR — contract 'kagan.tui private module access'` when running
`uv run poe check-boundaries`.

## House rules

- Mutate `task.status` and `session.status` through `transition_task` / `transition_session`; add missing valid transitions to the funnel instead of bypassing it.
- Use `db_sync` / `db_async` helpers for database access. Do not open raw SQLModel sessions in feature code.
- Use `loguru.logger` for application logging, not stdlib `logging`.
- Do not write `task.status = ...` or `session.status = ...` directly outside the documented low-level DB callback exceptions.

## Adding a TUI screen

1. Create `src/kagan/tui/screens/your_screen.py` — subclass `Screen` (Textual)
1. Register it in `src/kagan/tui/app.py` under `SCREENS`:
   ```python
   SCREENS = {
       ...
       "your-screen": YourScreen,
   }
   ```
1. Push it from any screen or app method with `self.app.push_screen("your-screen")` or
   `self.app.push_screen(YourScreen())`

## Internal docs

Rich architecture and feature docs live in `docs/internal/` (not published to the docs site). Start here:

1. **[`docs/internal/README.md`](docs/internal/README.md)** — reading order
1. **[`docs/internal/testing.md`](docs/internal/testing.md)** — test philosophy, DSL, patterns
1. **`docs/internal/architecture/*.md`** — per-module implementation guides
1. **`docs/internal/features/*.md`** — per-module behavioral specs (map 1:1 to test files)

## Commit conventions

This project uses [conventional commits](https://www.conventionalcommits.org/) for semantic release:

```
feat: add new agent backend for X
fix: prevent merge conflict on concurrent tasks
docs: update GitHub Models guide
refactor: extract shared prompt resolver
test: add edge case for empty acceptance criteria
```

## What to submit

- Small, focused PRs — one concern per PR
- Tests for behavior changes
- Run `uv run poe check` before pushing

## Prompt changes

If you modify `src/kagan/core/prompts/`:

1. Run `uv run poe eval` to benchmark against the eval suite
1. Update `evals/promptfooconfig.yaml` if adding new prompt behaviors
1. CI runs the eval automatically on PRs touching prompt files

## Pre-commit hooks

Hooks run automatically on commit: gitleaks, ruff lint/format, pyrefly typecheck, mdformat, uv-lock sync. Install once:

```bash
pre-commit install
```

## Security

- Never include secrets in prompts or preset files
- Keep presets as human-reviewable JSON
- Prefer immutable references (commit SHA) when sharing versions
