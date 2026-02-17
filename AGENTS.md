# AGENTS.md - Kagan Coding Agent Guide

Purpose: give coding agents the minimum high-signal rules needed to ship safe, testable changes.

## Rule Scope and Precedence

- This file is the canonical repo-wide agent instruction file.
- `.github/copilot-instructions.md` defers to this file.
- No Cursor rules are currently present (`.cursorrules` and `.cursor/rules/` absent).
- Keep this file concise and action-oriented; avoid architecture essays and ticket-era process detail.
- Keep entries short, self-contained, and broadly applicable.
- Avoid conflicting instructions across files.
- Put file-type or directory-specific rules in `.github/instructions/*.instructions.md` if needed.

## Engineering Principles (PEP 20, Pragmatic Form)

- Prefer explicit over implicit behavior.
- Prefer simple, readable solutions over clever ones.
- Avoid ambiguity; define assumptions in code/tests.
- Fail loudly on invalid state unless failure is intentionally suppressed.
- Keep one obvious way to do routine tasks (build, test, lint, release).
- Follow Zen of Python as a hard constraint: explicit, simple, readable, and one obvious way.

## Instruction Maintenance

- Treat this file as operational policy, not a design document.
- Keep critical commands and rules near the top.
- Remove stale migration-era instructions once they stop affecting behavior.
- Prefer additive, scoped updates over large rewrites.

## Setup

```bash
uv sync --dev
uv run kagan
uv run poe dev
```

## Build / Lint / Format / Typecheck

```bash
uv build --wheel --package kagan
uv run poe lint
uv run poe format
uv run poe fix
uv run poe typecheck
uv run poe check
uv run pre-commit run --all-files
```

## Test Commands

```bash
uv run pytest
```

Or with paths/filters:

```bash
uv run pytest tests/ -v
uv run pytest tests/core/unit/test_runtime_state_service.py -v
uv run pytest tests/ -k "runtime and refresh" -v
uv run pytest tests/ -m "core and unit" -v
uv run pytest tests/ -n 0 -v   # sequential (debug/snapshot update)
uv run pytest tests/tui/snapshot/ -n 0 -v --snapshot-update   # update snapshots
```

## Pytest and Marker Policy

- Default addopts include `-n auto --dist=loadgroup`.
- Snapshot tests use `xdist_group` and run with `-n auto`; only `--snapshot-update` requires `-n 0`.
- Package/type markers are path-assigned in `tests/conftest.py`.
- Do not manually add: `core`, `mcp`, `tui`, `plugins`, `fast`, `unit`, `contract`, `snapshot`, `smoke`.
- `integration` marker is deprecated/disallowed for explicit use.
- Do not write tautology tests (tests that only restate implementation internals).
- Prefer tests that validate useful user-facing behavior and observable outcomes.

## Test Value Gate (Mandatory)

- Add tests only for user-visible behavior, API/contract guarantees, or real regressions.
- Do not add tautology tests or pass-through wiring tests already covered elsewhere.
- Search first (`rg`) for existing coverage and extend current tests instead of adding near-duplicates.
- Reuse fixtures/helpers from `tests/**/conftest.py` and `tests/helpers/**`; avoid local fixtures when reusable ones exist.
- Every new test must fail on the pre-fix path and pass after the fix.
- If a new fixture is unavoidable, add a one-line comment explaining why shared fixtures are insufficient.
- Before commit, remove or merge redundant tests introduced during the change.

Path mapping:

- `tests/core/fast/*` -> `core`, `fast`
- `tests/core/unit/*` -> `core`, `unit`
- `tests/core/smoke/*` -> `core`, `smoke`
- `tests/mcp/contract/*` -> `mcp`, `contract`
- `tests/mcp/smoke/*` -> `mcp`, `smoke`
- `tests/tui/snapshot/*` -> `tui`, `snapshot`
- `tests/tui/smoke/*` -> `tui`, `smoke`
- `tests/plugins/*` -> `plugins`, `unit`

## Code Style

- Ruff is source of truth (`line-length = 100`, target `py312`).
- Use `from __future__ import annotations` in Python modules.
- Import order:
  - standard library
  - third-party
  - local `kagan.*`
  - type-only imports under `if TYPE_CHECKING:`
