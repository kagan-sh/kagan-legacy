# Testing rationalization matrix

Phase-2 decisions: which **unit / monkeypatched** tests are candidates to delete or replace once Tier A
Playwright + behavioral Python smoke covers the same user-visible behavior. **No automatic deletion**
— this file is an inventory for humans.

______________________________________________________________________

## Top files by `monkeypatch` usage

Counts from `rg --count-matches 'monkeypatch' tests --glob '*.py'` (representative snapshot; re-run before large refactors).

| Rank  | File                                                                                                                                                   | ~Uses | Suggested disposition                                                                                     |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- | --------------------------------------------------------------------------------------------------------- |
| 1     | `tests/core/test_cli_surface.py`                                                                                                                       | 65    | **Keep / trim** — CLI contract surface; migrate only where Tier A duplicates exact assertions             |
| 2     | `tests/unit/test_sessions_shutdown.py`                                                                                                                 | 58    | **Migrate vs keep** — event-loop shutdown is hard to E2E; prefer **keep** with `legacy_contract` if flaky |
| 3     | `tests/unit/test_tui_osc8.py`                                                                                                                          | 54    | **Keep** — terminal escape sequences; not replaceable by browser E2E                                      |
| 4     | `tests/unit/test_chat_batched_approvals.py`                                                                                                            | 48    | **Migrate** — overlaps orchestrator UX; candidate once chat Playwright + CLI smoke stable                 |
| 5     | `tests/unit/core/test_worktrees_security.py`                                                                                                           | 38    | **Keep** — security carve-out ([`testing.md`](./testing.md)); never delete for E2E alone                  |
| 6     | `tests/unit/test_chat_commands.py`                                                                                                                     | 30    | **Keep (short term)** — slash grammar; optional migrate after CLI smoke expands                           |
| 7     | `tests/unit/core/test_subprocess_resolve.py`                                                                                                           | 28    | **Keep** — platform/path edge cases                                                                       |
| 8     | `tests/unit/test_agent_spawn_acp.py`                                                                                                                   | 18    | **Migrate gradually** — overlaps `tests/integration/acp_real/` + fake-agent smoke                         |
| 9     | `tests/server/test_session_actions_route.py`                                                                                                           | 18    | **Migrate** — REST contract; Playwright hits real server for product paths                                |
| 10    | `tests/unit/test_doctor.py`                                                                                                                            | 17    | **Keep** — `kg doctor` output contract                                                                    |
| 11–20 | `tests/unit/test_chat_approval_panel.py`, `tests/unit/test_textual_compat.py`, `tests/unit/test_acp_session.py`, `tests/server/test_integration.py`, … | 8–17  | Case-by-case — tag **`legacy_contract`** if retained while Tier A grows                                   |

______________________________________________________________________

## Replacement scenarios (E2E IDs)

| Area                  | Current test / pattern                                    | Behavior claimed | Replacement scenario                                      | Risk if deleted                  | Marker                                  |
| --------------------- | --------------------------------------------------------- | ---------------- | --------------------------------------------------------- | -------------------------------- | --------------------------------------- |
| Web orchestrator send | Many server route tests + skipped Playwright (historical) | Chat POST + SSE  | `packages/web/e2e/workspace-chat.spec.ts`, `chat.spec.ts` | Loss of HTTP status-code matrix  | `legacy_contract` for thin 4xx/5xx rows |
| Board load            | `tests/server/*` + Vitest                                 | Project gate     | `board.spec.ts`, `navigation.spec.ts`                     | Low for pure duplicate           | —                                       |
| CLI chat plumbing     | `tests/unit/test_chat_repl.py` (monkeypatch-heavy)        | REPL wiring      | `tests/cli/test_chat_oneshot_smoke.py`                    | Breaks prompt_toolkit edge cases | `legacy_contract`                       |
| TUI workspace         | Snapshot-heavy modules                                    | Layout           | `tests/tui/test_e2e_smoke_workspace.py`                   | Visual regressions               | pair with snapshot tests                |
| ACP wire              | `tests/integration/acp_real/`                             | Real SDK types   | **No replacement** — keep                                 | High                             | `contract`                              |
| Git/path validation   | `tests/unit/core/test_git_validation.py`                  | Traversal safety | **No replacement**                                        | Critical                         | `security`                              |

______________________________________________________________________

## Pytest markers / CI split (recommended)

| Marker                         | Meaning                                                   | Suggested job                            |
| ------------------------------ | --------------------------------------------------------- | ---------------------------------------- |
| `@pytest.mark.smoke`           | Fast behavioral slice                                     | PR gate (already used in parts of suite) |
| `@pytest.mark.smoke_e2e`       | Playwright + subprocess smoke (document-only until wired) | Optional `poe` alias or nightly          |
| `@pytest.mark.legacy_contract` | Kept only until Tier A supersedes                         | Excluded from “strict migration” jobs    |

CI workflow edits are **out of scope** for this wave unless a trivial `poe` task is already missing.

______________________________________________________________________

## Feature doc cross-links

Scenario backlog and UX intent:

- [`docs/internal/features/web.md`](./features/web.md)
- [`docs/internal/features/tui.md`](./features/tui.md)
- [`docs/internal/features/chat.md`](./features/chat.md)
