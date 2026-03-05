# AGENTS.md — Kagan Codebase Guide

AI-powered Kanban TUI for autonomous development workflows.
Single Python package (`src/kagan/`) with six modules: `core`, `chat`, `tui`, `mcp`, `cli`, `plugins`.

## Architecture

```
src/kagan/
  core/      -- domain models, services, adapters, agents (NO dependency on chat/tui/mcp/cli/plugins)
  chat/      -- conversational abstractions, slash commands, REPL, orchestrator chat
  tui/       -- Textual UI (screens, widgets, modals, styles)
  mcp/       -- MCP server and tool registration
  cli/       -- CLI entry points (Click)
  plugins/   -- plugin system (entry-point discovery, import plugins)
```

**Dependency rule:** `core` has no dependency on `chat`, `tui`, `mcp`, `cli`, or `plugins`.
`chat` depends on `core` for agent spawning and event streaming. TUI/CLI import `chat` for REPL and chat features.
Plugins depend on `core` but not on `chat`, `tui`, `mcp`, or `cli`.

## Prerequisites

- Python 3.12–3.14, `uv` for dependency management
- tmux (for PAIR mode testing on macOS/Linux)
- Git (for worktree functionality)

## Build & Install

```bash
uv sync --dev                          # Install all dependencies
uv run poe install-local               # Install kagan as local CLI tool
uv run poe dev                         # Run app with hot reload
uv run kagan                           # Run the app
```

## Lint / Format / Typecheck

```bash
uv run poe fix                         # Auto-fix lint + format (run first!)
uv run poe lint                        # Ruff linter only
uv run poe format                      # Ruff formatter only
uv run poe typecheck                   # Pyrefly type checker
uv run poe deadcode                    # Vulture dead-code scan
uv run poe check                       # Full quality gate (lint+typecheck+deadcode+migrations+test)
uv run poe check-guardrails            # LOC budget + complexity check
```

## Testing

```bash
uv run pytest                          # Run all tests (parallel by default: -n auto)
uv run pytest tests/ -v                # Verbose
uv run pytest tests/ -n 0 -v           # Sequential (for debugging)

# Single file
uv run pytest tests/core/test_tasks.py -v

# Single class
uv run pytest tests/core/test_tasks.py::TestClassName -v

# Single test function
uv run pytest tests/core/test_tasks.py::test_create_task_appears_in_backlog_with_id -v

# By marker
uv run pytest tests/ -m "core and unit" -v
uv run pytest tests/ -m "mcp and contract" -v

# Database migration check
uv run poe db-migrations-check
```

### Test Markers

| Marker     | Purpose                                                    |
| ---------- | ---------------------------------------------------------- |
| `fast`     | Pure-logic tests, no I/O, no DB                            |
| `unit`     | Pure logic tests, no I/O                                   |
| `core`     | kagan-core behaviors                                       |
| `mcp`      | MCP protocol boundary                                      |
| `tui`      | Textual UI flows and rendering                             |
| `smoke`    | Critical user-path checks                                  |
| `contract` | Protocol/schema boundary tests                             |
| `property` | Property-based tests (Hypothesis)                          |
| `slow`     | Deselect with `-m "not slow"`                              |
| `e2e`      | Requires real agent binaries (`KAGAN_INTEGRATION_TESTS=1`) |

### Test Configuration

- **Framework:** pytest with `pytest-asyncio` (`asyncio_mode = "auto"`)
- **Parallelism:** `pytest-xdist` (`-n auto --dist=loadgroup`), use `-n 0` to disable
- **Default opts:** `-x -n auto --dist=loadgroup` (fail-fast, parallel)
- **Coverage:** `pytest-cov` on `src/kagan`, branch coverage enabled

### Test Conventions

