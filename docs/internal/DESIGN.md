# Kagan — Design & Methodology

> Canonical design document (`docs/internal/DESIGN.md`). Supersedes the former
> `docs/internal/plans/`, `adrs/`, and `architecture.md` (removed in Phase 0).
> Single source of truth for what kagan is, why, and how it is built.

______________________________________________________________________

## How to read this document

**RFC 2119 / RFC 8174.** The key words **MUST**, **MUST NOT**, **REQUIRED**,
**SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**,
**OPTIONAL** are to be interpreted as described in RFC 2119 and RFC 8174 — that
is, **only when in uppercase**. Lowercase uses carry their ordinary English
meaning. Per RFC 2119 these are used sparingly, only where they constrain
behaviour that matters for correctness or interoperability.

**EARS** (Easy Approach to Requirements Syntax, Mavin et al.). Normative
requirements in this document follow one EARS pattern; the obligation verb is an
RFC 2119 keyword. See `docs/internal/specs/cli.md` for the full convention
table; the patterns are:

| Pattern      | Shape                                                                           |
| ------------ | ------------------------------------------------------------------------------- |
| Ubiquitous   | The `<actor>` **MUST** `<response>`.                                            |
| State-driven | **WHILE** `<state>`, the `<actor>` **MUST** `<response>`.                       |
| Event-driven | **WHEN** `<trigger>`, the `<actor>` **MUST** `<response>`.                      |
| Optional     | **WHERE** `<feature present>`, the `<actor>` **MAY/SHOULD** `<response>`.       |
| Unwanted     | **IF** `<condition>`, **THEN** the `<actor>` **MUST** `<response>`.             |
| Complex      | **WHILE** `<state>`, **WHEN** `<trigger>`, the `<actor>` **MUST** `<response>`. |

Clause order follows temporal logic: preconditions (**WHILE**, **WHERE**),
then triggers (**WHEN**), then unwanted behaviour (**IF** … **THEN**), then the
system response.

**Actors.** *harness* = the core engine (worktrees, ports, gate engine, ledger,
local mirror); *CLI* = its interactive command-line surface — the single `kagan`
session; *agent* = the opaque coding CLI. The agent↔harness contract is
specified in `specs/mcp.md`.

**IDs.** `DESIGN-<AREA>-NN`. Interactive harness/CLI behaviour that implements
these design decisions is normatively specified in `specs/cli.md` with `CLI-*`
IDs; this document states thesis, invariants, lever intent, UI language, and
roadmap.

______________________________________________________________________

## 1. Context & thesis

Kagan is a supervision layer for AI coding agents: it isolates each unit of agent
work in a git worktree, gates it (intake = input readiness, review = output
quality), lets the human adjudicate, and marks work `ready` **without ever
pushing**. Its instincts are sound. But it verifies the *code* and protects
*main* — and a synthesis of ~80 studies (`hai_coding/`) says the two factors
that actually decide whether AI helps or harms are neither:

1. **Does the human comprehend what they ship?** Usage *mode* predicts outcome,
   not the tool: engaged devs score ≥65% comprehension (= unaided baseline),
   delegators \<40% (Anthropic RCT). The 88% AI-code retention rate is a
   trust-miscalibration *risk* signal, not quality.
1. **Does the human stay the competent, un-burned-out anchor?** AI is an
   amplifier, not a substitute (HAI-Eval: AI-alone 0.67%, human-alone 18.89%,
   human+AI 31.11%). But the slot-machine loop drives compulsion — usage rises
   while satisfaction falls; heavy users work nights/weekends 96% of the time;
   "brain fry" raises major errors +39% and quit-intent +39%. The research's
   explicit design mandate: **build friction, not engagement; the most productive
   user must not be the heaviest user.**

Supporting evidence the design leans on: the bottleneck moved from writing to
*validating* code (+98% PRs, +91% review time, −7% main throughput); functional
≠ secure (82.8% of *passing* AI code carries a vuln; 45% OWASP rate, flat across
model generations); risk-routed autonomy (HITL/HOTL/auto by task *risk*;
irreversible = always human); builder+validator split with *different* models
beats single-agent self-review; measure durability/CFR/cycle-time, not
commits/LOC.

**Thesis:** *Kagan should verify the human as rigorously as it verifies the
code* — and do it through a calm, low-ceremony surface that protects the
supervisor's attention instead of competing for it.

- **DESIGN-GOAL-01** Kagan **SHOULD** verify the human supervisor as rigorously
  as it verifies the code.
- **DESIGN-GOAL-02** The CLI **SHOULD** be a calm, low-ceremony, invoke-when-you-choose
  surface that protects supervisor attention and **MUST NOT** compete for it with
  ambient dashboards or live generation streams.

______________________________________________________________________

## 2. Invariants

These survive the doc reset because the code depends on them. Normative
requirements:

### DESIGN-INV — architectural invariants

- **DESIGN-INV-01** The harness **MUST** persist per-task durable state as
  `state.json` (atomic: `mkstemp`→`fsync`→`os.replace`→**dir-fsync**) plus an
  append-only `events.jsonl`, using stdlib `json` only, and **MUST NOT** use a
  relational database.
- **DESIGN-INV-02** The harness **MUST** dir-fsync the state directory on
  `state.json` creation/rename so a crash after `os.replace` cannot lose a
  succeeded state; `append_event` **MUST** dir-fsync only on file creation (no
  per-append hot-path cost).
- **DESIGN-INV-03** The harness **MUST** be the single writer to the ledger;
  every surface **MUST** be a read-only view that mutates only through the
  harness.
- **DESIGN-INV-04** **WHILE** operating as built, the harness **MUST** resolve
  the operational ledger at `<git-toplevel>/.kagan/state` (gitignored), via
  `default_data_dir()` in `core/harness.py`, with a `KAGAN_DATA_DIR` override.
  An external machine-local store keyed per repo is a documented **FUTURE** item
  (§3.6), not the present state.
- **DESIGN-INV-05** The harness **MUST** read a single YAML manifest at
  `.kagan/repo.yaml` (`RepoConfig`, `extra="forbid"`), validated on load.
- **DESIGN-INV-06** **IF** the manifest is missing or invalid, **THEN** the
  harness **MUST** refuse to guess configuration and **MUST** report the problem
  clearly.
- **DESIGN-INV-07** Kagan itself **MUST NOT** push, merge, or force-push.
- **DESIGN-INV-08** The public `run_git` **MUST** keep a read-only allowlist
  (raises on anything outside
  `rev-parse/diff/status/log/show/rev-list/ls-files/cat-file/symbolic-ref/describe`).
- **DESIGN-INV-09** The single `_spawn_git` chokepoint **MUST** enforce a
  denylist of irreversible/destructive verbs
  (`push/merge/rebase/reset/clean/update-ref/fetch/pull/remote`), so a future
  careless `_run_git("push"/"reset", …)` raises instead of externalising ruin.
- **DESIGN-INV-10** `_git_subcommand` **MUST** skip git's `-c name=value`/`-C path` global flags so `-c commit.gpgsign=false commit` resolves to `commit`,
  not the flag value.
