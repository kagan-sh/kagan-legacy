# Test Layout and Rules

Kagan tests are organized by package first, then by test type.

## Directory map

- `tests/*.py`: cross-boundary behavior/regression tests that are not package-scoped
- `tests/core/unit/`: deterministic core logic tests
- `tests/tui/snapshot/`: Textual visual snapshot regressions
- `tests/tui/smoke/`: critical TUI interaction journeys
- `tests/plugins/`: plugin implementation tests (unit by default)
- `tests/integration/`: real-agent integration/e2e coverage
- `tests/helpers/`: shared test helpers and fixtures

## Package/type policy

- Core defaults to `unit` tests. Keep these fast, isolated, and deterministic.
- Integration tests are `integration` + `e2e` by path and may require explicit env setup.
- TUI defaults to `snapshot` tests for rendering regressions.
- Plugin tests default to `unit`. Place them under `tests/plugins/<plugin-name>/`.
- Smoke tests are allowed for critical cross-boundary paths only.
- `core/fast`, `core/smoke`, and `mcp/*` path groups are supported by marker rules when those paths are populated.

## Authoring standard

- Write one behavior per test. Name tests as behavior specs, not implementation details.
- Use Arrange-Act-Assert with clear spacing; keep setup local to the test unless reuse is obvious.
- Assert externally visible behavior (return values, state transitions, emitted events, rendered output).
- Do not assert implementation internals unless they are part of a stable contract.
- Keep tests deterministic: freeze time/randomness and avoid network/system dependencies.
- Use real adapters only in smoke tests; keep core unit tests free from I/O.
- For MCP tests, assert request/response schema and explicit error semantics.
- For TUI tests, prefer interaction checks (`run_test` + pilot) and keep snapshots focused.
- Avoid tautologies (`assert True`, “call succeeded” without a behavioral assertion).
- Avoid brittle mocks that duplicate production logic; prefer fakes/fixtures at system boundaries.
- Keep helpers small and composable; delete one-off helpers when no longer reused.

## Unit test desiderata (core/unit)

- Isolated: each test builds its own fixture state and can run independently.
- Composable: tests can run in any order and in parallel.
- Deterministic: no wall-clock/random/network dependence without explicit control.
- Specific: failures should point to one behavior and one narrow code path.
- Behavioral: assertions must describe externally visible behavior, not wiring details.
- Structure-insensitive: avoid strict mock choreography that mirrors implementation steps.
- Fast: unit tests should complete quickly and avoid I/O.
- Writable: setup should stay simple; hard-to-write tests indicate interface problems.
- Readable: Arrange-Act-Assert should be obvious at a glance.
- Automated: no manual steps or environment interaction.
- Predictive: failures should strongly indicate real behavior regressions.
- Inspiring: keep signal high; remove tautologies and duplicate table-echo tests.

## Marker enforcement

`tests/helpers/fixtures/markers.py` (registered by `tests/conftest.py`) auto-applies package and type markers from the file path:

- `tests/core/fast/*` => `@pytest.mark.core` + `@pytest.mark.fast`
- `tests/core/unit/*` => `@pytest.mark.core` + `@pytest.mark.unit`
- `tests/core/smoke/*` => `@pytest.mark.core` + `@pytest.mark.smoke`
- `tests/mcp/contract/*` => `@pytest.mark.mcp` + `@pytest.mark.contract`
- `tests/mcp/smoke/*` => `@pytest.mark.mcp` + `@pytest.mark.smoke`
- `tests/tui/snapshot/*` => `@pytest.mark.tui` + `@pytest.mark.snapshot`
- `tests/tui/smoke/*` => `@pytest.mark.tui` + `@pytest.mark.smoke`
- `tests/plugins/*` => `@pytest.mark.plugins` + `@pytest.mark.unit`
- `tests/integration/*` => `@pytest.mark.integration` + `@pytest.mark.e2e`

Do not add package/type markers manually in test files. Marker ownership is path-based.

Snapshot tests are grouped into one xdist worker for deterministic output.

Additional explicit markers:

- `@pytest.mark.windows_ci`: focused Windows compatibility behavior checks run in the Windows CI job.
- `@pytest.mark.slow`: optional slow test selection.
- `@pytest.mark.property`: hypothesis/property test selection.
- `@pytest.mark.mock_platform_system("...")`: overrides `platform.system()` for a test.

## Common commands

```bash
uv run pytest
uv run pytest tests/ -v
uv run pytest tests/core/unit/ -v
uv run pytest tests/integration/ -v
uv run pytest tests/tui/snapshot/ -v
uv run pytest tests/tui/snapshot/ -n 0 -v --snapshot-update   # update snapshots
uv run poe check        # lint + typecheck + all tests
```
