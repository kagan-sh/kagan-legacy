# Kagan v2 — CLI & Harness Specification

Normative specification for the Kagan **v2 supervision layer**: the interactive
command-line interface (**CLI**) and the engine it surfaces (**harness**). v2 is
**not a kanban board** — it isolates each unit of AI work, verifies it against the
repo's own bar before a human looks, and pulls the human in only for decisions a
human must make.

> **Provenance.** This set supersedes the board-era documents and the earlier
> full-screen-dashboard draft. It captures the v2 pivot, the re-platform to a
> single interactive CLI (`docs/internal/DESIGN.md` §3), and the behaviour of the
> reference prototype ("harness" Claude artifact). The canonical design rationale
> lives in `DESIGN.md`; this document is the normative requirement set.

## How to read this document

**RFC 2119 / RFC 8174.** The key words **MUST**, **MUST NOT**, **REQUIRED**,
**SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**,
**OPTIONAL** are to be interpreted as described in RFC 2119 and RFC 8174 — that
is, **only when in uppercase**. Lowercase uses carry their ordinary English
meaning. Per RFC 2119 these are used sparingly, only where they constrain
behaviour that matters for correctness or interoperability.

**EARS** (Easy Approach to Requirements Syntax, Mavin et al.). Every requirement
follows one EARS pattern; the obligation verb is an RFC 2119 keyword:

| Pattern      | Shape                                                                           |
| ------------ | ------------------------------------------------------------------------------- |
| Ubiquitous   | The `<actor>` **MUST** `<response>`.                                            |
| State-driven | **WHILE** `<state>`, the `<actor>` **MUST** `<response>`.                       |
| Event-driven | **WHEN** `<trigger>`, the `<actor>` **MUST** `<response>`.                      |
| Optional     | **WHERE** `<feature present>`, the `<actor>` **MAY/SHOULD** `<response>`.       |
| Unwanted     | **IF** `<condition>`, **THEN** the `<actor>` **MUST** `<response>`.             |
| Complex      | **WHILE** `<state>`, **WHEN** `<trigger>`, the `<actor>` **MUST** `<response>`. |

**Actors.** *harness* = the core engine (worktrees, ports, gate engine, ledger,
local mirror); *CLI* = its interactive command-line surface — the single `kagan`
session (a prompt-toolkit navigator that renders the externalized ledger and
exits when the user is done); *agent* = the opaque coding CLI. The agent↔harness
contract is specified separately in `mcp.md`.

**The one entrypoint.** `kagan` is the only command a human types. It opens a
stateless interactive session on the Inbox navigator; the user moves through the
queue, opens a task into its state-appropriate view (intake / review / ship /
workspace), acts, and quits. New task, stats, and help are in-session actions,
not separate commands. There is no persistent dashboard and no live agent-output
stream; the doing happens in a detached per-task runner (`kagan _run <id>`).

**IDs.** `CLI-<AREA>-NN`. Stories in `cli-stories.md` reference these.

______________________________________________________________________

## CLI-SHELL — session shell & navigation

- **CLI-SHELL-01** The CLI MUST present supervision state through state-appropriate views — an **Inbox** navigator, a **Gate** (review) view, and a **Workspaces** view — reached inside the single `kagan` session, and MUST NOT present work as kanban columns. "Inbox" is both the conceptual name and the on-screen label, and keeps the `CLI-INBOX-*` requirement prefix.
- **CLI-SHELL-02** WHEN the user requests a primary view, the CLI MUST switch to the Inbox, Gate, or Workspaces view respectively, within the same session.
- **CLI-SHELL-03** WHEN the user opens a task, the CLI MUST route to the view matching the task's lifecycle state: `intake`→Intake, `review`/`done`→Gate, `ready`→Ship, `running`/`validating`/`pr_open`→Workspaces.
- **CLI-SHELL-04** WHILE a text input is focused, the CLI MUST direct keystrokes to that input and MUST NOT invoke global single-key shortcuts.
- **CLI-SHELL-05** The CLI SHOULD provide an in-session help view that lists the currently active key bindings.
- **CLI-SHELL-06** WHEN a view is shown, the CLI SHOULD display a one-line next-step hint appropriate to the current view and task state.
- **CLI-SHELL-07** The CLI MUST be a stateless interactive session: it renders the externalized ledger on launch, mutates state only through the harness, and exits when the user quits; it MUST NOT run a persistent dashboard or an always-on refresh loop.