- **DESIGN-INV-11** Approve **MUST** mark a task `ready`; the human **MUST** run
  the printed `git push`/`gh pr create` themselves.
- **DESIGN-INV-12** `core/agent._agent_env` **MUST** scrub the child agent env
  (no token, `GIT_TERMINAL_PROMPT=0`), **MUST** drop the forwarded ssh-agent
  socket (`SSH_AUTH_SOCK`), and **MUST** blank the git credential helper
  (`GIT_CONFIG_COUNT/KEY_0/VALUE_0` → `credential.helper=`), so the agent's git
  has no credential source for push.
- **DESIGN-INV-13** Kagan's own read-only `ls-remote` **MAY** retain
  `SSH_AUTH_SOCK` via a separate env; the agent's shell is governed by the spawn
  env, not the public allowlist.
- **DESIGN-INV-14** OS-level sandboxing of the agent is **OPTIONAL** (a CLI
  sandbox flag); kagan **MUST NOT** claim a hard guarantee without it. A
  passphraseless on-disk SSH key remains a documented residual risk, not a
  fake-fixed one.
- **DESIGN-INV-15** The harness **MUST** treat agent completion as process-exit
  plus git-diff harvest and **MUST NOT** parse the agent's natural-language
  stream for lifecycle signals.
- **DESIGN-INV-16** The agent's only structured channel **MUST** be the seven MCP
  report tools (intake / needs-you / smoke / drift / findings /
  comprehension-prompts / done) — or the `.kagan/ask` JSONL fallback.
- **DESIGN-INV-17** **IF** a malformed `.kagan/ask` report or one bad finding
  is received during harvest, **THEN** the harness **MUST** log and skip it and
  **MUST NOT** abort the harvest (hardening **F3**, `_watch_agent`/`_apply_report`).
- **DESIGN-INV-18** Every spawned subprocess **MUST** have a wall-clock cap:
  agent runs via `agent.wait_bounded` (**F1**), git via `git._run_git` timeouts,
  the mirror's checks, and the `gh` CI read (**F4**, `remote_ci._gh_json`) — a
  stall **MUST** degrade to a recorded failure, never a hang.
- **DESIGN-INV-19** The harness **MUST** use the user's own git identity for all
  operations and **MUST NOT** create or use a separate kagan git persona.

______________________________________________________________________

## 3. Platform: from Textual TUI to an interactive CLI

### 3.1 Why de-TUI

A full-fledged TUI is overkill for a single-operator supervision tool and, worse,
*fights the thesis*: an always-on dashboard with live-updating panes is exactly
the kind of ambient surface that pulls a supervisor into idle-watching (the
slot-machine symptom). The leaner answer is a CLI you **invoke when you choose**,
that tells you what needs you (or "nothing — go do something else") and
**exits**. Calm, deferential, attention-protecting. The re-platform is therefore
not just simplification — it is the thesis applied to the tool's own shape.

`click`, `rich`, and `prompt-toolkit` are **already dependencies**; only
`textual` is removed. Net: fewer deps, ~3,700 LOC deleted, no new third-party
surface area.

- **DESIGN-PLAT-01** The CLI **MUST NOT** implement an always-on Textual-style
  dashboard with live-updating panes.
- **DESIGN-PLAT-02** The CLI **MUST** be invoke-when-you-choose: render the
  ledger, act, and exit when the user quits.

### 3.2 The three libraries

| Concern                  | Owner                                                                | Why                                                                        |
| ------------------------ | -------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Command dispatch / args  | **Click**                                                            | already the CLI front door (`cli/main.py`)                                 |
| Output rendering         | **Rich**                                                             | tables, panels, markdown, syntax, diffs; reuse existing `format/doctor.py` |
| Interactive input / keys | **prompt-toolkit**                                                   | the only piece with a real keyboard event loop                             |
| Stdout isolation         | prompt-toolkit `patch_stdout`                                        | Rich prints don't corrupt the input line                                   |
| Live-but-quiet status    | status-callback + `invalidate()` (kimi pattern), **not** `rich.Live` | `rich.Live` deadlocks against prompt-toolkit's stdout lock                 |