- Type annotate public APIs and meaningful internal boundaries.
- Prefer `X | None` over `Optional[X]`.
- Use `Protocol` for service interfaces/boundaries.
- Naming:
  - classes: `PascalCase`
  - functions/variables: `snake_case`
  - constants: `UPPER_SNAKE_CASE`
  - private members: `_leading_underscore`

## Error Handling and Safety

- Never use bare `except:`.
- Catch specific exceptions when possible.
- Use `ValueError` for invalid input/data-contract violations.
- Use `RuntimeError` for runtime/environment failures.
- Preserve causal chain with `raise ... from exc`.
- Broad `except Exception` only at explicit resilience boundaries.
- In critical core files, broad exceptions require `quality-allow-broad-except`.
- In critical core files, unbounded queues require `quality-allow-unbounded-queue`.

## Stable Architecture Boundaries

- Core daemon owns mutable runtime state.
- SQLite is the single persisted source of truth.
- DB writes happen through core services/adapters only.
- TUI, MCP, and CLI are frontends over core operations.
- No client-side mutation fallback around core.
- Direct subprocess calls are only allowed in:
  - `src/kagan/core/adapters/process.py`

### Module Map

**Domain layer** — `src/kagan/core/domain/`
- `enums.py` — canonical enums (TaskStatus, TaskType, etc.)
- `errors.py` — domain-specific error types
- `task_rules.py` — task lifecycle/transition rules

**Command dispatch** — `src/kagan/core/commands/`
- `tasks.py`, `projects.py`, `automation.py`, `workspaces.py`, `plugins.py` — command handlers by capability
- `_parsing.py` — input parsing helpers (limits, offsets, timeouts)
- `_serialization.py` — response building and output formatting
- `__init__.py` — `CommandRouter` dispatches `(capability, method)` pairs to handlers

**Policy** — `src/kagan/core/policy.py`
- Consolidated auth/security: `CapabilityProfile`, `AuthorizationPolicy`, `SessionBinding`, `@command` decorator, `RequestContext`
- Merged from the former `security.py`, `session_binding.py`, `expose.py`, `request_context.py`

**SDK** — `src/kagan/sdk/`
- `_client.py` — `KaganSDK` typed client
- `_transport.py` — `SDKTransport` (IPC communication)
- `_types.py` — response dataclasses
- `_errors.py` — `SDKError` hierarchy

**MCP server** — `src/kagan/mcp/`
- `server.py` — FastMCP server setup
- `tools.py` — MCP tool definitions (bridge layer)
- `_tool_gen.py` — tool registration/generation
- `_response_models.py` — MCP response models
- `_truncation.py` — response size management

### Compatibility Shims (transitional)

These modules delegate to `core/commands/` and exist only for backward-compatible imports in tests:
- `core/request_handlers/` — handler facades wrapping command functions
- `core/request_dispatch_map/` — dispatch map built from `CommandRouter`
- `core/request_handler_support.py` — re-exports from `commands/_parsing.py` and `commands/_serialization.py`

## TUI Rules

- Keep Textual styling in:
  - `src/kagan/tui/styles/kagan.tcss`
- Do not add `DEFAULT_CSS` in Python widgets/screens.
- Reuse shared keybindings from:
  - `src/kagan/tui/keybindings.py`

## Docs and Workflow Validation

```bash
uv run poe docs-serve
uv run poe docs-build
uv run poe workflows-check
```

- Any user-facing behavior change must be documented in user-facing docs in the same change.

## Commit Conventions

- Allowed tags:
  - `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `style`, `refactor`, `test`
- Keep commits small and single-purpose.
- In CI/automation contexts, disable GPG signing if needed:
  - `git config commit.gpgsign false`
- Before push:
  - `uv run poe fix`
  - `uv run poe check`

## Done Checklist for Agents

- Ran the smallest relevant tests first, then broader gates as needed.
- Do not claim completion without executing verification commands.
- Updated tests/docs when behavior or contracts changed.
- Confirmed tests exercise user-facing behavior (not implementation tautologies).
- Kept changes within existing boundaries unless task explicitly required boundary changes.
- Left a short summary with changed files and verification commands executed.
