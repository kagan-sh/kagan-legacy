# Testing Guide

How to write tests for Kagan.

______________________________________________________________________

## Philosophy

Tests are **behavioral specifications**. Each test describes what the system does from a user's
perspective — not how internal services are wired. A test name like
`test_auto_task_runs_to_completion_and_moves_to_review` is the spec.

**Real everything, fake agent.** Tests use a real database (in-memory SQLite), real git
(temp repos), and real services. The only fake is `FakeAgentFactory`, which simulates agent
responses. If you're mocking a service, you're writing a unit test — put it elsewhere.

______________________________________________________________________

## The DSL

All tests flow through `KaganDriver`. Test files never import from `kagan.core` internals,
repositories, or adapters. They import from `tests.helpers` and `kagan.core` (public API).

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

Unit tests live in `tests/unit/` — but only when they earn their place. A unit test earns
its place when it validates a **contract** (schema, shape, data structure) that acceptance
tests exercise but don't assert on directly, or when it tests **platform-dependent edges**
(e.g. XDG path fallback) that acceptance tests can't reach.

- Unit tests **may** import from `kagan.core._*` private modules.
- Every unit test file must use `pytestmark = [pytest.mark.unit]`.
- If an acceptance test covers the same behavior, the unit test does not belong.

______________________________________________________________________

## Real-stdio integration tests

Tests in `tests/integration/` exercise the *real* third-party SDK constructors and stdio path
without depending on a provider binary. They sit between unit and the `KAGAN_INTEGRATION_TESTS=1`
end-to-end suite, and they catch contracts unit-stubs falsify by accepting too much.

The current suite (`tests/integration/acp_real/`) drives the real `acp.client.connection.ClientSideConnection`
over either:

1. **TCP-loopback streams** (`tests/helpers/acp_loopback.py`) — yields real `asyncio.StreamReader`
   / `asyncio.StreamWriter` pairs via `asyncio.start_server` + `asyncio.open_connection`. Catches
   `isinstance(asyncio.StreamReader)` gates and read-method shape contracts in milliseconds.
2. **A hermetic echo subprocess** (`tests/helpers/echo_agent.py`, vendored from the ACP SDK
   examples) invoked via `sys.executable`. Speaks the real ACP wire protocol, exercises
   handshake → session → prompt → notification → teardown end-to-end.

Add a test here whenever a regression escapes through stubbed SDK fakes. Example: 0.19.0b34
shipped a `ClientSideConnection requires asyncio StreamWriter/StreamReader` runtime error
because the always-on suite stubbed `_FakeConnection` and never constructed the real SDK
type. Both checks now live in `acp_real/test_stream_wrappers.py`.

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

Test files mirror sections in `docs/internal/features/*.md` (one file per feature section):

