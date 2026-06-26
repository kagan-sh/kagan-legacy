# Kagan — Design & Methodology

> Canonical design document (`docs/internal/DESIGN.md`). Supersedes the former `docs/internal/plans/`, `adrs/`, and `architecture.md` (removed in Phase 0). Single source of truth for what kagan is, why, and how it is built.

______________________________________________________________________

## 1. Context & thesis

Kagan is a supervision layer for AI coding agents: it isolates each unit of agent work in a git worktree, gates it (intake = input readiness, review = output quality), lets the human adjudicate, and marks work `ready` **without ever pushing**. Its instincts are sound. But it verifies the *code* and protects *main* — and a synthesis of ~80 studies (`hai_coding/`) says the two factors that actually decide whether AI helps or harms are neither:

1. **Does the human comprehend what they ship?** Usage *mode* predicts outcome, not the tool: engaged devs score ≥65% comprehension (= unaided baseline), delegators \<40% (Anthropic RCT). The 88% AI-code retention rate is a trust-miscalibration *risk* signal, not quality.
1. **Does the human stay the competent, un-burned-out anchor?** AI is an amplifier, not a substitute (HAI-Eval: AI-alone 0.67%, human-alone 18.89%, human+AI 31.11%). But the slot-machine loop drives compulsion — usage rises while satisfaction falls; heavy users work nights/weekends 96% of the time; "brain fry" raises major errors +39% and quit-intent +39%. The research's explicit design mandate: **build friction, not engagement; the most productive user must not be the heaviest user.**

Supporting evidence the design leans on: the bottleneck moved from writing to *validating* code (+98% PRs, +91% review time, −7% main throughput); functional ≠ secure (82.8% of *passing* AI code carries a vuln; 45% OWASP rate, flat across model generations); risk-routed autonomy (HITL/HOTL/auto by task *risk*; irreversible = always human); builder+validator split with *different* models beats single-agent self-review; measure durability/CFR/cycle-time, not commits/LOC.

**Thesis:** *Kagan should verify the human as rigorously as it verifies the code* — and do it through a calm, low-ceremony surface that protects the supervisor's attention instead of competing for it.

______________________________________________________________________

## 2. Invariants (preserved from the deleted ADRs; do not regress)

These survive the doc reset because the code depends on them:

- **File ledger, no database** (was ADR-0001). Per-task `state.json` (atomic: `mkstemp`→`fsync`→`os.replace`→**dir-fsync**) + append-only `events.jsonl`, stdlib `json`. The dir-fsync (hardening **R2**, `core/ledger._fsync_dir`) makes the rename itself durable, not just the file body — without it a crash after `os.replace` could lose a "succeeded" state.json, the one unrecoverable loss for a single-source-of-truth ledger; `append_event` dir-fsyncs only on file creation (no per-append hot-path cost). The **Harness is the single writer**; every surface is a read-only view that mutates only through `Harness`. **Location (as built):** the operational ledger lives in-repo at `<git-toplevel>/.kagan/state` (gitignored, so it never enters commits), resolved by `default_data_dir()` in `core/harness.py` with a `KAGAN_DATA_DIR` override. The external machine-local store keyed per repo is a **documented FUTURE item** (§3.6), not the present state. See §3.6.
- **One YAML manifest** (was ADR-0002): `.kagan/repo.yaml` (`RepoConfig`, `extra="forbid"`), validated on load; the harness refuses to guess when it is missing.
- **Never push/merge/force-push** — two distinct layers, honestly scoped:
  - *kagan itself* never pushes: enforced on **two** layers (hardening **R1** made it symmetric). The public `run_git` keeps the read-only allowlist (raises on anything outside `rev-parse/diff/status/log/show/rev-list/ls-files/cat-file/symbolic-ref/describe`). Underneath, the single `_spawn_git` chokepoint — which the private `_run_git` used by mutating internals (`init/add/commit/worktree`) also funnels through — enforces a **denylist** of irreversible/destructive verbs (`push/merge/rebase/reset/clean/update-ref/fetch/pull/remote`), so a future careless `_run_git("push"/"reset", …)` raises instead of externalising ruin. `_git_subcommand` skips git's `-c name=value`/`-C path` global flags so `-c commit.gpgsign=false commit` resolves to `commit`, not the flag value. Approve = mark `ready`; the human runs the printed `git push`/`gh pr create` themselves.
  - *the agent's* own shell is governed by the spawn env, not the allowlist: `core/agent._agent_env` scrubs the child env (no token, `GIT_TERMINAL_PROMPT=0`), **drops the forwarded ssh-agent socket** (`SSH_AUTH_SOCK` — the agent works a local worktree and never needs ssh to a remote; kagan's own read-only `ls-remote` keeps it via a separate env), **and blanks the git credential helper** (`GIT_CONFIG_COUNT/KEY_0/VALUE_0` → `credential.helper=`), so the agent's git has no on-disk keychain/store helper and neither an HTTPS nor an ssh-agent push has a credential source.
  - This is defense-in-depth, not a hard guarantee: a HARD guarantee requires running the agent OS-sandboxed — kagan can opt into a CLI's own sandbox flag but cannot enforce OS isolation. **Residual:** a passphraseless on-disk SSH key remains usable by the agent's git; there is no clean kagan-side neutralisation, so it is documented, not fake-fixed.
- **Opaque agent** — completion is process-exit + git-diff harvest, never stream parsing. The agent's only structured channel is the five MCP report tools (or the `.kagan/ask` JSONL fallback).
- **Bounded & isolated I/O (rule 12)** — failure is contained to its unit and every external process is time-bounded. A malformed `.kagan/ask` report or one bad finding is logged and skipped, never aborting the harvest (hardening **F3**, `_watch_agent`/`_apply_report`). Every spawned subprocess has a wall-clock cap: agent runs via `agent.wait_bounded` (**F1**), git via `git._run_git` timeouts, the mirror's checks, and the `gh` CI read (**F4**, `remote_ci._gh_json`) — a stall degrades to a recorded failure, never a hang. This is what keeps a single runaway or poison input from stranding a task or the session.
- **User's own git identity** for all operations; no kagan persona.

______________________________________________________________________

## 3. Platform: from Textual TUI to an interactive CLI

### 3.1 Why de-TUI

A full-fledged TUI is overkill for a single-operator supervision tool and, worse, *fights the thesis*: an always-on dashboard with live-updating panes is exactly the kind of ambient surface that pulls a supervisor into idle-watching (the slot-machine symptom). The leaner, Apple-influenced answer is a CLI you **invoke when you choose**, that tells you what needs you (or "nothing — go do something else") and **exits**. Calm, deferential, attention-protecting. The re-platform is therefore not just simplification — it is the thesis applied to the tool's own shape.

`click`, `rich`, and `prompt-toolkit` are **already dependencies**; only `textual` is removed. Net: fewer deps, ~3,700 LOC deleted, no new third-party surface area.

### 3.2 The three libraries (composition proven by `references/kimi-cli`)

| Concern                  | Owner                                                                | Why                                                                        |
| ------------------------ | -------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Command dispatch / args  | **Click**                                                            | already the CLI front door (`cli/main.py`)                                 |
| Output rendering         | **Rich**                                                             | tables, panels, markdown, syntax, diffs; reuse existing `format/doctor.py` |
| Interactive input / keys | **prompt-toolkit**                                                   | the only piece with a real keyboard event loop                             |
| Stdout isolation         | prompt-toolkit `patch_stdout`                                        | Rich prints don't corrupt the input line                                   |
| Live-but-quiet status    | status-callback + `invalidate()` (kimi pattern), **not** `rich.Live` | `rich.Live` deadlocks against prompt-toolkit's stdout lock                 |

