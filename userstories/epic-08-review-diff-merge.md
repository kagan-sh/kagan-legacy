# Epic 8: Review, Diff, and Merge

The review modal is a read-only decision surface showing static/completed content.
Live review-agent output streams in the orchestrator overlay (Epic 7), not in the modal.

| ID     | Story                                                                                                                                                                    |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| US-072 | As a user, I want a review modal with static tabs (summary, diff, review verdict, PR comments) for full decision context without any streaming or live-updating content. |
| US-073 | As a user, I want approve/reject/rebase actions and review-agent trigger from the review modal.                                                                          |
| US-074 | As a user, I want REVIEW transition guardrails (plugin hooks) so missing PR/lease conflicts can block unsafe transitions.                                                |
| US-075 | As a user, I want rejection feedback flow that moves task back to BACKLOG or IN_PROGRESS with recorded notes.                                                            |
| US-076 | As a user, I want no-change close flow (close_exploratory) so exploratory tasks can complete without merge.                                                              |
| US-077 | As a user, I want rebase conflict handling that annotates task, moves to IN_PROGRESS, and can restart AUTO.                                                              |
| US-078 | As a user, I want merge safety logic (runtime quiesce, risk assessment, optional pre-merge/auto rebase retry).                                                           |
| US-079 | As a user, I want serialize_merges setting to enforce one-at-a-time merges.                                                                                              |
| US-080 | As a user, I want require_review_approval setting so merge requires prior explicit approval state.                                                                       |
| US-081 | As an MCP user, I want review_apply with actions approve/reject/merge/rebase and defined rejection actions.                                                              |