```text
tests/
├── core/                                # kagan.core (behavioral)
│   ├── test_cli_surface.py              # CLI help text, exit codes (snapshot carve-out)
│   ├── test_client_lifecycle.py          # Client construction, context manager, bootstrap
│   ├── test_projects_and_repos.py
│   ├── test_tasks.py
│   ├── test_task_lifecycle.py
│   ├── test_workspaces.py
│   ├── test_sessions_attached.py
│   ├── test_sessions_detached.py
│   ├── test_reviews.py
│   └── test_settings_and_audit.py
├── unit/                                # schema/contract validation only
│   ├── test_agent_registry.py           # backend registry data structure
│   ├── test_config_paths.py             # XDG/env path resolution edges
│   ├── test_acp_session.py              # ACP session handling edges
│   ├── test_agent_spawn_acp.py          # ACP agent spawn edges
│   ├── test_chat_commands.py            # Chat slash command parsing
│   ├── test_chat_policy.py              # Chat policy logic
│   ├── test_secret_scrubbing.py         # Security: secret redaction patterns
│   ├── test_textual_compat.py           # Platform: asyncio subprocess filter
│   ├── test_tool_profiles.py            # Agent role → tool access schema
│   ├── test_tui_keybinding_namespace.py # Structural: binding centralization
│   ├── test_tui_tutorial_overlay.py     # Tutorial step navigation logic
│   └── core/                            # Core-specific contracts
│       ├── test_git_validation.py       # Security: ref name, path traversal
│       ├── test_worktrees_security.py   # Security: worktree path injection
│       └── test_runtime_env.py          # Platform: env sanitization
├── tui/                                 # kagan.tui (behavioral)
│   ├── test_welcome_and_onboarding.py
│   ├── test_kanban_board.py
│   ├── test_task_authoring.py
│   ├── test_task_output.py
│   ├── test_review_and_diff.py
│   ├── test_chat_overlay.py
│   ├── test_chat_modes.py               # Orchestrator/task chat mode switching
│   ├── test_session_and_backend.py
│   ├── test_settings_modal.py           # Settings screen behaviors
│   ├── test_workspace_screen.py         # Workspace provisioning screen
│   └── test_task_screen_review_no_criteria.py  # Review gate without acceptance criteria
├── mcp/                                 # kagan.server.mcp (behavioral)
│   ├── test_task_tools.py
│   ├── test_session_tools_attached.py
│   ├── test_session_tools_detached.py
│   ├── test_project_and_repo_tools.py
│   ├── test_review_tools.py
│   ├── test_settings_and_audit_tools.py
│   ├── test_diagnostics_optional.py
│   ├── test_resources_read_only.py
│   ├── test_prompts.py
│   ├── test_access_control.py
│   ├── test_smoke.py                    # Transport & lifespan smoke tests
│   └── test_mcp_driver_parity.py        # McpDriver CRUD parity checks
├── server/                              # kagan.server (REST/SSE contract)
│   ├── test_access_control.py           # HTTP route access tier enforcement
│   ├── test_integration.py              # REST lifecycle, JSON error envelopes
│   ├── test_middleware.py               # Rate limiting middleware
│   ├── test_presence.py                 # Presence tracker contracts
│   ├── test_server.py                   # Health endpoint
│   ├── test_sse_polling.py              # Cross-process DB polling
│   └── test_web_ui.py                   # SPA static file serving
├── integrations/                        # kagan.core.integrations (behavioral)
│   └── test_github.py                    # GitHub sync: preflight, preview, create, skip, re-import, labels
├── integration/                          # real-stdio integration (real SDK, hermetic agent)
│   └── acp_real/
│       └── test_stream_wrappers.py      # Stream wrappers + spawn pipeline against the echo agent
└── helpers/                             # DSL: KaganDriver, FakeAgent, fixtures
    ├── acp_loopback.py                   # TCP-loopback fixture yielding real asyncio.StreamReader/Writer
    └── echo_agent.py                     # Vendored ACP echo agent (run as subprocess via sys.executable)
```

Name tests as specs: `test_<behavior>_<expected_outcome>`. Each file has 2-6 tests,
each test is 5-15 lines. The suite targets under 60 seconds.

______________________________________________________________________

## Markers

```python
@pytest.mark.unit           # Implementation details (tests/unit/ only)
@pytest.mark.smoke          # Fast, core behaviors
@pytest.mark.slow           # Workspace provisioning, merges
```

______________________________________________________________________

## The Fake Agent

Configure `FakeAgent` per-test:

```text
board.configure_agent(responses=["<complete/>"])
board.configure_agent(responses=["<blocked reason='needs API key'/>"])
board.configure_review_agent(verdict="approve", summary="LGTM")
```

______________________________________________________________________

## MCP Tests

Test tools through the router driver, not by calling tool functions directly:

```python
async def test_task_create_via_mcp(board):
    result = await board.mcp_call("task_create", {"title": "New feature"})
    assert result["status"] == "BACKLOG"
```

Access tier enforcement:

```python
@pytest.mark.parametrize(
    "tier,tool,allowed",
    [
        ("readonly", "task_list", True),
        ("readonly", "task_create", False),
        ("default", "task_create", True),
        ("default", "task_delete", False),
        ("admin", "task_delete", True),
    ],
)
async def test_access_tier_gates(board, tier, tool, allowed):
    if allowed:
        await board.mcp_call(tool, {}, tier=tier)
    else:
        with pytest.raises(PermissionDenied):
            await board.mcp_call(tool, {}, tier=tier)
```

______________________________________________________________________

## TUI Tests

Use `app.run_test()` with `Pilot`. Use targeted waits (`wait_for_screen`,
`pilot.pause()`), never `wait_for_workers()` — orphaned background workers cause timeouts.

______________________________________________________________________

## Web Client Tests

Web tests follow a two-layer split:

1. **Vitest + @testing-library/react** for isolated component/state behavior (fast, no server)
1. **Playwright** for end-to-end behavior against a real running `kagan web` instance

Vitest conventions:

