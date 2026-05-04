






# CHANGELOG

<!-- version list -->





## v0.19.0-beta.25 (2026-05-04)




### Features

- **core**: Add transition_task / transition_session funnel (R5 phase 5a)
  ([#137](https://github.com/kagan-sh/kagan/pull/137),
  [`663a83a`](https://github.com/kagan-sh/kagan/commit/663a83a8b42ea1a7c4e04e1ed93a786f0f3c3e80))













### Bug Fixes

- **R5**: Close REVIEW→DONE break and TOCTOU windows (Greptile P1 + P2)
  ([#137](https://github.com/kagan-sh/kagan/pull/137),
  [`663a83a`](https://github.com/kagan-sh/kagan/commit/663a83a8b42ea1a7c4e04e1ed93a786f0f3c3e80))




















### Refactoring

- **R5**: Funnel-function transitions (no enforcement magic)
  ([#137](https://github.com/kagan-sh/kagan/pull/137),
  [`663a83a`](https://github.com/kagan-sh/kagan/commit/663a83a8b42ea1a7c4e04e1ed93a786f0f3c3e80))

- **server**: Route task/session status mutations through transitions (R5 phase 5b)
  ([#137](https://github.com/kagan-sh/kagan/pull/137),
  [`663a83a`](https://github.com/kagan-sh/kagan/commit/663a83a8b42ea1a7c4e04e1ed93a786f0f3c3e80))















### Chores

- **core**: Document transition funnel + fix test collision (R5 phase 5c)
  ([#137](https://github.com/kagan-sh/kagan/pull/137),
  [`663a83a`](https://github.com/kagan-sh/kagan/commit/663a83a8b42ea1a7c4e04e1ed93a786f0f3c3e80))





## v0.19.0-beta.24 (2026-05-04)




### Bug Fixes

- **R4**: Address Greptile P1 findings — duplicates, naming, broken tests
  ([#136](https://github.com/kagan-sh/kagan/pull/136),
  [`2fa65ec`](https://github.com/kagan-sh/kagan/commit/2fa65ec92c9c48a9323a6b7a3d687ad01e513060))

- **R4**: Allow_indirect_imports must be TOML boolean, not string (Greptile P1)
  ([#136](https://github.com/kagan-sh/kagan/pull/136),
  [`2fa65ec`](https://github.com/kagan-sh/kagan/commit/2fa65ec92c9c48a9323a6b7a3d687ad01e513060))

- **R4**: Update test_web_ctrl_c_exits_cleanly monkeypatch path
  ([#136](https://github.com/kagan-sh/kagan/pull/136),
  [`2fa65ec`](https://github.com/kagan-sh/kagan/commit/2fa65ec92c9c48a9323a6b7a3d687ad01e513060))




















### Refactoring

- **R4**: Enforce package boundaries — promote privates + import-linter
  ([#136](https://github.com/kagan-sh/kagan/pull/136),
  [`2fa65ec`](https://github.com/kagan-sh/kagan/commit/2fa65ec92c9c48a9323a6b7a3d687ad01e513060))

- **boundaries**: Promote cross-package privates to public exports (R4 phase 4a)
  ([#136](https://github.com/kagan-sh/kagan/pull/136),
  [`2fa65ec`](https://github.com/kagan-sh/kagan/commit/2fa65ec92c9c48a9323a6b7a3d687ad01e513060))















### Chores

- **boundaries**: Add import-linter contract + poe check-boundaries (R4 phase 4b)
  ([#136](https://github.com/kagan-sh/kagan/pull/136),
  [`2fa65ec`](https://github.com/kagan-sh/kagan/commit/2fa65ec92c9c48a9323a6b7a3d687ad01e513060))





## v0.19.0-beta.23 (2026-05-04)




### Features

- **scripts**: Extend generate_wire_types.py to emit full wire surface (R3 phase 3a)
  ([#135](https://github.com/kagan-sh/kagan/pull/135),
  [`991cf61`](https://github.com/kagan-sh/kagan/commit/991cf61eb8355fc718e2f36d9fcc417a19537c2a))


















### Bug Fixes

- **R3**: Address Greptile P2 — top-level Priority import + broader ESLint pattern
  ([#135](https://github.com/kagan-sh/kagan/pull/135),
  [`991cf61`](https://github.com/kagan-sh/kagan/commit/991cf61eb8355fc718e2f36d9fcc417a19537c2a))

- **R3**: Resolve @kagan/shared-api-client to source in VS Code vitest
  ([#135](https://github.com/kagan-sh/kagan/pull/135),
  [`991cf61`](https://github.com/kagan-sh/kagan/commit/991cf61eb8355fc718e2f36d9fcc417a19537c2a))

























### Refactoring

- **vscode**: Consume @kagan/api-client wire types (R3 phase 3c)
  ([#135](https://github.com/kagan-sh/kagan/pull/135),
  [`991cf61`](https://github.com/kagan-sh/kagan/commit/991cf61eb8355fc718e2f36d9fcc417a19537c2a))

- **web**: Migrate to generated wire types (R3 phase 3b)
  ([#135](https://github.com/kagan-sh/kagan/pull/135),
  [`991cf61`](https://github.com/kagan-sh/kagan/commit/991cf61eb8355fc718e2f36d9fcc417a19537c2a))

- **R3**: One TS wire source — consolidate hand-rolled types
  ([#135](https://github.com/kagan-sh/kagan/pull/135),
  [`991cf61`](https://github.com/kagan-sh/kagan/commit/991cf61eb8355fc718e2f36d9fcc417a19537c2a))





## v0.19.0-beta.22 (2026-05-04)




### Bug Fixes

- **mcp**: Catch pydantic.ValidationError in batch task_create (Greptile P1)
  ([#134](https://github.com/kagan-sh/kagan/pull/134),
  [`c17f51a`](https://github.com/kagan-sh/kagan/commit/c17f51a59a1e47d561e6be7db5f0520f81bc7aa2))






























### Refactoring

- **server**: Shared Pydantic request models for projects + reviews (R2 phase 2c)
  ([#134](https://github.com/kagan-sh/kagan/pull/134),
  [`c17f51a`](https://github.com/kagan-sh/kagan/commit/c17f51a59a1e47d561e6be7db5f0520f81bc7aa2))

- **R2**: Shared Pydantic request models for REST + MCP
  ([#134](https://github.com/kagan-sh/kagan/pull/134),
  [`c17f51a`](https://github.com/kagan-sh/kagan/commit/c17f51a59a1e47d561e6be7db5f0520f81bc7aa2))

- **server**: Shared Pydantic request models for sessions (R2 phase 2b)
  ([#134](https://github.com/kagan-sh/kagan/pull/134),
  [`c17f51a`](https://github.com/kagan-sh/kagan/commit/c17f51a59a1e47d561e6be7db5f0520f81bc7aa2))

- **server**: Shared Pydantic request models for tasks (R2 phase 2a)
  ([#134](https://github.com/kagan-sh/kagan/pull/134),
  [`c17f51a`](https://github.com/kagan-sh/kagan/commit/c17f51a59a1e47d561e6be7db5f0520f81bc7aa2))





## v0.19.0-beta.21 (2026-05-04)




### Features

- **core/chat**: Add first-class permission seam (R1 phase 5-pre)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **core/chat**: Add LongLivedACPFactory (R1 phase 5a)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))





















































### Bug Fixes

- **R1 phase 3**: Address Greptile P1 data-loss + P2 task leak
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **R1 phase 3**: Address Greptile P1 slot leak + P2 duplicate broadcast
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **R1 phase 3**: Address Greptile P2 — stale PATCH updated_at + AsyncGenerator annotation
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **core/chat**: Address Greptile phase 2 review
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **R1 phase 4c**: Claim turn slot before user persist + broadcast (Greptile P1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **lint**: Move builtins import into TYPE_CHECKING block
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **server**: Post-CHAT_DONE refresh outside error handler (Greptile P1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **server**: Release turn slot on client disconnect mid-stream (Greptile P1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **server**: Widen post-claim guard to cover all pre-stream awaits + yields (Greptile P1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

































































### Refactoring

- **core/chat**: Add ChatEngine + events + ACP factory (R1 phase 2)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **core/chat**: Address Greptile P1 review on phase 1
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **tui/kanban**: Consume ChatEngine for chat turns (R1 phase 4a)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **cli/core**: Delete legacy chat shim + replace_history + _chat_acp residue (R1 phase 6)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **core**: Extract ChatSessions aggregate (R1 phase 1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **cli**: Extract CLIRenderer + PermissionUI from _chat_acp.py (R1 phase 5b)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **tui**: Finish ChatEngine migration — sweep screens (R1 phase 4c)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **server**: Migrate _chat_routes.py to ChatEngine (R1 phase 3)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **cli**: Rewire controller to ChatEngine + delete _OrchestratorACPClient (R1 phase 5c)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **tui**: Split ChatPanel into ChatTranscript / ChatInput / ChatSessionMenu (R1 phase 4b, Option A)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **R1**: Unify chat engine — phase 1 (ChatSessions aggregate)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))































### Testing

- **web/vscode**: Add chat E2E + VS Code chat-participant integration (R1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **tui**: Add Pilot-driven chat lifecycle behavioral tests (R1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))

- **core/server**: Consolidate chat test suite per testing.md (R1)
  ([#133](https://github.com/kagan-sh/kagan/pull/133),
  [`f7eabe3`](https://github.com/kagan-sh/kagan/commit/f7eabe394d358f88dd9682e9b35a24c16092cf41))





## v0.19.0-beta.20 (2026-05-03)




### Features

- **chat**: Match kimi-cli REPL polish — input separator, stateful prompt, toolbar
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Overhaul kg chat approval panel and REPL UX
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Overhaul kg chat REPL — approval panel, geometric UX language, terminal-bottom-pinned
  toolbar ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Pin toolbar footer during streaming + lift completion-meta contrast
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Pin toolbar footer through entire agent reply via TurnLiveRegion
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Render streaming Markdown live via Rich Live region
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Replace emoji prompt glyphs with geometric set + animated streaming
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat,tui,web**: Unify streaming indicator on animated half-disc
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))











































### Bug Fixes

- **chat**: Address greptile review findings ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Address greptile review on PR #131 ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Apply review findings — modal-aware print routing + safer prompt session caching
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Keep _flush_batch under the C901 complexity cap
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Remove redundant wave spinner during agent reply
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Tighten approval panel hygiene from review
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Use ○ instead of ❯ as toolbar idle indicator
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))






























### Refactoring

- **chat**: Batched approval panel shows resolved items distinctly
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Centralize REPL palette in _theme.py
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Pin toolbar at terminal bottom via long-lived prompt-toolkit session
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Remove pointless `── input ──` separator from toolbar
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))


















### Documentation

- **chat**: Document approval panel, batched approvals, /approvals, env knobs
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- **chat**: Document new prompt/toolbar UX, missing slash commands, drop stale wave reference
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))























### Chores

- Dead-code sweep — vulture findings + orphan task-completion doc
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- Gitignore agent-generated tasks/ scratch directory
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))

- Pre-commit format sweep across drifted docs and tests
  ([#131](https://github.com/kagan-sh/kagan/pull/131),
  [`b8d94f6`](https://github.com/kagan-sh/kagan/commit/b8d94f6c34f5ac251b534c9efe31bc3db59b39c3))















### Code Style

- Apply formatter pass across chat/server/core/tui/tests
  ([#132](https://github.com/kagan-sh/kagan/pull/132),
  [`62827f1`](https://github.com/kagan-sh/kagan/commit/62827f17ce389fb29f8bab37f5b15c6865696b88))





## v0.19.0-beta.19 (2026-05-01)




### Bug Fixes

- **tests**: Attach repo before GitHub sync API test
  ([`e232f57`](https://github.com/kagan-sh/kagan/commit/e232f57c892ccfd0c49e432bc93c99d19cee8053))





## v0.19.0-beta.18 (2026-04-30)




### Features

- **chat**: Add --yolo flag to auto-approve tool calls
  ([`a78eb5b`](https://github.com/kagan-sh/kagan/commit/a78eb5bf3c34ff751b2591c7145297e8da4f17fd))













### Bug Fixes

- **integrations**: Require repo_id for GitHub issue import
  ([`c2d0dfd`](https://github.com/kagan-sh/kagan/commit/c2d0dfd7112094a3156c38eae1f1383437979098))





## v0.19.0-beta.17 (2026-04-30)




### Bug Fixes

- **tui**: Bind . to command palette so kanban hint matches behavior
  ([`f41d9cd`](https://github.com/kagan-sh/kagan/commit/f41d9cdbf49ae8db1e54731ad12e05781833c4ef))





## v0.19.0-beta.16 (2026-04-30)




### Features

- **integrations**: Native GitHub integration
  ([`4b6b6e0`](https://github.com/kagan-sh/kagan/commit/4b6b6e0e12bfabd4cc2a193f619b030386af47cb))





## v0.19.0-beta.15 (2026-04-28)




### Bug Fixes

- **tui**: Guard _sync_branch query_one(KaganHeader) against NoMatches
  ([`9447785`](https://github.com/kagan-sh/kagan/commit/94477858f37a09035d3de6f5ef500c93007f510b))





## v0.19.0-beta.14 (2026-04-28)




### Bug Fixes

- **tui**: Keep tutorial/state init in on_mount, defer only widget queries
  ([`001bda6`](https://github.com/kagan-sh/kagan/commit/001bda6454aa73b21d32f851bac1abb22df61f93))





## v0.19.0-beta.13 (2026-04-28)




### Bug Fixes

- **tui**: Defer on_mount widget queries to call_after_refresh
  ([`5e69a52`](https://github.com/kagan-sh/kagan/commit/5e69a523267682ae8380c07e30532ad3e6a78191))





## v0.19.0-beta.12 (2026-04-28)




### Bug Fixes

- **tui**: Guard _inspector_visible against NoMatches before mount
  ([`37576d0`](https://github.com/kagan-sh/kagan/commit/37576d044b3937b1a8feae116b7582716ba20f7b))





## v0.19.0-beta.11 (2026-04-28)




### Features

- **chat**: Convergent live multi-client chat with per-session SSE watch
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Finish pmf-push polish + migrate to review-gate data model
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **server+web**: Inline task payloads in board SSE
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **server+web**: Live diff-in-board — the "oh moment"
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Progressive backend picker + a11y pass on settings/picker
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))










































































































































### Bug Fixes

- **branch**: Address first-pass review findings across all lanes
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **chat**: Address Greptile P1/P2 review findings
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **chat**: Address Greptile P2/P3 findings — delete teardown + keep-alive on disconnect
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **branch**: Address second-pass review findings
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **branch**: Address third-pass pre-existing review findings
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **vscode**: Align ReviewVerdict + AcceptanceCriterion to wire shape
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **ts**: Align shared review wire types ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Announce agent event stream to screen readers
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **ci**: Build @kagan/shared-api-client before web tests
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **cd**: Build @kagan/shared-api-client before web-build step
  ([`fb9c339`](https://github.com/kagan-sh/kagan/commit/fb9c3393b4093234fa4ef41e396389c44b5fa6a2))

- **tui**: Defer chat rendering until children mount
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui+web**: Drop unsupported OptionList tooltip; role=timer for elapsed span
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **server**: Extract _claim_turn_slot to keep _register_stream_routes ≤ C20
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Guard chat session switch before mount
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **core**: Honest review gate ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **core**: Keep MERGE trigger out of move_task allowed set
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **migrations**: Make 6f4d63a80a1e idempotent ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **lint**: Resolve TC004 duplicate import, E501 long line, I001 unsorted imports
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Stabilize chat session selector mount
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Tighten suppress(NoMatches) scoping in chat panel
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Tolerate early board reactive refresh
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Tolerate early chat panel mount ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Tolerate early kanban chat panel mount
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Tolerate early peek overlay initialization
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Tolerate early task inspector rendering
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **e2e**: Update board tests to match current UX — drop peek/x bindings
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))































































































### Refactoring

- **core**: Centralize SQLModel column casts ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **server**: Consolidate response serialization
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Defer chat panel setup via ChatPanel.Ready message
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Demote analytics from primary nav ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Deterministic task-card layout ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Drop dead Peek dialog ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **core**: Drop Task.review_approved shim and route callers to real review state
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Land on board, drop welcome screen ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Layered dark theme, AA contrast ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **tui**: Progressive exposure on settings screen
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **vscode+tui**: Share board helpers and guard chat mount
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **vscode+tui**: Share command helpers and harden chat mount
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **vscode+core**: Simplify review documents and learnings lookup
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **core**: Single trigger-keyed state machine for task transitions
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Slim agent-control; extract instructions dialog
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Unify chat engine behind useChatStream + ChatView
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Use crypto.randomUUID for follow-up queue ids
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))













### Documentation

- Reposition around the review gate; demote companion surfaces
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))
















































### Chores

- Purge dead modules and defensive junk ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Regenerate wire types ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- Remove temporary analytics artifacts ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- **web**: Remove unused frontend dependencies ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- Simplification wave A — delete dead code across all lanes
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- Simplification wave B — adopt @kagan/shared-api-client
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- Simplification wave D — tier 1 cleanups across all lanes
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))

- Simplification wave E — tier 2 architectural collapses
  ([#126](https://github.com/kagan-sh/kagan/pull/126),
  [`7ab5666`](https://github.com/kagan-sh/kagan/commit/7ab566675caa28071bfcf28f9c7ba358248e3b55))





## v0.19.0-beta.10 (2026-04-23)




### Chores

- **deps**: Bump the all group in /packages/web with 5 updates
  ([#124](https://github.com/kagan-sh/kagan/pull/124),
  [`ae93c59`](https://github.com/kagan-sh/kagan/commit/ae93c59a95d822bf55b371b8fab342433e9eac82))

- **deps-dev**: Bump typescript from 5.9.3 to 6.0.3 in /packages/vscode
  ([#124](https://github.com/kagan-sh/kagan/pull/124),
  [`ae93c59`](https://github.com/kagan-sh/kagan/commit/ae93c59a95d822bf55b371b8fab342433e9eac82))

- **deps**: Bump typescript from 5.9.3 to 6.0.3 in /packages/web
  ([#124](https://github.com/kagan-sh/kagan/pull/124),
  [`ae93c59`](https://github.com/kagan-sh/kagan/commit/ae93c59a95d822bf55b371b8fab342433e9eac82))

- **deps-dev**: Bump vitest from 4.1.4 to 4.1.5 in /packages/vscode
  ([#124](https://github.com/kagan-sh/kagan/pull/124),
  [`ae93c59`](https://github.com/kagan-sh/kagan/commit/ae93c59a95d822bf55b371b8fab342433e9eac82))

- **deps**: Bundle open dependabot bumps (#117 #118 #119 #120)
  ([#124](https://github.com/kagan-sh/kagan/pull/124),
  [`ae93c59`](https://github.com/kagan-sh/kagan/commit/ae93c59a95d822bf55b371b8fab342433e9eac82))

- **deps**: Update pnpm-lock.yaml for bundled bumps
  ([#124](https://github.com/kagan-sh/kagan/pull/124),
  [`ae93c59`](https://github.com/kagan-sh/kagan/commit/ae93c59a95d822bf55b371b8fab342433e9eac82))





## v0.19.0-beta.9 (2026-04-23)




### Bug Fixes

- **server**: Guard fs/browse per-entry against OSError in resolve/exists
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

- **runtime_env**: Platform-aware essential env for Windows
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

- **core**: Resolve .cmd shims via cmd.exe on Windows
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

- **core**: Terminate agent processes via handle, not os.kill
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

- Windows support across fs/browse, agent spawn, env, and signals
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

- **server**: Windows-safe fs/browse endpoint ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

- **web**: Windows-safe PathPicker ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))



















### Chores

- **wire**: Regenerate TS types for FsBrowse/FsEntry
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))

















### Testing

- **agent_kill**: Strengthen returncode assertion to satisfy test-quality check
  ([#123](https://github.com/kagan-sh/kagan/pull/123),
  [`da963d0`](https://github.com/kagan-sh/kagan/commit/da963d01aecd938991660fbcca453584e84e4aa9))





## v0.19.0-beta.8 (2026-04-23)




### Bug Fixes

- **tui**: Defer query_one work in on_mount/on_screen_resume across screens (xdist race)
  ([#122](https://github.com/kagan-sh/kagan/pull/122),
  [`3adc7c5`](https://github.com/kagan-sh/kagan/commit/3adc7c529ccb93ed9d718d5983c756ffa45af1ee))























### Code Style

- **tui**: Drop unnecessary async on WelcomeScreen.on_mount
  ([`bceff8a`](https://github.com/kagan-sh/kagan/commit/bceff8aa61225fcfac658d4ee5caa7011deb81ea))





## v0.19.0-beta.7 (2026-04-23)




### Bug Fixes

- **tui**: Defer _reload_projects to call_after_refresh to survive xdist race
  ([#121](https://github.com/kagan-sh/kagan/pull/121),
  [`8bd88cb`](https://github.com/kagan-sh/kagan/commit/8bd88cbf5e33a42952d0c795827c920bdbec96ab))





## v0.19.0-beta.6 (2026-04-23)




### Bug Fixes

- **doctor**: Pass backend name not executable to preflight (ghost backend bug)
  ([`45335d1`](https://github.com/kagan-sh/kagan/commit/45335d1441fd3ddfec7e203b861ce4e650d288e9))

























### Testing

- **e2e**: Add Docker sandbox harness for doctor-gated onboarding scenarios
  ([`23bc68d`](https://github.com/kagan-sh/kagan/commit/23bc68daa92f36c50e28cf6bd53089d843d487bd))





## v0.19.0-beta.5 (2026-04-21)




### Features

- **doctor**: Doctor-gated onboarding — interactive preflight with install guidance and auto-promote
  ([`32dcf1e`](https://github.com/kagan-sh/kagan/commit/32dcf1ee4d2ca9da6838923d004ec77837c643e7))





## v0.19.0-beta.4 (2026-04-21)




### Chores

- **ci**: Bump actions/upload-pages-artifact from 4 to 5
  ([#116](https://github.com/kagan-sh/kagan/pull/116),
  [`b5895bc`](https://github.com/kagan-sh/kagan/commit/b5895bc130f044a5621679885900ac9dd679d25a))





## v0.19.0-beta.3 (2026-04-19)




### Chores

- **deps-dev**: Bump ovsx from 0.10.10 to 0.10.11 in /packages/vscode
  ([#113](https://github.com/kagan-sh/kagan/pull/113),
  [`69ec762`](https://github.com/kagan-sh/kagan/commit/69ec762931f0c1b67188f2834f49d7ef2ed43ba0))

- **deps-dev**: Update pnpm-lock.yaml for ovsx 0.10.11
  ([#113](https://github.com/kagan-sh/kagan/pull/113),
  [`69ec762`](https://github.com/kagan-sh/kagan/commit/69ec762931f0c1b67188f2834f49d7ef2ed43ba0))





## v0.19.0-beta.2 (2026-04-19)




### Chores

- **deps-dev**: Bump @vscode/vsce from 3.7.1 to 3.9.0 in /packages/vscode
  ([#111](https://github.com/kagan-sh/kagan/pull/111),
  [`2efdd3a`](https://github.com/kagan-sh/kagan/commit/2efdd3a861242b49926c3b3557c53e5b77fba11f))

- **deps-dev**: Bump @vscode/vsce in /packages/vscode
  ([#111](https://github.com/kagan-sh/kagan/pull/111),
  [`2efdd3a`](https://github.com/kagan-sh/kagan/commit/2efdd3a861242b49926c3b3557c53e5b77fba11f))

- **deps-dev**: Update pnpm-lock.yaml for vsce 3.9.0
  ([#111](https://github.com/kagan-sh/kagan/pull/111),
  [`2efdd3a`](https://github.com/kagan-sh/kagan/commit/2efdd3a861242b49926c3b3557c53e5b77fba11f))





## v0.19.0-beta.1 (2026-04-17)




### Features

- **web**: UX/UI v2 — a11y foundation, command palette, intent home, settings disclosure, living
  cards
  ([`411c6fb`](https://github.com/kagan-sh/kagan/commit/411c6fb99241a12f0fa2f80cb341df82ba62e79c))



















### Documentation

- Document v0.18.0 analytics across external and internal guides
  ([`e622d8f`](https://github.com/kagan-sh/kagan/commit/e622d8f447e80705c34ed47e3cd8fd6581e46351))





## v0.18.1-beta.4 (2026-04-16)




### Bug Fixes

- **ci**: Strip leading whitespace from release notes template
  ([`6ffb07a`](https://github.com/kagan-sh/kagan/commit/6ffb07ab3f69036ddaedaf817cbd8c787fb3ba47))





## v0.18.1-beta.3 (2026-04-16)




### Bug Fixes

- **vscode**: Downgrade @types/vscode to match engines.vscode version
  ([`550e7bc`](https://github.com/kagan-sh/kagan/commit/550e7bc5046e23913bffc7a89301d682efc08b23))





## v0.18.1-beta.2 (2026-04-16)




### Bug Fixes

- **vscode**: Add format utilities for analytics commands
  ([`72f36f5`](https://github.com/kagan-sh/kagan/commit/72f36f5ea93c0ec7e2c669bea14628a6cbe41927))



















### Chores

- **vscode**: Bump to 0.18.0 [skip ci]
  ([`6f87307`](https://github.com/kagan-sh/kagan/commit/6f87307b251d85bf93617596e4f3efa9324acd0e))





## v0.18.1-beta.1 (2026-04-16)




### Bug Fixes

- **server**: Reduce complexity in analytics routes registration
  ([`196bee5`](https://github.com/kagan-sh/kagan/commit/196bee532bee0678aab46bffef5babb0db29c940))





## v0.18.0 (2026-04-16)




### Features

- **analytics,types**: Add backend timeline summary + enforce board dialog type safety
  ([`8ebc812`](https://github.com/kagan-sh/kagan/commit/8ebc8121d1f79f75d847621b1c556708069085ce))

- Add intelligent backend recommendation setting
  ([`98bbff4`](https://github.com/kagan-sh/kagan/commit/98bbff4b80c75a06597cfa74bc679a91f255e888))

- Add multi-dimensional analytics and intelligent backend selection
  ([`de7f2b6`](https://github.com/kagan-sh/kagan/commit/de7f2b6595b55a7ff1652e47c6815b852b548b42))

- **analytics**: Add smart backend recommendation in settings
  ([`b9c855d`](https://github.com/kagan-sh/kagan/commit/b9c855dca8bd262cfa00e6a9077958523ae7db30))

- **analytics**: Add terminology glossary popup
  ([`1d986ac`](https://github.com/kagan-sh/kagan/commit/1d986ac9c8389d67aa887a87c97918aae73f71b2))


















### Bug Fixes

- **types**: Explicitly use BoardDialog type in closeDialog function
  ([`2f3985c`](https://github.com/kagan-sh/kagan/commit/2f3985c96852a3c9105e0e966862b6786f59895c))

- Resolve linting and dead code issues
  ([`1c6ca8d`](https://github.com/kagan-sh/kagan/commit/1c6ca8dcb94bae615727d109183f4ff61202a516))

























### Refactoring

- **analytics**: Consolidate multi-dimensional aggregation queries
  ([`3043346`](https://github.com/kagan-sh/kagan/commit/304334661069fdcc320876d9eee3338f76c141d8))

- **analytics,web**: Optimize performance and code quality
  ([`cd16373`](https://github.com/kagan-sh/kagan/commit/cd163735abef1fe505e42d80c9ffb23add631994))

- Simplify task card dropdown to limit to open, edit, delete
  ([`993d22e`](https://github.com/kagan-sh/kagan/commit/993d22ea6e6f0f4ce5c1357a5edbf5283127271a))


















### Documentation

- Enhance analytics glossary with success/failure definitions
  ([`4ab6735`](https://github.com/kagan-sh/kagan/commit/4ab6735a8c719dd956008186de543fd2842160db))

- Update analytics guide with multi-dimensional features
  ([`fe55a54`](https://github.com/kagan-sh/kagan/commit/fe55a5426a15a6a3c520f7a5be363630742cea79))





## v0.17.1-beta.2 (2026-04-14)




### Chores

- **deps**: Merge all dependabot updates and fix CI
  ([#110](https://github.com/kagan-sh/kagan/pull/110),
  [`e0cc4c8`](https://github.com/kagan-sh/kagan/commit/e0cc4c8bd0f13e44eb353f85e1900b62c8ac9480))





## v0.17.1-beta.1 (2026-04-13)




### Chores

- **ci**: Bump actions/github-script from 8 to 9
  ([#105](https://github.com/kagan-sh/kagan/pull/105),
  [`fc19f59`](https://github.com/kagan-sh/kagan/commit/fc19f5944d2036146d309870a6be70a1a01ccfaa))

- **ci**: Bump pypa/gh-action-pypi-publish in the all group
  ([#103](https://github.com/kagan-sh/kagan/pull/103),
  [`5678117`](https://github.com/kagan-sh/kagan/commit/5678117ccd666ed07992363bc74772e356575279))





## v0.17.0 (2026-04-10)







## v0.17.0-beta.2 (2026-04-10)




### Bug Fixes

- Revert ACP git dependency to PyPI release for publishability
  ([`a66cf02`](https://github.com/kagan-sh/kagan/commit/a66cf02ed85b8f2eb88e6d713ac1a9b10f6710ad))





## v0.17.0-beta.1 (2026-04-10)




### Refactoring

- Consolidate MCP toolsets and simplify tool surface
  ([`1a537d1`](https://github.com/kagan-sh/kagan/commit/1a537d1c5ec64966322b01c94e1243ad298dca2e))





## v0.16.1-beta.1 (2026-04-09)




### Chores

- Improve release notes for user-friendly, laconic output
  ([`943077a`](https://github.com/kagan-sh/kagan/commit/943077a09a01d5a36f50c78480ac4db8b837d1ae))





## v0.16.0 (2026-04-09)







## v0.16.0-beta.5 (2026-04-09)




### chores

- Add server metadata and KAGAN_DB_PATH configuration
  ([`2b1e93d`](https://github.com/kagan-sh/kagan/commit/2b1e93d4080cbb4761fbd479d1b02e9ec260d7d6))





## v0.16.0-beta.4 (2026-04-09)




### bug fixes

- Improve DBWatcher resilience and change detection accuracy
  ([`9386351`](https://github.com/kagan-sh/kagan/commit/93863519bfb355d06b8efa53694a4a1530360f5e))





## v0.16.0-beta.3 (2026-04-09)




### bug fixes

- Default repo_id for MCP-created tasks to project's first repo
  ([#97](https://github.com/kagan-sh/kagan/pull/97),
  [`0bc90ab`](https://github.com/kagan-sh/kagan/commit/0bc90abbf825cd717c642e8a9fd66b70bf691f50))

- Make _ByteCountingStreamReader inherit from asyncio.StreamReader
  ([#97](https://github.com/kagan-sh/kagan/pull/97),
  [`0bc90ab`](https://github.com/kagan-sh/kagan/commit/0bc90abbf825cd717c642e8a9fd66b70bf691f50))





## v0.16.0-beta.2 (2026-04-07)




### refactoring

- Polish test suite for Zen of Python compliance ([#96](https://github.com/kagan-sh/kagan/pull/96),
  [`cdd5909`](https://github.com/kagan-sh/kagan/commit/cdd5909b25503aab8bcfe1e548c27a91cb0d5fc5))





## v0.16.0-beta.1 (2026-04-07)




### features

- Selective GitHub issue import with preview workflow
  ([`156d0a6`](https://github.com/kagan-sh/kagan/commit/156d0a6eba568ad5c0096aad7878b3114749a282))





## v0.15.1-beta.1 (2026-04-07)




### bug fixes

- **ci**: Refresh pnpm lockfile for web dependency bump
  ([#93](https://github.com/kagan-sh/kagan/pull/93),
  [`90a6f37`](https://github.com/kagan-sh/kagan/commit/90a6f37f9e7a6d2e429596fe8c99c72db2c9b4b1))

- Wire repo_id through task lifecycle for multi-repo project support
  ([`4bba2ed`](https://github.com/kagan-sh/kagan/commit/4bba2edf6b8f971ee1862aab95c164f258c2c7ec))














### chores

- **deps**: Bump the all group in /packages/web with 7 updates
  ([#93](https://github.com/kagan-sh/kagan/pull/93),
  [`90a6f37`](https://github.com/kagan-sh/kagan/commit/90a6f37f9e7a6d2e429596fe8c99c72db2c9b4b1))











### documentation

- Align web dashboard positioning on docs home
  ([`eda73b1`](https://github.com/kagan-sh/kagan/commit/eda73b18cffab15ba44eb877ba3030151803dd64))





## v0.15.0 (2026-04-06)







## v0.15.0-beta.8 (2026-04-05)




### chores

- Fix docs accuracy and remove dead event_bus param
  ([`9461925`](https://github.com/kagan-sh/kagan/commit/9461925a421cf5ca6cc38262ec2ffb275753f621))





## v0.15.0-beta.7 (2026-04-05)




### chores

- **deps-dev**: Bump esbuild from 0.27.4 to 0.27.5 in /packages/vscode
  ([#90](https://github.com/kagan-sh/kagan/pull/90),
  [`a744bc1`](https://github.com/kagan-sh/kagan/commit/a744bc11407bb148fb272da132895cfade9934a2))

- Update pnpm-lock.yaml for esbuild bump ([#90](https://github.com/kagan-sh/kagan/pull/90),
  [`a744bc1`](https://github.com/kagan-sh/kagan/commit/a744bc11407bb148fb272da132895cfade9934a2))





## v0.15.0-beta.6 (2026-04-05)




### chores

- **deps-dev**: Bump typescript from 5.9.3 to 6.0.2 in /packages/vscode
  ([#91](https://github.com/kagan-sh/kagan/pull/91),
  [`cd89c2a`](https://github.com/kagan-sh/kagan/commit/cd89c2a36542ac78f5960401041a6eba0e350118))

- Update pnpm-lock.yaml for typescript bump ([#91](https://github.com/kagan-sh/kagan/pull/91),
  [`cd89c2a`](https://github.com/kagan-sh/kagan/commit/cd89c2a36542ac78f5960401041a6eba0e350118))





## v0.15.0-beta.5 (2026-04-02)




### features

- Add agent reliability and UX refinements
  ([`313c45f`](https://github.com/kagan-sh/kagan/commit/313c45f3588ae480df9eae3b0764e3380cb9d24e))





## v0.15.0-beta.4 (2026-04-02)




### bug fixes

- Wait for file picker loading on Windows before asserting
  ([`930efd2`](https://github.com/kagan-sh/kagan/commit/930efd2a7645f06c70aa8646fbe0c5d559f088f6))





## v0.15.0-beta.3 (2026-04-02)




### bug fixes

- Eliminate flaky Windows TUI test failures
  ([`4ec03da`](https://github.com/kagan-sh/kagan/commit/4ec03da32bdf3f346d8eca552e76d76943fb7013))





## v0.15.0-beta.2 (2026-04-02)




### bug fixes

- **ci**: Skip MCP registry publish on prerelease tags
  ([`5298a5e`](https://github.com/kagan-sh/kagan/commit/5298a5eb05e1ba3aa05e12a4f7ad87608d0dc02d))





## v0.14.3 (2026-03-29)







## v0.14.3-beta.1 (2026-03-29)




### chores

- **vscode**: Bump to 0.3.2 [skip ci]
  ([`75eeed7`](https://github.com/kagan-sh/kagan/commit/75eeed7e9d54230aed1b7fcd020172c69869321c))











### documentation

- Fix homepage grid layout
  ([`1b91adc`](https://github.com/kagan-sh/kagan/commit/1b91adce829b19577fac4bab3c86769ae794e0ba))











### refactoring

- **deps**: Make sqlalchemy explicit, document httpx pin
  ([`cbdc5a6`](https://github.com/kagan-sh/kagan/commit/cbdc5a67dfb3dcc67d6228a8481f7107256c183f))





## v0.14.2 (2026-03-29)







## v0.14.2-beta.1 (2026-03-29)




### bug fixes

- **deps**: Pin httpx to stable versions <1.0.0
  ([`12129f1`](https://github.com/kagan-sh/kagan/commit/12129f175e90707baefa24546da7baae44017cac))











### chores

- **vscode**: Bump to 0.3.1 [skip ci]
  ([`1db6a01`](https://github.com/kagan-sh/kagan/commit/1db6a0125eb171ac25c4acff926896da78c38b27))





## v0.14.1 (2026-03-29)







## v0.14.1-beta.2 (2026-03-29)




### bug fixes

- **deps**: Add missing pathspec dependency for file_picker
  ([`3b4dcc7`](https://github.com/kagan-sh/kagan/commit/3b4dcc7b2b3bc72191877f76201089a757598099))





## v0.14.1-beta.1 (2026-03-29)




### bug fixes

- **web**: Defensive handling in timeAgo for null/undefined values
  ([`2bdfd11`](https://github.com/kagan-sh/kagan/commit/2bdfd11d345a20cf4c3c6be1b2e6f0cf3ffef612))





## v0.14.0-beta.1 (2026-03-29)




### documentation

- Clarify VS Code extension install paths
  ([`e31a82f`](https://github.com/kagan-sh/kagan/commit/e31a82f2e14c5566ef3ac2857bd67c8e66a3697b))











### features

- Improve cross-client interoperability and onboarding
  ([`b13bed3`](https://github.com/kagan-sh/kagan/commit/b13bed30afad6b749fd36e41cf8643a670aaf895))





## v0.14.0 (2026-03-29)

### Features

- **cli**: First-launch surface picker for improved onboarding — running `kagan` for the first time now shows an interactive picker to choose your preferred interface (TUI, Web, Chat, VS Code, or MCP)
- **core**: Capability-based backend specification system — Claude Code and Codex are now designated as "reference backends" with first-class support
- **core**: Reference backend guidance in doctor and preflight — `kagan doctor` now surfaces specific installation and authentication hints when backend checks fail
- **core**: Shared event rendering protocol — ensures consistent display of agent output across TUI, Web, and VS Code
- **core**: Real-time presence and task watching — task cards now display watcher counts when multiple clients are viewing
- **core**: Event bus for cross-client synchronization — broadcasts events across clients for real-time updates
- **core**: Session resume modal and file picker in TUI
- **vscode**: Agent backend settings commands — `kagan.settings.agentBackend`, `kagan.settings.reviewStrictness`, `kagan.settings.planningDepth`
- **vscode**: Shared event rendering implementation for consistent output display
- **vscode**: SSE polling fallback for disconnected states
- **vscode**: Follow-up message support in chat
- **web**: Workspace view in activity bar and command palette
- **web**: Review snapshot and evidence log with criteria coverage and decision guidance
- **web**: Type-ahead chat input with interrupt-and-edit
- **web**: Task presence indicators showing watcher counts
- **web**: Agent picker with reference backend badges

### Bug Fixes

- **core**: Shell operator support in success_command — commands with `&&`, pipes, redirects now work correctly
- **core**: Tolerate float timeout settings — fixed crash when agent_timeout_seconds was a float
- **vscode**: Stable client_id for SSE presence tracking
- **vscode**: Clear sticky /watch state on new chat
- **vscode**: Auto-start uses `kagan serve` instead of `kagan web --no-open`
- **web**: Stable client_id generation for presence tracking
- **web**: Presence heartbeat mechanism for live watcher counts
- **server**: Increased rate limits and connection token validation for presence

### Documentation

- Updated quickstart with surface hierarchy and canonical workflow
- Updated MCP setup guide with role-based access control
- Updated troubleshooting with `kagan doctor` command
- Clarified VS Code extension vs MCP guidance



## v0.13.1-beta.7 (2026-03-28)




### bug fixes

- **cd**: Skip commit when vscode version already matches
  ([`185af4a`](https://github.com/kagan-sh/kagan/commit/185af4aa8d0e965bab84e6e2e9519e8dcfae5707))





## v0.13.1-beta.6 (2026-03-28)




### bug fixes

- **vscode**: Replace SVG with PNG in README (marketplace restriction)
  ([`fbe6ace`](https://github.com/kagan-sh/kagan/commit/fbe6ace5d7f1d7fc48faf35353234fba92587a3e))

- **vscode**: Use hero SVG in README, regenerate colored icon from logo-dark
  ([`c402951`](https://github.com/kagan-sh/kagan/commit/c40295126fedaf0fa0753b0c9cfd36cae462eadb))











### chores

- **vscode**: Bump to 0.2.1 [skip ci]
  ([`012050e`](https://github.com/kagan-sh/kagan/commit/012050e7928e1d652ab26d9f057b400cc9d89877))





## v0.13.1-beta.5 (2026-03-28)




### bug fixes

- **vscode**: Regenerate icon as 8-bit RGBA, use absolute URL in README
  ([`42a65e5`](https://github.com/kagan-sh/kagan/commit/42a65e5b2c4adbb9564acd4457a5c4f0dc495af9))





## v0.13.1-beta.4 (2026-03-28)




### chores

- **deps**: Bump @types/node from 20.19.37 to 25.5.0 in /packages/vscode
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump @vitejs/plugin-react from 4.4.1 to 6.0.1 in /packages/web
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump @wdio/globals from 8.46.0 to 9.27.0 in /packages/vscode
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump @wdio/mocha-framework from 8.46.0 to 9.27.0 in /packages/vscode
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump actions/cache from 4 to 5 ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump actions/configure-pages from 5 to 6
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump actions/deploy-pages from 4 to 5 ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump actions/setup-python from 5 to 6 ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump esbuild from 0.25.12 to 0.27.4 in /packages/vscode
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump jsdom from 26.1.0 to 29.0.1 in /packages/web
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump the npm_and_yarn group in /packages/web with 2 updates
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump vite from 6.3.5 to 8.0.3 in /packages/web
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Bump vitest from 4.1.1 to 4.1.2 in /packages/vscode
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Consolidate all dependabot updates ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Update pnpm-lock.yaml ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))

- **deps**: Upgrade all wdio packages to v9 for consistency
  ([#83](https://github.com/kagan-sh/kagan/pull/83),
  [`713291a`](https://github.com/kagan-sh/kagan/commit/713291a750bf3b7793af6d4d39f70c0654122324))





## v0.13.1-beta.3 (2026-03-28)




### bug fixes

- **cd**: Create Open VSX namespace before publish
  ([`3a5fc13`](https://github.com/kagan-sh/kagan/commit/3a5fc13d4abdf7508f5958b7885f91381885ef68))











### chores

- **vscode**: Bump to 0.2.0 [skip ci]
  ([`5f3fe85`](https://github.com/kagan-sh/kagan/commit/5f3fe85d30269180f33f07e7df56ef4a26631464))





## v0.13.1-beta.2 (2026-03-28)




### bug fixes

- **cd**: Make vscode publish fully manual with version input and target selection
  ([`3535d93`](https://github.com/kagan-sh/kagan/commit/3535d9344dbfeec69f3a3cdc9f3a11e8c9c4013a))





## v0.13.1-beta.1 (2026-03-28)




### bug fixes

- **cd**: Gracefully skip vscode publish when version already exists
  ([`f1d6f20`](https://github.com/kagan-sh/kagan/commit/f1d6f20e4d30d3548f761c046b0aa83b9be18a7c))











### chores

- **vscode**: Bump to 0.1.1, add LICENSE for marketplace
  ([`db61057`](https://github.com/kagan-sh/kagan/commit/db6105773cee6fea893b3bac41c045c9bd14c4a2))





## v0.13.0 (2026-03-28)







## v0.13.0-beta.5 (2026-03-28)




### chores

- **ci**: Warn when extension source changes without version bump
  ([`609ead1`](https://github.com/kagan-sh/kagan/commit/609ead1f5160a8e4bd4499d08da4cc0cfa040108))





## v0.13.0-beta.4 (2026-03-28)




### bug fixes

- **cd**: Decouple vscode version from pypi — independent lifecycles
  ([`74c8b66`](https://github.com/kagan-sh/kagan/commit/74c8b6669652598dfbfb51dfc98520b78a7cdc51))





## v0.13.0-beta.3 (2026-03-28)




### bug fixes

- **cd**: Sync vscode version with pypi, add to semantic-release version_variables
  ([`8528ea9`](https://github.com/kagan-sh/kagan/commit/8528ea93585844bde92a4bcb55410cffb54f9f2d))





## v0.13.0-beta.2 (2026-03-28)




### bug fixes

- **cd**: Publish vscode betas as pre-release, Open VSX only on prod
  ([`0197c62`](https://github.com/kagan-sh/kagan/commit/0197c62959251a68f18c4d7cb6dbaec9eea5ef3b))

- **cd**: Use env context instead of secrets in step-level if conditions
  ([`00deded`](https://github.com/kagan-sh/kagan/commit/00dededdda06666ff4fbbde2801ccc4282c4276d))











### chores

- **cd**: VS Code extension publishing to Marketplace and Open VSX
  ([`0197c62`](https://github.com/kagan-sh/kagan/commit/0197c62959251a68f18c4d7cb6dbaec9eea5ef3b))














### features

- **vscode**: Add marketplace metadata, icon, README, and changelog
  ([`0197c62`](https://github.com/kagan-sh/kagan/commit/0197c62959251a68f18c4d7cb6dbaec9eea5ef3b))

- **cd**: Add VS Code extension publishing to Marketplace and Open VSX
  ([`0197c62`](https://github.com/kagan-sh/kagan/commit/0197c62959251a68f18c4d7cb6dbaec9eea5ef3b))





## v0.13.0-beta.1 (2026-03-28)




### bug fixes

- **cd**: Remove pnpm version override conflicting with packageManager
  ([`9ad66f6`](https://github.com/kagan-sh/kagan/commit/9ad66f6660108ded6067a66b5544ca2e8c91ea2a))











### features

- VS Code extension, web dashboard refinements, and CI hardening
  ([`11c1f78`](https://github.com/kagan-sh/kagan/commit/11c1f78372b7895608e4b1e656d2a5de4299e2c9))





## v0.12.2-beta.2 (2026-03-25)




### bug fixes

- **server**: Add DB polling to SSE stream for cross-process task updates
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))

- **tui**: Add defensive handling in onboarding form
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))

- **core,tui**: Eliminate redundant DB lookup in project activation
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))

- **server**: SSE stream misses cross-process task updates
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))

- **core**: Suppress stdout during DB migrations to prevent MCP JSON-RPC corruption
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))














### refactoring

- **core**: Address Greptile review comments on PR #66
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))

- Address Greptile review — Zen of Python compliance
  ([#67](https://github.com/kagan-sh/kagan/pull/67),
  [`3f31516`](https://github.com/kagan-sh/kagan/commit/3f315165cad165c54fbedb436ccf386e17c98762))





## v0.12.2-beta.1 (2026-03-24)




### bug fixes

- **tui**: Add defensive handling in onboarding form
  ([#66](https://github.com/kagan-sh/kagan/pull/66),
  [`a5e08bb`](https://github.com/kagan-sh/kagan/commit/a5e08bb2759843d8549d5dfd974b27a7d0f3ceb4))

- **core,tui**: Eliminate redundant DB lookup in project activation
  ([#66](https://github.com/kagan-sh/kagan/pull/66),
  [`a5e08bb`](https://github.com/kagan-sh/kagan/commit/a5e08bb2759843d8549d5dfd974b27a7d0f3ceb4))

- **core**: Suppress stdout during DB migrations to prevent MCP JSON-RPC corruption
  ([#66](https://github.com/kagan-sh/kagan/pull/66),
  [`a5e08bb`](https://github.com/kagan-sh/kagan/commit/a5e08bb2759843d8549d5dfd974b27a7d0f3ceb4))











### refactoring

- **core**: Address Greptile review comments on PR #66
  ([#66](https://github.com/kagan-sh/kagan/pull/66),
  [`a5e08bb`](https://github.com/kagan-sh/kagan/commit/a5e08bb2759843d8549d5dfd974b27a7d0f3ceb4))





## v0.12.1 (2026-03-23)







## v0.12.1-beta.5 (2026-03-23)




### bug fixes

- **tui**: Add defensive handling in onboarding form
  ([#65](https://github.com/kagan-sh/kagan/pull/65),
  [`c86beb0`](https://github.com/kagan-sh/kagan/commit/c86beb01d8dfcb25159e05b7001d92f39b274476))

- **core,tui**: Eliminate redundant DB lookup and handle race condition
  ([#65](https://github.com/kagan-sh/kagan/pull/65),
  [`c86beb0`](https://github.com/kagan-sh/kagan/commit/c86beb01d8dfcb25159e05b7001d92f39b274476))

- **core,tui**: Eliminate redundant DB lookup in project activation
  ([#65](https://github.com/kagan-sh/kagan/pull/65),
  [`c86beb0`](https://github.com/kagan-sh/kagan/commit/c86beb01d8dfcb25159e05b7001d92f39b274476))





## v0.12.1-beta.4 (2026-03-23)




### bug fixes

- **tui**: Add defensive handling in onboarding form
  ([#64](https://github.com/kagan-sh/kagan/pull/64),
  [`b71b625`](https://github.com/kagan-sh/kagan/commit/b71b6252569bb9756ad4e81e9e60ef2b43e3ee6e))





## v0.12.1-beta.3 (2026-03-23)




### bug fixes

- **deps**: Pin httpx to stable versions <1.0 ([#63](https://github.com/kagan-sh/kagan/pull/63),
  [`7b5b6e8`](https://github.com/kagan-sh/kagan/commit/7b5b6e8323bd2479d05ed6082ca8107ac4dddbfc))





## v0.12.1-beta.2 (2026-03-23)




### chores

- **deps**: Bump typescript from 5.9.3 to 6.0.2 in /packages/web
  ([#60](https://github.com/kagan-sh/kagan/pull/60),
  [`c7099aa`](https://github.com/kagan-sh/kagan/commit/c7099aace754e8f775b0d0409fb8cd113cbcf7fb))





## v0.12.1-beta.1 (2026-03-23)




### bug fixes

- **web**: Replace unstable GitHub icon import
  ([`5a37881`](https://github.com/kagan-sh/kagan/commit/5a378816f48b2441058f78fbf2843d827e651853))






































### chores

- **security**: Add Socket license policy
  ([`ffffe9b`](https://github.com/kagan-sh/kagan/commit/ffffe9b916594337d6ef32050a8bf93bdca6c349))

- **ci**: Bump actions/create-github-app-token from 2 to 3
  ([#57](https://github.com/kagan-sh/kagan/pull/57),
  [`11081af`](https://github.com/kagan-sh/kagan/commit/11081af701b4f52b03fa4b60400a11d4295149e6))

- **ci**: Bump actions/github-script from 7 to 8 ([#53](https://github.com/kagan-sh/kagan/pull/53),
  [`ed4bb82`](https://github.com/kagan-sh/kagan/commit/ed4bb82b043a0a872206a487dd6d6096ded2e115))

- **ci**: Bump actions/setup-node from 4 to 6 ([#56](https://github.com/kagan-sh/kagan/pull/56),
  [`c0cd18a`](https://github.com/kagan-sh/kagan/commit/c0cd18ad744c5f6ceeabda4c52fd3717032f5d28))

- **ci**: Bump actions/upload-artifact from 4 to 7
  ([#55](https://github.com/kagan-sh/kagan/pull/55),
  [`1190a8b`](https://github.com/kagan-sh/kagan/commit/1190a8b770a280e1697b6771e443320dc6f9623c))

- **deps**: Bump lucide-react from 0.469.0 to 1.0.1 in /packages/web
  ([#62](https://github.com/kagan-sh/kagan/pull/62),
  [`9652e9b`](https://github.com/kagan-sh/kagan/commit/9652e9b77e5768f466d79b081e54b58343b12413))

- **deps**: Bump marked from 15.0.12 to 17.0.5 in /packages/web
  ([#59](https://github.com/kagan-sh/kagan/pull/59),
  [`44584aa`](https://github.com/kagan-sh/kagan/commit/44584aadafd366190222e3d030d3ab6301cfa6a9))

- **ci**: Bump pnpm/action-setup from 4 to 5 ([#54](https://github.com/kagan-sh/kagan/pull/54),
  [`b3d6969`](https://github.com/kagan-sh/kagan/commit/b3d6969dc035de877475826c01bb7f627ba93aa2))

- **deps**: Bump the all group in /packages/web with 8 updates
  ([#58](https://github.com/kagan-sh/kagan/pull/58),
  [`0c597d8`](https://github.com/kagan-sh/kagan/commit/0c597d801ddbf208ed348932a0993af589eed3b1))

- **deps**: Bump zod from 3.25.76 to 4.3.6 in /packages/web
  ([#61](https://github.com/kagan-sh/kagan/pull/61),
  [`5538356`](https://github.com/kagan-sh/kagan/commit/5538356ca573f58d7af0e3e721b3b33d324c5a67))














### continuous integration

- Guard semantic release summaries
  ([`505126e`](https://github.com/kagan-sh/kagan/commit/505126edb8457663e176f4d2c5ff8a41633d2533))

- Improve semantic release notes
  ([`ecce4da`](https://github.com/kagan-sh/kagan/commit/ecce4da763254df5a603126d6321642ca199e74e))





## v0.12.0 (2026-03-23)


## v0.12.0-beta.1 (2026-03-23)

### Bug Fixes

- **chat**: Satisfy lint on prompt and ACP probe ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- **chat**: Stabilize copilot ACP and refine kg chat
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- **ci**: Resolve GitHub Models eval model from catalog
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- **ci**: Use app token for prompt evaluation ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- **prompts**: Address review feedback on export helpers
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- **web**: Eliminate 5-second delay on project switch
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

### Chores

- Auto-assign kagan-agent to issues and PRs ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- Close contributor infrastructure gaps from review
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

### Continuous Integration

- Make prompt evaluation advisory ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

### Documentation

- Fix broken font CDN and add llms.txt
  ([`e4a4601`](https://github.com/kagan-sh/kagan/commit/e4a4601be205fb9482b129342b7531e93b8fce37))

- Rewrite CONTRIBUTING.md for developer onboarding
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

### Features

- Add GitHub Models integration with prompt export and evaluation
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- GitHub Models integration with prompt export and evaluation
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

### Refactoring

- Apply Zen of Python review to prompt export pipeline
  ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- Reduce eval suite from 78 to 12 API calls ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))

- Route all dev commands through uv run poe ([#52](https://github.com/kagan-sh/kagan/pull/52),
  [`a28104f`](https://github.com/kagan-sh/kagan/commit/a28104fb976c200e213307e003e48e292c58cd18))


## v0.11.4 (2026-03-23)

### Documentation

- Add MCP tool descriptions
  ([`cbcc0eb`](https://github.com/kagan-sh/kagan/commit/cbcc0ebf114c331f2b54dd66088e9039cef78737))

- Move glama badge to secondary row
  ([`9c27f44`](https://github.com/kagan-sh/kagan/commit/9c27f44c7a2dc98f2e2850ebe42c963ef2ae8f72))


## v0.11.4-beta.2 (2026-03-23)

### Chores

- Improve glama metadata
  ([`d30c1c0`](https://github.com/kagan-sh/kagan/commit/d30c1c0500500c484ef4bb8ab7c5759fecb98fe1))


## v0.11.4-beta.1 (2026-03-23)

### Chores

- Add glama metadata
  ([`ab12fc3`](https://github.com/kagan-sh/kagan/commit/ab12fc3362bd328f3878f19efe17d3000ea78f89))


## v0.11.3 (2026-03-23)


## v0.11.3-beta.1 (2026-03-23)

### Chores

- Remove unused environmentVariables from MCP server.json
  ([`cb4b2ce`](https://github.com/kagan-sh/kagan/commit/cb4b2ce6b25efdbd430f9293bbec89c4926c9be9))


## v0.11.2 (2026-03-23)


## v0.11.2-beta.1 (2026-03-23)

### Chores

- Add MCP registry publishing configuration
  ([`0e860ea`](https://github.com/kagan-sh/kagan/commit/0e860ea453e6fef71cb8b8cd0c661bd6468f91cf))


## v0.11.1 (2026-03-23)


## v0.11.1-beta.1 (2026-03-23)

### Bug Fixes

- **mcp**: Keep attached session tools consistent ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Report attached session state explicitly
  ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Resolve remaining bot review findings ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Restore static resource registration ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

### Documentation

- **mcp**: Align tiers and payload wording ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Clarify orchestrator tier semantics ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Document explicit session and review tools
  ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Explain review tool registration split ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

### Refactoring

- **mcp**: Align role profiles with explicit tools
  ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Apply bot review follow-ups ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Make session and review tools explicit ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Read resources from request context ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Split attached session actions into explicit tools
  ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))

- **mcp**: Split review actions into explicit tools
  ([#49](https://github.com/kagan-sh/kagan/pull/49),
  [`a2f2dcf`](https://github.com/kagan-sh/kagan/commit/a2f2dcf801d44047d1487f2ad0bafce6dcc17075))


## v0.11.0 (2026-03-23)


## v0.11.0-beta.2 (2026-03-23)

### Bug Fixes

- Address pre-release audit findings (security, correctness, metadata)
  ([`80b1d4a`](https://github.com/kagan-sh/kagan/commit/80b1d4a47762c28221719969611f5aaaaf051a5e))

- **server**: Add @require_context auth to /api/fs/browse endpoint
  ([`80b1d4a`](https://github.com/kagan-sh/kagan/commit/80b1d4a47762c28221719969611f5aaaaf051a5e))

### Refactoring

- Apply Zen of Python UX refinements across TUI, web, and CLI
  ([`3beb88a`](https://github.com/kagan-sh/kagan/commit/3beb88a4a329c43129a3addfd9ba91614607e8bb))

- Zen of Python refinements across server, web, and tests
  ([`be8e0ce`](https://github.com/kagan-sh/kagan/commit/be8e0ceb55f84c94a352c0d2fedfdd4b1e35ec1c))


## v0.11.0-beta.1 (2026-03-22)

### Documentation

- Sync documentation with web, mcp, chat, and tui implementations
  ([`1b76bec`](https://github.com/kagan-sh/kagan/commit/1b76bec5cd0b8b583ee8029b23642aa3525c5fe7))

### Features

- **cli**: Improve error UX and discoverability per clig.dev guidelines
  ([`bd8b883`](https://github.com/kagan-sh/kagan/commit/bd8b883ef0295d724c01ee6c529a916a5a85fac1))


## v0.10.1 (2026-03-21)


## v0.10.1-beta.1 (2026-03-21)

### Bug Fixes

- **web**: Graceful shutdown and service worker API denylist
  ([`b5d9aca`](https://github.com/kagan-sh/kagan/commit/b5d9acac4279fcd689563706d966c0ba6a959e92))

### Documentation

- Restore star history chart to README
  ([`157f77c`](https://github.com/kagan-sh/kagan/commit/157f77c5890d5bf432b5e3f05cf806acb4f93f29))


## v0.10.0 (2026-03-21)


## v0.10.0-beta.4 (2026-03-21)

### Bug Fixes

- **build**: Restore force-include with exclude to prevent duplicates
  ([`98b05d0`](https://github.com/kagan-sh/kagan/commit/98b05d04d3e783308f560660c2937da6091a9140))


## v0.10.0-beta.3 (2026-03-21)

### Bug Fixes

- **core**: Compat import for ACP KillTerminalResponse rename
  ([`2db3485`](https://github.com/kagan-sh/kagan/commit/2db34855eb3fb4687d828f45d218b28134c08c27))


## v0.10.0-beta.2 (2026-03-21)

### Bug Fixes

- **build**: Remove duplicate force-include causing PyPI upload rejection
  ([`6aa37e5`](https://github.com/kagan-sh/kagan/commit/6aa37e585d1fc50423ab9e200ce51eadebc9bb2e))


## v0.10.0-beta.1 (2026-03-21)

### Bug Fixes

- Address greptile review — persist, subprocess leak, task cancel, backoff
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Clear busy state on agent failure in web UI and flush throttler on chat error
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Guard page reference in docs template, resolve all type errors
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Include web-build in dev-setup sequence ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Raise repetition guard threshold, expose worktree path, smart cancel recovery
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Remove type:ignore suppressions, use proper type annotations
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Repetition guard false-positive, event ordering race, session interop
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Resolve pyrefly type errors in chat routes and agent status widget
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Simplify PAIR launchers — prompt as CLI arg, IDE opens worktree+file
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Web admin access, ws reconnect, load-earlier pagination, and worker board awareness
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Web streaming resilience, race condition resolution, and repetition guard integration
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **chat**: Persist user message before turn and recover busy state on remount
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **chat**: Re-read session before title save to prevent history overwrite
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Audit task mutations ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Emit board events for all session lifecycle changes
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Kill subprocess on success_command timeout
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **e2e**: Seed one task in ensureBoardReady so Kanban columns render
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **e2e**: WaitForLoadState('load') — networkidle hangs on SSE stream
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **prompts**: Correct agent prompt inconsistencies with actual MCP toolset
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **server**: Allow project creation from web ui ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **server**: Handle WebSocket scope in SPA static handler
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **streaming**: Overhaul agent output streaming across TUI and web
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **tui**: Pair instruction modal keybindings fire non-existent actions
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Allow chat input while WebSocket is disconnected
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Blank screen on first board load after project creation
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Chat stream survives page reload + project picker blank page
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Filter streaming noise from board task inspector activity
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Recover dashboard runtime failures ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Split task chat rail by lane ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Streaming resilience, race conditions, structural improvements + test helpers
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

### Chores

- Comments and docstrings cleanup ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Track pnpm-lock.yaml, restore frozen-lockfile in CI
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Update project configuration, CI pipeline, and dependencies
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

### Continuous Integration

- Add test-web job for Vitest unit tests and Playwright E2E
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Trigger rerun after cache fix ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **test-web**: Bump timeout to 20m, fix pnpm store path
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **test-web**: Fix pnpm store caching — use actions/cache@v4 directly
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **test-web**: Pnpm-lock.yaml is gitignored — no-frozen-lockfile, key on package.json
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **test-web**: Use poe web-build to copy assets into _web_static
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

### Documentation

- Add mkdocs-redirects plugin to fix 404 errors for old URLs
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Add mkdocs-redirects plugin to fix 404 errors for old URLs
  ([#43](https://github.com/kagan-sh/kagan/pull/43),
  [`bebfe06`](https://github.com/kagan-sh/kagan/commit/bebfe06477cf0847e127dc2226838ee5c43f9da2))

- Align mcp, tui, and web references ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Clean internal chat and review feature notes ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Clean internal docs index and testing examples ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Correct plugin registration guidance ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Docs bump
  ([`9d46b7f`](https://github.com/kagan-sh/kagan/commit/9d46b7f4f2442ca1c5db27e8804dbd5b346845a6))

- Fix 404 redirects, add OG tags, improve page titles and docs metadata
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Fix Material tab formatting in MCP setup guide ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Label internal platform architecture code fences
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Minor seo tweaks ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Minor seo tweaks ([#43](https://github.com/kagan-sh/kagan/pull/43),
  [`bebfe06`](https://github.com/kagan-sh/kagan/commit/bebfe06477cf0847e127dc2226838ee5c43f9da2))

- Normalize command examples in chat and CLI docs ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Normalize internal chat and task architecture docs
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Refine docs ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Refine docs ([#43](https://github.com/kagan-sh/kagan/pull/43),
  [`bebfe06`](https://github.com/kagan-sh/kagan/commit/bebfe06477cf0847e127dc2226838ee5c43f9da2))

- Remove shortcut artifacts from user navigation docs
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Repair internal architecture and testing rendering
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Rewrite guidance for managed and interactive runs
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Tighten lifecycle and remote access sections ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Update AGENTS.md and server architecture for response models
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Update architecture and feature specifications ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Update documentation and add remote access guide
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Update internal architecture and feature docs for AI best practices
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

### Features

- Add attribution (OSS license, GitHub, MakerX) to web UI
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Add HTTP/WebSocket server, crypto, and wire protocol subsystems
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Add React 19 web dashboard with jotai state and Tailwind CSS 4
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Display ACP token usage and cost metrics across all surfaces
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Enhance core domain with reviews, prompts, events, and DB migrations
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Redesign TUI task screen, chat system, and MCP toolsets
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Refactor MCP access to role-based model and refine web pair mode UX
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Remote clients, web dashboard, unified sessions, and attach-as-interrupt
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Replace WebSocket with SSE, add repetition guard, retry logic, context warnings, error
  classification ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **chat**: Refine picker and slash-command UX ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **chat**: Unified per-session backend switching across REPL, TUI, and web
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **chat,tui,web**: Session picker improvements, chat commands, and keybindings
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **cli**: Restore informative impact summary to kg reset command
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Add secret scrubbing on event storage ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Add session token tracking with ACP UsageUpdate extraction
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Inject project-scoped learnings into task prompts
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **mcp**: Add typed tool profiles for per-session tool filtering
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **server**: Add response models as single source of truth for API wire shape
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **tui**: Add resume context to task detail ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **tui,web**: Attach interrupts managed runs and improves board resume
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

### Refactoring

- Eliminate wire model layer, serialize SQLModel directly
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Reduce chat route complexity below McCabe cap ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Remove dead code, consolidate duplicates, clean unused parameters
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Replace stringly-typed patterns with StrEnum and TypedDict
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- Server API and TUI widgets for remote client resilience
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **core**: Unify runs around launcher sessions ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **mcp**: Reduce complexity in review toolset register function
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **prompts**: Remove redundant hardcoded MCP tool listings from agent prompts
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **tui**: Remove dead review modal styles ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **tui,web**: Replace task modes with start and attach flows
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

### Testing

- **core**: Add prompt snapshot tests for regression detection
  ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))

- **web**: Align e2e smoke flows with current ui ([#44](https://github.com/kagan-sh/kagan/pull/44),
  [`7010551`](https://github.com/kagan-sh/kagan/commit/7010551d00dba0cb12dbe0bc67aee80bd59e87d8))


## v0.9.0 (2026-03-08)


## v0.9.0-beta.1 (2026-03-08)

### Bug Fixes

- Guard worktree removal against missing repo directories
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))

- Import asyncio compat filter from public API instead of private module
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))

- Remove ctrl+j binding and add ctrl+c hint to chat placeholder
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))

- Remove ctrl+j binding, extract asyncio compat to core, and harden worktree cleanup
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))

### Chores

- Bump version to 0.8.1
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))

### Features

- Add acp_args field to all agent backend configs
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))

### Refactoring

- Extract asyncio subprocess filter from tui to core for MCP reuse
  ([`22d5d3c`](https://github.com/kagan-sh/kagan/commit/22d5d3c65f5cbb926d4825d3c151f89efb1d5728))


## v0.8.1 (2026-03-08)


## v0.8.1-beta.4 (2026-03-08)

### Bug Fixes

- Override default Ctrl+C behavior to handle chat interrupts
  ([`9c75652`](https://github.com/kagan-sh/kagan/commit/9c756524342770d02001908f14b1c3e1ebec9453))


## v0.8.1-beta.3 (2026-03-08)

### Bug Fixes

- Improve Ctrl+C interrupt handling in chat orchestrator
  ([#41](https://github.com/kagan-sh/kagan/pull/41),
  [`6ff707a`](https://github.com/kagan-sh/kagan/commit/6ff707a6e50ad8faf47f07df7cc76556566f637d))

### Refactoring

- Address PR review feedback on interrupt handling
  ([#41](https://github.com/kagan-sh/kagan/pull/41),
  [`6ff707a`](https://github.com/kagan-sh/kagan/commit/6ff707a6e50ad8faf47f07df7cc76556566f637d))


## v0.8.1-beta.2 (2026-03-08)

### Bug Fixes

- Catch AttributeError from malformed ACP JSON-RPC messages
  ([`4bcbec3`](https://github.com/kagan-sh/kagan/commit/4bcbec3b523f7e577b5d3c1e63327fc9f831f0f3))


## v0.8.1-beta.1 (2026-03-08)

### Bug Fixes

- Warn when running inside Zellij < 0.42.0
  ([`da5f143`](https://github.com/kagan-sh/kagan/commit/da5f14349b5f838df9abcb131193ab2e68808333))


## v0.8.0 (2026-03-08)


## v0.8.0-beta.2 (2026-03-08)

### Bug Fixes

- Downgrade agent backend preflight check from FAIL to WARN
  ([`eb2a3dd`](https://github.com/kagan-sh/kagan/commit/eb2a3dd51ac3a132cc1b06305435bacd95f9eb02))


## v0.8.0-beta.1 (2026-03-08)

### Bug Fixes

- Add explicit Save/Cancel buttons to settings dialog
  ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

- Address community-reported issues #35–#39 ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

- Clean shutdown of subprocess transports on quit ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

- Drop hardcoded ACP format flags for claude-code backend
  ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

- Guard worktree creation against missing git repo
  ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

### Chores

- Improve streaming responsiveness and refresh assets
  ([`2b40a77`](https://github.com/kagan-sh/kagan/commit/2b40a77abc4a6d49a4e393df1d3c1a159c7374ee))

### Documentation

- Refine docs ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

### Features

- Add project deletion from Welcome screen ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

### Refactoring

- Address PR review feedback ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))

### Testing

- Update ACP spawn test to match empty acp_args ([#40](https://github.com/kagan-sh/kagan/pull/40),
  [`53af0e5`](https://github.com/kagan-sh/kagan/commit/53af0e5c3e24d8cafe776ea76c88860fce5e06d5))


## v0.7.0 (2026-03-08)

### Documentation

- Tweaks
  ([`f7aa602`](https://github.com/kagan-sh/kagan/commit/f7aa6023b956b1ba8b0b293ade0d0f156d609bbb))

### Refactoring

- Bug fixes ([#34](https://github.com/kagan-sh/kagan/pull/34),
  [`d6d5ca2`](https://github.com/kagan-sh/kagan/commit/d6d5ca224d645c5ffce451ce2e9583d98ee09dfe))


## v0.7.0-beta.2 (2026-03-05)

### Documentation

- Readme tweak
  ([`0fec93a`](https://github.com/kagan-sh/kagan/commit/0fec93a24dc55c6130914db4cd3e02cbe4159d2b))


## v0.7.0-beta.1 (2026-03-05)

### Chores

- Logo patch for pypi
  ([`f96a3ff`](https://github.com/kagan-sh/kagan/commit/f96a3fff61356b02c47b3165cbe985248c66a2e7))

### Documentation

- Favicon
  ([`4ced1b1`](https://github.com/kagan-sh/kagan/commit/4ced1b1f93ede8958db513979e4a689b579fe9a7))

- Icon tweaks
  ([`756fbcc`](https://github.com/kagan-sh/kagan/commit/756fbcc2aba0cd2da4f07e95ead7f5ee114fe787))

### Features

- Refactoring ([#33](https://github.com/kagan-sh/kagan/pull/33),
  [`c31852e`](https://github.com/kagan-sh/kagan/commit/c31852edf3f00200aaebd84d61ffc12cd01173e5))


## v0.6.0-beta.1 (2026-02-20)

### Bug Fixes

- Cap orchestrator smoke wait times and stabilize ci
  ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

- Include pending chat overlay collaborator wiring
  ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

- Resolve lint gate failure in mcp tool closures ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

- Stabilize auto backlog enter ci flows ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

- Stabilize orchestrator overlay ci smoke tests ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

- Unblock CI gates and commit workspace updates ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

### Chores

- Commit all current workspace changes ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

- Commit all remaining workspace edits ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

### Documentation

- Final copy pass — remove emojis, leaked paths, and tighten reference prose
  ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))

### Features

- Simplification ui and ux improvements; github integration; orchestrator > planner
  ([#27](https://github.com/kagan-sh/kagan/pull/27),
  [`32e0eb3`](https://github.com/kagan-sh/kagan/commit/32e0eb3ccfafafac3bdd4b0be25be57d462f3b06))


## v0.6.0 (unreleased)

> **Upgrade from v0.5.0:** No migration required. The database schema is unchanged.
> Run `kagan update` and restart — your data is safe.

### Breaking changes

- **SDK/MCP mutation response shapes** — `task_create`, `project_create`, and `task_patch` now return nested canonical payloads only. Flat top-level fields (`task_id`, `project_id`, `title`, `status`, `name`, `description`) were removed. Migrate to:
  - `result.task.id` instead of `result.task_id`
  - `result.project.id` instead of `result.project_id`
  - `result.task.title`, `result.task.status` instead of top-level `title`/`status`
  See [MCP tools reference](https://docs.kagan.sh/reference/mcp-tools/#mutation-response-shapes-sdk--mcp) for full details.

### Features

- **Acceptance criteria coverage check** — tasks cannot transition to REVIEW unless all
  acceptance criteria are addressed
- **Resume Context panel** — task details modal now shows agent context for easy handoff
- **Structured summary panel** in ReviewModal — surfaces agent-written summaries at review time
- **MCP persona presets** — `kagan personas` lists and applies built-in agent personas;
  `default_worker_agent` / `orchestrator_persona` config fields added
- **`task_annotate` MCP tool** — agents can append structured reasoning notes to a task's
  scratchpad mid-run
- **Interaction verbosity** — global `interaction_verbosity` setting controls how much
  user-facing UX output agents emit
- **Doctor-driven startup checks** — deterministic, verbose doctor output; critical blockers
  surface immediately on `kagan` launch
- **Orchestrator slash commands** simplified; persona switching added to the chat overlay
- **Ctrl+P fullscreen / Ctrl+O docked** orchestrator panel toggles
- **Unified overlay chat targets** and consistent task terminology across TUI

### Bug Fixes

- Harden prompt-injection and privacy boundaries (redaction, tag escaping)
- Restore planner chat UX with real-time streaming
- Restore first-run onboarding so users can choose their backend agent before Welcome
- Standardize canonical Pydantic domain models and rebuild MCP schemas
- `poe dev` path corrections and local docs-serve fixes
- TUI chat loading UX hardened: animated `initializing` during connection, chat input locked while requests are in-flight, and timeout recovery prevents indefinite thinking loops


### Documentation

- Comprehensive MkDocs overhaul: IA consolidation (17 → 12 files), features and content parity
- Architecture doc invites plugin ecosystem discussion
- Save bindings updated to Ctrl+S / Ctrl+E; F2 removed

## v0.5.0 (2026-02-12)

### Documentation

- Fix Snyk badge and move to secondary row [skip ci]
  ([`9d3af86`](https://github.com/kagan-sh/kagan/commit/9d3af861a395d23c7ef1de8ddb18032e19778547))


## v0.5.0-beta.1 (2026-02-12)

### Bug Fixes

- **core**: Reject unreachable tcp endpoints during discovery
  ([#21](https://github.com/kagan-sh/kagan/pull/21),
  [`f5c94c3`](https://github.com/kagan-sh/kagan/commit/f5c94c3c06c727dec6097122e59a51d583714e34))

- **tui**: Read boundary scan files as utf-8 ([#21](https://github.com/kagan-sh/kagan/pull/21),
  [`f5c94c3`](https://github.com/kagan-sh/kagan/commit/f5c94c3c06c727dec6097122e59a51d583714e34))

- **windows**: Stabilize daemon startup lock and console output
  ([#21](https://github.com/kagan-sh/kagan/pull/21),
  [`f5c94c3`](https://github.com/kagan-sh/kagan/commit/f5c94c3c06c727dec6097122e59a51d583714e34))

### Features

- Admin mcp; decoupled and refined architecture; initial work on plugin system
  ([#21](https://github.com/kagan-sh/kagan/pull/21),
  [`f5c94c3`](https://github.com/kagan-sh/kagan/commit/f5c94c3c06c727dec6097122e59a51d583714e34))

- Decoupled into core; tui; mcp components; full admin control over kagan board via admin roled mcp
  ([#21](https://github.com/kagan-sh/kagan/pull/21),
  [`f5c94c3`](https://github.com/kagan-sh/kagan/commit/f5c94c3c06c727dec6097122e59a51d583714e34))


## v0.4.1 (2026-02-08)


## v0.4.1-beta.1 (2026-02-08)

### Bug Fixes

- Allow Escape to close review modal during automation-managed live streams
  ([#20](https://github.com/kagan-sh/kagan/pull/20),
  [`939c2e7`](https://github.com/kagan-sh/kagan/commit/939c2e76f5bf221b9b7b7ca5a74ccaf6b4388345))

- Refresh Kanban board when returning from planner to show newly created tasks
  ([#20](https://github.com/kagan-sh/kagan/pull/20),
  [`939c2e7`](https://github.com/kagan-sh/kagan/commit/939c2e76f5bf221b9b7b7ca5a74ccaf6b4388345))

- Run MCP server in degraded mode instead of crashing outside a Kagan project
  ([#20](https://github.com/kagan-sh/kagan/pull/20),
  [`939c2e7`](https://github.com/kagan-sh/kagan/commit/939c2e76f5bf221b9b7b7ca5a74ccaf6b4388345))

- Skip auto-update for local/file-source installations
  ([#20](https://github.com/kagan-sh/kagan/pull/20),
  [`939c2e7`](https://github.com/kagan-sh/kagan/commit/939c2e76f5bf221b9b7b7ca5a74ccaf6b4388345))


### Testing

- Update snapshots, add AUTO restart test, skip flaky Windows CI tests
  ([#20](https://github.com/kagan-sh/kagan/pull/20),
  [`939c2e7`](https://github.com/kagan-sh/kagan/commit/939c2e76f5bf221b9b7b7ca5a74ccaf6b4388345))


## v0.4.0 (2026-02-08)


## v0.4.0-beta.1 (2026-02-08)

### Bug Fixes

- Handles database connection errors gracefully ([#19](https://github.com/kagan-sh/kagan/pull/19),
  [`8904a04`](https://github.com/kagan-sh/kagan/commit/8904a04142db7c2248984b8d8323860ed65fe6ba))

- Output streaming and branch popup bug fixes; cleanup and refinements
  ([#19](https://github.com/kagan-sh/kagan/pull/19),
  [`8904a04`](https://github.com/kagan-sh/kagan/commit/8904a04142db7c2248984b8d8323860ed65fe6ba))

### Chores

- Remove Makefile and dead code script, update docs formatting
  ([#19](https://github.com/kagan-sh/kagan/pull/19),
  [`8904a04`](https://github.com/kagan-sh/kagan/commit/8904a04142db7c2248984b8d8323860ed65fe6ba))

### Features

- Add unified RuntimeService for session, startup, and task orchestration
  ([#19](https://github.com/kagan-sh/kagan/pull/19),
  [`8904a04`](https://github.com/kagan-sh/kagan/commit/8904a04142db7c2248984b8d8323860ed65fe6ba))


### Testing

- Add and update tests for all updated modules ([#19](https://github.com/kagan-sh/kagan/pull/19),
  [`8904a04`](https://github.com/kagan-sh/kagan/commit/8904a04142db7c2248984b8d8323860ed65fe6ba))


## v0.3.0 (2026-02-07)


## v0.3.0-beta.6 (2026-02-07)

### Bug Fixes

- Add additional is_mounted guards in async worker methods
  ([#18](https://github.com/kagan-sh/kagan/pull/18),
  [`58c51ec`](https://github.com/kagan-sh/kagan/commit/58c51ec7e0692bd9f748373431e374654201de02))

- Add is_mounted guards to prevent database access during shutdown
  ([#18](https://github.com/kagan-sh/kagan/pull/18),
  [`58c51ec`](https://github.com/kagan-sh/kagan/commit/58c51ec7e0692bd9f748373431e374654201de02))

### Continuous Integration

- Race condition in async workers accessing database during widget unmount
  ([#18](https://github.com/kagan-sh/kagan/pull/18),
  [`58c51ec`](https://github.com/kagan-sh/kagan/commit/58c51ec7e0692bd9f748373431e374654201de02))


## v0.3.0-beta.5 (2026-02-07)

### Bug Fixes

- Harden review modal against ci race conditions
  ([`24a0674`](https://github.com/kagan-sh/kagan/commit/24a0674e7017e5e4f586f08573992db28981601f))


## v0.3.0-beta.4 (2026-02-07)

### Bug Fixes

- Stabilize enter review auto-start assertion in ci
  ([`c301968`](https://github.com/kagan-sh/kagan/commit/c301968302c77927aeac534791c6ccbf75a0fae9))


## v0.3.0-beta.3 (2026-02-07)

### Bug Fixes

- Prevent cd release hangs from snapshot tests
  ([`0bc6fa5`](https://github.com/kagan-sh/kagan/commit/0bc6fa5c3d7437598b22d5450325ac64277d40bf))


## v0.3.0-beta.2 (2026-02-07)

### Bug Fixes

- Port Windows compatibility, snapshot isolation, and CI hardening
  ([#15](https://github.com/kagan-sh/kagan/pull/15),
  [`0602373`](https://github.com/kagan-sh/kagan/commit/0602373bef984f50f66a52867d2109e9c10ed029))

- Resolve quality blockers and stabilize test suite
  ([#15](https://github.com/kagan-sh/kagan/pull/15),
  [`0602373`](https://github.com/kagan-sh/kagan/commit/0602373bef984f50f66a52867d2109e9c10ed029))

### Chores

- Windows tweaks
  ([`e8c1fe9`](https://github.com/kagan-sh/kagan/commit/e8c1fe9eb186b03eec17e7336a28de662f4991df))

### Documentation

- Cap Python to 3.12–3.13 and update all user-facing documentation
  ([`a873c6a`](https://github.com/kagan-sh/kagan/commit/a873c6a10c3447f4ae44cc3f7b5a746fae0564ec))

- Refresh documentation and remove outdated internal references
  ([#15](https://github.com/kagan-sh/kagan/pull/15),
  [`0602373`](https://github.com/kagan-sh/kagan/commit/0602373bef984f50f66a52867d2109e9c10ed029))

### Features

- Implement planner mode, pair flow, and ACP streaming UI
  ([#15](https://github.com/kagan-sh/kagan/pull/15),
  [`0602373`](https://github.com/kagan-sh/kagan/commit/0602373bef984f50f66a52867d2109e9c10ed029))

- Projects, multi-repos, workspaces, bug fixes, ui polishing, windows support
  ([#15](https://github.com/kagan-sh/kagan/pull/15),
  [`0602373`](https://github.com/kagan-sh/kagan/commit/0602373bef984f50f66a52867d2109e9c10ed029))


## v0.3.0-beta.1 (2026-02-02)

### Chores

- **deps**: Add hypothesis testing library and update test config
  ([#11](https://github.com/kagan-sh/kagan/pull/11),
  [`d7c686a`](https://github.com/kagan-sh/kagan/commit/d7c686a6678a1ed7861f6ab2aff77126881344af))

### Continuous Integration

- Fix cd failing due to lack of git profile
  ([`1ea33fc`](https://github.com/kagan-sh/kagan/commit/1ea33fcb2384d76ad1d0e8f723632042e4dc4e36))

### Documentation

- Update documentation and add architecture guide
  ([#11](https://github.com/kagan-sh/kagan/pull/11),
  [`d7c686a`](https://github.com/kagan-sh/kagan/commit/d7c686a6678a1ed7861f6ab2aff77126881344af))

### Features

- Ux improvements and minor new features
  ([#11](https://github.com/kagan-sh/kagan/pull/11),
  [`d7c686a`](https://github.com/kagan-sh/kagan/commit/d7c686a6678a1ed7861f6ab2aff77126881344af))

- **cli**: Add tools command for agent management
  ([#11](https://github.com/kagan-sh/kagan/pull/11),
  [`d7c686a`](https://github.com/kagan-sh/kagan/commit/d7c686a6678a1ed7861f6ab2aff77126881344af))


## v0.2.1 (2026-01-31)

### Bug Fixes

- Use PEP 440 version syntax for uv tool upgrade command
  ([#10](https://github.com/kagan-sh/kagan/pull/10),
  [`92e4240`](https://github.com/kagan-sh/kagan/commit/92e4240d74501f767db90090c4420f2bec883b2e))

### Documentation

- Update readme
  ([`ae2c9a2`](https://github.com/kagan-sh/kagan/commit/ae2c9a2a33801184cc02edbbe2ce05dd9e1f6455))


## v0.2.0 (2026-01-31)


## v0.2.0-beta.3 (2026-01-31)

### Bug Fixes

- Add auto-mock for tmux in E2E tests for CI runners without tmux
  ([#8](https://github.com/kagan-sh/kagan/pull/8),
  [`6ea7f44`](https://github.com/kagan-sh/kagan/commit/6ea7f449d7af3e63ff97b88e7af0d27c81d00ee9))

- Improves agent detection and troubleshooting UX ([#8](https://github.com/kagan-sh/kagan/pull/8),
  [`6ea7f44`](https://github.com/kagan-sh/kagan/commit/6ea7f449d7af3e63ff97b88e7af0d27c81d00ee9))

- Include .gitignore in initial commit on first boot
  ([#8](https://github.com/kagan-sh/kagan/pull/8),
  [`6ea7f44`](https://github.com/kagan-sh/kagan/commit/6ea7f449d7af3e63ff97b88e7af0d27c81d00ee9))

- Resolve UI freezes from blocking operations ([#8](https://github.com/kagan-sh/kagan/pull/8),
  [`6ea7f44`](https://github.com/kagan-sh/kagan/commit/6ea7f449d7af3e63ff97b88e7af0d27c81d00ee9))

- Use explicit foreground colors for troubleshooting screen text
  ([#8](https://github.com/kagan-sh/kagan/pull/8),
  [`6ea7f44`](https://github.com/kagan-sh/kagan/commit/6ea7f449d7af3e63ff97b88e7af0d27c81d00ee9))

- **ci**: Separate test jobs to fix matrix conditional evaluation
  ([#9](https://github.com/kagan-sh/kagan/pull/9),
  [`fe57f66`](https://github.com/kagan-sh/kagan/commit/fe57f663aef153780eadd5699082932d0266ca1a))

- **tests**: Convert update CLI tests to async for proper event loop cleanup
  ([`769e46e`](https://github.com/kagan-sh/kagan/commit/769e46e5e3d0a6caf73c5f5b6f96bf5593c99afd))

### Chores

- Update GitHub Actions to latest versions ([#9](https://github.com/kagan-sh/kagan/pull/9),
  [`fe57f66`](https://github.com/kagan-sh/kagan/commit/fe57f663aef153780eadd5699082932d0266ca1a))

### Continuous Integration

- Add macOS ARM64 to PR test matrix ([#9](https://github.com/kagan-sh/kagan/pull/9),
  [`fe57f66`](https://github.com/kagan-sh/kagan/commit/fe57f663aef153780eadd5699082932d0266ca1a))

### Features

- Add dynamic agent detection and improve troubleshooting UX
  ([#8](https://github.com/kagan-sh/kagan/pull/8),
  [`6ea7f44`](https://github.com/kagan-sh/kagan/commit/6ea7f449d7af3e63ff97b88e7af0d27c81d00ee9))

### Performance Improvements

- **ci**: Optimize CI workflow for faster PR feedback
  ([#9](https://github.com/kagan-sh/kagan/pull/9),
  [`fe57f66`](https://github.com/kagan-sh/kagan/commit/fe57f663aef153780eadd5699082932d0266ca1a))


## v0.2.0-beta.2 (2026-01-31)

### Bug Fixes

- Add packaging as explicit dependency ([#7](https://github.com/kagan-sh/kagan/pull/7),
  [`1e0e7ea`](https://github.com/kagan-sh/kagan/commit/1e0e7eadf47e11292bf3f42eb1a218a358859b58))


## v0.2.0-beta.1 (2026-01-30)

### Chores

- Update typo in src/kagan/ui/widgets/empty_state.py
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

### Documentation

- Refining docs
  ([`67ea1fe`](https://github.com/kagan-sh/kagan/commit/67ea1fea945c4188a137c442db6b787ba2ad359f))

- Update documentation with testing rules and agent capabilities
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

### Features

- Cleanup and new features ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

- **agents**: Add prompt refiner for pre-send enhancement
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

- **ansi**: Add terminal output cleaner for escape sequences
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

- **cli**: Add update command with auto-upgrade support
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

- **core**: Enhance screens with keybindings registry and read-only agents
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

- **keybindings**: Add centralized keybindings registry
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))

- **ui**: Add new modals, widgets, and clipboard utilities
  ([#6](https://github.com/kagan-sh/kagan/pull/6),
  [`d47160f`](https://github.com/kagan-sh/kagan/commit/d47160f38c7c7d7d91939529001fd21cedb151ca))


## v0.1.0 (2026-01-29)


## v0.1.0-beta.3 (2026-01-29)

### Bug Fixes

- Fix missing readme on pyproject ([#5](https://github.com/kagan-sh/kagan/pull/5),
  [`b1693ca`](https://github.com/kagan-sh/kagan/commit/b1693ca918e9bad96b9f1195b82df8b9d150712f))

### Continuous Integration

- Add docs_only flag to CD workflow for independent documentation publishing
  ([#5](https://github.com/kagan-sh/kagan/pull/5),
  [`b1693ca`](https://github.com/kagan-sh/kagan/commit/b1693ca918e9bad96b9f1195b82df8b9d150712f))

### Documentation

- Refines documentation
  ([`f1ac3d1`](https://github.com/kagan-sh/kagan/commit/f1ac3d1945ec7a546344f704f29643373b232ba8))


## v0.1.0-beta.2 (2026-01-29)

### Bug Fixes

- Fix missing readme on pyproject
  ([`a1cbb66`](https://github.com/kagan-sh/kagan/commit/a1cbb6664e564beb9b8e8d7b2febf4d9bf93c26d))


## v0.1.0-beta.1 (2026-01-29)

- Initial Release
