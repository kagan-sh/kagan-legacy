# Contributing to Kagan

Canonical guide for developers working on the codebase. User documentation lives in `docs/`.

## Prerequisites

- Python 3.12 – 3.13
- `uv` for dependency management
- A terminal that supports Textual (for running the TUI)
- tmux (for PAIR mode testing on macOS/Linux)
- Git (for worktree functionality)

## Getting Started

Clone and install:

```bash
git clone https://github.com/aorumbayev/kagan.git
cd kagan
uv sync --dev
```

Run the app:

```bash
uv run kagan
```

## Development Mode

```bash
uv run poe dev
```

Hot reload enabled.

## Linting, Formatting, Typecheck, Tests

```bash
uv run poe fix        # Auto-fix lint issues + format (run this first!)
uv run poe lint       # Ruff linter
uv run poe format     # Format with ruff
uv run poe typecheck  # Pyrefly type checker
uv run poe deadcode   # Vulture dead-code scan (src/)
uv run pytest tests/ -v
```

Fast quality gate:

```bash
uv run poe check
```

## Testing

```bash
uv run pytest
# or
uv run pytest tests/ -v

# Single file
uv run pytest tests/core/unit/test_runtime_state_service.py -v

# Single class
uv run pytest tests/core/unit/test_runtime_state_service.py::TestRuntimeStateService -v

# Single test
uv run pytest tests/mcp/contract/test_mcp_v2_end_to_end.py::test_end_to_end_job_flow_uses_submit_wait_events_contract -v

# By marker
uv run pytest tests/ -m "core and unit" -v
uv run pytest tests/ -m "mcp and contract" -v
uv run pytest tests/ -m "tui and snapshot" -v
uv run pytest tests/ -n 0 -v          # Sequential (for debugging)
```

## UI Snapshots

```bash
uv run pytest tests/tui/snapshot/ -v
uv run pytest tests/tui/snapshot/ -n 0 -v --snapshot-update   # update snapshots
```

## Docs Preview

```bash
uv run poe docs-serve
```

Open `http://127.0.0.1:8000/` in your browser.

## GitHub Actions Workflow Validation

Before pushing workflow changes, validate locally with [act](https://github.com/nektos/act):

```bash
# Install act (macOS)
brew install act

# Validate all workflows
uv run poe workflows-check
```

This command:

1. Lists all workflows and triggers
1. Dry-runs CI (`ci.yml`)
1. Dry-runs CD (`cd.yaml`)
1. Dry-runs post-release update test (`post-release-update-test.yaml`)

`--dryrun` validates syntax and structure without running containers.

## Architecture

Kagan is a single Python package (`src/kagan/`) with four modules:

```
src/kagan/
  core/   -- domain models, services, adapters, IPC, agents
  tui/    -- Textual UI (screens, widgets, modals, styles)
  mcp/    -- MCP server bridge and tool registration
  cli/    -- CLI entry points
```

### Contract

Read the architecture contract before making structural changes:

- [`docs/concepts/architecture-overview.md`](docs/concepts/architecture-overview.md)

**Dependency rule:** `core` has no dependency on `tui`, `mcp`, or `cli`.
`tui` and `mcp` depend only on `core`. `cli` assembles entry points.

### Onboarding (30 min)

1. **Clone and install** (2 min): `git clone ... && cd kagan && uv sync --dev`
1. **Read this file** (5 min): Prerequisites, linting, tests
1. **Skim architecture** (5 min): `docs/concepts/architecture-overview.md`
1. **Run the app** (2 min): `uv run kagan`
1. **Run the quality gate** (30 sec): `uv run poe check`
1. **Pick a task** and explore the relevant module (10 min)

### Source Layout

```
src/kagan/
  core/                    # Domain models, services, adapters, agents, IPC
  tui/                     # app.py, ui/, styles/, keybindings, theme
  mcp/                     # server.py, tools.py, registrars
  cli/                     # CLI commands
  __main__.py              # Entry point
tests/
  core/                    # Unit + smoke
  mcp/                     # Contract + smoke
  tui/                     # Snapshot + smoke
```

### Placement

- Domain models, services, persistence, IPC/runtime contracts: `src/kagan/core/`
- MCP tool bindings/bridge: `src/kagan/mcp/`
- Textual screens/widgets/modals/styles/keybindings: `src/kagan/tui/`
- CLI commands: `src/kagan/cli/`
- Tests: `tests/{core,mcp,tui}/` by boundary, not implementation detail.

## Code Style

### Imports

Order: stdlib, third-party, local. Use `from __future__ import annotations`.

```python
from __future__ import annotations
from typing import TYPE_CHECKING, cast
from textual.app import ComposeResult
from kagan.core.constants import COLUMN_ORDER
from kagan.core.adapters.db.schema import Task

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
```

### Type Annotations

- Always annotate function signatures and class attributes
- Use `X | None` union syntax (not `Optional[X]`)
- Use `TYPE_CHECKING` block for type-only imports
- Use `cast()` for type narrowing: `return cast("KaganApp", self.app)`

### Naming Conventions

| Type      | Convention        | Example                           |
| --------- | ----------------- | --------------------------------- |
| Classes   | PascalCase        | `TaskCard`, `KanbanScreen`        |
| Functions | snake_case        | `get_all_tasks`, `_refresh_board` |
| Private   | underscore prefix | `_get_focused_card`               |
| Constants | UPPER_SNAKE       | `COLUMN_ORDER`, `MIN_WIDTH`       |
| Enums     | PascalCase/UPPER  | `TaskStatus.BACKLOG`              |

### Textual Patterns

```python
# Messages as dataclasses
@dataclass
class Selected(Message):
    task: Task


# Button handlers with @on decorator
@on(Button.Pressed, "#save-btn")
def on_save(self) -> None:
    self.action_submit()


# Reactive with recompose
tasks: reactive[list[Task]] = reactive(list, recompose=True)


# Widget IDs in __init__
def __init__(self, task: Task, **kwargs) -> None:
    super().__init__(id=f"card-{task.id}", **kwargs)
```

### CSS in TCSS Only

All styles go in `src/kagan/tui/styles/kagan.tcss`. Never use `DEFAULT_CSS` in Python.

## Commits

Disable GPG signing in agent workflows:

```bash
git config commit.gpgsign false
```

## Key Rules

1. **CSS in `.tcss` only** - All styles in `kagan.tcss`, never use `DEFAULT_CSS`
1. **Async database** - All DB operations via SQLModel TaskRepository
1. **Constants module** - Use `kagan.core.constants` for shared values
1. **Property assertions** - Use `@property` with `assert` for required state
1. **Module boundaries by change** - Split modules when responsibilities or change cadence diverge; keep cohesive code together even if large.

## Notes

- Kagan uses Textual; styles should live in `src/kagan/tui/styles/kagan.tcss`
- See `AGENTS.md` for agent workflow and coding guidelines
