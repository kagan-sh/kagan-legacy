# Kagan v2 — MCP / Agent-Contract User Stories

Stories for the **deterministic channel** between an opaque agent and the
harness. Most are told from the Dev's perspective (what the channel must buy
them); a few are from the agent's perspective (what it must report). Each maps to
`mcp.md`. The board-era MCP stories are under `legacy/`.

> The agent stays opaque — a subprocess in a worktree, harvested by git diff.
> It needs only a tiny, predictable way to say "here's what I'd assume", "I need
> you", and "verify these". That tiny channel is the whole contract.

______________________________________________________________________

## A minimal, opaque channel

- As a Dev, I want the agent driven as an **opaque subprocess** with a small MCP report channel, not a deep turn protocol, so the tool doesn't rot every time an agent CLI changes. _refs: MCP-SRV-01, MCP-SRV-02, MCP-AGENT-04_
- As a Dev, I want completion decided by **process exit + git diff**, so I don't depend on the agent announcing it correctly. _refs: MCP-AGENT-02, MCP-AGENT-03_
- As a Dev, I want the only CLI-specific knowledge to be a **launch recipe**, so adding an installed agent is trivial. _refs: MCP-AGENT-01_
- As a Dev, I want agents without MCP support to still work via a **`.kagan/ask` file** fallback. _refs: MCP-AGENT-02_

## Intake — surface decisions, don't invent them

- As a Dev, I want the agent, during intake, to run **plan-only with no write capability** and report every decision it would otherwise assume, so an underspecified ticket is never silently implemented. _refs: MCP-INTAKE-01, MCP-INTAKE-02, MCP-INTAKE-03_
- As the agent, I must report my **restated understanding + options + severity** so the human can answer or bless each before I run. _refs: MCP-INTAKE-02_
- As a Dev, I want my pinned decisions **passed back as constraints** when the run starts. _refs: MCP-INTAKE-04_

## Needs-you — one structured interrupt

- As the agent, when I hit a decision I can't resolve mid-run, I must emit **one structured needs-you** (reason code + question + context), never a crash or a buried log line. _refs: MCP-NEEDS-01, MCP-NEEDS-04_
- As a Dev, I want a needs-you to become a **first-class Inbox state with a notification**, so I can answer and leave. _refs: MCP-NEEDS-02_
- As a Dev, I want the agent to **prefer intake over mid-run questions** for anything predictable. _refs: MCP-NEEDS-03_

## Smoke-tests & drift

- As the agent, on completion I must report the **behaviours a human should verify** (since there's no e2e net), each referencing the live service. _refs: MCP-SMOKE-01, MCP-SMOKE-02_
- As a Dev, I want **drift detected from the diff by the harness**, not left to the agent's honesty, though the agent may also flag a concern. _refs: MCP-DRIFT-01, MCP-DRIFT-02_

## Boundaries

- As a Dev, I want each agent **scoped to its own worktree** — unable to touch another task's workspace, decisions, or leases. _refs: MCP-SEC-01, MCP-SEC-03_
- As a Dev, I want it to be **impossible for the agent to push, merge, or force-push** — there is no such tool. _refs: MCP-SEC-02_
- As a Dev, I want **unknown tool calls rejected**, so the contract can't be widened by accident. _refs: MCP-SRV-04_