- Tests live in `packages/web/src/**/*.test.ts` and `packages/web/src/**/*.test.tsx`
- Prefer `.test.tsx` for component suites that render React trees
- Mock API singletons (`apiClient`) with `vi.mock()`
- Prefer behavior assertions (rendered output, grouped state, visible status labels)

```bash
pnpm run web:test
```

Playwright conventions:

- Tests live in `packages/web/e2e/*.spec.ts`
- Start the server first (`kagan web`) and run tests against `BASE_URL` (default `http://127.0.0.1:8765`)
- Focus on high-value flows (board visibility, route transitions, creation actions)
- Keep E2E suites small and resilient; avoid brittle selectors tied to styling

```bash
pnpm run web:test:e2e
```

Relationship to Python tests:

- Python behavioral suites (`tests/server/`) validate the REST/SSE contract directly
- Web tests validate browser behavior and UI integration with that contract
- Both layers are complementary; neither replaces the other

Prioritize web tests in this order: **stores -> components -> E2E smoke flows**.

______________________________________________________________________

## VS Code Extension Tests

The VS Code extension follows a three-layer split. There should be one obvious way to test each
kind of behavior:

1. **Vitest** for pure helpers and small state-free logic
1. **`@vscode/test-cli` / `@vscode/test-electron`** for extension-host integration
1. **WDIO + `wdio-vscode-service`** for real VS Code UI smoke flows

Directory layout:

```text
packages/vscode/
├── src/**/*.test.ts                  # Vitest unit tests
├── test/integration/**/*.test.ts     # Official extension-host tests
├── test/e2e/**/*.spec.ts             # WDIO real-VSCode smoke tests
├── test/helpers/                     # Shared fake Kagan server + fixtures
├── .vscode-test.mjs                  # Official VS Code test runner config
├── test/wdio.conf.ts                 # WDIO runner config
├── tsconfig.test.json                # Integration test compile target
└── test/tsconfig.json                # WDIO type environment
```

Use each layer for one job only:

- **Vitest** tests pure functions such as URI builders, launcher normalization, diff slicing, and
  API-client edge behavior. No VS Code instance, no browser, no real workbench.
- **Integration tests** run inside the Extension Development Host and assert extension behavior via
  the real `vscode` API: activation, command registration, virtual documents, SCM content
  providers, and configuration wiring.
- **WDIO smoke tests** run against a real downloaded VS Code instance and verify the installed
  extension still works end to end in a dummy editor window.

The fake backend for VS Code tests is a tiny local HTTP/SSE server, not a pile of mocks. That
keeps the extension honest while keeping tests deterministic.

Commands:

```bash
pnpm run vscode:test:unit
pnpm run vscode:test:integration
pnpm run vscode:test:e2e
```

Root shortcuts:

```bash
uv run poe vscode-check
uv run poe vscode-test-integration
uv run poe vscode-test-e2e
```

Conventions:

- Keep **unit tests** in the same namespace as the source file they exercise.
- Keep **integration tests** behavior-first: pass command arguments, inspect opened documents,
  assert observable state.
- Keep **WDIO** small. One or two smoke flows are worth more than a maze of brittle UI selectors.
- Prefer `browser.executeWorkbench(...)` when the behavior belongs to VS Code itself. Use page
  objects or raw selectors only when the UI surface is the thing under test.
- Do not invent a fourth layer. If a test is hard to place, the test is probably badly shaped.

Prioritize VS Code tests in this order: **helpers -> command/provider integration -> one real UI smoke path**.

______________________________________________________________________

## Priority

What to test first:

1. **Core lifecycle** — task CRUD, status transitions, managed runs, interactive launches, reviews, workspaces
1. **Integration** — project/repo management, MCP tool dispatch, settings
1. **Edge cases** — concurrent starts, merge conflicts, agent crashes, orphan cleanup

Add a test when a bug escapes or a feature ships. Don't add tests "just in case."

______________________________________________________________________

## Don'ts

- Don't mock services, repos, or adapters — only mock the agent
- Don't assert on logs, mock call counts, or DB rows — assert on observable state
- Don't use `monkeypatch` on production code in behavioral integration tests; for CLI
  surface tests, targeted monkeypatching of process-bound seams (for example TUI launch,
  startup update hint, or Ctrl-C simulation) is allowed when asserting observable CLI behavior
- Don't depend on timing — wait for state changes, never `asyncio.sleep`
- Don't duplicate behaviors — one test per behavior, parametrize variants
- Don't import from `kagan.core` internals (private modules or legacy paths) in behavioral tests (`tests/core/`, `tests/mcp/`, `tests/tui/`)
