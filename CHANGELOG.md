# CHANGELOG

<!-- version list -->

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
