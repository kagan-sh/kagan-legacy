# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-13
**Commit:** ddf5c5f
**Branch:** feat/remote-clients

## OVERVIEW

Kagan — AI-powered Kanban TUI (Python 3.12+/Textual) that orchestrates coding agents on your codebase. Supports 14 agent backends, auto/pair execution modes, MCP protocol, web dashboard (React 19), and encrypted remote pairing.

## STRUCTURE

```
kagan/
├── src/kagan/           # Python package (core logic, TUI, CLI, MCP, server)
│   ├── core/            # Domain: DB, models, agents, tasks, sessions, worktrees
│   ├── tui/             # Textual TUI: screens/, widgets/, styles/
│   ├── cli/             # Click CLI surface (entrypoint: `kagan`/`kg`)
│   ├── mcp/             # MCP server: toolsets/, prompts, resources
│   ├── server/          # HTTP/WS server: REST API, WebSocket, auth, web UI
│   ├── chat/            # CLI chat REPL: ACP streaming, commands, sessions
│   ├── crypto/          # X25519 key exchange, TLS, tokens, QR
│   ├── wire/            # Wire protocol: JSON schema for client-server sync
│   ├── integrations/    # GitHub integration
│   └── plugins/         # Plugin system (entry-point based)
├── packages/
│   ├── web/             # React 19 + jotai + Tailwind CSS 4 web dashboard (SPA)
│   └── wire/            # TypeScript wire types (generated from schema)
├── tests/               # pytest: core/, tui/, mcp/, server/, unit/, helpers/
├── scripts/             # Build/quality scripts (LOC budget, web build)
├── docs/                # MkDocs documentation site
├── registry/            # Persona repo whitelist
└── references/          # External reference repos (NOT part of build)
```

## WHERE TO LOOK

| Task                  | Location                                                  | Notes                                                                             |
| --------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Add CLI command       | `src/kagan/cli/`                                          | Click group in `main.py`, lazy-loaded modules                                     |
| Add MCP tool          | `src/kagan/mcp/toolsets/`                                 | One file per domain, use `get_context()`                                          |
| Add TUI screen        | `src/kagan/tui/screens/`                                  | Register in `app.py` SCREENS dict                                                 |
| Add TUI widget        | `src/kagan/tui/widgets/`                                  | Follow Textual compose pattern                                                    |
| Modify task lifecycle | `src/kagan/core/_transitions.py`                          | State machine for task status                                                     |
| Add agent backend     | `src/kagan/core/_agent.py`                                | AGENT_BACKENDS registry dict                                                      |
| Add DB migration      | `alembic -c alembic.ini revision --autogenerate -m "msg"` | Via `poe db-migration-generate`                                                   |
| Wire protocol change  | `src/kagan/wire/` + `packages/wire/`                      | Python schema → JSON → TypeScript                                                 |
| Web UI feature        | `packages/web/src/`                                       | React 19 + jotai + Tailwind CSS 4                                                 |
| API endpoint          | `src/kagan/server/_routes.py`                             | aiohttp routes                                                                    |
| Modify prompt system  | `src/kagan/core/_prompts.py`                              | Three-layer resolution: dotfile → defaults + behavioral → additional instructions |

## CONVENTIONS

- **Private modules**: Underscore prefix (`_tasks.py`, `_agent.py`) = internal; `client.py`, `models.py`, `enums.py` = public API
- **DB access**: Always via `_db_sync`/`_db_async` helpers wrapping SQLModel sessions
- **Async pattern**: `asyncio.to_thread` for DB ops, native async for I/O
- **Logging**: `loguru.logger` everywhere (not stdlib logging)
- **Error hierarchy**: All errors inherit `KaganError` (see `core/errors.py`)
- **LOC budget**: 2500 lines max per Python file (enforced via `poe check-loc`)
- **Complexity cap**: McCabe max-complexity = 20 (ruff C90)
- **Type annotations**: All public functions typed; pyrefly for typechecking (not mypy)
- **MCP annotations**: TC001/TC002/TC003 suppressed in `src/kagan/mcp/` — MCP evaluates annotations at runtime
- **Prompt resolution**: Three-layer pipeline in `core/_prompts.py` — dotfile override → code defaults + behavioral settings → additional instructions
- **Settings keys**: Behavioral controls (`default_execution_mode`, `review_strictness`, `planning_depth`, `auto_confirm_single_tasks`) + single `additional_instructions` field