Rich renders into ANSI strings; prompt-toolkit consumes them as `FormattedText` (kimi's `render_to_ansi`). They never battle for stdout. Reusable kimi patterns to copy (not vendor): `ChoiceInput` (list selection), `ApprovalPromptDelegate` (modal adjudication with numbered options + inline feedback), `render_to_ansi`, `patch_stdout`, a small `StatusSnapshot`.

### 3.3 Interaction model — **one entrypoint, a stateless interactive session**

`kagan` is the only command a human types. It opens an interactive session (prompt-toolkit) on the Inbox navigator; you move through the queue with keys, open a task into its state-appropriate view (intake / review / ship / workspace), act, and quit. New task, stats, and help are in-session actions — not separate commands. No persistent dashboard, no live agent-output stream: the session renders the externalized ledger and exits when you're done.

The slot-machine risk is **not the surface existing** — it is a live variable-reward loop *inside* it (watching tokens stream, hitting regenerate). kagan has none: the agent is opaque (process-exit + diff harvest), so a single calm session that shows **outcomes, not generation** is consistent with the thesis. Leaving is safe because return is notification-backed (§3.5).

**All in-session input renders inside the rounded frame.** Every prompt — the new-task wizard, the comprehension answer, the findings disagree reason, send-back, intake override, approve-all/ship confirms, the needs-you answer — is captured by `prompt_in_frame`/`choose_in_frame`/`confirm_in_frame` (`cli/_interactive.py`), which run the SAME full-screen centered-frame Application as the navigator and draw the live input inside the Rich body (Rich renders, prompt-toolkit only handles keys — §3.2). No prompt drops to a raw line beneath the box. `test_no_in_session_prompt_escapes_the_frame` enforces this structurally. **Deferred exception:** the `kagan init` / `doctor` preflight (`cli/init.py`, `cli/main.py`) runs BEFORE the control-plane session exists, so its `click`/raw prompts break no illusion and stay as-is.

Hidden plumbing (not user entrypoints): `kagan _run <id>` (the detached per-task runner, §3.5) and `kagan mcp` (spawned by the agent's own MCP client). `doctor` runs as preflight on launch.

Rejected, named for the record: **many one-shot verbs** (cognitive sprawl, not a single entrypoint); an **always-on dashboard / Textual TUI** (persistent surface + live panes); a **type-commands REPL** (kimi-style — heavier than a navigate-and-act session needs).

### 3.4 Surface → in-session view map

Everything is reached inside the one `kagan` session — there are no per-surface commands.

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

New module layout (lean; reuse `format/` for Rich, add prompt-toolkit helpers):

- `src/kagan/format/` — pure Rich renderers, each `(Task|list[Task]) -> RenderableType`, unit-tested by rendering to a string: `inbox.py`, `gate.py`, `ship.py`, `workspaces.py`, `intake.py`, `receipt.py`, `stats.py` (+ existing `doctor.py`).
- `src/kagan/cli/_interactive.py` — thin prompt-toolkit helpers: `choose()`, `confirm()`, `text()`, `multiline()`, `adjudicate()` (kimi `ApprovalPromptDelegate` shape). The only place prompt-toolkit is imported.
- `src/kagan/cli/session.py` — the single `kagan` interactive session: an inbox navigator that opens a task into its state view and routes key actions to `Harness`. `new`/`stats`/`help` are in-session actions. The only user entrypoint.
- `src/kagan/cli/_run.py` — hidden detached per-task runner (§3.5). `src/kagan/cli/mcp.py` — the agent-spawned report server. Neither is a user entrypoint.
- **`core/` is untouched by the re-platform.** The Harness/ledger/gate/ship contracts are surface-agnostic.

### 3.5 Detached per-task runner (keeps the UI stateless)

Because the UI exits, the agent run + harvest + validator + gate must finish headless. `kagan` spawns **`kagan _run <id>`** detached (new session — the existing agent-launch pattern): it runs the agent to exit, harvests the diff, runs `VALIDATING` + the gate, writes `REVIEW` to the ledger, and fires **one** OS notification. The interactive session is a pure viewer/actor over the ledger; the doing happens in per-task runners. No daemon — nothing is "always on."

**Hard-kill reconciliation (rule 12).** Because the runner is detached, a kill-9 or reboot mid-run would otherwise strand the task in `RUNNING`/`VALIDATING` forever — no liveness check — eating a lever-5 cap slot and blocking re-run. The runner stamps its own `os.getpid()` onto `Task.runner_pid` as it takes ownership of the `RUNNING` transition (`Harness.start_task`). On every session launch, before the first inbox render, `Harness.reconcile_in_flight()` probes each in-flight task's `runner_pid` with `os.kill(pid, 0)`: a dead pid (`ProcessLookupError`) flags the task `interrupted`, which excludes it from `running_count` (frees the slot) and surfaces it in the inbox as a top-precedence re-runnable signal; a re-run clears the flag and `start_task` finishes cleanly in the same worktree. A live pid is left untouched, and a task that already reached `REVIEW`/`READY` is never reaped. Residual: pid-reuse — a recycled pid could read as alive; pid liveness is primary and the next launch re-checks, so it is accepted, not engineered around.

### 3.6 Storage — in-repo gitignored operational state, committable artifact subset

The operational ledger is gitignored so it never enters commits; only a shareable subset is tracked. As built, the operational store lives **in-repo** at `<git-toplevel>/.kagan/state` (under the blanket-gitignored `.kagan/`), not in an external machine-local directory — see the FUTURE note below.

| What                                                                                                                          | Where (as built)                     | Committed                                    | Why                                                                      |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | -------------------------------------------- | ------------------------------------------------------------------------ |
| `state.json`, `events.jsonl`                                                                                                  | in-repo `.kagan/state/` (gitignored) | no                                           | operational; gitignored so it never enters commits                       |
| worktree/port/pid bookkeeping, cooldown + **fatigue** (l5), **stats** source (l7)                                             | in-repo `.kagan/state/` (gitignored) | no — l5/l7 are **private**                   | machine-local self-mirror; gitignored, must never be committed           |
| `.kagan/repo.yaml` (risk tiers, checks, rubric)                                                                               | in-repo `.kagan/`                    | yes (intended — see gitignore note)          | shared review contract                                                   |
| receipt = decision record (l6): understanding + pinned decisions + findings/verdicts + comprehension + not-covered + diff ref | in-repo `.kagan/reviews/<task>.md`   | yes — **auto-written on approve** (intended) | the cross-team provenance / trust artifact + durable decision log (§3.7) |
| `AGENTS.md` deltas (l8)                                                                                                       | in-repo root                         | yes                                          | compounding org knowledge                                                |

**FUTURE (not built):** an external store at `platformdirs.user_data_dir("kagan")/repos/<repo-key>/`, with `<repo-key>` derived from `git rev-parse --git-common-dir` so worktrees resolve to their parent repo's key. That would make the tool fully stateless toward the working tree (no untracked `.kagan/state/` clutter). Today the operational ledger sits in-repo and gitignored instead; it does not enter commits, but it is untracked clutter in the tree, which the external store would remove. Surfaces mutate only through `Harness` (the single writer), pointed at `default_data_dir()`.

**RESOLVED (committable subset):** kagan scaffolds `<repo>/.kagan/.gitignore` (containing `state/`) when it creates the in-repo ledger, so the committable subset is tracked: `.kagan/state` stays ignored while `.kagan/repo.yaml` and `.kagan/reviews/<task>.md` — which the table marks "yes (intended)" — remain trackable. The scaffold is idempotent and never clobbers a hand-edited `.kagan/.gitignore`; worktree creation likewise appends `.kagan_worktrees/` to the repo-root `.gitignore`. `cli/reset.py` still treats `.kagan/repo.yaml` as the user's own config (not in the kill-list), consistent with it being a committed artifact.

### 3.7 What is shared: durable knowledge, never the live task

A *task* is operational (state, events, worktree, the agent's tool-specific session) — it stays external and is **never** shared; sharing it would resurrect the killed kanban board, smuggle activity-tracking back, and break statelessness (research anti-patterns: anti-cockpit, outcome-not-activity, Isolate/Compress). What IS shared is the task's *distilled knowledge*: the intake spec (understanding + pinned decisions = the WHY), the adjudicated findings + verdicts, the comprehension rationale, and what was **not** covered — written by approve into `.kagan/reviews/<task>.md`.

This is what the research calls for and what tool-specific session files lose: spec-as-durable-artifact (Spec Kit), Write-to-disk external memory + AGENTS.md (35–55% fewer agent bugs, 86% less drift), compound org knowledge (the factory retro), and comprehension as institutional memory against the trust-incompetence spiral.

Two hard rules:

- **Distill, never archive.** The agent's raw transcript is NOT persisted — it is noise (context-rot research: distill to ~1–2k tokens of findings, not raw context) and a **security hazard** (transcripts carry secrets/paths/tokens; auto-committing them is a leak). An optional one-line breadcrumb in the receipt (`agent: claude · session: <local path>`) makes the transcript *findable while it lives*, not committed.
- **No index, no DB.** `.kagan/reviews/` becomes the repo's **decision log / institutional memory** — tool-agnostic, surviving people and vanished sessions. Retrieval is `grep`/`rg` over the folder (research: agentic grep beats vector RAG, 97% fewer tokens). This closes a loop: a new task's intake can grep prior reviews for related decisions, so each shipped task makes the next intake better — the compound-knowledge loop (lever 8) extended from `AGENTS.md` to the full decision history.

A teammate who pulls the repo reads `.kagan/reviews/` as **read-only provenance + searchable history**; their own operational store is empty, so they audit the author's adjudication instead of re-deriving trust (lever 6).

**Receipt = light decision record.** Format is an ADR spine — **Context / Decision / Consequences / Status** (Proposed→Accepted→Superseded) — kept light (skip full options/criteria/citations except for genuinely architectural tasks). When a later task changes an earlier decision, its record **supersedes** the earlier one (a link, not a delete), so `.kagan/reviews/` is a navigable decision history, not a pile. Content is built with a **distillation heuristic** (from kipp `/handoff`): KEEP decisions+rationale, the *working* solution (not the journey), config choices, constraints discovered, open questions, files changed; DROP corrections/retries, verbose tool output, permission prompts, settled back-and-forth, boilerplate.

**Abandoned/sent-back tasks leave a one-line "productive dead end"** (kipp `/handoff`): *what was tried, why it failed, what it constrains* — so the log captures negative knowledge ("tried X, abandoned because Y") at near-zero noise, not only shipped work.

**Send-back delivers the verdict to the re-run agent.** When the human sends a task back, the re-run prompt (`core/agent._run_prompt` via `_sendback_section`) carries: the reviewer's send-back note (the directive, a `source="sendback"` finding), the findings the human **upheld** (verdict `agree` → "fix these"), and the ones the human **overruled** (verdict `disagree` → "leave as-is", with the reviewer's reason). Without this the re-run agent is blind to the adjudication and just rebuilds the same diff. Lists are capped (`_MAX_RERUN_FINDINGS`) to bound prompt size.

**In-flight tasks get a session-boundary handoff** (borrowed from "The Six"): when a run pauses or a session ends mid-task, kagan writes a short human-curated re-anchor summary — never the raw transcript (distill-never-archive still holds) — so a resumed task starts from intent, not a cold context. This is the report's "Write" operation at the session edge.

### 3.8 Patterns adopted from kipp (`/Users/aorumbayev/repos/MakerX/kipp`)

kipp is a mature Claude-skills library covering kagan's domain (`/review`, `/build`, `/security`, `/git`, `/handoff`, `/adr`). Adopted:

- **Agree-bar as comprehension test** (`/review`): a finding may be marked *agree* only if the human can state the defect in their own words AND would file it unprompted at the same severity. This is lever 1 applied per-finding. A **Pushback section is always rendered** in the receipt (disagreed findings + one-line reason, even when empty) — a static, greppable trust signal. → levers 1, 6.
- **Enriched finding schema** (`/review`, `/security`): `Finding` gains **confidence (0–10)**, **status** (VERIFIED/UNVERIFIED/TENTATIVE), and a **mandatory failure-path** (no speculative findings — state the concrete exploit/break). The confidence gate is **risk-routed**: low-risk surfaces only ≥8; high-risk surfaces tentative (≥2). → levers 2, 3, 4.
- **Per-finding independent verify + variant sweep** (`/security`): the validator verifies each finding via a sub-agent that reads only that location (score 1–10, discard below gate), then greps for sibling instances of a verified pattern. → lever 2 algorithm.
- **5-section comprehension scaffold** (`/build explain`): postcondition / delta / dependencies / security implications / gotchas — the *structure* of the comprehension prompts, but **human-authored** (kipp's is agent-generated; our thesis needs the human articulating, else it is the rubber-stamp the gate exists to prevent). → lever 1.
- **Hard-gate whitelist + soft-gate-auto + transparency banner** (`/git`, `/maintain`): a whitelist of confirmations that risk routing can never auto-resolve (irreversible/high-risk), vs soft gates auto-advanced with a logged note; refusal path = skip + log + continue, never abort. The receipt states the ceremony applied ("reviewed at: high-risk — validator + security + 2nd approver"). → lever 4, receipt.
- **Re-invocation hygiene** (cross-cutting): every `kagan` invocation re-probes state from the ledger (in-repo `.kagan/state`, gitignored — §3.6), treats any in-session draft as stale, discards caches — the disciplined form of the stateless model. → §3.3/§3.6.

**Deliberately NOT adopted** (over-engineering for a tool that already has `repo.yaml` + risk tiers): kipp's Decision-Guide Q1–Q7 preference lifecycle, per-repo optimisation caching, signal-cue routing, and fork/inline governance. The sub-agent contract (self-contained prompt, ≤1KB schema'd response) is kept as a Phase-2 *implementation* note, not a design decision.

### 3.9 Independent review of an external idea set ("The Six")

A separate brainstorm proposed six convention-first mechanisms; an independent researcher evaluated them against the report. Net: kagan is already the synthesis the evidence points to — **committed plain-text artifacts (conventions, high-spread) wrapped by thin un-bypassable enforcement gates** — so the right move is to lean the enforcement layer *thinner and more agent-CLI-agnostic*, NOT to reframe kagan as pure conventions. The report's core finding is that *unenforced* friction gets bypassed under deadline (governance Level 2 "policy not enforced" vs Level 4 "automated enforcement"; the delta is "a thing that refuses" — which is what kagan's gates are).

- **Adopted:** the structural-debt signal (now **lever 9** — the one genuine gap it exposed); a session-boundary handoff for in-flight tasks (§3.7).
- **Rejected, for the record** (so they don't creep back): **TRAPDOOR** (a planted-lie comprehension tripwire — the AI removes its own lie, a dev bypasses with one `grep`, it trains the wrong reflex; lever 1's articulate-it-yourself is the evidence-backed version); the **per-agent-territory / multi-agent** manifest (contradicts the single-agent default — CooperBench 2-agent 25% vs 50% solo); **fabricated productivity numbers** (an individual "actual delta −14% METR-adjusted" is statistically indefensible — METR is a population RCT with CI −15%/+9%; surface only *measured* proxies); and the **session ritual** (closing poem, gaze-pause — theater with no cultural authority; the report says culture beats tool-policy; keep only the cap/cooldown, already lever 5).

______________________________________________________________________

## 4. The levers (evidence → mechanism → seam)

Each lever builds on existing core seams; surfaces are the new CLI. Risk tier (lever 4) is the spine that keeps levers 1–3 *proportionate*.

### 1. Comprehension gate — a third structural lock (FIRST after re-platform)

- **Evidence:** mode decides outcome; delegators \<40%. Today `can_approve` (`core/tasks.py:142`) checks only that blocking findings carry a verdict — a human can rubber-stamp with zero comprehension.
- **Mechanism:** approve stays locked until the human records, in their own words, a "why correct / what could break" for the diff and a resolution note per blocking finding. Empty/templated/trivial = lock holds (mirrors the mutation-probe philosophy: the gate must be *able* to fail). The scaffold depth is **risk-scaled** (kipp `/build explain` 5-section structure): low-risk = one line; medium = postcondition + what-could-break; high = the full five (postcondition / delta / dependencies / security / gotchas). Never five paragraphs to approve a typo. Phase 1 ships the self-authored form (no agent). Lever 2 upgrades it: the validator generates adversarial prompts on the riskiest hunks the rationale must address.
- **Cross-team:** the rationale travels in the receipt (lever 6) — a reviewer sees *why* the author believed it correct.
- **Seam:** `core/models.py` (`Task.comprehension`, `Finding.resolution_note`), `core/tasks.py:142` (`can_approve` + new `record_comprehension`), `core/receipt.py` (new section), `cli/review.py` + `format/gate.py` (the prompt + render).
- **Breaking?** Additive model fields; changes the approve precondition. Low.

### 2. Adversarial validator stage — resurrect the dead `VALIDATING` state

- **Evidence:** builder+validator with *different* models beats single-agent self-review (context collapse). `VALIDATING` is declared (`core/enums.py:16`) but never assigned — harvest goes `RUNNING`→`REVIEW` directly (`core/harness.py:222`). A real empty slot.
- **Mechanism:** between harvest and the human gate, spawn one validator agent (**a fresh, separate spawn that never sees the builder's session** — read-only worktree, adversarial ruleset, model set in `repo.yaml` via `reviewer:`). The anti-bias guarantee is the *fresh separate context*, not vendor identity: a different model is **recommended, not required** — `reviewer == builder` is allowed, and the same model at a different size (e.g. opus builder, haiku reviewer) is a valid one-vendor setup, so kagan never forces a second paid tool. It emits blocking/question `Finding`s; merge with GateEngine findings; human still adjudicates all. One validator only (Princeton: single agent matches multi on 64% at half cost). Also generates lever 1's prompts. (No effort/thinking knob: recipes carry no effort flag, so it would be an unenforceable hollow config — model *size* via the `reviewer` string is the supported axis.)
- **Seam:** `core/enums.py` + `core/harness.py:222` (`RUNNING`→`VALIDATING`→`REVIEW`), `core/gate.py` (merge; add `Finding.source`), `core/config.py` (`builder`/`reviewer` model fields in `RepoConfig`), `core/agent.py` + `core/recipes.py` (read-only validator recipe + model override), `format/workspaces.py` (show "reviewing…").
- **Breaking?** Real state-machine change + a second agent invocation. Medium; gated by risk tier so low-risk skips it.
- **Fail-safe (hardening F2):** the validator is an enhancement, never the floor. If `launch_validate` crashes (raises) OR exits unclean / hits the F1 wall-clock cap (`ok=False`), `run_validation` does NOT strand the task in `VALIDATING` — it records a non-blocking `ai-review` finding ("validator did not complete — reviewed unaided"), sets `Task.validator_outcome="failed"`, and lets `run_gate` carry the task to `REVIEW` for unaided human review (the research baseline; human-alone ≫ AI-alone). Crucially the receipt's ceremony banner reads `validator_outcome` and appends "(validator unavailable — reviewed unaided)" — a failed/timed-out validator must never read as one that ran (false provenance is worse than an honest gap — the trust-incompetence spiral). `validator_outcome` is `None` when the stage is not applicable (low risk / no `reviewer:` / no worktree).

### 3. Security gate, risk-routed

- **Evidence:** 45% OWASP rate, flat across models; tests can't catch it. Today the only security check is a filename-regex secrets scan (`core/gate.py:21`).
- **Mechanism:** a first-class `security` check — repo declares a SAST command (semgrep/bandit/CodeQL) in `repo.yaml`; **blocking on high-risk scope, advisory elsewhere**. Pair with an adversarial security pass in the validator for the deep flaws SAST misses (authz, privilege paths — the +153%/+322% categories).
- **Seam:** `core/config.py` (RepoConfig `security` + risk tiers), `core/gate.py`, `core/mirror.py` (already runs declared checks).
- **Breaking?** `repo.yaml` schema addition (additive). Low.

### 4. Risk routing — the autonomy ladder, operationalized (the spine)

- **Evidence:** risk-routed autonomy; irreversible = human. Today every task gets identical ceremony.
- **Mechanism:** `repo.yaml` declares risk tiers by path glob (`src/auth/** = high`, `docs/** = low`); intake classifies a task's tier from `scope`. Tier sets ceremony — **low:** machine checks + fast approve; **medium:** + validator; **high/irreversible** (auth, payments, migrations, schema, public API): validator + security + full comprehension + (cross-team) second approver, no auto-advance.
- **Seam:** `core/config.py`, `core/models.py` (`Task.risk`), `core/harness.py` (intake), `core/tasks.py` (`can_approve` consults tier), `core/inbox.py` (tier can lift precedence).
- **Breaking?** Touches intake + approve preconditions; default tier = medium so unconfigured repos behave like today. Medium.

### 5. Supervisor protection — anti-slot-machine

- **Evidence:** the doc's explicit mandate. Parallel-agent cliff after 3 (cap 2); mandatory wait between generation and commit breaks VRR; 3–4h/day ceiling; cultural signal beats policy.
- **Mechanism:** (a) hard cap of 2 concurrent in-flight tasks (`RUNNING`/`VALIDATING`, configurable), enforced in `start_task` before any worktree/launch side effect (raises `AgentCapError`); (b) a short mandatory cooldown after a task lands in REVIEW before approve unlocks (forces a real read) — a SEPARATE, time-injectable `approve_cooldown_remaining(task_id, now)` derived from the RUNNING/VALIDATING→REVIEW event timestamp, kept OUT of `can_approve` so the comprehension/findings lock stays pure and deterministic; (c) a *private* coach line on after-hours/weekend sessions ("it is after hours — the queue keeps") plus a gentle recent-approval-burst nudge, both derived at render time. Signals, not blocks; never persisted, never a team metric. The single outcome-not-generation session (§3.3) is itself the largest anti-slot-machine move. DEFER: a precise cumulative-session-duration timer needs the FUTURE external machine-local store (§3.6 l5 fatigue; today the l5/l7 state sits in the gitignored in-repo ledger); after-hours + recent-activity stand in until it exists.
- **Seam:** `core/harness.py` (`start_task` cap + `can_start_agent`/`running_count` + `approve_cooldown_remaining`), `core/inbox.py` (`after_hours_note`/`throughput_note` coach), `core/config.py` (`max_concurrent_agents`/`approve_cooldown_seconds` knobs), `core/errors.py` (`AgentCapError`), `cli/session.py` (surface catches the cap + checks the cooldown on approve).
- **Breaking?** Behavioral; knobs default-on (cap=2, cooldown=60), tunable. Low-medium.
- **Bounded execution (hardening F1):** `agent_timeout_seconds` (repo.yaml, default 1800 = 30 min, generous so a legit long run is never sabotaged; `0` disables) caps every single agent run — builder, intake, validator — via `agent.wait_bounded` (`asyncio.wait_for`→`terminate` the process group). This is the research's circuit-breaker / unbounded-loop guard, and it also lets `reconcile_in_flight` reap a runaway: a hung agent's pid would otherwise read as *alive* forever, stranding the task. A builder timeout still **harvests the partial diff** and lands in `REVIEW` with a blocking finding ("Agent exceeded Nm — review the partial diff, then re-run to continue in the same worktree"); downside capped, work never discarded, re-run resumes idempotently in place. **Scoped out, deliberately:** a cross-task consecutive-failure breaker — kagan spawns the runner *detached* (`kagan _run`), so an in-memory counter can't accumulate across tasks, and launches are human-gated one-at-a-time (the human sees task 1 fail before launching task 2), making an auto-breaker speculative complexity (YAGNI) until there is evidence of churn.

### 6. Provenance receipt → PR body + multi-approver (cross-team)

- **Evidence:** trust tax; team-level dynamics is an industry open gap. The receipt (`core/receipt.py`) already states what was/wasn't verified.
- **Mechanism:** the receipt becomes the cross-team trust artifact — add comprehension (l1), validator-source provenance (l2), security verdicts (l3); kagan emits a PR-body-ready block the human pastes (still never pushes). A teammate **audits the author's adjudication instead of re-deriving trust**. High-risk requires a second human approver.
- **Seam:** `core/receipt.py` (sections + PR-body variant), `core/ship.py` (surface at approve), `core/models.py` (`approvers`, second-approver lock).
- **Breaking?** Additive; multi-approver only on high-risk. Low.

### 7. Outcome scorecard — `kagan stats`

- **Evidence:** measure durability/CFR/cycle-time, not activity (an explicit open gap). Kagan has the data (`events.jsonl`, the CI tripwire) but computes nothing.
- **Mechanism:** `kagan stats` reads ledger + `git log` → **durability** (approved files surviving 14/30d unreverted), **CFR** (post-PR CI-fail via tripwire), **cycle time** (intake→ready). Stdlib + git, no DB. A **private self-calibration mirror**, never a team productivity metric.
- **Prereq fix:** `remote_pr_url` is never written today, so the tripwire is inert — capture it at `mark_pushed`.
- **Seam:** `cli/stats.py` + `format/stats.py`, `core/ledger.py` (read), `core/ship.py` (`mark_pushed` writes `remote_pr_url`), `core/remote_ci.py`.
- **Breaking?** New command + one field. None to existing flows.

### 8. Retro / compound-knowledge loop

- **Evidence:** AGENTS.md cuts agent bugs 35–55%, drift 86%; ACE *delta* updates prevent collapse; the factory retro converts session learning into org knowledge.
- **Mechanism:** on approve, offer to append the task's learnings (resolved decisions, drift causes, recurring finding patterns) to the repo's `AGENTS.md` as a delta. Human confirms; kagan never edits silently.
- **Seam:** `core/ship.py` (offer at approve), `core/reports.py` (aggregates), new `core/retro.py` (delta append).
- **Breaking?** Additive, opt-in. None.

### 9. Structural debt budget — the blind spot the independent review exposed

- **Evidence:** kagan's levers verify *this diff* (correct/secure/understood) but are blind to *the codebase rotting across diffs* — the report's best-documented, *permanent* harm. CMU (807 repos): complexity +40%, static-analysis warnings +30%, velocity gains transient while complexity gains permanent ("3x complexity fully cancels the velocity boost"). GitClear: duplication 10x, refactoring share 24.1%→9.5%, churn 3.1%→7.1%. Lever 7 tracks durability/CFR — but a repo can have high durability and clean CI while structurally rotting. The report lists this as an urgent open gap.
- **Mechanism:** compute a per-scope **debt delta** from real tools only — cyclomatic/cognitive complexity + duplication + coupling (the SAST/`git` signals the report names) — with **no hand-rolled "novelty" term** (gaming it pushes toward boilerplate, the GitClear pathology). Surface it as a tracked number in `kagan stats` (l7) and let a rising debt delta on a scope **escalate that scope's risk tier** (l4) — a rotting area routes itself into heavier review. **Not a hard block, no self-serve override** (the independent review judged a one-flag escape would go reflexive under deadline — the friction-that-gets-bypassed finding). Debt routes through the human gate kagan already has; it never refuses generation.
- **Seam:** new `core/debt.py` (compute delta from SAST + `git`, reusing the mirror's check-runner), `cli/stats.py` + `format/stats.py` (surface), `core/config.py` (per-scope threshold → tier escalation), `core/tasks.py` / `core/harness.py` (apply escalation at intake/gate).
- **Breaking?** Additive metric + a new risk-tier input; no DB (computed over `git` + SAST per the no-database invariant). Low.
- **Real exposure, not a proxy (hardening M1):** the cross-diff scope signal now reads `Task.changed_files` — the actual harvested changed-file set (run-artifacts stripped, capped at 500), persisted in `_harvest`. The earlier proxy used *finding locations*, which read **zero** for a churning scope that generated no findings (the turkey problem — absence of findings ≠ absence of churn), silently defeating the escalation. Legacy tasks with no `changed_files` fall back to finding locations (graceful migration). The same field also widens lever-7 durability, which previously skipped any task with no findings.

______________________________________________________________________

## 5. Screens — views within the single `kagan` session

These are **not** separate commands — they are views the one `kagan` session moves between (inbox → task → act → back). `[render]` marks Rich output, `[prompt]` marks a prompt-toolkit interaction. (Sub-headers below still read `kagan review <id>` etc. from the earlier draft; treat them as "the review view" — to be relabelled on the next pass.)

Design language (Apple HIG, applied to a CLI): **clarity** (one job per command; plain sentences; a 5-symbol set — `●` needs you · `▸` in review · `✓` done/passed · `✗` blocker · `○` optional; risk is a quiet word, only `high` emphasized); **deference** (work is the content; hairline rules + whitespace, no boxes, dim right-aligned metadata); **depth** (progressive disclosure — summaries you step into); **calm over cockpit** (state in one sentence, quiet by default, invoke-and-exit); **one primary action** that states its own readiness. Annotations: `[render]` = Rich one-shot, `[prompt]` = prompt-toolkit interaction.

### `kagan` — Inbox, quiet default `[render]` (an empty queue is the brand)

```
  kagan · myrepo                                                      all quiet

  Nothing needs you right now.

  2 agents working · last shipped 1h ago

  ───────────────────────────────────────────────────────────────────────────
  n new · enter open a task · w workspaces · S stats · ? help · q quit
```

(No "next check ~5m" clause — kagan is invoke-and-exit with no background poll
timer; the standing line states what is running and when the queue last shipped,
both cheaply derived from the ledger on each render. "last shipped" is dropped
when nothing has ever shipped.)

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

### `kagan` → needs-you `[prompt]` (a mid-run question that gates a running agent)

The highest-stakes "unblock the agent" decision gets the standard chrome: the `●`
needs-you glyph, the shared header with risk context, and a footer. The answer is a
multi-line prompt (ctrl-o opens `$EDITOR`); an empty/cancelled answer leaves the task
waiting (a fail-loud "still waiting" line), a real answer echoes back with its
consequence ("… will continue"). The agent is blocked on this — it is not optional.

```
  migrate-billing                                                       high risk

  waiting · ambiguous currency assumption
  ●  Which currency rounding? — banker's, half-up, or ask finance?
     the invoice builder calls round() with no mode; the agent paused rather than guess

  > ▏
  ───────────────────────────────────────────────────────────────────────────
  enter submit · ctrl-o editor · esc leave it waiting
```

### `kagan review <id>` — readiness checklist `[prompt]` (the screen IS a to-do that unlocks approve)

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
  ↑↓ / j k move · enter open · a approve · c comprehension · s send back
  f findings · v smoke · r re-validate · q back
```

(`f` opens the findings walk — a single opener; `g`/`d` are agree/disagree ONLY
inside that walk, not duplicated at review level. The comprehension answer is a
single-line prompt — Enter submits and advances to the next prompt — with the
changed-file list shown above the questions so "what does this change do" is
answerable in place.)

`●` blocks approve, `✓` satisfied, `○` optional. The lock block is persistent — it names every unmet approve condition (findings, comprehension, cooldown, high-risk approver) instead of printing a transient refusal only when `a` is pressed.

### `kagan review <id>` → Findings `[prompt]` (focused walk; g/d act on the focused finding)

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

`j`/`k` move the cursor over open findings; `g` agrees the focused one, `d` disagrees and prompts for a reason. The footer echoes the focused finding's location and severity.

### `kagan review <id>` → Smoke `[prompt]` (one focused test verified at a time)

```
  Smoke tests
  › ○  health check passes
    ○  api up  (:51802)

  ───────────────────────────────────────────────────────────────────────────
  ↑↓ / j k move · v verify · q back
```

`v` verifies only the focused smoke test, not every unverified test at once.

### `kagan review <id>` → Comprehension `[prompt]` (a note, not a quiz)

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

### `kagan review <id>` → high risk `[prompt]` (security blocker + second approver folded into the checklist)

```
  migrate-billing                                        kagan/task-9d4e → main
  high risk · irreversible — touches billing & migrations

     ●  Adjudicate 1 security blocker
     ●  Answer 3 comprehension prompts             (required at this risk)
     ✓  Checks passed · 9 of 9
     ●  Second approver — high-risk can't be approved alone
           approved by none yet · waiting for one more
```

### `kagan workspaces` `[render]` (`--watch` for a quiet refresh)

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

Service health is plain dim text, not a glyph — `●` stays needs-you only (§3.1). The
log is a dim teaser (the last few lines, each truncated to width), never a 200-line
dump that pushes the take-over hand-off off-screen; the full log is the take-over step.
The cooldown nudge is threaded from `view_workspaces` (it computes
`approve_cooldown_remaining` for a just-landed REVIEW task and passes it as the detail's
`cooldown_note`) — the screen's contribution to the attention thesis, previously dropped.

### `kagan intake <id>` `[prompt]` (risk stated once; decision walk)

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

> **Terminology:** a surfaced decision is **Approved** (accept the agent's assumption) or **Rejected** (override it with the correct answer) — this replaces kagan's old "bless". Implementation: rename `Decision.blessed` → `approved` and add an explicit reject-with-answer path. The task-level gate verb stays **Approve** / **Send back**; finding verdicts stay **agree** / **disagree** (different axes, kept distinct).

The decision walk is a real walk: `↑↓` / `j k` move a focus cursor (the `›`) and
`a` / `x` act on the FOCUSED decision (not always the first), with the frame updating
in place rather than stacking a panel per keypress. `A` approve-all is gated behind a
confirm naming the count + risk and is REFUSED outright at high/irreversible risk
(parity with review's no-skip) — it must never be a one-key bypass of the gate intake
exists to be.

### `kagan ship <id>` `[render]` + copy `[prompt]` (next-step first)

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

The retro affordance (`l`) renders only when `propose_retro()` returns a learning —
the lever-8 loop closes HERE, on the ship screen, not as a transient approve-time
prompt the user blows past. A successful copy persists in the rendered frame as
`[c ✓ copied]` (not a print that scrolls off). "kagan never pushes" is a dim trailing
clause, not an anxious action header. When the receipt digest is hollow (nothing
machine-verified or adjudicated) a dim line says so: "This receipt is thin — nothing
was machine-verified or adjudicated." Pressing enter does NOT auto-push — it confirms,
then cheaply VERIFIES the branch is on origin (`git ls-remote --heads origin <branch>`,
read-only) before flipping to `pr_open`: branch absent → "branch not found on origin —
did you push?"; gh/network unavailable → "marking as pushed (could not verify)".

### `kagan new` `[prompt]` (sequential fields, then a confirm gate that shows the risk)

The session collects title → scope → agent as three sequential prompts — all
captured **in-frame** (`prompt_in_frame`/`choose_in_frame`), never raw lines below
the box — then renders the form ONCE as a **confirm gate before any task is
created** (also in-frame via `confirm_in_frame`, with the form as its body): the
computed risk-from-scope (lever 4) and the launch/queue line are shown, and
`create_task → run_intake` runs only on confirm. Cancelling at the gate aborts
loudly ("Cancelled — no task created.") — no task is written. An empty title, an
esc on the scope field, or a cancelled agent pick aborts the same way, each with
its own fail-loud line. (A single live form that re-renders risk per keystroke is
intentionally NOT built; the risk is surfaced at the gate, which is where it gates
the commit.)

**Scope is explained in-frame** (first-time users find it opaque): the Scope prompt
draws a dim help block — *"the paths the agent may edit (e.g. `src/auth/**`); edits
outside flag as drift, and scope sets the review tier; blank = the whole repo."* —
so the field never needs the docs. This is the product bar: intuitive at every step.

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

### `kagan stats` `[render]` (calm private mirror — sentences, not anxious bars)

```
  myrepo · 14 shipped in 30 days                                     just for you

  Durability       11 of 14 still untouched after two weeks
  Clean merges     12 of 14 passed CI after opening
  Comprehension     9 of 14 answered first try · 2 notes were thin

  Cycle time       low 40m   ·   med 3h   ·   high 1d

  You supervised 18h across 22 sessions, 2 after hours.
  The most durable work wasn't the longest day — it was the read-before-approve.
```

The scorecard IS this screen — the operational per-state tally is NOT stacked here
(it is a cockpit reading, not the calm mirror). A brand-new repo (nothing shipped, no
signals) shows one calm line instead of five dashes: "Too new to mirror yet — ship a
few tasks and this fills in." The closing read-before-approve line always trails. The
supervision-hours reflection is derived from the private coach data; a precise
cumulative-hours timer needs the deferred machine-local session store (lever 5 TODO),
so today the line is the after-hours signal, not a fabricated hour count.

### `kagan doctor` `[render]` (preflight)

```
  ✓ git repository    found at /usr/bin/git
  ✓ python 3.14       Python 3.14
  ✓ coding agent      found: codex, claude
  ⚠ github cli        GitHub CLI not found (optional, for PR workflows)
      Install gh: https://cli.github.com
  ✓ repo config       valid manifest (3 service(s), …)

  Usable — 1 warning(s).
```

`kagan doctor` (default) reuses this calm preflight — ONE visual language for the same
data; the box/table form is `--verbosity technical` (raw check names, full diagnostic).
Labels are calm sentences ("git repository", "python 3.14"), the raw name reserved for
technical. The dimmed `fix_hint` sits under each fail/warn line — the moment the user
needs it — never under a passing check. The launch preflight renders on ANY non-pass
(warn too), so degraded-mode warnings are visible; the blocking "Continue anyway?"
confirm gates ONLY on a hard fail. When the SOLE hard fail is a missing manifest and we
are in a git repo, the launch offers `kagan init` instead (declining exits rather than
dropping into a manifestless session). A **branch-protection** check (shown only when
`gh` and a remote exist) probes whether the base branch requires reviews on the remote —
WARN-not-FAIL, since kagan gates locally but cannot own the remote wall.

______________________________________________________________________

## 6. Industry open gaps kagan can lead on

Unsolved in the literature; the levers make kagan a first-mover and a research instrument (bets, not claims): **comprehension-debt metric** (none validated — l1 rationale + l2 scored prompts produce a proxy + the data); **verification-aware productivity metrics** (l7's durability/CFR ledger is the instrument); **team trust protocol** (l6's provenance receipt is a testable intervention); **governance for hours-long autonomy** (l4+l5 risk tiers + caps are a falsifiable proposal).

______________________________________________________________________

## 7. Roadmap

### Phase 0 — Re-platform & doc reset (PREREQUISITE)

The rip-out and the new skeleton. Independently shippable; no behavior change beyond surface.

**0a. Remove Textual (code + config + tests).**

- Delete `src/kagan/tui/` entirely (app.py, keybindings.py, theme.py, `screens/` ×10, `widgets/` ×4, `styles/*.tcss` ×4).
- Delete `tests/kagan/tui/` (19 files incl. `widgets/`, `smoke/`, `__snapshots__/*.svg`) and `tests/helpers/snapshot.py`.
- `pyproject.toml`: drop `textual` dep + `"textual"` keyword; drop ruff ignores `RUF012`/`SIM117` (Textual-only); replace poe `dev` (`python -m textual run …`) with `kagan` runner; remove `snapshot-update` task; remove `tui`/`tui_chat`/`tui_shell` pytest markers. Refresh `uv.lock`.
- `tests/conftest.py`: remove the `TEXTUAL_ANIMATIONS` line and the xdist TUI-grouping logic.

**0b. Build the CLI surface layer** (`format/` Rich renderers + `cli/_interactive.py` prompt-toolkit helpers + Click commands per §3.4). Reuse `format/doctor.py`. Copy kimi patterns (`ChoiceInput`, `ApprovalPromptDelegate`, `render_to_ansi`, `patch_stdout`, `StatusSnapshot`) — adapted, not vendored. `core/` untouched.

**0c. Rewire entry.** Rewrite `cli/main.py` so bare `kagan` renders the Inbox once (not `app.run()`); replace `cli/tui.py` with the new commands; keep the `doctor` preflight.

**0d. Docs reset.** Delete `docs/internal/plans/` (19), `docs/internal/adrs/` (2 — decisions preserved in §2 here), `docs/internal/architecture.md`. Rewrite `specs/tui.md`→`specs/cli.md` (TUI-\* → CLI-\* IDs, retarget to the CLI model) and `tui-stories.md`→`cli-stories.md`; keep `specs/mcp.md`/`mcp-stories.md` (de-TUI the intro only). Scrub every "TUI"/"Textual"/"Kanban TUI" mention repo-wide (README lines 5/34/75; any `docs/` reference).

**0e. Persist this document** to `docs/internal/DESIGN.md` as the canonical single source.

Files: `pyproject.toml`, `tests/conftest.py`, `src/kagan/cli/*`, new `src/kagan/format/*`, new `src/kagan/cli/_interactive.py`, `README.md`, `docs/internal/**`.

### Phase 1 — Comprehension gate (lever 1), self-authored form. `core/models.py`, `core/tasks.py`, `core/receipt.py`, `cli/review.py`, `format/gate.py`.

### Phase 2 — Adversarial validator stage (lever 2). Resurrect `VALIDATING`; upgrades the comprehension gate to prompt-driven. `core/enums.py`, `core/harness.py`, `core/gate.py`, `core/agent.py`, `core/recipes.py`.

### Phase 3 — Risk routing + security gate (levers 3+4). The spine; makes 1–2 proportionate. `core/config.py`, `core/models.py`, `core/gate.py`, `core/harness.py`, `core/tasks.py`.

### Phase 4 — Supervisor protection (lever 5). `core/harness.py` (cap + cooldown), `core/inbox.py` (private coach), `core/config.py` (knobs), `core/errors.py` (`AgentCapError`), `cli/session.py` (surface). Cooldown is a separate `approve_cooldown_remaining`, NOT in `can_approve` (kept pure).

### Phase 5 — Provenance receipt → PR body + multi-approver (lever 6). `core/receipt.py`, `core/ship.py`, `core/models.py`.

### Phase 6 — Outcome scorecard + retro (levers 7+8). `cli/stats.py`, `format/stats.py`, `core/retro.py`, `core/ship.py`, `core/remote_ci.py`.

### Phase 7 — Structural debt budget (lever 9). `core/debt.py`, `cli/stats.py`, `format/stats.py`, `core/config.py`, `core/tasks.py`.

### Phase 14 — `kagan init` onboarding + branch-protection doctor probe. `cli/init.py`, `core/onboard.py`, `format/onboard.py`, `core/agent.py` (`launch_manifest_draft`), `core/doctor_checks.py`, `cli/main.py`.

Aids the kagan-specific setup the doctor only *named* before (the hand-written manifest), leaving tool-level setup (git/agent CLI/auth/gh) to the developer. An available agent CLI PROPOSES `.kagan/repo.yaml` read-only (the same sandbox intake uses, reporting a `manifest` envelope via `.kagan/ask`); the human reads and approves each command BEFORE anything runs (a `flag_dangerous` string-scan forces a second confirm on destructive shapes), an opt-in pass verifies the approved commands actually run (reuses `mirror.run_mirror`), and the result is written through `RepoConfig` validation so init can never write a manifest the loader rejects. No agent / declined / empty draft falls to a deterministic commented skeleton — incompleteness degrades, never blocks. Because kagan needs a git repo (per-task worktrees fork from a HEAD), onboarding outside one OFFERS to bootstrap it (git init + a project-agnostic `.gitignore` + an initial commit, defaulting yes) and BLOCKS if declined rather than proceeding into an unusable state. The draft is sanitized at parse (unknown risk tiers dropped, duplicate check names collapsed first-wins, services validated, scalars coerced) so a flaky proposal can't strand the human's approval work. Only WALKED executables (`checks`) and DECLARATIVE fields (risk tiers, builder/reviewer models) are committed; `security` and `services.command` also execute later but are NOT walked, so — via negativa, rather than adding more approval ceremony that would train rubber-stamping — kagan does not auto-write them and surfaces them as paste-ready suggestions the user adds by a deliberate hand-edit. The trust boundary is the human gate, not the agent; `.kagan/repo.yaml` stays a `PROTECTED_PATH` so an agent can't silently rewrite the contract afterwards. Bare `kagan` in a git repo with no manifest offers `init` instead of the generic "continue anyway". The branch-protection probe (`gh api …/branches/{base}/protection`) makes governance level 4 visible — WARN-not-FAIL, since only the remote can actually enforce the wall (DESIGN never-push reframe).

Each phase updates the `specs/cli.md`/`mcp.md` requirements and this doc in the same change (docs-internal is source of truth).

______________________________________________________________________

## 8. Verification

Per phase the existing bar stays green: `uv run poe lint`, `pyrefly`, `import-linter`, the LOC-budget and test-quality linters, and `uv run pytest tests/`. The re-platform **simplifies testing**: Pilot/snapshot tests are gone; surfaces are now (a) pure renderers tested by rendering a seeded `Task` to a string and asserting content, and (b) interactive flows tested by calling the flow function with scripted inputs (prompt-toolkit supports piped input / `app.run` with a test input). No event-loop simulation, no SVG baselines.

- **Phase 0:** `uv run pytest tests/` green with zero `textual` imports remaining (grep asserts none); bare `kagan` renders the Inbox; `kagan review/intake/ship/workspaces/new/doctor` work end-to-end against the fake agent; no `.tcss`/snapshot artifacts remain; `docs/internal/DESIGN.md` exists; no "TUI"/"Textual" strings remain in `docs/` or `README.md`.
- **Lever 1:** `can_approve` stays `False` with blocking findings verdicted but comprehension empty/trivial; flips `True` only with a real rationale (encodes *why*: the gate must be able to fail).
- **Lever 2:** a fake validator emits a finding; assert `RUNNING`→`VALIDATING`→`REVIEW` runs it and merges with a distinct `source`.
- **Lever 3:** a planted vuln trips `security` blocking on high-risk scope, advisory on low.
- **Lever 4:** scope under a `high` glob classifies high and demands the full ceremony; a `docs/**` task auto-satisfies comprehension.
- **Lever 5:** launching a 3rd concurrent task is refused; approve is locked during cooldown.
- **Lever 6:** the receipt PR-body block carries all provenance sections; a high-risk task needs two distinct approvers.
- **Lever 7:** `kagan stats` on a seeded ledger reports correct durability/CFR/cycle-time; `remote_pr_url` is populated post-`mark_pushed`.
- **Lever 8:** approve offers an AGENTS.md delta; confirming appends (never silently), declining is a no-op.
- **Lever 9:** a scope with a rising complexity/duplication delta escalates its risk tier and shows in `kagan stats`; generation is never blocked.
- **Antifragile hardening:** **R1** — `_run_git("push"/"reset"/"clean"/"rebase", …)` raises `WorktreeError` while `init/add/commit/worktree` still pass (the legit-mutation set is proven), and `_git_subcommand` resolves `-c …=… commit` to `commit`. **R2** — `save_task` round-trips (the dir-fsync is best-effort, never a new crash). **F1** — a sleeping agent is killed at `agent_timeout_seconds`; a builder timeout still harvests the partial diff, lands in `REVIEW` with a blocking re-runnable finding; `wait_bounded(…, 0)` disables the cap. **F2** — a validator that raises AND one that returns `ok=False` (timeout) both degrade: task reaches `REVIEW`, `validator_outcome="failed"`, receipt banner says "validator unavailable"; a clean run reads `"ran"`. **F3** — a malformed report between two valid ones is skipped and the task still reaches `REVIEW`. **F4** — a sleeping `gh` degrades to `unknown` within the timeout. **M1** — a churning scope with no findings still counts toward debt via `changed_files`; legacy tasks fall back to finding locations.
- **In-frame input:** `prompt_in_frame`/`choose_in_frame`/`confirm_in_frame` driven by a pipe input return the typed string / index / bool, backspace edits, esc cancels; `test_no_in_session_prompt_escapes_the_frame` asserts `session.py` contains no raw `PromptSession` call (preflight excepted). Comprehension submits on Enter and advances; the new-task Scope prompt carries help; `f` opens findings.
- **Phase 14:** no agent → `kagan init` writes a valid commented skeleton + rubric that `load_repo_config` parses; a stubbed agent draft walked + approved writes a validated manifest; a dangerous command needs a second confirm; an opt-in verify drops a failing check; a draft with an unknown risk tier / extra service key still writes (sanitized) rather than crashing after the walk; the branch-protection probe is pass/warn/skip per gh state and never fails. A real-TTY tmux smoke drives `kagan init` end-to-end with a fake agent CLI on PATH.

End-to-end smoke (any phase): `kagan new` in a scratch repo → run the fake agent → confirm the gate enforces the new lock(s) → approve → verify the receipt + ledger reflect the new provenance, via the harness/MCP fixtures under `tests/kagan/`.

______________________________________________________________________

## Appendix A — End-to-end walkthrough (build a ratatui calculator)

A full lifecycle in the single `kagan` session — the panels the user sees, the keys they press. Demonstrates: first-boot scaffold → intake gate (Approve/Reject decisions) → detached run → builder+validator (different models) catching real bugs → send-back loop → comprehension gate → approve + receipt → ship (never pushes) → CI tripwire → private stats.

Legend — `●` needs you · `◷` working · `⟳` reviewing/re-run · `▸` cursor · `✓` done · `✗` blocker · `⚠` note · `○` optional · `☑` verified · `◐` med-risk · `🔔` notification

**① First run — scaffold the manifest** (built as `kagan init`, Phase 14 — also offered automatically when bare `kagan` finds no manifest)

The mockup below is illustrative; the built flow does not deterministically detect the
stack. An available agent CLI reads the repo and *proposes* the checks (preferring commands
already declared in CI/scripts), then the human walks and approves each one before anything
runs — the per-command gate that the single-frame `⏎ scaffold & continue` here compresses.

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

Resolve the three blocking ones → run unlocks

```
┌─────────────────────────────────────────────────────────────┐
│  a ratatui calculator app · INTAKE               ◐ med risk
│
│  ▌ RESOLVED
│    ✓ precedence  → proper            (rejected left-to-right)
│    ✓ number      → floating point    (approved assumption)
│    ✓ divide by 0 → show "Error"      (approved assumption)
│    ○ mouse       → left optional
│
├─────────────────────────────────────────────────────────────┤
│  r run      q quit
└─────────────────────────────────────────────────────────────┘
```

**④ Running — go do something else** — `r` spawns the detached runner; quiet inbox

```
┌─────────────────────────────────────────────────────────────┐
│  kagan · rcalc                              ✓ nothing needs you
│
│  ◷ a ratatui calculator app       working…  ~4m · codex
│
│  ▌ I'll notify you when it needs your judgment.
│    Go do something else.
│
├─────────────────────────────────────────────────────────────┤
│  w workspaces      q quit
└─────────────────────────────────────────────────────────────┘
```

**⑤ Reviewing** — headless validator (different model)

```
   🔔  kagan: reviewing rcalc…
       ⟳ a ratatui calculator app    reviewing · claude-opus
```

**⑥ Needs you** — the screen IS the to-do that unlocks approve

```
┌─────────────────────────────────────────────────────────────┐
│  a ratatui calculator app           kagan/task-1a2b → main
│  9 files · +412 −0                                ◐ med risk
│
│  ▌ ALMOST READY — 2 things before you approve
│    ▸ ● adjudicate 2 findings
│      ● answer 1 comprehension prompt
│      ✓ checks · build · clippy · test · mutation-probe
│      ✓ security · clean
│      ○ smoke · 2 to verify
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ drill in · a approve (2 left) · s send back · o diff · q
└─────────────────────────────────────────────────────────────┘
```

**⑦ Validator caught real bugs** — agree they're real, send back (don't hand-fix, don't rubber-stamp)

```
┌─────────────────────────────────────────────────────────────┐
│  ◀ FINDINGS · rcalc                               2 blocking
│
│  ▸ ✗ src/eval.rs:80   blocking · ai-review
│       "2+3*4" → 20, not 14  —  precedence ignored
│       › agree, send back to fix    disagree…    open file
│
│    ✗ src/eval.rs:54   blocking · ai-review
│       bare "." panics instead of showing "Error"
│       ✓ agreed
│
├─────────────────────────────────────────────────────────────┤
│  both real → s send back to the agent       esc back
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│  SEND BACK · rcalc
│
│  Agent re-runs in the SAME worktree with your note:
│  ┃ fix precedence + the parse panic; bad input must show
│  ┃ "Error", never crash.
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ send back       esc cancel
└─────────────────────────────────────────────────────────────┘
```

**⑧ Pass 2 — comprehension gate** — findings clear; write it in your own words (med = 2 prompts)

```
┌─────────────────────────────────────────────────────────────┐
│  a ratatui calculator app    kagan/task-1a2b → ⟳ re-run 2
│  9 files · +447 −31                               ◐ med risk
│
│  ▌ ALMOST READY — 1 thing before you approve
│    ▸ ● answer 1 comprehension prompt
│      ✓ findings · 0 open  (2 fixed, re-validated clean)
│      ✓ checks · build · clippy · test · mutation-probe
│      ☑ smoke · 2 to verify
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ open · a approve (1 left) · s send back · o diff · q
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│  ◀ BEFORE YOU APPROVE                             ◐ med risk
│
│  ▌ IN YOUR OWN WORDS
│  1 · What does the evaluator do now, end to end?
│      ┃ tokenises input, shunting-yard with ×÷ over +−,
│      ┃ evaluates to f64; bad tokens → Error ▏
│
│  2 · What could still break it?
│      ┃ huge numbers overflow f64 → inf; fine for v1 ▏
│
│  ▌ context · src/eval.rs  (shunting-yard, ~60 lines)
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ submit       ^O editor
└─────────────────────────────────────────────────────────────┘
```

**⑨ Approve** — all clear → `a`; receipt auto-writes, retro offer

```
┌─────────────────────────────────────────────────────────────┐
│  a ratatui calculator app           kagan/task-1a2b → main
│
│    ✓ findings 0 open         ✓ comprehension recorded
│    ✓ checks passed           ☑ smoke 2/2 verified
│
│  ▌ ✓ ALL CLEAR
│
├─────────────────────────────────────────────────────────────┤
│  a  ✓ APPROVE · ready         s send back        o diff
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│  ✓ APPROVED · a ratatui calculator app
│
│    ✓ marked ready   (not pushed — that's yours)
│    ✓ receipt → .kagan/reviews/2026-06-23-ratatui-calc.md
│
│  ▌ ONE LEARNING FOR AGENTS.md?
│    ▸ "expr eval = shunting-yard in src/eval.rs; bad input
│       → Error, never panic"
│
├─────────────────────────────────────────────────────────────┤
│  ⏎ add to AGENTS.md        s skip → ship
└─────────────────────────────────────────────────────────────┘
```

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

**⑪ PR open — read-only CI tripwire**

```
┌─────────────────────────────────────────────────────────────┐
│  kagan · rcalc                              ✓ nothing needs you
│
│  ▸ a ratatui calculator app     PR open · ⟳ watching CI…
│
├─────────────────────────────────────────────────────────────┤
│  q quit
└─────────────────────────────────────────────────────────────┘
```

```
   🔔  kagan: CI passed
       ✓ a ratatui calculator app    merged-ready · CI green
```

*(CI red → re-surfaces as `● needs you`.)*

**⑫ The private mirror** — `kagan stats`

```
┌─────────────────────────────────────────────────────────────┐
│  kagan stats · rcalc                           ▌ just for you
│
│    durability     ▰▱▱▱   1/1   (too new for 14d)
│    clean merges   ▰▰▰▰   1/1   CI green
│    comprehension  ▰▰▰▰   1/1   first try
│    review caught  ✗✗→✓   2 real bugs before they shipped
│    supervised     0h22m · 1 session · no after-hours
│
└─────────────────────────────────────────────────────────────┘
```

Mapped to the levers: risk routing (med → validator + comprehension, no 2nd approver, l4); builder+validator with different models catching real bugs (l2); the send-back loop (human judgment, not hand-fix or rubber-stamp); the comprehension gate (l1, risk-scaled); never-push (l6 / invariant); receipt → `.kagan/reviews/` as committable provenance; quiet-by-default + notification-backed return (l5 / §3.3).
