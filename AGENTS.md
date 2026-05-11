# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-13
**Commit:** ddf5c5f
**Branch:** feat/remote-clients

## OVERVIEW

Kagan — AI-powered Kanban TUI (Python 3.12+/Textual) that orchestrates coding agents on your codebase. Supports 14 agent backends, auto/pair execution modes, MCP protocol, and a bundled web dashboard (React 19).

## STRUCTURE

```
kagan/
├── src/kagan/           # Python package (core logic, TUI, CLI, MCP, server)
│   ├── core/            # Domain: DB, models, agents, tasks, sessions, worktrees
│   ├── tui/             # Textual TUI: screens/, widgets/, styles/
│   ├── cli/             # Click CLI surface (entrypoint: `kagan`/`kg`)
│   ├── mcp/             # MCP server: toolsets/, prompts, resources
│   ├── server/          # HTTP server: REST API, SSE streaming, auth, web UI
│   ├── chat/            # CLI chat REPL: ACP streaming, commands, sessions
│   ├── crypto/          # X25519 key exchange, TLS, tokens, QR
│   ├── wire/            # (compat shim) Re-exports envelope types
│   └── integrations/    # Typed native integrations (GitHub, future: Jira/Linear)
├── packages/
│   ├── vscode/          # VS Code extension: chat participant, tree view, SCM, reviews
│   ├── web/             # React 19 + jotai + Tailwind CSS 4 web dashboard (SPA)
│   └── wire/            # (removed — TS types now generated from response models)
├── tests/               # pytest: core/, tui/, mcp/, server/, unit/, helpers/
├── scripts/             # Build/quality scripts (LOC budget, web build)
├── docs/                # MkDocs documentation site
├── registry/            # Persona repo whitelist
└── references/          # External reference repos (NOT part of build)
```

## WHERE TO LOOK

| Task                  | Location                                                                                                                        | Notes                                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Add CLI command       | `src/kagan/cli/`                                                                                                                | Click group in `main.py`, lazy-loaded modules                                                                              |
| Add MCP tool          | `src/kagan/mcp/toolsets/`                                                                                                       | One file per domain, use `get_context()`                                                                                   |
| Add TUI screen        | `src/kagan/tui/screens/`                                                                                                        | Register in `app.py` SCREENS dict                                                                                          |
| Add TUI widget        | `src/kagan/tui/widgets/`                                                                                                        | Follow Textual compose pattern                                                                                             |
| Modify task lifecycle | `src/kagan/core/_transitions.py`                                                                                                | State machine for task status                                                                                              |
| Add agent backend     | `src/kagan/core/_agent.py`                                                                                                      | AGENT_BACKENDS registry dict                                                                                               |
| Add DB migration      | `alembic -c alembic.ini revision --autogenerate -m "msg"`                                                                       | Via `poe db-migration-generate`                                                                                            |
| Wire protocol change  | `src/kagan/server/responses.py`                                                                                                 | Response models → JSON Schema → TypeScript via `scripts/generate_wire_types.py`                                            |
| Add SSE event channel | `src/kagan/server/_event_routes.py`                                                                                             | Register route + hook into `register_event_routes(mcp)` in `server.py`                                                     |
| Add frame consumer    | `src/kagan/tui/_event_source.py` / `packages/web/src/lib/hooks/use-entry-stream.ts` / `packages/vscode/src/api/event-source.ts` | TUI: implement `InProcEventSource`/`HttpEventSource` interface; Web: use `useEntryStream`; VS Code: use `KaganEventSource` |
| Web UI feature        | `packages/web/src/`                                                                                                             | React 19 + jotai + Tailwind CSS 4                                                                                          |
| API endpoint          | `src/kagan/server/_routes.py`                                                                                                   | Starlette routes via FastMCP                                                                                               |
| Add integration       | `src/kagan/core/integrations/`                                                                                                  | Implement Integration protocol, register in `all_enabled()`                                                                |
| VS Code feature       | `packages/vscode/src/providers/`                                                                                                | One provider per VS Code API surface                                                                                       |
| VS Code command       | `packages/vscode/src/commands/`                                                                                                 | Register in `extension.ts`                                                                                                 |
| Modify prompt system  | `src/kagan/core/_prompts.py`                                                                                                    | Three-layer resolution: dotfile → defaults + behavioral → additional instructions                                          |

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