Rich renders into ANSI strings; prompt-toolkit consumes them as `FormattedText`
(kimi's `render_to_ansi`). They never battle for stdout. Reusable kimi patterns to
copy (not vendor): `ChoiceInput` (list selection), `ApprovalPromptDelegate`
(modal adjudication with numbered options + inline feedback), `render_to_ansi`,
`patch_stdout`, a small `StatusSnapshot`.

- **DESIGN-PLAT-03** The CLI **MUST** render Rich output into ANSI and feed it
  to prompt-toolkit as `FormattedText`; it **MUST** use `patch_stdout` so Rich
  prints do not corrupt the input line.
- **DESIGN-PLAT-04** The CLI **MUST NOT** use `rich.Live` against
  prompt-toolkit's stdout lock; live status **SHOULD** use a status-callback plus
  `invalidate()`.

### 3.3 Interaction model — one entrypoint, a stateless interactive session

`kagan` is the only command a human types. It opens an interactive session
(prompt-toolkit) on the Inbox navigator; you move through the queue with keys,
open a task into its state-appropriate view (intake / review / ship /
workspace), act, and quit. New task, stats, and help are in-session actions —
not separate commands. No persistent dashboard, no live agent-output stream: the
session renders the externalized ledger and exits when you're done.

The slot-machine risk is **not the surface existing** — it is a live
variable-reward loop *inside* it (watching tokens stream, hitting regenerate).
kagan has none: the agent is opaque (process-exit + diff harvest), so a single
calm session that shows **outcomes, not generation** is consistent with the
thesis. Leaving is safe because return is notification-backed (§3.5).

- **DESIGN-PLAT-05** `kagan` **MUST** be the only user-typed command; new task,
  stats, and help **MUST** be in-session actions, not separate commands.
- **DESIGN-PLAT-06** The CLI **MUST** show outcomes, not live agent generation.
- **DESIGN-PLAT-07** **WHILE** the interactive session is active, every prompt —
  new-task wizard, comprehension answer, findings disagree reason, send-back,
  intake override, approve-all/ship confirms, needs-you answer — **MUST** be
  captured by `prompt_in_frame`/`choose_in_frame`/`confirm_in_frame`
  (`cli/_interactive.py`) inside the rounded frame; no prompt **MUST** drop to
  a raw line beneath the box.
- **DESIGN-PLAT-08** `test_no_in_session_prompt_escapes_the_frame` **MUST**
  enforce DESIGN-PLAT-07 structurally.
- **DESIGN-PLAT-09** The `kagan init` / `doctor` preflight (`cli/init.py`,
  `cli/main.py`) **MAY** use `click`/raw prompts because it runs **BEFORE** the
  control-plane session exists.

Hidden plumbing (not user entrypoints): `kagan _run <id>` (the detached per-task
runner, §3.5) and `kagan mcp` (spawned by the agent's own MCP client). `doctor`
runs as preflight on launch.

Rejected, named for the record: **many one-shot verbs** (cognitive sprawl); an
**always-on dashboard / Textual TUI**; a **type-commands REPL**.

### 3.4 Surface → in-session view map

Everything is reached inside the one `kagan` session — there are no per-surface
commands.

| Old Textual screen   | In-session view / action                               |
| -------------------- | ------------------------------------------------------ |
| ShellScreen (3 tabs) | the session itself; views replace tabs                 |
| InboxPane            | default view on launch (the navigator)                 |
| GatePane             | open a `review`-state task → review view               |
| IntakeScreen         | open an `intake`-state task → decision walk            |
| ShipScreen           | open a `ready`-state task → ship view (receipt + push) |
| WorkspacesPane       | `w` → workspaces view; `t` on a row prints the `cd`    |
| NeedsYouModal        | surfaced atop the navigator; open → answer             |
| NewTaskModal         | `n` → new-task flow                                    |
| StartupScreen        | preflight (`doctor`) on launch                         |
| HelpScreen           | `?` → help                                             |

Module layout:

- `src/kagan/format/` — pure Rich renderers, each `(Task|list[Task]) -> RenderableType`.
- `src/kagan/cli/_interactive.py` — thin prompt-toolkit helpers; the only place
  prompt-toolkit is imported.
- `src/kagan/cli/session.py` — the single `kagan` interactive session.
- `src/kagan/cli/_run.py` — hidden detached per-task runner. `src/kagan/cli/mcp.py`
  — agent-spawned report server.
- **`core/` is untouched by the re-platform.** The Harness/ledger/gate/ship
  contracts are surface-agnostic.

### 3.5 Detached per-task runner

Because the UI exits, the agent run + harvest + validator + gate finish
headless (DESIGN-PLAT-10).

- **DESIGN-PLAT-10** **WHEN** a task runs, the harness **MUST** spawn
  `kagan _run <id>` detached (new session): run the agent to exit, harvest the
  diff, run `VALIDATING` + the gate, write `REVIEW` to the ledger, and fire
  **one** OS notification.
- **DESIGN-PLAT-11** The interactive session **MUST** be a pure viewer/actor
  over the ledger; the doing **MUST** happen in per-task runners. There **MUST
  NOT** be a daemon.
- **DESIGN-PLAT-12** **WHEN** the runner takes ownership of the `RUNNING`
  transition (`Harness.start_task`), it **MUST** stamp `Task.runner_pid` with
  `os.getpid()`.
- **DESIGN-PLAT-13** **WHEN** the CLI launches, before the first inbox render,
  `Harness.reconcile_in_flight()` **MUST** probe each in-flight task's
  `runner_pid` with `os.kill(pid, 0)`.
- **DESIGN-PLAT-14** **IF** `os.kill(pid, 0)` raises `ProcessLookupError`,
  **THEN** the harness **MUST** flag the task `interrupted`, exclude it from
  `running_count`, and surface it in the inbox as a top-precedence re-runnable
  signal.
- **DESIGN-PLAT-15** A live pid **MUST** be left untouched; a task that already
  reached `REVIEW`/`READY` **MUST NOT** be reaped. Pid-reuse is an accepted
  residual, re-checked on the next launch.

### 3.6 Storage

The operational ledger is gitignored so it never enters commits; only a shareable
subset is tracked.

| What                                                                                                                          | Where (as built)                     | Committed                                    | Why                                                                      |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | -------------------------------------------- | ------------------------------------------------------------------------ |
| `state.json`, `events.jsonl`                                                                                                  | in-repo `.kagan/state/` (gitignored) | no                                           | operational; gitignored so it never enters commits                       |
| worktree/port/pid bookkeeping, cooldown + **fatigue** (l5), **stats** source (l7)                                             | in-repo `.kagan/state/` (gitignored) | no — l5/l7 are **private**                   | machine-local self-mirror; gitignored; never committed                   |
| `.kagan/repo.yaml` (risk tiers, checks, rubric)                                                                               | in-repo `.kagan/`                    | yes (intended — see gitignore note)          | shared review contract                                                   |
| receipt = decision record (l6): understanding + pinned decisions + findings/verdicts + comprehension + not-covered + diff ref | in-repo `.kagan/reviews/<task>.md`   | yes — **auto-written on approve** (intended) | the cross-team provenance / trust artifact + durable decision log (§3.7) |
| `AGENTS.md` deltas (l8)                                                                                                       | in-repo root                         | yes                                          | compounding org knowledge                                                |

- **DESIGN-PLAT-16** Operational ledger files (`state/`, fatigue, stats source)
  **MUST** stay gitignored and **MUST NOT** be committed.
- **DESIGN-PLAT-17** `.kagan/repo.yaml` and `.kagan/reviews/<task>.md`
  **SHOULD** be committable artifacts.
- **DESIGN-PLAT-18** **WHEN** kagan creates the in-repo ledger, it **MUST**
  scaffold `<repo>/.kagan/.gitignore` (containing `state/`) idempotently and
  **MUST NOT** clobber a hand-edited `.kagan/.gitignore`.
- **DESIGN-PLAT-19** **WHEN** a worktree is created, kagan **MUST** append
  `.kagan_worktrees/` to the repo-root `.gitignore`.
- **DESIGN-PLAT-20** `cli/reset.py` **MUST** treat `.kagan/repo.yaml` as the
  user's own config (not in the kill-list).

**FUTURE (not built):** an external store at
`platformdirs.user_data_dir("kagan")/repos/<repo-key>/`, with `<repo-key>`
derived from `git rev-parse --git-common-dir` so worktrees resolve to their parent
repo's key. That would make the tool fully stateless toward the working tree (no
untracked `.kagan/state/` clutter). Today the operational ledger sits in-repo and
gitignored instead.

### 3.7 What is shared: durable knowledge, never the live task

A *task* is operational — it stays external and is **never** shared. What **IS**
shared is the task's *distilled knowledge*: intake spec, adjudicated findings,
comprehension rationale, and what was **not** covered — written on approve into
`.kagan/reviews/<task>.md`.

- **DESIGN-SHARE-01** A live task (state, events, worktree, agent session)
  **MUST NOT** be shared across teammates; sharing it would resurrect the killed
  kanban board and break statelessness.
- **DESIGN-SHARE-02** **WHEN** a task is approved, the harness **MUST** write a
  receipt to `.kagan/reviews/<task>.md` containing distilled knowledge: intake
  understanding, pinned decisions, adjudicated findings + verdicts, comprehension
  rationale, and not-covered scope.
- **DESIGN-SHARE-03** The agent's raw transcript **MUST NOT** be persisted or
  committed; it is noise and a security hazard.
- **DESIGN-SHARE-04** The receipt **MAY** include a one-line breadcrumb
  (`agent: claude · session: <local path>`) making the transcript findable while
  it lives locally, not committed.
- **DESIGN-SHARE-05** `.kagan/reviews/` **MUST** serve as the repo's decision
  log / institutional memory with **no** index and **no** database; retrieval is
  `grep`/`rg` over the folder.
- **DESIGN-SHARE-06** Receipt format **SHOULD** follow an ADR spine — Context /
  Decision / Consequences / Status (Proposed→Accepted→Superseded) — kept light
  (skip full options/criteria/citations except for genuinely architectural tasks);
  when a later task changes an earlier decision, its record **SHOULD** supersede
  the earlier one (link, not delete). Content **SHOULD** use a distillation
  heuristic (from kipp `/handoff`): KEEP decisions+rationale, the *working*
  solution, config choices, constraints discovered, open questions, files changed;
  DROP corrections/retries, verbose tool output, permission prompts, settled
  back-and-forth, boilerplate.
- **DESIGN-SHARE-07** **WHEN** a task is abandoned or sent back, the harness
  **SHOULD** leave a one-line "productive dead end" in the log.
- **DESIGN-SHARE-08** **WHEN** the human sends a task back, the re-run prompt
  (`core/agent._run_prompt` via `_sendback_section`) **MUST** carry: the
  send-back note, findings upheld (`agree` → "fix these"), and findings
  overruled (`disagree` → "leave as-is", with reason). Lists **MUST** be capped
  (`_MAX_RERUN_FINDINGS`).
- **DESIGN-SHARE-09** **WHEN** a run pauses or a session ends mid-task, kagan
  **SHOULD** write a short human-curated re-anchor summary — never the raw
  transcript.

### 3.8 Patterns adopted from kipp (`/Users/aorumbayev/repos/MakerX/kipp`)

kipp is a mature Claude-skills library covering kagan's domain (`/review`,
`/build`, `/security`, `/git`, `/handoff`, `/adr`). Adopted:

