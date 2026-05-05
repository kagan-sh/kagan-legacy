# GitHub Import User Experience Plan

Concrete rollout plan for exposing GitHub issue import to non-technical users without exposing the plugin system.

## 1. Product framing

- User-facing feature name: **Import from GitHub**.
- Internal implementation detail: plugin architecture remains internal.
- Golden rule: users should never need to learn the word "plugin" to succeed.

## 2. Goals and non-goals

### Goals

- Make first import successful in under 2 minutes for a layman user.
- Provide clear, guided fixes when prerequisites are missing.
- Keep architecture extensible for future third-party connectors.

### Non-goals

- Exposing community plugin discovery/management in default UX.
- Adding a general plugin marketplace UI.
- Supporting every GitHub workflow in V1.

## 3. Options considered

### Option A - Zero-config guided import (recommended)

- Entry points: welcome empty state, board empty state, Quick Actions action.
- Guided flow: connect GitHub -> pick repo -> preview -> import.
- Best for first-time success and least cognitive load.

### Option B - Integrations hub in Settings

- Dedicated "Integrations" section with connection status and actions.
- Better long-term scalability for Jira/Linear/GitLab.
- Slightly more navigation friction than Option A for first-time users.

### Option C - CLI-only flow

- Interactive command for terminal-first users.
- Useful fallback but weak as primary onboarding for layman users.

### Recommendation

- Ship Option A as primary UX.
- Add Option B as management surface in phase 2.
- Keep Option C as power-user and support path.

## 4. End-user journey (V1)

### 4.1 First-run path (no tasks yet)

1. User opens project board and sees: "Bring in tasks from GitHub".
1. User selects "Import from GitHub".
1. Kagan checks prerequisites:
   - `gh` installed
   - `gh` authenticated
1. Ask for repository (`owner/repo`), prefilled from the active git remote when available.
1. Show preview of first 10 open issues.
1. User confirms import.
1. Show success summary (`created`, `skipped`, `errors`) with "Open board" action.

### 4.2 Repeat path

- User runs "Sync GitHub issues" from Quick Actions.
- Show quick toast summary only.

### 4.3 Failure path

- Convert technical errors into actionable steps with one primary fix.
- Example: "GitHub login needed. Run: gh auth login".

## 5. Interaction surfaces

### TUI surfaces

- Welcome/empty state CTA: "Import from GitHub".
- Quick Actions actions:
  - `Import from GitHub`
  - `Sync GitHub issues`
  - `Manage GitHub connection`
- Settings (phase 2): new "Integrations" category with GitHub status.

### CLI surfaces

- New command: `kagan import github` (interactive prompts by default).
- Optional flags for scripted use:
  - `--repo owner/repo`
  - `--state open|closed|all`
  - `--label <label>`
  - `--yes` (skip confirmation)
- Command output must stay plain-language and concise.

### Docs surfaces

- Public guide title: "Import from GitHub" (not "GitHub plugin").
- Quickstart includes one "Optional: import existing issues" step.
- Troubleshooting keeps advanced dependency/debug details.

## 6. Copy deck (exact strings)

### Primary CTAs

- "Import from GitHub"
- "Sync GitHub issues"
- "Connect GitHub"

### Prerequisite checks

- PASS: "GitHub CLI is ready"
- WARN (missing gh): "Install GitHub CLI first: https://cli.github.com"
- WARN (auth): "Sign in to GitHub: run `gh auth login`"

### Repo step

- Label: "Repository"
- Helper: "Use owner/repo, for example: octocat/hello-world"
- Default value: active repository slug detected from the selected project repo's `origin` remote when available

### Preview step

- Title: "Issues to import"
- Subtitle: "We found {count} issues. Import will skip items already linked."

### Completion

- "Import complete"
- "{created} tasks created, {skipped} already imported, {errors} errors"

## 7. Error UX contract

- Every error message must include:
  - what failed
  - why it likely failed
  - one immediate fix action
- Never show raw traceback in primary UI.
- Keep advanced details behind "Show details".

## 8. Future-proof architecture guardrails

- Keep plugin discovery and lifecycle internal.
- Expose only official allowlisted connectors in user-facing surfaces.
- Gate community connectors behind explicit feature flags and trust controls.
- Maintain capability model for eventual third-party ecosystem rollout.

## 9. Implementation plan by phase

### Phase 1 - Guided import MVP

- Add TUI Quick Actions action and modal flow.
- Add CLI `kagan import github` interactive command.
- Add public docs rewrite from "plugin" language to "import" language.

### Phase 2 - Integrations management

- Add Settings -> Integrations panel for connection state and last sync.
- Add reconnect/disconnect UX.

### Phase 3 - Connector expansion foundation

- Reuse same UX shell for additional official connectors.
- Keep third-party connectors hidden by default until trust model is finalized.

## 10. Acceptance criteria

- Layman can import issues without knowing plugin internals.
- First import success path requires at most 4 user decisions.
- Missing prerequisites produce actionable guidance in one screen.
- Repeat sync is one action from board or Quick Actions.
- Internal plugin architecture remains hidden in default user surfaces.