- Tests live under `tests/{core,mcp,tui,plugins}/` by boundary, not implementation detail.
- Name tests as behavioral specs: `test_<behavior>_<expected_outcome>`.
- Each file has 2–6 tests, each test is 5–15 lines.
- Most tests are `async def`; CLI surface tests with Click's `CliRunner` are sync.
- Use `KaganDriver` DSL from `tests.helpers.driver` — never import from `kagan.core` internals.
- Import test harness APIs from `kagan.testing` (canonical surface).
- Use `tests.helpers` as the only shared test-support API (`.constants`, `.builders`, `.fakes`).
- Reuse fixtures from `tests/conftest.py` before adding local fixtures.
- **Real everything, fake agent.** Tests use real DB (in-memory SQLite), real git. Only fake is `FakeAgentFactory`.
- Don't mock services/repos/adapters — only mock the agent.
- Don't assert on logs, mock call counts, or DB rows — assert on observable state.
- Don't use `asyncio.sleep` — wait for state changes.

## Code Style

### Imports

Order: stdlib → third-party → local. Use string quotes for forward references.

```python
from typing import TYPE_CHECKING, Any, cast
from collections.abc import AsyncIterator, Mapping

from loguru import logger
from sqlmodel import Field, SQLModel, select

from kagan.core.enums import TaskStatus, WorkMode
from kagan.core.errors import NotFoundError

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
```

- Ruff enforces import sorting (`I` rules enabled).
- Use `TYPE_CHECKING` block for type-only imports to avoid circular dependencies.
- Absolute imports everywhere (no relative imports).
- For forward references in type annotations, use string quotes: `def foo() -> "SomeClass":`

### Type Annotations

- Always annotate function signatures and class attributes.
- Use `X | None` union syntax — **never** `Optional[X]`.
- Use `cast()` for type narrowing: `return cast("KaganApp", self.app)`.
- Use `TYPE_CHECKING` block for imports needed only by type checkers.
- Type checker: Pyrefly (not mypy). Some cross-module errors are suppressed in `pyproject.toml`.

### Naming Conventions

| Type            | Convention        | Example                           |
| --------------- | ----------------- | --------------------------------- |
| Classes         | PascalCase        | `TaskCard`, `KanbanScreen`        |
| Functions       | snake_case        | `get_all_tasks`, `_refresh_board` |
| Private         | underscore prefix | `_get_focused_card`, `_db.py`     |
| Constants       | UPPER_SNAKE       | `COLUMN_ORDER`, `MIN_WIDTH`       |
| Enums           | PascalCase/UPPER  | `TaskStatus.BACKLOG`              |
| Private modules | underscore prefix | `_transitions.py`, `_agent.py`    |

### Naming Conventions

| Type            | Convention        | Example                           |
| --------------- | ----------------- | --------------------------------- |
| Classes         | PascalCase        | `TaskCard`, `KanbanScreen`        |
| Functions       | snake_case        | `get_all_tasks`, `_refresh_board` |
| Private         | underscore prefix | `_get_focused_card`, `_db.py`     |
| Constants       | UPPER_SNAKE       | `COLUMN_ORDER`, `MIN_WIDTH`       |
| Enums           | PascalCase/UPPER  | `TaskStatus.BACKLOG`              |
| Private modules | underscore prefix | `_transitions.py`, `_agent.py`    |

### Error Handling

Custom error hierarchy rooted in `KaganError`:

```
KaganError
├── NotFoundError(entity, entity_id)
├── InvalidTransitionError(from_status, to_status)
├── WorktreeError
│   └── MergeConflictError(message, conflict_files)
├── AgentError
├── PreflightError
└── PluginError
    └── PluginSyncError
```

- All errors carry structured data (not just messages).
- Import errors from `kagan.core.errors` or `kagan.core` (re-exported).

### Formatting

- **Line length:** 100 characters (Ruff enforced).
- **Formatter:** Ruff (`ruff format`), docstring code formatting enabled.
- **Target:** Python 3.12.
- **Ruff rules:** E, F, I, UP, B, SIM, TCH, RUF (see `pyproject.toml` for ignores).

### Logging

- **Loguru only** — no stdlib `logging`. Import: `from loguru import logger`.
- One `logger.configure()` call in `kagan.core.__init__`. Other modules just use `logger` directly.
- Use `logger.bind(task_id=..., session_id=...)` for structured context.
- File sink at `~/.local/state/kagan/kagan.log`, 10 MB rotation, 3 retained.

### Models & Database

- **SQLModel** — one class is both Pydantic model and DB table definition.
- All DB operations via sync `sqlmodel.Session` (async is for agent/terminal ops, not DB).
- IDs are 8-char hex UUIDs: `uuid4().hex[:8]`.
- Timestamps use `datetime.now(UTC)`.

