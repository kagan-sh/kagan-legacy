---
title: Security
description: Security model, threat boundaries, and safe usage practices for Kagan
icon: material/shield-check
---

# Security Documentation

This document describes Kagan's security model, trust boundaries, and safe usage practices. It explains how the system protects your data and what you should know to use Kagan safely.

---

## 1. Security Overview

### Threat Model

Kagan is designed with a **defense-in-depth** approach that assumes:

| Threat | Mitigation |
|--------|------------|
| Malicious persona presets | Progressive trust scoring + mandatory audit before import |
| Environment credential leaks | Subprocess environment sanitization (allowlist-based) |
| Path traversal attacks | Path validation on all file operations |
| Git ref injection | Ref name validation before git operations |
| Prompt injection | Input validation + prompt structure enforcement |
| Privilege escalation | Role-based access control (RBAC) for MCP tools |

### Trust Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    User Trust Boundary                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │   Config    │    │   Source    │    │  Persona Presets │  │
│  │   (local)   │    │   (local)   │    │  (GitHub import) │  │
│  └──────┬──────┘    └──────┬──────┘    └────────┬────────┘  │
│         │                  │                     │           │
│         └──────────────────┼─────────────────────┘           │
│                            ▼                                 │
│              ┌─────────────────────────┐                     │
│              │    Kagan Core (TUI)     │                     │
│              │    ┌─────────────┐      │                     │
│              │    │  Audit Log  │      │                     │
│              │    └─────────────┘      │                     │
│              └───────────┬─────────────┘                     │
│                          │                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │ Agent 1 │  │ Agent 2 │  │ Agent N │  (Sandboxed via
        │ (tmux)  │  │(managed)│  │(various)│   env sanitization)
        └─────────┘  └─────────┘  └─────────┘
```

**Key Boundaries:**

- **Local data never leaves your machine** — Kagan operates entirely locally except when explicitly connecting to agent backends or importing persona presets
- **Agent processes are isolated** — Each agent runs in a sanitized subprocess environment without access to sensitive credentials
- **Persona presets are untrusted by default** — All imported presets undergo automated security auditing before you can use them

---

## 2. Persona Preset Security

### Progressive Trust System

Kagan uses a **reputation-based trust assessment** when you import persona presets from GitHub repositories. This system helps you evaluate whether a preset is safe to use.

### Understanding Trust Scores

When you audit or import a persona preset, Kagan calculates a **trust score** (0.0 to 1.0) based on three factors:

| Factor | Weight | What It Measures |
|--------|--------|------------------|
| **Security Audit** | 50% | Presence of suspicious patterns in prompts |
| **GitHub Stars** | 30% | Social proof and community adoption |
| **Repository Age** | 20% | Longevity indicates stability |

**Star Score Formula:**
- 0 stars = 0.3 base score
- 10 stars = 0.5
- 100 stars = 0.7
- 1000+ stars = 0.9

**Age Score Formula:**
- < 30 days = 0.3 (new, higher risk)
- 30-90 days = 0.5
- 90-365 days = 0.7
- 365+ days = 0.9 (established)

### Trust Tiers

Based on the combined trust score, repositories are classified into three tiers:

| Tier | Score Range | Behavior |
|------|-------------|----------|
| **Low Risk** | ≥ 0.7 + clean audit | Can auto-import with `--auto-confirm` |
| **Medium Risk** | 0.4 - 0.7 | Shows audit summary, requires confirmation |
| **High Risk** | < 0.4 or high audit risk | Requires `--acknowledge-risk` flag |

### Why a Persona Import Shows "Medium Risk"

A "medium risk" rating typically means one or more of the following:

1. **Security findings detected** — The audit found suspicious tokens in prompts (e.g., `curl`, `rm -rf`, `password`, `secret`)
2. **Limited GitHub presence** — The repository has few stars (< 100)
3. **Relatively new** — The repository was created less than 90 days ago
4. **Archived repository** — The repository is archived (indicates unmaintained code)

### How to Evaluate a Persona Preset

Before importing any persona preset, follow these steps:

```bash
# 1. Audit the repository first
kagan tools prompts persona audit owner/repo