## CLI-BOOT — startup & empty state

- **CLI-BOOT-01** WHEN the CLI starts, the harness MUST run a health check (`doctor` preflight) for required external tools (git, and at least one agent CLI) and report each result.
- **CLI-BOOT-02** IF no agent CLI backend is available, THEN the CLI MUST warn the user and MUST still allow continuing in a no-agent ("I drive") mode.
- **CLI-BOOT-03** WHILE the project has no tasks, the CLI MUST present a quiet empty state inviting task creation and MUST NOT imply that work is in progress.
- **CLI-BOOT-04** The CLI MUST provide a `kagan init` command that aids creating `.kagan/repo.yaml`: WHERE an agent CLI is available it MAY propose the manifest read-only, but the user MUST approve each proposed check command before it is written, and any command the user has not approved MUST NOT be written or executed. The harness MUST NOT auto-write other executable manifest fields the user did not walk (e.g. `security`, `services.*.command`); it MAY surface them as suggestions for the user to add by hand. IF no agent is available or the user declines or the draft is empty, THEN `kagan init` MUST write a valid commented skeleton manifest. The harness MUST validate the assembled manifest before writing it, and MUST NOT write one the loader would reject. `kagan init` MUST tunnel tool-level setup (installing git/agent CLI/gh, authenticating) to the user rather than performing it.
- **CLI-BOOT-05** BEFORE running any user-approved check command for verification, `kagan init` MUST flag obviously-destructive command shapes and require an additional explicit confirmation; verification of approved commands MUST be opt-in (default off).
- **CLI-BOOT-06** WHEN bare `kagan` starts and the only hard failure is a missing manifest, the CLI MUST offer to run `kagan init` rather than the generic continue prompt, and MUST NOT drop into a session with no manifest (or no usable repo) if the user declines or setup does not complete.
- **CLI-BOOT-08** kagan requires a git repository (per-task worktrees fork from a HEAD). WHEN onboarding runs outside a git repository, it MUST offer to initialize one (git init + a recommended project-agnostic `.gitignore` + an initial commit), defaulting to yes; IF the user declines, onboarding MUST stop and MUST NOT proceed to manifest setup or a session until a git repository exists.
- **CLI-BOOT-09** WHILE the agent draft runs, onboarding MUST show a live liveness indicator (so the user can tell it is working, not hung), MUST bound the draft with a timeout, and MUST allow the user to skip it; on timeout, skip, or failure it MUST fall back to the deterministic skeleton rather than hang or abort.
- **CLI-BOOT-07** WHERE `gh` and a git remote are present, the `doctor` preflight MUST report whether the base branch requires reviews on the remote, as a WARNING (never a hard failure) since the harness cannot enforce remote branch protection.

## CLI-INBOX — urgency-sorted supervision queue

