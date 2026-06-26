# Kagan v2 — CLI User Stories

Stories told from the perspective of **the Dev** — a human who uses AI to write
and review software faster than they can supervise by hand. Each story maps to
the normative requirements in `cli.md`.

> v2 thesis: AI writes code faster than a human can watch it, so the bottleneck
> moved from *writing* to *supervising*. The CLI is a supervision layer — a single
> interactive `kagan` session you invoke when you choose. It isolates each unit of
> work, verifies it against the repo's own bar before a human looks, pulls the
> human in only for decisions a human must make, and exits when you're done.

______________________________________________________________________

## Inbox — stop the slot machine

- As a Dev, I want one calm entrypoint — I type `kagan`, it shows what needs me or "nothing — go do something else", and **exits** — so the tool never becomes an always-on surface I idle-watch. _refs: CLI-SHELL-07, CLI-INBOX-02_
- As a Dev, I want the home view **quiet by default** — "nothing needs you, go do something else" — so watching an agent think stops feeling like progress. _refs: CLI-INBOX-02, CLI-BOOT-03_
- As a Dev, I want work sorted by **who needs a human most**, not by column or age, so the next decision is always on top. _refs: CLI-INBOX-01, CLI-INBOX-06_
- As a Dev, I want running tasks **collapsed to one heartbeat line** with a rough ETA, so I trust the agent is alive and walk away instead of staring. _refs: CLI-INBOX-03_
- As a Dev, I want a **"since you left" delta** and a **one-line resume point** when I reopen a task, so re-entering one of several parallel threads costs seconds. _refs: CLI-INBOX-04, CLI-INBOX-05_
- As a Dev, I want to be **notified only when a run needs me, lands in review, finishes, drifts, or fails CI** — never on progress — so leaving the machine is safe. _refs: CLI-NOTIFY-01, CLI-NOTIFY-02, CLI-RUN-03_

## Intake gate — never auto-imply an underspecified ticket

- As a Dev, I want a new task to **pause for intake** where the agent (running plan-only, unable to edit) lists every decision it would otherwise guess, so nothing underspecified is silently invented. _refs: CLI-INTAKE-01, CLI-INTAKE-02, CLI-INTAKE-06_
- As a Dev, I want the **run locked** until each blocking decision is answered or explicitly **approved**, so "use your judgment" is a recorded choice, not a silent assumption. _refs: CLI-INTAKE-03, CLI-INTAKE-04_
- As a Dev, I want a fully specified ticket to **pass intake with zero friction**, so terse tickets aren't punished. _refs: CLI-INTAKE-07_
- As a Dev, I want my pinned decisions to **constrain the run and feed the drift alarm**, so the agent is held to them. _refs: CLI-INTAKE-05, CLI-DRIFT-01_

## Workspace — parallel branches without collisions

- As a Dev, I want each task in its **own git worktree** on the same repo, so I run several branches without re-cloning. _refs: CLI-WS-01_
- As a Dev, I want **auto-assigned, non-colliding ports** and a single **port/resource map**, so I never type "don't touch :4000" again. _refs: CLI-WS-02, CLI-WS-03_
- As a Dev, I want **isolated env per workspace** and the ability to **pin a do-not-touch** branch/process, so an agent can't clobber shared state or a long-lived server. _refs: CLI-WS-04, CLI-WS-05_
- As a Dev, I want the harness to **run my repo's declared services** in the worktree on free ports — not the agent improvising — and to **free everything when the task ends**. _refs: CLI-WS-07, CLI-WS-06_
- As a Dev, I want to **see a process's recent logs and get a copy-ready command to open it in my own terminal** to take over when something looks stuck — not an auto-attach launcher. _refs: CLI-WS-08_

## Review gate — review is the real work, shifted left

- As a Dev, I want **self-review checks to run before I ever look**, filtering the recurring problems (sprawl, weak tests, duplication, out-of-scope edits). _refs: CLI-GATE-01, CLI-GATE-02_
- As a Dev, I want the gate to **also run my repo's own rubric**, so the tool reads my definition of good rather than hardcoding one. _refs: CLI-GATE-03, CLI-CONFIG-02_
- As a Dev, I want **findings as the main surface**, severity-tagged with a location, and an explicit **agree/disagree verdict** on each — no silent dismissal. _refs: CLI-GATE-04, CLI-GATE-05_
- As a Dev, I want **approve locked while any blocking finding is open**, so the human gate is structurally unbypassable. _refs: CLI-GATE-06_
- As a Dev, I want a **smoke-test checklist** (since there's no e2e net) pointing at the live port, so the "eyeball the running app" loop becomes a tracked step. _refs: CLI-GATE-08_
- As a Dev, I want a fast **send-back loop** that re-runs in the same worktree, so correcting the draft is cheap. _refs: CLI-GATE-07_

## Local mirror — deterministic checks in seconds

- As a Dev, I want my repo's **cheap CI run locally pre-merge**, so I catch failures in seconds, not a 15–25 minute remote round-trip. _refs: CLI-MIRROR-01_
- As a Dev, I want **codegen checked against an up-to-date base**, so I'm warned before a stale branch pulls in unrelated drift. _refs: CLI-MIRROR-02_
- As a Dev, I want **remote CI status shown inline**, so I don't context-switch to the web UI. _refs: CLI-MIRROR-03_

## Ship — I push, the tool never does

- As a Dev, I want **approve to mean "ready", not "merged"** — the tool hands me the push command and never pushes or merges for me. _refs: CLI-SHIP-01, CLI-SHIP-02, CLI-SHIP-03_
- As a Dev, I want a **reviewed-before-push receipt** (what the gate verified, what I adjudicated, my comprehension note, what's NOT covered) to paste into the PR, so my reviewer doesn't re-derive it. _refs: CLI-RECEIPT-01, CLI-RECEIPT-02, CLI-RECEIPT-03_
- As a Dev, once I've opened the PR, I want the harness to **watch remote CI read-only** and pull a task back to me only if CI fails or the base goes stale. _refs: CLI-SHIP-04, CLI-POSTPR-01, CLI-POSTPR-02, CLI-POSTPR-03_

## Drift, ledger, config

- As a Dev, I want a **drift alarm** when the agent edits out of scope, contradicts a decision, or exceeds the plan — the only mid-run reason to interrupt me. _refs: CLI-DRIFT-01, CLI-DRIFT-02, CLI-DRIFT-04_
- As a Dev, I want **topology to survive between invocations** — tasks, branches, ports, stage, decisions — and in-flight runs to **resume after a crash**, because the session is stateless. _refs: CLI-LEDGER-01, CLI-LEDGER-02, CLI-SHELL-07_
- As a Dev, I want one **~6-line repo manifest** to describe my services, checks, rubric, and pinned processes, so the same harness works on any repo. _refs: CLI-CONFIG-01, CLI-CONFIG-03_
- As a Dev, I want all git operations to use **my own identity**, never a separate "kagan" profile. _refs: CLI-CONFIG-05_

## The doing happens headless

- As a Dev, I want the agent run + harvest + validator + gate to finish in a **detached per-task runner** while my session exits, so leaving is safe and nothing is "always on". _refs: CLI-RUN-01, CLI-RUN-02, CLI-RUN-03, CLI-SHELL-07_

## Agent stays opaque

- As a Dev, I want each agent treated as an **opaque subprocess** (prompt in, raw stream + git diff out) and to **pick from the CLIs I actually have installed**, not a registry of backends behind an ABC. _refs: CLI-AGENT-01, CLI-AGENT-02, CLI-AGENT-03_