# 2. Review the output:
#    - Check trust_score and trust_tier
#    - Review findings for any security concerns
#    - Examine persona preview to understand what it does
```

**Example audit output:**

```json
{
  "repo": "acme-corp/presets",
  "trust_tier": "medium_risk",
  "trust_assessment": {
    "trust_score": 0.65,
    "stars": 45,
    "repo_age_days": 120,
    "audit_risk_level": "medium",
    "findings": [
      {
        "persona": "devops",
        "severity": "medium",
        "message": "Prompt contains security-sensitive tokens",
        "evidence": ["curl", "wget"]
      }
    ]
  },
  "personas": [
    {
      "key": "devops",
      "name": "DevOps Specialist",
      "prompt_preview": "You are a DevOps engineer... (200 chars shown)"
    }
  ]
}
```

**Manual Review Checklist:**

- [ ] Read the full prompt content in the source repository
- [ ] Verify the prompt doesn't instruct the agent to perform dangerous operations
- [ ] Check that the repository owner is reputable
- [ ] Look at recent commits to ensure active maintenance
- [ ] Review the repository's README and documentation

### Registry Whitelist

Kagan maintains a registry whitelist at `registry/persona_repo_whitelist.json`. This list contains repositories that have been reviewed by the Kagan maintainers:

```json
[
  "kagan-sh/kagan"
]
```

You can also maintain your own whitelist:

```bash
# Add a repository to your personal whitelist
kagan tools prompts persona whitelist add owner/repo

# View your whitelist
kagan tools prompts persona whitelist list
```

---

## 3. Environment Sanitization

### What Gets Stripped and Why

Kagan uses an **allowlist-based approach** to environment variable sanitization. When spawning agent subprocesses, only explicitly allowed variables are passed through.

### Essential Variables (Always Preserved)

```
PATH, HOME, USER, SHELL, PWD, LANG, LC_ALL, TERM, EDITOR,
SSH_AUTH_SOCK, GIT_CONFIG_GLOBAL
```

These variables are required for basic system operation and git functionality.

### Sensitive Patterns (Always Stripped)

Any variable matching these patterns is **automatically removed**:

| Pattern | Examples of Stripped Variables |
|---------|-------------------------------|
| `TOKEN` | `GITHUB_TOKEN`, `API_TOKEN` |
| `KEY` | `AWS_ACCESS_KEY`, `SECRET_KEY` |
| `SECRET` | `DATABASE_SECRET`, `APP_SECRET` |
| `PASSWORD` | `DB_PASSWORD`, `USER_PASSWORD` |
| `AWS_` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| `AZURE_` | `AZURE_CLIENT_SECRET` |
| `GCP_` | `GCP_SERVICE_ACCOUNT_KEY` |
| `OPENAI_` | `OPENAI_API_KEY` |
| `ANTHROPIC_` | `ANTHROPIC_API_KEY` |
| `GITHUB_` | `GITHUB_TOKEN` |
| `LD_PRELOAD` | Library injection attacks |
| `DYLD_INSERT_LIBRARIES` | macOS library injection |

### Python-Specific Variables (Stripped)

All variables starting with `PYTHON` are removed to prevent:
- `PYTHONPATH` hijacking
- `PYTHONHOME` manipulation
- Version-specific behavior changes

### Platform-Specific Noisy Variables

On macOS, these debugging variables are stripped to prevent output pollution:

```
MallocStackLogging, MallocStackLoggingNoCompact,
MALLOCSTACKLOGGING, MALLOCSTACKLOGGINGNOCOMPACT
```

### What Environment Variables Are Passed to Agents

When Kagan launches an agent, it passes:

```bash
# Essential system variables
PATH=/usr/local/bin:/usr/bin:/bin
HOME=/home/username
USER=username
...