- **CLI-INBOX-01** The Inbox MUST order tasks by how much they need a human, in the precedence `drift > ci-failed > needs-you > intake > review > ready > validating > pr-open > running > done`, and MUST NOT order by creation time or by column.
  - Display vocabulary (normative): the `pr_open` state is surfaced to the user with the label **"in review · on github"** (the prototype's wording); the precedence token above stays `pr-open`.
- **CLI-INBOX-02** WHEN nothing requires the user, the Inbox MUST state plainly that nothing needs them (quiet by default).
- **CLI-INBOX-03** WHILE a task is running, the Inbox MUST collapse it to a single line showing a liveness heartbeat and a rough ETA, and MUST NOT stream the agent's output on the Inbox.
- **CLI-INBOX-04** WHEN the user reopens a task they have previously viewed, the CLI MUST present a "since you left" delta (what changed, what was decided, what is now blocked) and MUST NOT require reading the full transcript.
- **CLI-INBOX-05** WHEN a task is reopened, the CLI MUST display a one-line resume point naming the next action.
- **CLI-INBOX-06** WHEN a task changes lifecycle state, a re-launched or refreshed Inbox MUST re-sort per CLI-INBOX-01 from the ledger, without the user choosing an ordering.

## CLI-INTAKE — the intake gate (input readiness)

- **CLI-INTAKE-01** WHEN a task is created, the harness MUST place it in an `intake` state and MUST run the agent in a plan-only mode that cannot modify files before any implementation begins.
- **CLI-INTAKE-02** The Intake view MUST display the agent-generated understanding and the list of decisions the agent would otherwise assume, each tagged with a severity (`blocking`/`question`).
- **CLI-INTAKE-03** WHILE any blocking decision is neither answered nor explicitly approved, the harness MUST keep the "run agent" action locked.
- **CLI-INTAKE-04** WHEN the user answers or approves a decision, the harness MUST record it to the ledger as pinned context for the run.
- **CLI-INTAKE-05** WHEN all blocking decisions are resolved and the user starts the run, the harness MUST start the agent with the pinned decisions as constraints.
- **CLI-INTAKE-06** The harness MUST NOT allow an underspecified task to proceed to implementation unless each blocking decision has been explicitly answered or approved by a human.
- **CLI-INTAKE-07** IF intake surfaces zero decisions, THEN the harness MAY auto-advance the task to running, and MUST still record that intake produced no unknowns.

> **Terminology.** A surfaced intake decision is **Approved** (accept the agent's assumption) or **Rejected** (override it with the correct answer); this replaces kagan's old "bless". The task-level gate verb stays **Approve** / **Send back**; finding verdicts stay **agree** / **disagree** (different axes, kept distinct).

## CLI-WS — workspace, ports & process supervision

- **CLI-WS-01** WHEN a task starts, the harness MUST create a dedicated git worktree for it on the same repository (no re-clone).
- **CLI-WS-02** WHEN a workspace's services start, the harness MUST assign non-colliding ports per workspace and MUST record the assignment.
- **CLI-WS-03** The Workspaces view MUST present a map of worktrees and the ports/resources bound to each.
- **CLI-WS-04** The harness MUST give each workspace an isolated environment (its own copy of secrets/config) and MUST NOT let an agent modify the shared environment that other workspaces depend on.
- **CLI-WS-05** WHEN the user pins a branch or process as do-not-touch, the harness MUST preserve it across runs and MUST declare it off-limits to agents.
- **CLI-WS-06** WHEN a task completes or is abandoned, the harness MUST free that workspace's ports, environment, and device leases.
- **CLI-WS-07** The harness MUST start the services declared in the repo manifest within the task's worktree; service startup MUST be driven by the manifest, not improvised by the agent.
- **CLI-WS-08** WHILE a workspace process is running, the Workspaces view MUST surface its recent log output and MUST print the worktree path plus a copy-ready command so the user can open that process in their own terminal to take over; the CLI MUST NOT auto-attach a launcher.
- **CLI-WS-09** WHERE a task targets a mobile platform, the harness MAY lease a dedicated simulator/emulator/device per workspace.
- **CLI-WS-10** WHEN the harness creates a task's worktree, it MUST create it on a dedicated named branch `kagan/<task-id>` and MUST NOT use a detached HEAD, so the push command (CLI-SHIP-02) and the PR can reference the branch by name.

## CLI-MIRROR — local CI mirror & remote status

- **CLI-MIRROR-01** WHEN a task enters validation, the harness MUST run the repo's declared cheap, deterministic checks (e.g. lint, types, unit, codegen) locally and before a human reviews.
- **CLI-MIRROR-02** IF a branch's base has moved such that generated artifacts would drift, THEN the harness MUST warn before codegen pulls in unrelated upstream changes.
- **CLI-MIRROR-03** The CLI MUST display remote CI status inline next to the task and MUST treat remote CI as read-only.

## CLI-GATE — the review gate (output quality)

- **CLI-GATE-01** WHEN a task finishes running, the harness MUST run the review gate (universal checks + repo rubric + local mirror) before presenting the task for human review.
- **CLI-GATE-02** The universal checks MUST include at least: it builds; types pass; tests pass **and can actually fail** (mutation probe, not tautology); the diff is in scope; the diff is minimal; secrets and shared environment are untouched.
- **CLI-GATE-03** The harness MUST also apply the repo's own rubric (from the manifest) and MUST NOT hardcode a single team's checklist.
- **CLI-GATE-04** The Gate view MUST present findings as the primary content, each tagged by severity (`blocking`/`question`/`nit`) with a one-line problem and an anchored location.
- **CLI-GATE-05** Each finding MUST carry an explicit agree/disagree verdict; a disagree MUST capture a reply; the harness MUST NOT allow a finding to be silently dropped (downgrade, never delete).
- **CLI-GATE-06** WHILE any blocking finding is open, the harness MUST keep the approve action locked.
- **CLI-GATE-07** WHEN the user sends a task back with a comment, the harness MUST re-run the agent **in the same worktree** (no new branch). The comment MUST be recorded on the task as a blocking finding with verdict `disagree` (so the re-run agent sees the reviewer's reason and it is not silently dropped), and any prior drift alarm MUST be cleared.
- **CLI-GATE-08** The Gate view MUST present an agent-generated smoke-test checklist referencing the live service port, and MUST let the user mark each item verified.
- **CLI-GATE-09** WHEN the Gate is opened for a task, the CLI MUST show the pinned-at-intake decisions so deliberate choices are distinguishable from inferred ones.
- **CLI-GATE-10** IF the base moved since the gate checks ran, THEN the CLI MUST flag the results as potentially stale and MUST offer re-validation.

## CLI-SHIP — approve, then the human ships

- **CLI-SHIP-01** WHEN the user approves a task, the harness MUST mark it `ready` and MUST NOT push, merge, or open a pull request on the user's behalf.
- **CLI-SHIP-02** The Ship view MUST provide the exact push command (and a PR-create command) for the user to run themselves.
- **CLI-SHIP-03** The harness MUST NOT force-push and MUST NOT auto-merge under any configuration.
- **CLI-SHIP-04** WHEN the user indicates they have pushed and opened the PR, the harness MUST move the task to `pr_open` and begin read-only remote CI watching.
- **CLI-SHIP-05** The harness MUST enforce the no-push, no-force-push, and no-merge guarantees through its own git command allowlist, and MUST NOT install a git hook or write git config inside the worktree to enforce them — the worktree shares the main repository's `.git` common directory, so such state would leak into the user's repository.
- **CLI-SHIP-06** WHEN the user marks a task pushed, the harness MUST best-effort capture the PR URL via a read-only `gh pr view <branch> --json url` and persist it on the task so the post-PR tripwire (CLI-POSTPR) and the change-failure-rate metric (CLI-STATS) work. IF `gh` is absent or no PR exists yet, the capture MUST degrade to no URL and the `ready`→`pr_open` flip MUST still proceed (capture is an opportunity, never a precondition).

## CLI-RECEIPT — reviewed-before-push receipt

- **CLI-RECEIPT-01** WHEN a task becomes `ready`, the harness MUST be able to generate a "reviewed-before-push" receipt containing: machine-verified checks, pinned-at-intake decisions, author-adjudicated findings with verdicts, the author's comprehension note, hand-verified smoke-tests, and an explicit "not covered" section.
- **CLI-RECEIPT-02** The receipt MUST state honestly what was NOT verified; it MUST NOT present unverified items as passed.
- **CLI-RECEIPT-03** WHEN the user requests the receipt, the CLI MUST make it copyable for pasting into the pull request.

## CLI-POSTPR — read-only post-PR tripwire

- **CLI-POSTPR-01** WHILE a task is in review on the remote, the harness MUST poll remote CI status and base freshness read-only.
- **CLI-POSTPR-02** IF remote CI fails for a pr-open task, THEN the harness MUST re-surface the task in the Inbox at needs-you precedence.
- **CLI-POSTPR-03** IF a pr-open task's base goes stale, THEN the harness MUST surface a stale warning recommending a rebase before codegen.
- **CLI-POSTPR-04** The harness MUST NOT write tool state back to the remote (no bidirectional sync); remote interaction MUST be limited to read-only ingestion and explicit, human-initiated pull/import.

## CLI-DRIFT — the one mid-run interrupt

- **CLI-DRIFT-01** WHEN the agent edits files outside the task's declared scope, contradicts a recorded decision, or exceeds the agreed plan, the harness MUST raise a drift alarm and notify the user.
- **CLI-DRIFT-02** A raised drift alarm MUST sort to the top of the Inbox.
- **CLI-DRIFT-03** WHEN a drift alarm is raised, the CLI MUST offer a send-back action and an allow-scope action, and MUST record the choice.
- **CLI-DRIFT-04** Apart from a needs-you request, drift MUST be the only mid-run condition that interrupts the user.

## CLI-LEDGER — durable state

- **CLI-LEDGER-01** The harness MUST own durable state — tasks, each task's branch/worktree, port assignments, lifecycle stage, recorded decisions, and findings — so the agent stays stateless.
- **CLI-LEDGER-02** WHEN the CLI is re-invoked after a crash or quit, the harness MUST restore tasks and in-flight runs from the ledger, because the session itself is stateless (CLI-SHELL-07).
- **CLI-LEDGER-03** The agent MUST NOT be required to re-explain the environment map between sessions; the ledger MUST persist it.
- **CLI-LEDGER-04** The ledger MUST be stored as per-task files on disk — a document-shaped state file written atomically (temp file + rename) plus an append-only event log — and MUST NOT depend on a relational database; the data is small, per-task, and single-writer.

## CLI-NOTIFY — notify and leave

- **CLI-NOTIFY-01** WHEN a task needs human input, lands in review, finishes, drifts, or fails remote CI, the harness MUST notify the user (OS notification and/or terminal bell), so the user can leave the CLI and be called back.
- **CLI-NOTIFY-02** The harness MUST NOT notify on routine progress; only the events in CLI-NOTIFY-01 warrant a notification.
- **CLI-NOTIFY-03** WHERE a webhook is configured, the harness MAY deliver the same notifications to it.

## CLI-CONFIG — per-repo manifest

- **CLI-CONFIG-01** The harness MUST read a per-repo manifest (`.kagan/repo.yaml`) declaring services, check commands, the review-rubric path, and pinned do-not-touch processes.
- **CLI-CONFIG-02** The harness MUST read the repo's review rubric (`.kagan/review.md`) and apply it as the repo-specific gate layer.
- **CLI-CONFIG-03** The harness MUST function on any repository that supplies a valid manifest and MUST NOT hardcode one project's services or checks.
- **CLI-CONFIG-04** IF the manifest is absent or invalid, THEN the harness MUST report the problem clearly and MUST NOT silently guess service or port configuration.
- **CLI-CONFIG-05** The harness MUST use the user's own git identity for all git operations and MUST NOT create or use a separate "kagan" git profile or persona.
- **CLI-CONFIG-06** The manifest MAY declare `risk_tiers` (tier name → path globs) and a `security` SAST command. Both are additive: a manifest that omits them MUST behave exactly as before (every task `medium`, no security gate).
- **CLI-CONFIG-07** The manifest MAY declare `max_concurrent_agents` (default 2) and `approve_cooldown_seconds` (default 60). Both are additive: a manifest that omits them MUST behave with these defaults (lever 5).
- **CLI-CONFIG-08** The manifest MAY declare `debt_threshold` (int, lever 9). It is additive: a manifest that omits it (None) MUST disable debt escalation entirely, so the repo behaves exactly as before.

## CLI-RISK — risk routing & the security gate (the spine, lever 3+4)

- **CLI-RISK-01** WHEN intake completes, the harness MUST classify the task's risk tier from its `scope` against `risk_tiers`: `high` if ANY scope path matches a high glob; `low` only if EVERY scope path matches a low glob; else `medium`. The tier MUST be persisted on the task and re-derived whenever scope changes (it is never one-shot).
- **CLI-RISK-02** A repo with no `risk_tiers` MUST classify every task `medium`, so unconfigured repos keep today's ceremony.
- **CLI-RISK-03** The harness MUST scale ceremony by tier: `low` skips the adversarial validator stage (machine checks only) and does NOT require a comprehension note to approve; `medium`/`high` run the validator (when a reviewer model is configured) and require the substantive comprehension note. The blocking-findings-adjudicated lock (CLI-GATE-06) holds for ALL tiers.
- **CLI-RISK-04** WHEN a `security` command is declared, the gate MUST run it in the worktree and, on a non-zero exit, raise a finding sourced `security` that is `blocking` on `high`-risk scope and advisory (`question`) elsewhere. IF no `security` command is declared, the gate MUST record an explicit "skipped" finding rather than report security-clean.
- **CLI-RISK-05** After findings are gathered, the harness MUST downgrade (never drop) any `ai-review`/`security` finding whose self-rated confidence is below the tier's bar to advisory: `low` demands high confidence to stay blocking, `high` keeps even tentative findings blocking. A finding with no confidence is unaffected.
- **CLI-RISK-06** The CLI MUST surface the risk tier on the intake header, the gate header, and the inbox row.

## CLI-SUP — supervisor protection, anti-slot-machine (lever 5)

- **CLI-SUP-01** The harness MUST cap concurrent in-flight agents at `max_concurrent_agents` (default 2): WHILE that many tasks are RUNNING or VALIDATING, it MUST refuse to start a new run, raising a clear domain error BEFORE preparing the worktree or launching the agent. The task being started MUST NOT count against itself (a send-back re-running in place is always allowed).
- **CLI-SUP-02** The surface (re-run, the intake run path, new-task) MUST read the cap (`can_start_agent`/`running_count`) and refuse with a plain message ("N agents already working (cap) — finish a review first") BEFORE spawning the detached runner, so the refusal is visible and not buried in the detached process.
- **CLI-SUP-03** After a task lands in REVIEW, the harness MUST compute a gen→approve cooldown (`approve_cooldown_seconds`, default 60) derived from the RUNNING/VALIDATING → REVIEW event timestamp; it MUST NOT write the cooldown into the committable ledger. The cooldown MUST be a SEPARATE method from `can_approve` (which stays a pure findings+comprehension lock).
- **CLI-SUP-04** The approve action MUST check BOTH `can_approve` AND the cooldown: WHILE the cooldown remains, approve MUST refuse with "give it a read — approve unlocks in Ns" and stay in the review view.
- **CLI-SUP-05** The inbox MAY show private, non-blocking coach lines derived at render time: an after-hours nudge ("it is after hours — the queue keeps") on an evening/night/weekend local clock, and a gentle high-throughput nudge from recent approval timestamps. These MUST NEVER be persisted, committed, or surfaced as a team metric. A precise cumulative-session-duration timer is DEFERRED (needs a private machine-local store).

## CLI-STATS — outcome scorecard, a private mirror (lever 7)

- **CLI-STATS-01** The stats action MUST compute outcome metrics read-only from the ledger (task state + event log) and read-only `git log` only: no database, no new git verbs, no schema change.
- **CLI-STATS-02** Cycle time MUST be measured from a task's first event (intake) to its REVIEW→READY transition and reported as a median per risk tier; it MUST key on that canonical transition, NOT the `approved` event (which has two emitters). Tasks that never reached `ready` MUST be excluded, not counted as zero.
- **CLI-STATS-03** Change-failure-rate MUST count `pr_open` tasks whose remote CI is `fail` over those with a settled (`pass`|`fail`) verdict; `pending`/`unknown` MUST be excluded so a pending check is never silently a pass. WHEN no task has a settled verdict, the metric MUST report N/A, not 0%.
- **CLI-STATS-04** Comprehension first-try MUST count tasks whose event log holds exactly one `comprehension_recorded`; the denominator MUST be tasks asked at all (low-risk tasks emit none and MUST NOT dilute the rate).
- **CLI-STATS-05** Review-caught MUST count blocking findings sourced `ai-review`/`security` that the human marked `agree` (a `disagree` is a human override and MUST be excluded) — "real bugs caught before they shipped".
- **CLI-STATS-06** Durability MUST be best-effort and labelled as such: kagan never merges, so it can only observe (via read-only `git log` on the base branch) approved files later re-edited within a window. It MUST NOT be presented as a hard reliability number, and MUST report "too new" when nothing is observable.
- **CLI-STATS-07** The scorecard MUST render as calm sentences ("just for you"), is a PRIVATE self-calibration mirror, and MUST NEVER be written to the committable `.kagan/` nor surfaced as a team productivity metric.

## CLI-DEBT — structural debt budget, the cross-diff blind spot (lever 9)

- **CLI-DEBT-01** The debt signal MUST be computed from real, language-agnostic signals only — DUPLICATION (added lines that recur as a repeated line-window within a changeset) + CHURN (added-line count) — with NO hand-rolled "novelty" term: deleting a duplicate MUST lower the score, so the signal cannot be gamed by writing boilerplate (the GitClear pathology).
- **CLI-DEBT-02** A per-scope cumulative debt MUST be derived from ledger history only (prior tasks' touched-file/finding locations under the scope's globs): no database, no new persisted store beyond the existing events. It is best-effort and observational, never authoritative.
- **CLI-DEBT-03** WHEN a scope's cumulative debt exceeds `debt_threshold`, the harness MUST bump that scope's risk tier UP exactly one level (`low`→`medium`→`high`) at classification time, so the rotting area routes into heavier review. The bump MUST be ONE-DIRECTIONAL (never lowers a tier) and MUST re-apply on every scope change (it rides the existing risk classification).
- **CLI-DEBT-04** Debt MUST NEVER block or refuse generation, MUST NOT add a blocking finding, and MUST NOT expose a self-serve override flag. Classification MUST NOT raise on a debt read error — it MUST degrade to the un-escalated base tier. `debt_threshold` unset MUST disable escalation entirely.
- **CLI-DEBT-05** The scorecard MAY surface a per-scope debt trend; like the rest of the scorecard it is a PRIVATE self-mirror and MUST NEVER be written to the committable `.kagan/` nor surfaced as a team metric.

## CLI-RETRO — compound-knowledge loop (lever 8)

- **CLI-RETRO-01** WHEN a task reaches `ready`, the CLI MAY offer one candidate learning distilled (purely from the task model) from its resolved decisions, drift causes, and recurring finding locations; WHEN there is nothing worth recording, it MUST make no offer.
- **CLI-RETRO-02** The candidate learning MUST be appended to the repo-root `AGENTS.md` (created if absent, under a stable heading, append-only so human-edited content is never clobbered) ONLY on an explicit human confirm; an empty or skipped edit MUST be a no-op. kagan MUST NEVER edit `AGENTS.md` without confirmation.

## CLI-AGENT — opaque agent (harness side)

- **CLI-AGENT-01** The harness MUST treat each agent as an opaque subprocess in a worktree — spawned with a prompt, its raw stream read, its result harvested from the git diff — and MUST NOT normalize the agent through a deep turn-protocol layer.
- **CLI-AGENT-02** WHEN the user creates a task, the CLI MUST let the user choose among the agent CLIs actually installed and MUST NOT require a registry of unavailable backends.
- **CLI-AGENT-03** The only structured signal the harness REQUIRES from the agent is the report channel defined in `mcp.md`; the harness MUST NOT depend on parsing the agent's turn lifecycle.

## CLI-RUN — the detached per-task runner

- **CLI-RUN-01** Because the interactive session is stateless and exits, the harness MUST run the agent, harvest the diff, run validation + the gate, and write the result to the ledger in a detached per-task runner (`kagan _run <id>`), not inside the interactive session.
- **CLI-RUN-02** The detached runner MUST be hidden plumbing (not a user entrypoint); the only command a human types is `kagan`.
- **CLI-RUN-03** WHEN the detached runner reaches a point that needs the human (review, needs-you, drift, finished, CI fail), it MUST fire exactly one notification per such event (CLI-NOTIFY-01) and MUST NOT run an always-on daemon.

______________________________________________________________________

## Out of scope (anti-features)

The harness MUST NOT implement any of the following; they are the machinery that
sank v1 and comparable tools:

- Kanban columns or board-as-the-product.
- An always-on, full-screen dashboard with live-updating panes (the slot-machine surface the re-platform removed).
- A type-commands REPL or a sprawl of one-shot verbs; there is one entrypoint (`kagan`) and in-session actions.
- Deep ACP / agent-protocol turn modelling.
- A registry of many "supported" agents behind an abstract base class.
- Bidirectional GitHub sync firing on edits (read-only ingestion + explicit pull only).
- Auto-push, force-push, or auto-merge.
- Interactive auto-attach launchers (tmux/IDE); the CLI prints the worktree + commands instead.
- Persona presets or remote persona import.
- Orchestration-as-the-product.

**Deferred (future, non-normative).** Teammate / cross-timezone hand-off (seeing
teammates' tasks, passing a task with its workspace and resume point) MAY be
added once the single-developer loop is proven; it is out of scope for the
initial build.
