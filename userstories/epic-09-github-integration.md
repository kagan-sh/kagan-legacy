# Epic 9: GitHub Integration (Bundled Plugin)

GitHub operations are accessible from three surfaces: TUI board actions,
orchestrator overlay (natural language or commands), and MCP tools.

| ID     | Story                                                                                                                           |
| ------ | ------------------------------------------------------------------------------------------------------------------------------- |
| US-082 | As a user, I want contract probing (kagan_github_contract_probe) to verify GitHub plugin compatibility.                         |
| US-083 | As a user, I want repo connection preflight (kagan_github_connect_repo) to persist canonical GitHub metadata.                   |
| US-084 | As a user, I want issue sync (kagan_github_sync_issues) to project GitHub issues into Kagan tasks.                              |
| US-085 | As a user, I want deterministic issue-status mapping (OPEN->BACKLOG, CLOSED->DONE) and [GH-#] task title prefixing.             |
| US-086 | As a user, I want AUTO/PAIR mode inference from issue labels and repo defaults.                                                 |
| US-087 | As a user, I want lease controls (acquire/release/get_lease_state) to prevent concurrent issue handling collisions.             |
| US-088 | As a user, I want PR operations (create_pr_for_task, link_pr_to_task, reconcile_pr_status) tied to task state.                  |
| US-089 | As a user, I want GitHub CI status check and PR review comments retrieval from task context.                                    |
| US-090 | As a user, I want PR merge operation (kagan_github_merge_pr) with merge strategy support.                                       |
| US-091 | As a user, I want task-to-issue status sync (kagan_github_sync_task_status) including labels/close/reopen actions.              |
| US-092 | As a TUI user, I want GitHub repo actions (connect, sync) and task actions (create PR, link PR) plus status badge on the board. |
| US-093 | As a user, I want GitHub guardrails on REVIEW transition and automatic status sync on task state changes.                       |