### Textual (TUI) Patterns

- **Hybrid CSS architecture**: Widget `DEFAULT_CSS` for scoped structural styling (lowest specificity), `CSS_PATH` TCSS files for global theme and screen layout (higher specificity). See `docs/internal/architecture/tui.md` § Styling Strategy.
- Messages as dataclasses: `@dataclass class Selected(Message): task: Task`.
- Button handlers with `@on(Button.Pressed, "#save-btn")`.
- Reactive attributes: `tasks: reactive[list[Task]] = reactive(list, recompose=True)`.
- Widget IDs in `__init__`: `super().__init__(id=f"card-{task.id}", **kwargs)`.

### Module Structure

- `core/` is flat (~27 files, no sub-packages). Private modules prefixed with `_`.
- Public API re-exported from `__init__.py` with explicit `__all__`.
- Fluent API: `client.tasks.create()`, `client.projects.list()` — namespace is the subject, don't repeat it in method names.

## Git & Commits

```bash
git config commit.gpgsign false        # Disable GPG signing for agent workflows
```

- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `ci:`, `perf:`.
- Semantic release on main branch.

## Database Migrations (Alembic)

```bash
uv run poe db-migration-generate "describe schema change"  # Generate revision
uv run poe db-migrations-check                              # Validate migrations
```

- Migration files in `src/kagan/core/adapters/db/migrations/versions/`.
- Autogenerated files are excluded from Ruff/Pyrefly/pre-commit — review SQL manually.

## Key Rules

1. **Hybrid CSS** — Widget `DEFAULT_CSS` for structural styling, TCSS files (`app.tcss`, `kanban.tcss`, `chat.tcss`) for theme/layout. Never inline `CSS = """..."""` on App.
1. **Async database** — All DB operations via SQLModel TaskRepository.
1. **Constants module** — Use `kagan.core.constants` for shared values.
1. **Module boundaries by change** — Split when responsibilities or change cadence diverge.
1. **Core owns execution** — Frontends call `task.run()`/`task.pair()`, never launch agents directly.
1. **No type suppression** — Never use `as any`, `@ts-ignore`, `# type: ignore` (except SQLModel `__tablename__` in `models.py`).

## Deep Dive

The `docs/internal/` directory contains detailed architecture and behavioral specs. Consult these before making non-trivial changes to a module:

| Module  | Architecture                                                                                                          | Behavioral Spec                     |
| ------- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| core    | `docs/internal/architecture/core.md` — client construction, fluent API, data models, event streaming, agent lifecycle | `docs/internal/features/core.md`    |
| chat    | `docs/internal/architecture/chat.md` — controller, slash commands, sessions, REPL, ACP integration                    | `docs/internal/features/chat.md`    |
| tui     | `docs/internal/architecture/tui.md` — screen hierarchy, state management, CSS strategy, chat integration              | `docs/internal/features/tui.md`     |
| mcp     | `docs/internal/architecture/mcp.md` — server structure, toolset registration, access control, transport               | `docs/internal/features/mcp.md`     |
| cli     | `docs/internal/architecture/cli.md` — command structure, bootstrap, lazy imports                                      | `docs/internal/features/cli.md`     |
| plugins | `docs/internal/architecture/plugins.md` — entry-point discovery, ABC hierarchy, provenance, GitHub import             | `docs/internal/features/plugins.md` |

Testing conventions and DSL guide: `docs/internal/testing.md`.

## Pitfalls

### core

- **Don't import from `_`-prefixed modules** — `_db.py`, `_transitions.py`, `_agent.py` etc. are private. Use the public API re-exported from `kagan.core.__init__`.
- **Don't use `asyncio.sleep` for waiting** — use `task.events.stream()` which signals reactively via `asyncio.Event`. The 5-second timeout is a safety net, not a polling interval.
- **Don't create a second `KaganCore`** — one instance per process. Frontends share it. The TUI creates it in `on_mount`, CLI in `_bootstrap.make_client()`, MCP in lifespan.
- **Don't skip the state machine** — task status transitions go through `_transitions.py`. Calling `task.set_status()` validates the transition; writing to the DB directly will corrupt state.
- **Don't put chat logic in core** — conversational abstractions (`ChatSession`, slash commands) live in `kagan.chat`. Core provides raw primitives only.
- **Unified Session model** — there's one `Session` model with a `mode` field (AUTONOMOUS or PAIR). Don't create separate models for different execution modes.

