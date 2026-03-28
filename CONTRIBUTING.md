# Contributing to Kagan

## Prerequisites

| Tool                             | Install                                                             | Why                           |
| -------------------------------- | ------------------------------------------------------------------- | ----------------------------- |
| Python 3.12+                     | [python.org](https://www.python.org/downloads/)                     | Runtime                       |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh`                  | Package manager + task runner |
| Git                              | system package manager                                              | Version control               |
| Node 18+ / pnpm                  | [nodejs.org](https://nodejs.org) — only if touching `packages/web/` | Web dashboard                 |

`uv run poe` is the single entry point for all dev commands. [Poe the Poet](https://poethepoet.naez.com/) is installed automatically by `uv sync`.

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
uv run poe web-build       # build web dashboard
uv run poe eval            # run prompt evaluation suite
```

Run `uv run poe --help` for the full task list.

## Where to look

| Task              | Location                     | Notes                         |
| ----------------- | ---------------------------- | ----------------------------- |
| Add CLI command   | `src/kagan/cli/`             | Click group, lazy-loaded      |
| Add MCP tool      | `src/kagan/mcp/toolsets/`    | One file per domain           |
| Add TUI screen    | `src/kagan/tui/screens/`     | Register in app.py            |
| Add agent backend | `src/kagan/core/_agent.py`   | Dict entry in AGENT_BACKENDS  |
| Web UI feature    | `packages/web/src/`          | React 19 + jotai + Tailwind 4 |
| Modify prompts    | `src/kagan/core/_prompts.py` | Run `uv run poe eval` after   |

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

## Web dashboard

If your PR touches `packages/web/`:

```bash
uv run poe dev-web-hot     # backend + Vite hot reload (best for development)
uv run poe web-check       # typecheck + unit tests
uv run poe web-build       # bundle for Python package
```

The Vite dev server proxies API calls to a running Kagan backend. `dev-web-hot` starts both automatically.

See [`packages/web/README.md`](packages/web/README.md) for frontend-specific details and [`docs/internal/architecture/web.md`](docs/internal/architecture/web.md) for architecture.

## Prompt changes

If you modify `src/kagan/core/_prompts.py`:

1. Run `uv run poe eval` to benchmark against the eval suite
1. Update `evals/promptfooconfig.yaml` if adding new prompt behaviors
1. CI runs the eval automatically on PRs touching prompt files

## Pre-commit hooks

Hooks run automatically on commit: gitleaks, ruff lint/format, pyrefly typecheck, mdformat, uv-lock sync. Install once:

```bash
pre-commit install
```

## Persona preset safety

Kagan imports persona presets from public GitHub repos. Trusted repos are listed in `registry/persona_repo_whitelist.json`. To add your repo, open a PR with: what the preset contains, why it is safe, and how users can review it.

## Security

- Never include secrets in prompts or preset files
- Keep presets as human-reviewable JSON
- Prefer immutable references (commit SHA) when sharing versions