### Status mutations

`task.status` and `session.status` may only be written through
`kagan.core.transitions.transition_task` and `transition_session`. Direct
assignments (`task.status = ...`) bypass review gates and are forbidden in
external-facing code paths (REST routes, MCP tools, CLI commands).
The funnel functions enforce the (from, to) matrix at runtime; if you
encounter a transition the matrix does not cover, add a match arm with the
appropriate guard rather than working around the funnel.

Exceptions: raw DB writes inside `_db_sync` / `_db_async` callbacks that
operate at the SQLAlchemy layer (e.g. `_orphan_reap.py`, `_sessions.py`
internal helpers) may assign `.status` directly when they cannot call the
async funnel from within a sync transaction context.

## ANTI-PATTERNS (THIS PROJECT)

- **NEVER** suppress types with `as any` / `@ts-ignore` / `# type: ignore` without documented reason
- **NEVER** add direct SQLAlchemy session usage — always use `_db_sync`/`_db_async`
- **NEVER** import from `_`-prefixed modules outside their parent package
- **NEVER** modify migration files after they ship — generate a new migration
- **DO NOT** use stdlib `logging` — use `loguru`
- **DO NOT** put test fixtures in test files — use `tests/helpers/`
- **DO NOT** write `task.status = X` outside a `_db_sync`/`_db_async` callback or the files listed above — use `transition_task` instead
- **DO NOT** use `/api/chat/sessions/{id}/watch` or `/messages?after_id=` — these were removed in W9a cleanup; subscribe via `GET /api/sessions/{id}/events` with `Last-Event-ID` for resume
- **DO NOT** write `task.status` or `session.status` directly in EventLog frame producers — frames are supplementary; status transitions still go through `transition_task` / `transition_session`
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
| vscode | `docs/internal/architecture/vscode.md` | `docs/internal/features/vscode.md` |

## TypeScript / Web Checks

```bash
cd packages/web && pnpm exec vitest run
cd packages/web && pnpm exec playwright test   # requires running server (`kagan web`)
cd packages/web && pnpm run build
```

## TypeScript / VS Code Extension Checks

```bash
cd packages/vscode && pnpm run check-types
cd packages/vscode && pnpm run test:unit
cd packages/vscode && pnpm run test:integration
cd packages/vscode && pnpm run test:e2e
```

## Module Pitfalls

### web

- Do not bypass `apiClient`; keep HTTP calls centralized in `src/lib/api/client.ts`.
- Do not add global styles outside `src/app.css`; keep overrides inside component `<style>` blocks.
- Use `@/` path alias for imports (maps to `src/`).
- State management via jotai atoms — no class-based stores.

### vscode

- Event type strings come from `EVENT_TYPE` / `SSE_TYPE` consts in `api/types.ts` — never hand-type event strings.
- ACP payloads nest tool data under `payload.acp` — use `acpPayload()` helpers, not direct field access.
- All HTTP calls go through `KaganClient` — no raw `fetch` in providers.
- One provider per VS Code API surface — do not mix concerns.

## NOTES

- `references/` contains external repos for study — excluded from build/test/lint
- `.claude/worktrees/` are agent worktrees — excluded from analysis
- `CLAUDE.md` is a symlink to `AGENTS.md`
- Pre-commit runs: gitleaks, ruff lint/format, pyrefly, mdformat, uv-lock
- CI pipeline: lint → fast-gate (unit) → test-pr (full suite, matrix: py3.12-3.14, ubuntu/macos/windows)
- Semantic release on main: conventional commits, beta prereleases
- Web UI is bundled as static files into the Python package at build time