- **Agree-bar as comprehension test** (`/review`): a finding **MAY** be marked
  *agree* only if the human can state the defect in their own words AND would
  file it unprompted at the same severity. A Pushback section **MUST** always
  render in the receipt (disagreed findings + one-line reason, even when empty).
- **Enriched finding schema** (`/review`, `/security`): `Finding` gains
  **confidence (0–10)**, **status** (VERIFIED/UNVERIFIED/TENTATIVE), and a
  **mandatory failure-path** (no speculative findings). The confidence gate is
  risk-routed: low-risk surfaces only ≥8; high-risk surfaces tentative (≥2).
- **Per-finding independent verify + variant sweep** (`/security`): the
  validator verifies each finding via a sub-agent that reads only that location,
  then greps for sibling instances of a verified pattern.
- **5-section comprehension scaffold** (`/build explain`): postcondition /
  delta / dependencies / security implications / gotchas — the *structure* of
  the static risk-tier prompts. The validator generates diff-specific prompts on
  the riskiest hunks (`report_comprehension_prompts`); this static set is the
  fallback when the validator is absent, failed, or returns too few (lever 2).
- **Hard-gate whitelist + soft-gate-auto + transparency banner** (`/git`,
  `/maintain`): irreversible/high-risk confirmations risk routing **MUST NOT**
  auto-resolve; soft gates **MAY** auto-advance with a logged note. The receipt
  **MUST** state the ceremony applied.
- **Re-invocation hygiene**: every `kagan` invocation **MUST** re-probe state
  from the ledger, treat in-session drafts as stale, and discard caches.

**Deliberately NOT adopted** (over-engineering for a tool that already has
`repo.yaml` + risk tiers): kipp's Decision-Guide Q1–Q7 preference lifecycle,
per-repo optimisation caching, signal-cue routing, and fork/inline governance.
The sub-agent contract (self-contained prompt, ≤1KB schema'd response) is kept
as a Phase-2 *implementation* note, not a design decision.

### 3.9 Independent review of "The Six"

Net: kagan is already the synthesis — **committed plain-text artifacts wrapped by
thin un-bypassable enforcement gates** — so the right move is to lean the
enforcement layer *thinner*, not reframe kagan as pure conventions.

- **Adopted:** structural-debt signal (lever 9); session-boundary handoff (§3.7).
- **Rejected:** TRAPDOOR tripwire; per-agent-territory manifest; fabricated
  productivity numbers; session ritual theater.

______________________________________________________________________

## 4. The levers (evidence → mechanism → seam)

Each lever builds on existing core seams. Risk tier (lever 4) is the spine that
keeps levers 1–3 *proportionate*. Normative CLI/harness implementation lives in
`specs/cli.md` (`CLI-RISK-*`, `CLI-SUP-*`, etc.); below states design intent.

### Lever 1 — Comprehension gate

**Evidence:** mode decides outcome; delegators \<40%. Today `can_approve`
(`core/tasks.py:142`) checks only blocking-finding verdicts.

- **DESIGN-LVR1-01** **WHILE** a task awaits approve, the harness **MUST** keep
  approve locked until the human records, in their own words, a "why correct /
  what could break" rationale and a resolution note per blocking finding.
- **DESIGN-LVR1-02** Empty, templated, or trivial comprehension **MUST** keep
  the lock (the gate **MUST** be able to fail).
- **DESIGN-LVR1-03** Comprehension scaffold depth **MUST** scale by risk tier:
  low = one line; medium = postcondition + what-could-break; high = full five
  sections (postcondition / delta / dependencies / security / gotchas).
- **DESIGN-LVR1-04** The comprehension rationale **MUST** travel in the receipt
  (lever 6).
- **DESIGN-LVR1-05** The prompt set itself is diff-specific: the validator
  generates prompts on the riskiest hunks (lever 2, `report_comprehension_prompts`),
  resolved through the single `prompts_for_task` / `required_keys_for_task`
  chokepoint (`core/comprehension.py`). The static risk-tier set is the fallback
  when the validator is absent, failed, or returns fewer than the tier requires;
  a degraded validator **MUST NOT** shrink the gate below the static count (the
  rule-8 floor guard in `record_comprehension_prompts`).

**Seam:** `core/models.py`, `core/tasks.py:142`, `core/receipt.py`,
`cli/review.py`, `format/gate.py`.

### Lever 2 — Adversarial validator stage

**Evidence:** builder+validator with *different* models beats single-agent
self-review. `VALIDATING` is declared but never assigned.

- **DESIGN-LVR2-01** **WHEN** harvest completes, the harness **MUST** transition
  `RUNNING`→`VALIDATING`→`REVIEW` (not `RUNNING`→`REVIEW` directly) **WHERE** risk
  tier and `reviewer:` config require validation.
- **DESIGN-LVR2-02** The validator **MUST** be a fresh, separate spawn that never
  sees the builder's session (read-only worktree, adversarial ruleset).
- **DESIGN-LVR2-03** A different model is **RECOMMENDED**; `reviewer` and
  `builder` **MAY** be the same model; same vendor at different size **MAY** be
  used.
- **DESIGN-LVR2-04** The validator **MUST** emit blocking/question `Finding`s;
  the human **MUST** still adjudicate all.
- **DESIGN-LVR2-05** **IF** `launch_validate` crashes, exits unclean, or hits the
  F1 wall-clock cap (`ok=False`), **THEN** the harness **MUST NOT** strand the
  task in `VALIDATING`; it **MUST** record a non-blocking `ai-review` finding,
  set `Task.validator_outcome="failed"`, and advance to `REVIEW` for unaided
  human review.
- **DESIGN-LVR2-06** The receipt ceremony banner **MUST** read
  `validator_outcome` and **MUST** append "(validator unavailable — reviewed
  unaided)" on failure; a failed validator **MUST NOT** read as one that ran.
