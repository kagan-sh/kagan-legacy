# Kagan v2 — MCP / Agent-Contract Specification

Normative specification for the **deterministic channel** between an opaque agent
and the harness. The agent stays opaque — a subprocess in a worktree — but it
needs a small, predictable way to report state. That channel is a **minimal MCP
server**: a handful of report tools, **not** a turn-lifecycle protocol.

> **Provenance.** Supersedes the board-era `legacy/mcp.md` (which modelled runs,
> verdicts, and human-input escalations as a fuller protocol). v2 deliberately
> shrinks the surface to the smallest contract that makes supervision reliable.

## How to read this document

RFC 2119 / RFC 8174 key words (**MUST**, **MUST NOT**, **SHOULD**, **MAY**, …)
apply **only in uppercase**. Requirements use EARS patterns (ubiquitous,
`WHILE` state, `WHEN` event, `WHERE` optional, `IF…THEN` unwanted). See `cli.md`
for the full convention table.

**Actors.** *agent* = opaque coding CLI in a worktree; *harness* = the engine;
*MCP server* = the harness's agent-facing endpoint. IDs: `MCP-<AREA>-NN`.

______________________________________________________________________

## MCP-SRV — the server

- **MCP-SRV-01** The harness MUST expose its agent-facing contract as a minimal MCP server over stdio.
- **MCP-SRV-02** The MCP surface MUST be limited to the small set of report tools defined in this document and MUST NOT model the agent's full turn lifecycle.
- **MCP-SRV-03** WHILE an agent runs for a task, the harness MUST make the MCP server reachable to that agent and MUST scope every report to that task.
- **MCP-SRV-04** IF the agent calls a tool not defined in this contract, THEN the MCP server MUST reject the call rather than execute an undefined action.

## MCP-AGENT — opacity, launch & watching

- **MCP-AGENT-01** The harness MUST launch the agent as a subprocess using a per-CLI launch recipe; that recipe MUST be the only CLI-specific knowledge the harness holds.
- **MCP-AGENT-02** The harness MUST determine task progress by watching three channels: the process, the working-tree git diff, and the report channel (MCP tool calls or a `.kagan/ask` file).
- **MCP-AGENT-03** WHEN the agent process exits, the harness MUST harvest the resulting git diff and advance the task to validation, whether or not an explicit completion signal was sent.
- **MCP-AGENT-04** The harness MUST NOT require parsing of the agent's natural-language stream to drive the lifecycle.

## MCP-INTAKE — report decisions before running

- **MCP-INTAKE-01** WHILE a task is in intake, the harness MUST run the agent in a plan-only mode that has no file-write capability.
- **MCP-INTAKE-02** WHEN running intake, the agent MUST report — via `report_intake_decisions` — its restated understanding and every decision it would otherwise assume, each with candidate options and a severity (`blocking`/`question`).
- **MCP-INTAKE-03** The harness MUST enforce the no-implementation rule of intake by withholding write capability, and MUST NOT rely on instruction alone.
- **MCP-INTAKE-04** WHEN the run later starts, the harness MUST pass the pinned decisions to the agent as constraints.

## MCP-NEEDS — one structured "needs you"

- **MCP-NEEDS-01** WHEN the agent reaches a decision it cannot resolve mid-run, it MUST emit a single structured message — via `report_needs_you` — carrying a reason code, the question, and minimal context.
- **MCP-NEEDS-02** WHEN a needs-you message is received, the harness MUST surface it as a first-class Inbox state and notify the user.
- **MCP-NEEDS-03** The agent SHOULD surface predictable decisions during intake rather than emitting needs-you mid-run.
- **MCP-NEEDS-04** A needs-you message MUST NOT be expressed as a process crash or an unstructured log line.

## MCP-SMOKE — what a human must verify

- **MCP-SMOKE-01** WHEN the agent completes implementation, it MUST report — via `report_smoke_tests` — the list of behaviours a human should verify, given the absence of an e2e net.
- **MCP-SMOKE-02** Each reported smoke-test item MUST be human-checkable and MUST reference the relevant running service where applicable.

## MCP-DRIFT — scope & decision violations

- **MCP-DRIFT-01** WHEN the harness detects, from the working-tree diff, edits outside the task's scope or contradicting a recorded decision, it MUST raise drift independently of the agent.
- **MCP-DRIFT-02** WHERE the agent can recognise its own scope concern, it MAY emit a drift signal; the harness MUST NOT rely solely on agent self-reporting to detect drift.
- **MCP-DRIFT-03** The harness MUST perform diff-based drift detection in the during-run watcher that supervises the live agent process (MCP-AGENT-02), not in the post-run review gate, so drift interrupts the run as it happens rather than after completion.

## MCP-DONE — completion

- **MCP-DONE-01** WHEN the agent finishes, it MAY emit a `report_done` signal; regardless, MCP-AGENT-03 governs completion via process exit and diff harvest.

## MCP-SEC — boundaries

- **MCP-SEC-01** The MCP server MUST scope each agent's file access and reports to that task's own worktree; an agent MUST NOT read or write another task's workspace.
- **MCP-SEC-02** The harness MUST NOT expose any tool that lets the agent push, merge, force-push, or otherwise alter remote state.
- **MCP-SEC-03** The harness MUST NOT expose any tool that lets the agent modify another task's pinned decisions, ledger entries, or port leases.

______________________________________________________________________

## Tool summary (informative)

| Tool                      | Direction       | Purpose                                      | Normative ref |
| ------------------------- | --------------- | -------------------------------------------- | ------------- |
| `report_intake_decisions` | agent → harness | understanding + decisions to pin (plan-only) | MCP-INTAKE-02 |
| `report_needs_you`        | agent → harness | one mid-run question, reason code + context  | MCP-NEEDS-01  |
| `report_smoke_tests`      | agent → harness | behaviours a human must verify               | MCP-SMOKE-01  |
| `report_drift` (optional) | agent → harness | self-reported scope concern                  | MCP-DRIFT-02  |
| `report_done` (optional)  | agent → harness | completion hint                              | MCP-DONE-01   |

The `.kagan/ask` file is an equivalent fallback for agents without MCP support;
the harness watches it per MCP-AGENT-02.

## Out of scope (anti-features)

The MCP server MUST NOT implement: deep ACP / turn-lifecycle modelling; a
registry or abstract base class of many backends; any agent-driven git
push/merge; remote persona import; or bidirectional GitHub sync.
