# Epic 1: Onboarding, Startup, and Environment Readiness

| ID     | Story                                                                                                                                                                                   |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| US-001 | As a first-time user, I want onboarding to collect my default AI agent and auto-review preference so Kagan is usable immediately after first launch.                                    |
| US-002 | As a user, I want onboarding to persist config.toml automatically so my initial setup survives restarts.                                                                                |
| US-003 | As a returning user, I want Kagan to restore my last active project/repo context so I can continue where I left off.                                                                    |
| US-004 | As a user launching from a repo folder, I want Kagan to suggest creating/opening a project from the current directory so startup is context-aware.                                      |
| US-005 | As a user, I want multiple TUI and MCP admin instances to coexist against a singleton core daemon with real-time state sync so concurrent sessions always reflect accurate board state. |
| US-006 | As a user, I want startup preflight checks (agent/tooling/backend) with blocking vs warning severity so I can fix issues before execution.                                              |
| US-007 | As a user with warnings only, I want an explicit "continue anyway" path so non-critical issues do not hard-stop work.                                                                   |
| US-008 | As a user with no installed AI agents, I want guided install prompts so I can bootstrap supported agents quickly.                                                                       |
| US-009 | As a user, I want core daemon auto-start behavior controlled by config (core_autostart) so runtime startup is predictable.                                                              |