# Kagan session variables
KAGAN_TASK_ID=abc123
KAGAN_TASK_TITLE="Fix login bug"
KAGAN_WORKTREE_PATH=/path/to/worktree
KAGAN_PROJECT_ROOT=/path/to/project
KAGAN_CWD=/path/to/worktree
KAGAN_MCP_SERVER_NAME=kagan

# Backend-specific defaults (only if not already set)
# e.g., ANTHROPIC_MODEL for Claude backends
```

### Explicit Override

You can explicitly allow additional variables using the `allow_extra` parameter in the API, but this is primarily for internal use:

```python
env = build_sanitized_subprocess_environment(
    allow_extra={"MY_CUSTOM_VAR": "safe_value"}
)
```

---

## 4. Input Validation

### Branch Name Validation

Git branch names are validated to prevent option injection and path traversal:

**Rejected patterns:**
- Names starting with `-` (option injection: `-help`)
- Names containing `..` (directory traversal)
- Names containing `@{` (reflog syntax injection)

**Validation process:**
1. Quick regex checks for dangerous patterns
2. Delegation to `git check-ref-format --branch` for canonical validation

```python
# This will fail validation
kagan task create --title "Test" --base-branch "--help"  # ❌ Rejected
kagan task create --title "Test" --base-branch "../../../etc"  # ❌ Rejected
```

### Path Validation

Repository paths for persona imports are validated:

```python
# Valid paths
.kagan/personas.json           # ✅ OK
configs/team/personas.json     # ✅ OK

# Invalid paths
../secrets.json               # ❌ Path traversal
../../etc/passwd              # ❌ Path traversal
```

### Settings Validation

Settings values are validated against allowed enums:

| Setting | Allowed Values |
|---------|---------------|
| `review_strictness` | `strict`, `balanced`, `relaxed` |
| `planning_depth` | `always`, `multi_task`, `never` |
| `doctor_verbosity` | `tldr`, `short`, `technical` |

### Request Body Validation

All API requests use Pydantic models for strict validation:

- Type checking for all fields
- Enum validation for constrained values
- Length limits for strings (e.g., follow-up text limited to 20,000 chars)
- Empty string rejection for required fields

---

## 5. Security Best Practices for Users

### How to Use Kagan Safely

#### 1. Audit Before Import

Always audit persona presets before importing:

```bash
# Audit first
kagan tools prompts persona audit owner/repo

# Only import if trust_tier is acceptable
kagan tools prompts persona import owner/repo --auto-confirm  # Only for low_risk
```

#### 2. Use Specific Git References

When importing presets, pin to a specific commit or tag:

```bash
# Pin to a specific commit
kagan tools prompts persona import owner/repo --ref abc123def

# Pin to a release tag
kagan tools prompts persona import owner/repo --ref v1.2.3
```

This protects against the repository owner changing the content after you've reviewed it.

#### 3. Review Persona Prompts

Before using an imported persona, read its full prompt:

```bash
# List all personas
kagan tools prompts persona list

# The prompt content is shown in the TUI when selecting a persona
```

**Red flags to watch for:**
- Instructions to execute shell commands
- Requests to access files outside the project directory
- Instructions to share credentials or secrets
- Prompts that ask the agent to ignore safety guidelines

#### 4. Use Role-Based MCP Access

Limit MCP tool exposure based on your use case:

```bash
# Read-only auditing (safest)
kagan mcp --readonly

# Worker role (task execution only)
kagan mcp --role worker

# Full orchestrator (all tools)
kagan mcp --role orchestrator
```

#### 5. Monitor the Audit Log

Regularly review the audit log for unexpected activity:

```bash
# View recent audit events
kagan audit list --limit 20
```

Look for:
- Unexpected persona imports
- Settings changes you didn't make
- Task deletions

#### 6. Keep Your Configuration Secure

```bash
# Set appropriate permissions on config directory
chmod 700 ~/.config/kagan

# Don't commit config files to version control
echo "config.toml" >> .gitignore
```

#### 7. Validate Agent Backend Integrity

Ensure your agent backends are installed from official sources:

```bash
# Kagan can check this for you
kagan doctor
```

### Secure Configuration Example

```toml
# config.toml
[general]
# Use strict review for sensitive codebases
review_strictness = "strict"

# Don't auto-approve single tasks
auto_confirm_single_tasks = false

# Require review approval before merge
require_review_approval = true

# Limit concurrent agents
max_concurrent_agents = 2
```

---

## 6. Reporting Security Issues

### Contact Information

If you discover a security vulnerability in Kagan, please report it responsibly:

**Email:** `security@kagan.sh`

**PGP Key:** (Placeholder — contact security@kagan.sh for the current PGP key)

```
-----BEGIN PGP PUBLIC KEY BLOCK-----
[Placeholder - PGP key will be provided upon request]
-----END PGP PUBLIC KEY BLOCK-----
```

### Responsible Disclosure

We follow responsible disclosure practices:

1. **Report privately** — Send details to security@kagan.sh
2. **Allow time for remediation** — We aim to respond within 48 hours and patch within 7 days
3. **Coordinate disclosure** — We'll work with you to publicly disclose the issue after a fix is released
4. **Credit researchers** — We publicly acknowledge security researchers who report valid vulnerabilities

### What to Include

Your report should include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if any)
- Your contact information for follow-up

### Out of Scope

The following are generally out of scope for security reports:

- Issues in dependencies (report to the upstream project)
- Social engineering attacks
- Physical security issues
- Issues affecting outdated versions (please test on the latest release)

---

## 7. Security Audit History

### Pre-Release Security Audit

Kagan underwent a security audit prior to its initial release. Key findings and mitigations:

| Finding | Severity | Status | Mitigation |
|---------|----------|--------|------------|
| Path traversal in worktree operations | High | ✅ Fixed | Added path validation and `resolve()` normalization |
| Environment credential leakage | Medium | ✅ Fixed | Implemented allowlist-based env sanitization |
| Git ref injection | Medium | ✅ Fixed | Added ref name validation with `git check-ref-format` |
| Prompt injection via persona presets | Medium | ✅ Mitigated | Implemented automated persona auditing |
| Missing audit trail | Low | ✅ Fixed | Added comprehensive audit logging |

### Ongoing Security Measures

- **Dependency scanning** — Automated vulnerability scanning via Socket
- **Code review** — All changes require peer review
- **CI security gates** — Pre-commit hooks for secrets detection (gitleaks)
- **Type safety** — Strict type checking with pyrefly

### Audit Log Schema

All security-relevant actions are logged:

```python
{
  "action": "persona.import",           # What happened
  "entity_type": "persona_preset",      # What was affected
  "entity_id": "owner/repo",            # Identifier
  "detail": {                           # Additional context
    "trust_tier": "medium_risk",
    "trust_score": 0.65,
    "imported_keys": ["analyst", "dev"],
    "auto_confirmed": false
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Logged actions include:**
- `persona.import` — Preset import with trust metadata
- `persona.export` — Preset export
- `persona.whitelist.add/remove` — Whitelist modifications
- `task.create/update/delete` — Task mutations
- `settings.set` — Configuration changes

---

## Summary

Kagan's security model prioritizes:

1. **Zero-trust for external content** — All persona presets are audited before use
2. **Defense in depth** — Multiple layers of validation and sanitization
3. **Transparency** — Audit logs for all security-relevant actions
4. **User control** — You decide what to trust and when

By following the best practices in this document, you can use Kagan confidently while maintaining a strong security posture.

For questions about security, contact: **security@kagan.sh**
