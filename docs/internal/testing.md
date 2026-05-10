# Testing Guide

How to write tests for Kagan. Product scenarios are described in
[`docs/internal/features/web.md`](./features/web.md), [`tui.md`](./features/tui.md), and
[`chat.md`](./features/chat.md) — keep Tier A tests aligned with those documents.

______________________________________________________________________

## Philosophy

Tests are **behavioral specifications**. Each test describes what the system does from a user's
perspective — not how internal services are wired. A test name like
`test_auto_task_runs_to_completion_and_moves_to_review` is the spec.

**Real everything, fake agent.** Primary workflows use a real database (typically SQLite on disk
or temp dirs), real git (temp repos), and real HTTP/SSE/TUI where the scenario demands it. The
only intentional fake is **agent behavior**: `FakeAgentFactory` in Python behavioral tests,
`register_fake_backend()` / **`fake-agent`** for deterministic ACP (`kagan web --fake-agent`,
`KAGAN_FAKE_AGENT=1`), or the hermetic **echo ACP subprocess** in [`tests/integration/acp_real/`](../integration/acp_real/).

The suite today still contains **many unit tests and monkeypatched HTTP/server tests** — see
[`testing-rationalization-matrix.md`](testing-rationalization-matrix.md) for migration and deletion
candidates. New tests should prefer **real seams** over mocks unless you are in an explicit
contract carve-out (below).

______________________________________________________________________

## CI tiers and evidence

Evidence is split so PRs stay fast while regressions still surface.

### Tier A — PR gate (merge-blocking)

Run on every PR / local `uv run poe check`:

1. **Lint / typecheck / unit-fast slices** — existing project gates (`ruff`, `pyrefly`, web `tsc`, Vitest).
1. **Python behavioral** — `tests/core/`, `tests/mcp/`, `tests/tui/` specs via [`KaganDriver`](../../tests/helpers/driver.py) where applicable.
1. **Playwright smoke** — `cd packages/web && pnpm exec playwright test` against an isolated
   [`packages/web/playwright.config.ts`](../../packages/web/playwright.config.ts) server (temp DB,
   `KAGAN_FAKE_AGENT=1`, short `KAGAN_FAKE_AGENT_DELAY_MS` for managed runs). Covers board navigation,
   Chat workspace (`packages/web/e2e/workspace-chat.spec.ts`: board → Chat → session → user message),
   task/session overlay after a fake-agent run (`chat.spec.ts`), and related flows **without** mocking
   `fetch` or `apiClient`. Asserting **assistant streaming text** in the live DOM is optional Tier B
   follow-up if product gaps prevent deterministic chunk visibility in CI.

### Tier B — Nightly or manual / extended

- Full Vitest (`pnpm run web:test`), VS Code integration/e2e (`pnpm run vscode:test:*`), larger TUI
  snapshots.
- Playwright with `BASE_URL` pointing at a long-lived dev server (caller owns isolation).

### Tier C — Contract carve-outs (keep even if Tier A grows)

These catch regressions that **end-to-end UI tests rarely reach** or that **must stay sub-second**:

| Area                             | Location                                                                                                                                                                   | Why E2E alone is insufficient                                                                |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **ACP / StreamReader contracts** | [`tests/integration/acp_real/`](../../tests/integration/acp_real/)                                                                                                         | Real SDK types (`ClientSideConnection`) diverge from stubs; caught historical shipping bugs. |
| **Git / path security**          | [`tests/unit/core/test_git_validation.py`](../../tests/unit/core/test_git_validation.py), [`test_worktrees_security.py`](../../tests/unit/core/test_worktrees_security.py) | Must reject malicious paths without spinning a browser.                                      |
| **Wire / codegen drift**         | `scripts/generate_wire_types.py`, CI wire drift check                                                                                                                      | TS/Python envelope parity is structural.                                                     |
| **Slash / parser contracts**     | [`tests/unit/test_chat_commands.py`](../../tests/unit/test_chat_commands.py) (and related)                                                                                 | Pure grammar — cheap and precise; optional long-term if superseded by CLI smoke.             |

Feature narratives live in [`docs/internal/features/`](./features/) — map scenarios there to Tier A
Playwright or Python smoke tests when adding coverage.

______________________________________________________________________

## The DSL