- **DESIGN-LVR2-07** **IF** `resolve_model` raises `ConfigurationError` for a
  model/CLI mismatch, **THEN** the harness **MUST** fail loud before side effects
  and **MUST NOT** degrade to "reviewed unaided".
- **DESIGN-LVR2-08** `builder`/`reviewer` **MUST** resolve per the task's CLI
  (`core/recipes.resolve_model`, called in `core/agent._build_cmd`). The portable
  vocabulary is `opus`/`sonnet`/`haiku` (top/mid/fast): claude takes the bare
  alias; opencode maps to `opencode/claude-*`; any non-alias value passes
  through verbatim. **IF** a tier alias is used on codex or kimi (vendor-locked
  with no claude-tier equivalent), **THEN** `resolve_model` **MUST** raise
  `ConfigurationError` — distinct from the F2 soft-degrade.
- **DESIGN-LVR2-09** The validator also generates lever-1's comprehension prompts
  on the riskiest hunks, reported via `report_comprehension_prompts`
  (`Harness.record_comprehension_prompts` → `core/tasks.py`) and stored capped to
  the risk floor. A short or empty generated set **MUST** fall back to the static
  count (the rule-8 floor guard) — a degraded validator can never shrink the gate.
- **DESIGN-LVR2-10** Builder/reviewer model compatibility is gated at the seam
  (`validate_model_for_cli`, `core/recipes.py`): a builder or reviewer model the
  task CLI cannot run **MUST** fail at init / doctor / harness, never as a silent
  review-time degrade of the validator.

**Seam:** `core/enums.py`, `core/harness.py:222`, `core/gate.py`, `core/config.py`,
`core/agent.py`, `core/recipes.py`, `mcp/server.py`, `format/workspaces.py`.
**Breaking?** Real
state-machine change + a second agent invocation. Medium; gated by risk tier so
low-risk skips it.

### Lever 3 — Security gate, risk-routed

- **DESIGN-LVR3-01** **WHERE** `repo.yaml` declares a `security` SAST command,
  the gate **MUST** run it in the worktree.
- **DESIGN-LVR3-02** A non-zero security exit **MUST** raise a `blocking`
  finding on high-risk scope and an advisory (`question`) finding elsewhere.

### Lever 4 — Risk routing (the spine)

- **DESIGN-LVR4-01** `repo.yaml` **MUST** declare risk tiers by path glob; intake
  **MUST** classify a task's tier from `scope`.
- **DESIGN-LVR4-02** Tier **MUST** set ceremony: **low** — machine checks + fast
  approve; **medium** — + validator; **high/irreversible** — validator +
  security + full comprehension + second approver, no auto-advance.
- **DESIGN-LVR4-03** Default tier **MUST** be `medium` so unconfigured repos
  behave like today.

### Lever 5 — Supervisor protection

- **DESIGN-LVR5-01** The harness **MUST** cap concurrent in-flight tasks
  (`RUNNING`/`VALIDATING`) at `max_concurrent_agents` (default 2), enforced in
  `start_task` before worktree/launch side effects.
- **DESIGN-LVR5-02** A mandatory approve cooldown after REVIEW landing **MUST**
  be a separate `approve_cooldown_remaining(task_id, now)`, **not** inside
  `can_approve`.
- **DESIGN-LVR5-03** Private coach lines (after-hours, recent-approval burst)
  **MAY** render at inbox time; they **MUST NOT** be persisted or surfaced as team
  metrics.
- **DESIGN-LVR5-04** `agent_timeout_seconds` (default 1800; `0` disables) **MUST**
  cap every agent run via `agent.wait_bounded`.
- **DESIGN-LVR5-05** **IF** a builder exceeds the timeout, **THEN** the harness
  **MUST** harvest the partial diff, land in `REVIEW` with a blocking re-runnable
  finding, and **MUST NOT** discard work.

### Lever 6 — Provenance receipt → PR body + multi-approver

- **DESIGN-LVR6-01** The receipt **MUST** become the cross-team trust artifact
  with comprehension, validator provenance, and security verdicts.
- **DESIGN-LVR6-02** Kagan **MUST** emit a PR-body-ready block; the human pastes
  it; kagan **MUST NOT** push.
- **DESIGN-LVR6-03** **WHERE** risk tier is high, a second distinct human
  approver **MUST** be required before `ready`.

### Lever 7 — Outcome scorecard

- **DESIGN-LVR7-01** `kagan stats` **MUST** compute durability, CFR, and cycle
  time from ledger + read-only `git log`; no database.
- **DESIGN-LVR7-02** The scorecard **MUST** be a private self-calibration mirror,
  never a team productivity metric.
- **DESIGN-LVR7-03** **WHEN** the user marks pushed, the harness **MUST** capture
  `remote_pr_url` at `mark_pushed` so the CI tripwire is not inert.

### Lever 8 — Retro / compound-knowledge loop

- **DESIGN-LVR8-01** **WHEN** a task reaches `ready`, the CLI **MAY** offer to
  append learnings to `AGENTS.md`.
- **DESIGN-LVR8-02** Kagan **MUST NOT** edit `AGENTS.md` without explicit human
  confirm.

### Lever 9 — Structural debt budget

- **DESIGN-LVR9-01** Debt delta **MUST** be computed from real tools only
  (complexity, duplication, coupling) with **no** hand-rolled "novelty" term.
- **DESIGN-LVR9-02** A rising debt delta on a scope **MUST** escalate that
  scope's risk tier (lever 4); debt **MUST NOT** block generation and **MUST
  NOT** expose a self-serve override.
- **DESIGN-LVR9-03** The cross-diff scope signal **MUST** read
  `Task.changed_files` (actual harvested changed-file set); legacy tasks **MAY**
  fall back to finding locations.

______________________________________________________________________

## 5. Screens — views within the single `kagan` session

These are **not** separate commands — they are views the one `kagan` session moves
between. `[render]` marks Rich output, `[prompt]` marks prompt-toolkit
interaction.

### DESIGN-UI — presentation requirements

- **DESIGN-UI-01** The CLI **SHOULD** follow Apple HIG principles adapted to CLI:
  clarity (one job per view; plain sentences; symbol set `●` needs you · `▸` in
  review · `✓` done · `✗` blocker · `○` optional); deference (content first,
  hairline rules, dim metadata); depth (progressive disclosure); calm over
  cockpit; one primary action stating its own readiness.
- **DESIGN-UI-02** **WHILE** the project queue is empty, the Inbox **MUST**
  present a quiet empty state ("Nothing needs you right now.").
- **DESIGN-UI-03** The Inbox **MUST NOT** show a background poll timer; it
  **MAY** state what is running and when the queue last shipped, derived from the
  ledger on each render.
- **DESIGN-UI-04** **WHILE** approve is locked, the review view **MUST** show a
  persistent lock block naming every unmet condition (findings, comprehension,
  cooldown, high-risk approver).