## ANTI-PATTERNS (THIS PROJECT)

- **NEVER** suppress types with `as any` / `@ts-ignore` / `# type: ignore` without documented reason
- **NEVER** add direct SQLAlchemy session usage — always use `_db_sync`/`_db_async`
- **NEVER** import from `_`-prefixed modules outside their parent package
- **NEVER** modify migration files after they ship — generate a new migration
- **DO NOT** use stdlib `logging` — use `loguru`
- **DO NOT** put test fixtures in test files — use `tests/helpers/`
- RUF012 / RUF006 / SIM102 / SIM117 intentionally suppressed (see pyproject.toml)

## COMMANDS

```bash
# Development
uv run poe dev             # Run TUI in dev mode (textual dev server)
uv run poe test            # Run all tests (pytest, parallel)
uv run poe lint            # Ruff lint
uv run poe format          # Ruff format
uv run poe typecheck       # Pyrefly typecheck
uv run poe deadcode        # Vulture dead code detection
uv run poe check           # All: lint + typecheck + deadcode + test
uv run poe check-guardrails # LOC budget + complexity check
uv run poe fix             # Auto-fix lint + format

# Database
uv run poe db-migration-generate "migration message"
uv run poe db-migrations-check

# Web
uv run poe web-build       # Build React app → src/kagan/server/_web_static/
uv run poe docs-dev        # MkDocs dev server

# Install
uv run poe install-local   # Install as local CLI tool
uv run poe dev-setup       # Install + reset DB + stop daemon

# Snapshots
uv run poe snapshot-update # Update TUI snapshot tests
```

## DEEP DIVE DOCS

| Module | Architecture Doc                       | Features Doc                       |
| ------ | -------------------------------------- | ---------------------------------- |
| core   | `docs/internal/architecture/core.md`   | `docs/internal/features/core.md`   |
| tui    | `docs/internal/architecture/tui.md`    | `docs/internal/features/tui.md`    |
| server | `docs/internal/architecture/server.md` | `docs/internal/features/server.md` |
| web    | `docs/internal/architecture/web.md`    | `docs/internal/features/web.md`    |

Web deep dives:

- Architecture: `docs/internal/architecture/web.md`
- Features: `docs/internal/features/web.md`

## TypeScript / Web Checks

```bash
cd packages/web && pnpm exec vitest run
cd packages/web && pnpm exec playwright test   # requires running server (`kagan web`)
cd packages/web && pnpm run build
```

## Module Pitfalls

### web

- Do not bypass `apiClient`; keep HTTP calls centralized in `src/lib/api/client.ts`.
- Do not add global styles outside `src/app.css`; keep overrides inside component `<style>` blocks.
- Use `@/` path alias for imports (maps to `src/`).
- State management via jotai atoms — no class-based stores.

## NOTES

- `references/` contains external repos for study — excluded from build/test/lint
- `.claude/worktrees/` are agent worktrees — excluded from analysis
- `CLAUDE.md` is a symlink to `AGENTS.md`
- Pre-commit runs: gitleaks, ruff lint/format, pyrefly, mdformat, uv-lock
- CI pipeline: lint → fast-gate (unit) → test-pr (full suite, matrix: py3.12-3.14, ubuntu/macos/windows)
- Semantic release on main: conventional commits, beta prereleases
- Web UI is bundled as static files into the Python package at build time