Behavioral Python tests flow through `KaganDriver`. Test files never import from `kagan.core` internals,
repositories, or adapters for domain assertions. They import from `tests.helpers` and `kagan.core` (public API).

```text
Test Cases  →  KaganDriver (DSL)  →  CoreDriver / TuiDriver  →  Real system
```

```python
async def test_auto_task_runs_to_completion_and_moves_to_review(board):
    task = await board.create_task("Fix login bug")
    await board.run_task(task.id)
    await board.wait_for_status(task, REVIEW)
    assert await board.get_status(task) == REVIEW
```

The DSL grows organically. Write a test, discover what method you need, add it to the driver.

______________________________________________________________________

## Unit Tests

Unit tests live in `tests/unit/` — when they validate a **contract** (schema, shape, security edge)
that Tier A does not assert, or **platform-dependent** behavior (XDG paths, env sanitization).

- Unit tests **may** import from `kagan.core._*` private modules.
- Every unit test file must use `pytestmark = [pytest.mark.unit]`.
- If Tier A E2E + a behavioral test fully cover the same user-visible behavior, prefer deleting the duplicate unit test (see matrix).

______________________________________________________________________

## Real-stdio integration tests

Tests in `tests/integration/` exercise the *real* third-party SDK constructors and stdio path
without depending on a provider binary. They sit between unit and the optional `KAGAN_INTEGRATION_TESTS=1`
heavy suite.

The current suite (`tests/integration/acp_real/`) drives the real `acp.client.connection.ClientSideConnection`
over either:

1. **TCP-loopback streams** (`tests/helpers/acp_loopback.py`).
1. **Hermetic echo subprocess** (`tests/helpers/echo_agent.py`) via `sys.executable`.

- Files use `pytestmark = [pytest.mark.integration]` and run on every PR (no env-var gate).
- They must not require any agent binary on PATH; spawn-based tests use `sys.executable`.

______________________________________________________________________

## Isolation

Each test creates its own universe — fresh `tmp_path`, fresh SQLite, fresh git repo.
No shared state, no cleanup code, no execution-order dependencies.

```python
@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("test-project")
    await driver.add_repo(init_git_repo(tmp_path / "repo"))
    yield driver
    await driver.teardown()
```

Most tests are `async def`. Use `pytest-asyncio` with `asyncio_mode = "auto"`.

Exception: CLI surface tests that use Click's `CliRunner` are sync `def` tests. Keep them
small and focused on observable CLI behavior (help text, flags, exit codes, output order).

______________________________________________________________________

## Test Organization

Test files should mirror [`docs/internal/features/*.md`](./features/). Exact filenames evolve —
prefer the rationalization matrix over this stale tree.

```text
tests/
├── core/              # kagan.core behavioral
├── unit/              # contracts / security / parser edges
├── tui/               # Textual Pilot + KaganDriver
├── mcp/               # MCP tools via driver
├── server/            # REST/SSE (often monkeypatched today — migration candidates)
├── integration/acp_real/
├── cli/
└── helpers/           # KaganDriver, FakeAgent, echo_agent, acp_loopback
```

Name tests as specs: `test_<behavior>_<expected_outcome>`.

______________________________________________________________________

## Markers

```text
@pytest.mark.unit           # Implementation details (tests/unit/ only)
@pytest.mark.smoke          # Fast, core behaviors
@pytest.mark.slow           # Workspace provisioning, merges
```

Recommended future markers (document only until wired in CI):

```text
@pytest.mark.smoke_e2e      # Playwright / subprocess CLI smoke (optional job)
```

______________________________________________________________________

## The Fake Agent

Configure `FakeAgent` per-test:

```text
board.configure_agent(responses=["<complete/>"])
board.configure_agent(responses=["<blocked reason='needs API key'/>"])
board.configure_review_agent(verdict="approve", summary="LGTM")
```

Web / Playwright: [`packages/web/playwright.config.ts`](../../packages/web/playwright.config.ts) passes
`KAGAN_FAKE_AGENT=1` so `kagan web` registers the **`fake-agent`** backend (`kagan.core._fake_agent`).

______________________________________________________________________

## MCP Tests

Test tools through the router driver, not by calling tool functions directly:

```python
async def test_task_create_via_mcp(board):
    result = await board.mcp_call("task_create", {"title": "New feature"})
    assert result["status"] == "BACKLOG"
```

______________________________________________________________________

## TUI Tests

Use `app.run_test()` with `Pilot`. Use targeted waits (`wait_for_screen`,
`pilot.pause()`), never `wait_for_workers()` — orphaned background workers cause timeouts.

Smoke journeys: [`tests/tui/test_e2e_smoke_workspace.py`](../../tests/tui/test_e2e_smoke_workspace.py),
[`tests/tui/test_orchestrator_overlay.py`](../../tests/tui/test_orchestrator_overlay.py).

______________________________________________________________________

## Web Client Tests

### Vitest (component / hook)

- Tests live in `packages/web/src/**/*.test.ts` and `packages/web/src/**/*.test.tsx`.
- **Prefer** exercising pure render logic, hooks with **in-memory state**, or **real module imports**
  without stubbing `fetch` — avoid `vi.mock('@/lib/api/client')` for **product-critical journeys**
  those journeys belong in Playwright (Tier A).
- **Allowed**: mocking **browser-only** boundaries (e.g. `ResizeObserver`), tiny stubs for **non-Kagan**
  libraries when unavoidable.

```bash
cd packages/web && pnpm exec vitest run
```

### Playwright (Tier A product smoke)

- Tests live in [`packages/web/e2e/*.spec.ts`](../../packages/web/e2e/).
- The config starts **`uv run kagan web`** with a **throwaway DB** and **`KAGAN_FAKE_AGENT=1`** — tests hit a **real**
  same-origin API (see [`packages/web/playwright.config.ts`](../../packages/web/playwright.config.ts)).
- When `BASE_URL` is set, the runner skips `webServer`; you must provide isolation.
- Prefer **`data-testid`** / roles over CSS selectors.

```bash
cd packages/web && pnpm run build && pnpm exec playwright test
```

Relationship to Python:

- [`tests/server/`](../../tests/server/) exercises REST/SSE contracts directly (often with **monkeypatch**
  today — candidates for slim-down per [`testing-rationalization-matrix.md`](testing-rationalization-matrix.md)).
- Playwright proves **browser + server + DB + fake agent** integration.

Prioritize: **Playwright smoke flows → Vitest for pure UI → thin Python server duplicates**.

______________________________________________________________________

## CLI chat smoke

One-shot orchestrator prompt with **`fake-agent`**:

```bash
KAGAN_DATA_DIR=/tmp/isolated kagan chat --prompt "ping" --agent fake-agent
```

Tests register `register_fake_backend()` and set `KAGAN_DATA_DIR` — see
[`tests/cli/test_chat_oneshot_smoke.py`](../../tests/cli/test_chat_oneshot_smoke.py).

______________________________________________________________________

## VS Code Extension Tests

Three-layer split ([`docs/internal/architecture/vscode.md`](./architecture/vscode.md)):

1. Vitest — pure helpers.
1. `@vscode/test-cli` — extension host.
1. WDIO — real VS Code smoke.

Fake backend: prefer small **real HTTP** server in [`packages/vscode/test/helpers/`](../../packages/vscode/test/helpers/), not piled mocks.

```bash
pnpm run vscode:test:unit
pnpm run vscode:test:integration
pnpm run vscode:test:e2e
```

______________________________________________________________________

## Priority

What to test first:

1. **Core lifecycle** — task CRUD, transitions, managed runs, reviews
1. **Tier A Playwright** — board → workspace → chat send with fake agent
1. **ACP real-stdio** — `tests/integration/acp_real/`
1. **Edge cases** — concurrent starts, orphan cleanup (often behavioral Python today)

______________________________________________________________________

## Don'ts

- Don't mock **Kagan** HTTP clients in Playwright product smoke — use real `kagan web`.
- Don't mock services/repos/adapters in **behavioral** Python tests — fake the **agent** only.
- Don't assert on logs or mock call counts — assert observable outcomes.
- Don't use `monkeypatch` in new behavioral tests except **CLI/process seams** (documented in matrix).
- Don't depend on timing — wait for state changes, never naked `asyncio.sleep` in assertions.
- Don't import `kagan.core` private modules from **`tests/core/`**, **`tests/mcp/`**, **`tests/tui/`** behavioral tests.