- **DESIGN-UI-05** Service health in workspaces **MUST** be plain dim text; `●`
  **MUST** stay reserved for needs-you only.
- **DESIGN-UI-06** **WHEN** the user presses enter on ship after pushing, the
  harness **MUST NOT** auto-push; it **MAY** verify the branch on origin via
  read-only `git ls-remote` before flipping to `pr_open`.
- **DESIGN-UI-07** New-task scope **MUST** explain itself in-frame with a dim help
  block on first use.
- **DESIGN-UI-08** `kagan doctor` **SHOULD** use calm sentence labels; raw check
  names **SHOULD** be `--verbosity technical` only.
- **DESIGN-UI-09** **IF** the sole hard fail is a missing manifest in a git repo,
  **THEN** bare `kagan` launch **MUST** offer `kagan init` instead of a generic
  continue prompt.

### `kagan` — Inbox, quiet default `[render]`

```
  kagan · myrepo                                                      all quiet

  Nothing needs you right now.

  2 agents working · last shipped 1h ago

  ───────────────────────────────────────────────────────────────────────────
  n new · enter open a task · w workspaces · S stats · ? help · q quit
```

### `kagan` — something needs you `[render]`

```
  kagan · myrepo                                        2 need you · 3 in review

  ● add-oauth-callback                                              high · drift
     An edit landed outside scope. Allow it, or send it back.
        enter → review

  ● migrate-billing                                              high · waiting
     "Which currency rounding?" — answer to let it continue.
        enter → answer

  ▸ refactor-parser                          in review · 2 findings, 2 prompts
  ▸ export-csv                               in review · ready to approve
  ▸ add-search                               reviewing…
  ✓ update-docs                              ready to push

  ───────────────────────────────────────────────────────────────────────────
  You've been at this 3h20m. Output tends to dip past 3–4h — the queue keeps.
```

### `kagan` → needs-you `[prompt]`

```
  migrate-billing                                                       high risk

  waiting · ambiguous currency assumption
  ●  Which currency rounding? — banker's, half-up, or ask finance?
     the invoice builder calls round() with no mode; the agent paused rather than guess

  > ▏
  ───────────────────────────────────────────────────────────────────────────
  enter submit · ctrl-o editor · esc leave it waiting
```

### Review view — readiness checklist `[prompt]`

```
  refactor-parser                                        kagan/task-1c0d → main
  6 files · +210 −83                                                   med risk

  Almost ready. Two things before you approve:

   › ●  Adjudicate 2 blocking findings
     ●  Answer 2 comprehension prompts
     ✓  Checks passed · 8 of 8
     ✓  Security · 1 advisory noted
     ○  Smoke tests · 2 to verify            (optional at med risk)

  ───────────────────────────────────────────────────────────────────────────
  Approve is locked: adjudicate the open blocking finding(s) first.
  Approve is locked: answer 2 comprehension prompt(s) first (press c).
  ───────────────────────────────────────────────────────────────────────────
  ↑↓ / j k move · enter open · a approve · c comprehension · D view diff
  s send back · f findings · v smoke · r re-validate · q back
```

### Review → Findings `[prompt]`

```
  Findings
  › blocking  ·  parser.py:88  ·  [ai-review]
      Recursion has no depth bound — deep input can stack-overflow.
      (open)
    blocking  ·  parser.py:140  ·  [machine]
      swallows ValueError
      (open)

  ───────────────────────────────────────────────────────────────────────────
  ↑↓ / j k move · g agree · d disagree · q back
  parser.py:88 · blocking
```

`j`/`k` move the cursor over open findings; `g` agrees the focused one, `d`
disagrees and prompts for a reason. The footer echoes the focused finding's
location and severity.

### Review → Smoke `[prompt]`

```
  Smoke tests
  › ○  health check passes
    ○  api up  (:51802)

  ───────────────────────────────────────────────────────────────────────────
  ↑↓ / j k move · v verify · q back
```

`v` verifies only the focused smoke test, not every unverified test at once.

### Review → Comprehension `[prompt]`

```
  ‹ before you approve                                                     1 of 2

  In your own words —
  what stops the new recursive descent from overflowing on deep input?

  > ▏

  context · parser.py:80–96
     80  def parse(node, depth):
     88      return parse(child, …)         ← no depth check
  ───────────────────────────────────────────────────────────────────────────
  enter submit · ctrl-o editor · (skip at med risk · no skip at high)
```

The prompts are diff-specific when the validator generated them (lever 2),
otherwise the static risk-tier set; a quiet provenance line marks which. `D` from
the review checklist opens the full change in an in-frame, scrollable diff viewer
(syntax-highlighted, virtualized across files; no external pager).

### Review → high risk `[prompt]`

```
  migrate-billing                                        kagan/task-9d4e → main
  high risk · irreversible — touches billing & migrations

     ●  Adjudicate 1 security blocker
     ●  Answer 3 comprehension prompts             (required at this risk)
     ✓  Checks passed · 9 of 9
     ●  Second approver — high-risk can't be approved alone
           approved by none yet · waiting for one more
```

### `kagan workspaces` `[render]`

```
  kagan · myrepo                                                  2 agents working

  add-search          reviewing…                web :51731       started 6m ago
  fix-rate-limit      working                   api :51802       started 4m ago

  ───────────────────────────────────────────────────────────────────────────
  fix-rate-limit
     api  :51802  healthy 4m         worker  healthy 4m
     log
       12:04:18  worker picked job 9f2
     take over →  cd .kagan_worktrees/task-bb34          (kagan takeover fix-rate-limit)

  export-csv just landed — give it a read before approving (unlocks 0:20).
```

Service health is plain dim text, not a glyph — `●` stays needs-you only (§3.1).
The log is a dim teaser (the last few lines, each truncated to width), never a
200-line dump; the full log is the take-over step. The cooldown nudge is threaded
from `view_workspaces` via `approve_cooldown_remaining`.

### Intake view `[prompt]`

```
  migrate-billing                                                       new task
  high risk · irreversible — billing & migrations

  What the agent understood
     Move billing per-seat → usage-based. Touches the Stripe webhook, the
     invoice builder, one migration. Won't change tax logic.

  Answer before it runs   ·   Approve = take the assumption · Reject = override
   › ●  Currency rounding?       banker's · half-up · ask finance
     ○  Backfill old invoices?   yes · no · later              (optional)

  Scope   src/billing/**   migrations/**
  ───────────────────────────────────────────────────────────────────────────
  ⏎ answer · a approve · x reject · A approve-all · r run (1 needed) · q quit
```

> **Terminology:** a surfaced decision is **Approved** (accept the agent's
> assumption) or **Rejected** (override it with the correct answer) — this
> replaces kagan's old "bless". The task-level gate verb stays **Approve** /
> **Send back**; finding verdicts stay **agree** / **disagree** (different axes,
> kept distinct). Implementation: rename `Decision.blessed` → `approved` and
> add an explicit reject-with-answer path.

The decision walk is a real walk: `↑↓` / `j k` move a focus cursor (the `›`) and
`a` / `x` act on the FOCUSED decision, with the frame updating in place. `A`
approve-all is gated behind a confirm naming the count + risk.