### tui

- **Never put business logic in TUI** — the TUI is a thin presentation shell. All state changes go through `self.app.core`. If you're writing an `if` that decides task behavior, it belongs in core.
- **Don't use `CSS = """..."""` on App or screens** — use `DEFAULT_CSS` on individual widgets for structural styles, and `.tcss` files for theme/layout. Inline CSS on App breaks the specificity model.
- **Don't call `refresh()` manually** — use `reactive` and `var` with watch methods. Textual's reactivity system handles re-renders.
- **Don't use `call_from_thread` or callbacks** — workers pull `task.events.stream()` and post Textual messages. One pattern, no bridging.
- **Don't import from `kagan.core._*`** — use `self.app.core` (the `KaganCore` instance) for all operations.

### mcp

- **Don't wrap `MCPServer`** — use `@mcp.tool()` directly. No abstraction layer over the python-sdk.
- **Tools are plain functions** — type hints drive the JSON schema. Don't construct schemas manually.
- **Don't add HTTP/SSE transport** — STDIO only. Hosts launch `kagan mcp` as a subprocess.
- **Access control is registration-time** — tools are filtered when registered based on `--readonly`/`--admin`/`--session-id` flags, not at call time.

### cli

- **Lazy imports only** — CLI command functions import `kagan.core`, `kagan.tui`, etc. inside function bodies, never at module top-level. This keeps `kagan --help` fast.
- **One error boundary** — `_CLIGroup` catches all exceptions. Don't add try/except in individual commands.
- **Use `_bootstrap.make_client()`** — don't construct `KaganCore` directly in commands.

### chat

- **Don't import from private submodules** — use public API from `kagan.chat.__init__` (`ChatController`, `run_chat`, slash command utilities).
- **ChatController owns the orchestrator turn** — TUI/CLI call `ChatController` methods; never spawn agents directly from chat components.
- **Slash commands are declarative** — register via `SlashCommandSpec`, not imperative registration calls.
- **Sessions persist in core settings** — chat sessions use `client.settings` for storage; no separate chat state DB.
- **REPL is stateful** — `run_chat_async` maintains conversation state; short-lived CLI commands use `run_chat` one-shot.

### plugins

- **Don't import from `_base.py` or `_github.py` directly** — use the public API from `kagan.plugins` (`PluginManager`, `ImporterPlugin`, etc.).
- **Always call `configure()` before `sync()`** — entry-point discovery instantiates plugins with no args. Configuration is a separate step.
- **Don't put plugin logic in core** — `kagan.plugins` depends on `kagan.core`, never the reverse.
- **Lazy imports in CLI/MCP** — `kagan.plugins` is imported inside function bodies, not at module top-level. This keeps startup fast.
- **Entry-point name must match `plugin.name`** — mismatches are skipped. The entry-point name in `pyproject.toml` is the canonical identifier.

### testing

- **Don't import from `kagan.core` internals in tests** — use `KaganDriver` DSL from `tests.helpers.driver`. Tests are behavioral specs, not implementation probes.
- **Don't mock services or repositories** — only mock the agent (`FakeAgentFactory`). Everything else runs real.
- **Don't assert on DB rows** — assert on observable state through the driver.
- **Don't add `asyncio.sleep` in tests** — wait for state changes via the driver's wait methods.

## Pre-Completion Checklist

Before marking a task complete, verify:

- [ ] `uv run poe fix` passes (auto-fix lint + format)
- [ ] `uv run poe typecheck` passes (Pyrefly)
- [ ] Tests pass for affected module: `uv run pytest tests/{module}/ -v`
- [ ] No new `# type: ignore` or `noqa` comments added
- [ ] If DB schema changed: `uv run poe db-migrations-check` passes
- [ ] Imports follow stdlib → third-party → local ordering with string quotes for forward references
- [ ] New code has type annotations on all function signatures