- **DESIGN-UI-10** `A` approve-all **MUST** be refused outright at
  high/irreversible risk (parity with review's no-skip).

### Ship view `[render]` + copy `[prompt]`

```
  update-docs · ready                                    kagan/task-3e9b → main

  Do this next
     git push -u origin kagan/task-3e9b                                    [c]
     gh pr create --fill                                                   [p]

  Receipt   (goes in the PR so your reviewer audits, not re-derives)       [r]
     ✓ checks   ✓ pinned decisions   ✓ ai-review (opus / codex)
     ✓ your comprehension note   ✓ smoke   ⚠ not covered: screenshots

  One learning for next time?
     "docs are generated from openapi.json — never hand-edit api.md"
     l  append to AGENTS.md
  ───────────────────────────────────────────────────────────────────────────
  c push · p pr · r receipt · l learning · ⏎ I pushed & opened PR · q quit    kagan never pushes
```

The retro affordance (`l`) renders only when `propose_retro()` returns a learning.
A successful copy persists as `[c ✓ copied]`. **IF** the receipt digest is hollow,
**THEN** a dim line **MUST** say so. Pressing enter **MUST NOT** auto-push.

### New task `[prompt]`

```
  New task

  Title    add-oauth-callback
  Scope    src/auth/**
           high risk — full review: validator, security, 2nd approver.
  Agent    › codex    claude    ✋ I'll drive
           reviewed by claude-opus (a different model)
  ───────────────────────────────────────────────────────────────────────────
  enter create & plan · q cancel        (2 agents running — this one will queue)
```

Sequential title → scope → agent, all in-frame; confirm gate shows computed risk
before `create_task → run_intake`. Cancelling **MUST** abort loudly with no task
written. Scope **MUST** carry an in-frame help block explaining paths, drift, and
review tier.

### `kagan stats` `[render]`

```
  myrepo · 14 shipped in 30 days                                     just for you

  Durability       11 of 14 still untouched after two weeks
  Clean merges     12 of 14 passed CI after opening
  Comprehension     9 of 14 answered first try · 2 notes were thin

  Cycle time       low 40m   ·   med 3h   ·   high 1d

  You supervised 18h across 22 sessions, 2 after hours.
  The most durable work wasn't the longest day — it was the read-before-approve.
```

The scorecard **MUST NOT** stack operational per-state tallies (cockpit reading).
Brand-new repo: "Too new to mirror yet — ship a few tasks and this fills in."

### `kagan doctor` `[render]`

```
  ✓ git repository    found at /usr/bin/git
  ✓ python 3.14       Python 3.14
  ✓ coding agent      found: codex, claude
  ⚠ github cli        GitHub CLI not found (optional, for PR workflows)
      Install gh: https://cli.github.com
  ✓ repo config       valid manifest (3 service(s), …)

  Usable — 1 warning(s).
```

`kagan doctor` reuses this calm preflight — ONE visual language. Raw check names
are `--verbosity technical` only. Launch preflight renders on ANY non-pass (warn
too); "Continue anyway?" gates ONLY on hard fail.

______________________________________________________________________

## 6. Industry open gaps kagan can lead on

Unsolved in the literature; the levers make kagan a first-mover and a research
instrument (bets, not claims): **comprehension-debt metric** (l1 + l2); **verification-aware
productivity metrics** (l7); **team trust protocol** (l6); **governance for
hours-long autonomy** (l4+l5).

______________________________________________________________________

## 7. Roadmap

Implementation phases. Each phase **SHOULD** update `specs/cli.md`/`mcp.md` and
this document in the same change.

### Phase 0 — Re-platform & doc reset (PREREQUISITE)

The rip-out and the new skeleton. Independently shippable; no behavior change
beyond surface.

**0a. Remove Textual (code + config + tests).**

- Delete `src/kagan/tui/` entirely.
- Delete `tests/kagan/tui/` and `tests/helpers/snapshot.py`.
- `pyproject.toml`: drop `textual` dep; replace poe `dev` with `kagan` runner;
  remove snapshot tasks/markers; refresh `uv.lock`.
- `tests/conftest.py`: remove `TEXTUAL_ANIMATIONS` and xdist TUI-grouping logic.

**0b. Build the CLI surface layer** (`format/` Rich renderers +
`cli/_interactive.py` prompt-toolkit helpers). Reuse `format/doctor.py`. Copy kimi
patterns — adapted, not vendored. `core/` untouched.

**0c. Rewire entry.** Rewrite `cli/main.py` so bare `kagan` renders the Inbox
once; keep the `doctor` preflight.

**0d. Docs reset.** Delete `docs/internal/plans/`, `docs/internal/adrs/`,
`docs/internal/architecture.md`. Rewrite `specs/tui.md`→`specs/cli.md` and
`tui-stories.md`→`cli-stories.md`; scrub "TUI"/"Textual" repo-wide.

**0e. Persist this document** to `docs/internal/DESIGN.md` as the canonical
single source.

### Phase 1 — Comprehension gate (lever 1)

`core/models.py`, `core/tasks.py`, `core/receipt.py`, `cli/review.py`,
`format/gate.py`.

### Phase 2 — Adversarial validator (lever 2)

Resurrect `VALIDATING`. `core/enums.py`, `core/harness.py`, `core/gate.py`,
`core/agent.py`, `core/recipes.py`.

### Phase 3 — Risk routing + security gate (levers 3+4)

`core/config.py`, `core/models.py`, `core/gate.py`, `core/harness.py`,
`core/tasks.py`.

### Phase 4 — Supervisor protection (lever 5)

`core/harness.py`, `core/inbox.py`, `core/config.py`, `core/errors.py`,
`cli/session.py`.

### Phase 5 — Provenance receipt + multi-approver (lever 6)

`core/receipt.py`, `core/ship.py`, `core/models.py`.

### Phase 6 — Outcome scorecard + retro (levers 7+8)

`cli/stats.py`, `format/stats.py`, `core/retro.py`, `core/ship.py`,
`core/remote_ci.py`.

### Phase 7 — Structural debt budget (lever 9)

`core/debt.py`, `cli/stats.py`, `format/stats.py`, `core/config.py`,
`core/tasks.py`.

### Phase 14 — `kagan init` onboarding + branch-protection doctor probe

`cli/init.py`, `core/onboard.py`, `format/onboard.py`, `core/agent.py`,
`core/doctor_checks.py`, `cli/main.py`.

- **DESIGN-INIT-01** `kagan init` **MUST** aid creating `.kagan/repo.yaml`; **WHERE**
  an agent CLI is available it **MAY** propose the manifest read-only; the human
  **MUST** approve each check command before it is written or executed.
- **DESIGN-INIT-02** The harness **MUST NOT** auto-write executable manifest
  fields the user did not walk (`security`, `services.*.command`); it **MAY**
  surface them as paste-ready suggestions.
- **DESIGN-INIT-03** **IF** no agent, declined draft, or empty draft, **THEN**
  `kagan init` **MUST** write a valid commented skeleton.
- **DESIGN-INIT-04** **BEFORE** running user-approved check commands for
  verification, `kagan init` **MUST** flag destructive shapes and require a second
  confirm; verification **MUST** be opt-in.
- **DESIGN-INIT-05** **WHEN** onboarding runs outside a git repository, it
  **MUST** offer `git init` + `.gitignore` + initial commit; **IF** declined,
  **THEN** onboarding **MUST** stop.
- **DESIGN-INIT-06** `.kagan/repo.yaml` **MUST** remain a `PROTECTED_PATH` so an
  agent cannot silently rewrite the contract.

______________________________________________________________________

## 8. Verification

Per phase the existing bar stays green: `uv run poe lint`, `pyrefly`,
`import-linter`, LOC-budget and test-quality linters, and `uv run pytest tests/`.
The re-platform **simplifies testing**: pure renderers tested by rendering a
seeded `Task` to a string; interactive flows tested with piped prompt-toolkit
input. No event-loop simulation, no SVG baselines.

- **DESIGN-VERIFY-01** **WHEN** Phase 0 completes, `uv run pytest tests/` **MUST**
  pass with zero `textual` imports; bare `kagan` **MUST** render the Inbox; no
  "TUI"/"Textual" strings **MUST** remain in `docs/` or `README.md`.
- **DESIGN-VERIFY-02** **WHEN** blocking findings are verdicted but comprehension
  is empty/trivial, `can_approve` **MUST** stay `False`.
- **DESIGN-VERIFY-03** **WHEN** a fake validator emits a finding, the harness
  **MUST** run `RUNNING`→`VALIDATING`→`REVIEW` and merge with distinct `source`.
- **DESIGN-VERIFY-04** **IF** a planted vuln trips `security`, **THEN** it
  **MUST** be blocking on high-risk scope and advisory on low.
- **DESIGN-VERIFY-05** **WHEN** launching a third concurrent task, the harness
  **MUST** refuse; **WHILE** approve cooldown remains, approve **MUST** be locked.
- **DESIGN-VERIFY-06** Antifragile hardening **R1**–**R2**, **F1**–**F4**, **M1**
  **MUST** hold as specified in §2 and §4 (git denylist, dir-fsync, bounded
  agent/git/gh, validator soft-degrade, malformed-report skip, `changed_files`
  debt signal).
- **DESIGN-VERIFY-07** `test_no_in_session_prompt_escapes_the_frame` **MUST**
  pass; comprehension submits on Enter; new-task Scope carries help; `f` opens
  findings.
- **DESIGN-VERIFY-08** Phase 14: skeleton init, walked agent draft, dangerous
  command second confirm, sanitized draft, branch-protection warn-not-fail.

End-to-end smoke (any phase): `kagan new` in a scratch repo → fake agent → gate
enforces locks → approve → receipt + ledger reflect provenance.

______________________________________________________________________

## Appendix A — End-to-end walkthrough (build a ratatui calculator)

Illustrative lifecycle in the single `kagan` session. Demonstrates: first-boot
scaffold → intake gate → detached run → builder+validator → send-back →
comprehension gate → approve + receipt → ship (never pushes) → CI tripwire →
private stats.

Legend — `●` needs you · `◷` working · `⟳` reviewing/re-run · `▸` cursor · `✓`
done · `✗` blocker · `⚠` note · `○` optional · `☑` verified · `◐` med-risk · `🔔`
notification

**① First run — scaffold the manifest** (Phase 14; also offered when bare `kagan`
finds no manifest)

```
┌─────────────────────────────────────────────────────────────┐
│  kagan · rcalc                                   ◷ first run
│
│  ▌ NO MANIFEST YET — detected Rust (Cargo.toml)
│
│  I'll scaffold .kagan/repo.yaml so reviews know this repo:
│    ✓ build    cargo build
│    ✓ lint     cargo clippy -- -D warnings
│    ✓ test     cargo test
│    ◆ risk     low docs/**  ·  med src/**  ·  high —
│    ◆ review   builder codex · reviewer claude-opus (≠ model)
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ scaffold & continue      e edit      q quit
└─────────────────────────────────────────────────────────────┘
```

**② New task** — `n`

```
┌─────────────────────────────────────────────────────────────┐
│  NEW TASK
│
│  ▌ title   a ratatui calculator app
│  ▌ scope   src/**
│            ◐ med risk — validator + comprehension, no 2nd ok
│  ▌ agent   ▸ codex      claude      ✋ I'll drive
│            reviewed by claude-opus  (a different model)
│
├─────────────────────────────────────────────────────────────┤
│  type fields · ←→ pick agent · ⏎ create & plan · q cancel
└─────────────────────────────────────────────────────────────┘
```

**③ Intake gate** — agent plans read-only, surfaces assumptions; Approve / Reject each

```
┌─────────────────────────────────────────────────────────────┐
│  a ratatui calculator app · INTAKE               ◐ med risk
│
│  ▌ WHAT THE AGENT UNDERSTOOD
│    TUI calc with ratatui + crossterm. Button grid, keyboard
│    input, a display line. Evaluate on Enter.
│
│  ▌ DECISIONS   (a approve assumption · x reject & answer)
│    ▸ ● precedence?    proper (×÷ before +−)  ·  left-to-right
│      ● number type?   floating point  ·  integer-only
│      ● divide by 0?   show "Error"  ·  panic  ·  inf
│      ○ mouse?         keyboard-only  ·  mouse+kb    (optional)
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ answer · a approve · x reject · r run (3 left) · q quit
└─────────────────────────────────────────────────────────────┘
```

**④ Running** — `r` spawns detached runner; quiet inbox; notification on return

**⑤ Reviewing** — headless validator (different model): `🔔 kagan: reviewing rcalc…`

**⑥ Review checklist** — the screen IS the to-do that unlocks approve

**⑦ Validator caught real bugs** — agree they're real, send back (same worktree)

**⑧ Pass 2 — comprehension gate** — human-authored rationale (med = 2 prompts)

**⑨ Approve** — receipt auto-writes to `.kagan/reviews/`; retro offer

**⑩ Ship — kagan never pushes**

```
┌─────────────────────────────────────────────────────────────┐
│  a ratatui calculator app · READY    kagan/task-1a2b → main
│
│  ▌ DO THIS NEXT   (kagan never pushes)
│    $ git push -u origin kagan/task-1a2b                   [c]
│    $ gh pr create --fill                                  [p]
│
│  ▌ RECEIPT → paste in the PR body                         [r]
│    ✓ checks   ✓ decisions   ✓ ai-review: 2 bugs caught+fixed
│    ✓ comprehension    ⚠ not covered: f64 overflow → inf
│
├─────────────────────────────────────────────────────────────┤
│  c push · p pr · r receipt · ⏎ I pushed & opened PR · q
└─────────────────────────────────────────────────────────────┘
```

**⑪ PR open — read-only CI tripwire** (CI red → re-surfaces as `● needs you`)

**⑫ Private mirror** — `kagan stats`

Mapped to levers: risk routing (l4); builder+validator (l2); send-back loop;
comprehension gate (l1); never-push (l6 / invariant); receipt provenance; quiet +
notification-backed return (l5 / §3.3).
