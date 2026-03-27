# Security API Reference

This document describes the security-related functions and classes available in the Kagan codebase for runtime environment sanitization, git reference validation, worktree path security, and persona trust assessment.

______________________________________________________________________

## Runtime Environment

### `runtime_env.build_sanitized_subprocess_environment()`

Builds a sanitized environment dictionary for safe subprocess execution using an allowlist-based approach.

#### Signature

```python
def build_sanitized_subprocess_environment(
    base_env: Mapping[str, str] | None = None,
    *,
    allow_extra: Mapping[str, str] | None = None,
) -> dict[str, str]
```

#### Parameters

| Parameter     | Type                        | Description                                                                                 |
| ------------- | --------------------------- | ------------------------------------------------------------------------------------------- |
| `base_env`    | `Mapping[str, str] \| None` | Base environment to sanitize. Defaults to `os.environ` if not provided.                     |
| `allow_extra` | `Mapping[str, str] \| None` | Additional environment variables to allow (name → value). These bypass all security checks. |

#### Return Value

Returns a `dict[str, str]` containing the sanitized environment with:

- Essential variables preserved: `PATH`, `HOME`, `USER`, `SHELL`, `PWD`, `LANG`, `LC_ALL`, `TERM`, `EDITOR`, `SSH_AUTH_SOCK`, `GIT_CONFIG_GLOBAL`
- Sensitive variables stripped: Any key matching patterns like `TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `AWS_*`, `AZURE_*`, `GCP_*`, `OPENAI_*`, `ANTHROPIC_*`, `GITHUB_*`, `LD_PRELOAD`, `DYLD_INSERT_LIBRARIES`
- Python-specific variables removed: Any key starting with `PYTHON` (e.g., `PYTHONPATH`, `PYTHONHOME`)
- Platform-specific noisy variables removed (e.g., `MallocStackLogging` on macOS)
- Explicitly allowed extra variables included (bypass all checks)

#### Examples

**Basic usage with default environment:**

```python
from kagan.runtime_env import build_sanitized_subprocess_environment
import subprocess

# Create sanitized environment
sanitized_env = build_sanitized_subprocess_environment()

# Use in subprocess
subprocess.run(["git", "status"], env=sanitized_env, capture_output=True)
```

**With additional allowed variables:**

```python
# Allow custom variables for specific subprocess
env = build_sanitized_subprocess_environment(
    allow_extra={
        "MY_APP_TOKEN": "secret-token",  # This will be included
        "CUSTOM_VAR": "custom-value",
    }
)
```

**Using a custom base environment:**

```python
import os

# Start from a minimal base
minimal_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
sanitized = build_sanitized_subprocess_environment(base_env=minimal_env)
```

______________________________________________________________________

## Git Reference Validation

### `git.validate_ref_name()`

Validates a git reference name for safety, preventing option injection and directory traversal attacks.

#### Signature

```python
async def validate_ref_name(name: str) -> bool
```

#### Parameters

| Parameter | Type  | Description                                                  |
| --------- | ----- | ------------------------------------------------------------ |
| `name`    | `str` | The git reference name to validate (e.g., branch name, tag). |

#### Return Value

Returns `bool`:

- `True` if the reference name is valid and safe
- `False` if the name is invalid, empty, or potentially malicious

#### Validation Rules

The function performs the following security checks:

1. **Empty check**: Empty strings are rejected
1. **Option injection**: Names starting with `-` are rejected (prevents `git checkout --some-option` attacks)
1. **Directory traversal**: Names containing `..` are rejected
1. **Reflog syntax**: Names containing `@{` are rejected (prevents reflog injection)
1. **Canonical validation**: Uses `git check-ref-format --branch` for final validation

#### Examples

**Basic validation:**

```python
import asyncio
from kagan.core import git


async def check_branch():
    # Valid branch names
    assert await git.validate_ref_name("feature/new-thing") is True
    assert await git.validate_ref_name("main") is True
    assert await git.validate_ref_name("v1.0.0") is True

    # Invalid/malicious names
    assert await git.validate_ref_name("--force") is False  # Option injection
    assert await git.validate_ref_name("../etc/passwd") is False  # Traversal
    assert await git.validate_ref_name("@{-1}") is False  # Reflog injection
    assert await git.validate_ref_name("") is False  # Empty


asyncio.run(check_branch())
```

**Using before git operations:**

```python
async def safe_checkout(repo_path: Path, branch_name: str):
    # Always validate before using in git commands
    if not await git.validate_ref_name(branch_name):
        raise ValueError(f"Invalid branch name: {branch_name}")

    # Now safe to use in git operations
    await git.worktree_add(repo.path, "/path/to/wt", branch=branch_name, base="main")
```

______________________________________________________________________

## Worktree Path Security

### `worktrees._resolve_worktree_path()`

Resolves and validates a task ID to a safe worktree path, preventing path traversal and injection attacks.

#### Signature

```python
@staticmethod
def _resolve_worktree_path(task_id: str) -> Path
```

#### Parameters

| Parameter | Type  | Description                                                         |
| --------- | ----- | ------------------------------------------------------------------- |
| `task_id` | `str` | The task identifier to resolve. Must be a valid UUID format string. |

#### Return Value

Returns a `pathlib.Path` that is:

- Absolute and normalized (no `..` or `.` components)
- Within the configured worktree base directory
- Named with the valid UUID task ID

#### Exceptions

| Exception         | Condition                                                                       |
| ----------------- | ------------------------------------------------------------------------------- |
| `ValidationError` | Task ID is not a valid UUID format, contains special characters, or is too long |
| `WorktreeError`   | Resolved path would escape the base directory (path traversal detected)         |
| `TypeError`       | Task ID is not a string (e.g., `None`, `int`)                                   |

#### Validation Rules

1. **UUID format**: Must match `^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`
1. **Path traversal**: Rejects `..`, `/`, `\`, encoded traversal sequences
1. **Special characters**: Rejects shell metacharacters, wildcards (`*`, `?`), quotes
1. **Length limit**: Rejects IDs exceeding reasonable length (prevents buffer issues)
1. **Control characters**: Rejects null bytes, control characters, Unicode escapes

#### Examples

**Valid usage with UUID:**

```python
from kagan.core._worktrees import Worktrees

# Valid UUID format
task_id = "550e8400-e29b-41d4-a716-446655440000"
path = Worktrees._resolve_worktree_path(task_id)
# Returns: Path("/home/user/.local/state/kagan/worktrees/550e8400-e29b-41d4-a716-446655440000")
```

**Path traversal attempts (all raise exceptions):**

```python
from kagan.core.errors import ValidationError, WorktreeError

# All of these will raise ValidationError or WorktreeError

try:
    Worktrees._resolve_worktree_path("../../../etc/passwd")
except (ValidationError, WorktreeError) as e:
    print(f"Blocked traversal: {e}")

try:
    Worktrees._resolve_worktree_path("..\\..\\windows\\system32")
except (ValidationError, WorktreeError) as e:
    print(f"Blocked Windows traversal: {e}")

try:
    Worktrees._resolve_worktree_path("task; rm -rf /")  # Shell injection
except (ValidationError, WorktreeError) as e:
    print(f"Blocked shell injection: {e}")
```

**Verifying path containment:**

```python
from pathlib import Path


def is_path_within_base(path: Path, base: Path) -> bool:
    """Check if resolved path stays within base directory."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


# Usage
base_dir = Path("/home/user/.local/state/kagan/worktrees")
resolved = Worktrees._resolve_worktree_path("550e8400-e29b-41d4-a716-446655440000")
assert is_path_within_base(resolved, base_dir)
```

______________________________________________________________________

## Persona Trust Assessment

### `persona.TrustAssessment`

A frozen dataclass representing the reputation-based trust assessment of a persona repository.

#### Class Definition

```python
@dataclass(frozen=True)
class TrustAssessment:
    repo: str  # Repository identifier (owner/repo format)
    stars: int  # GitHub star count
    repo_age_days: int  # Repository age in days
    audit_risk_level: str  # "low", "medium", or "high"
    trust_score: float  # Calculated score from 0.0 to 1.0
    trust_tier: str  # "low_risk", "medium_risk", or "high_risk"
    findings: list[dict[str, Any]]  # Security audit findings
    archived: bool  # Whether the repository is archived
```

#### Fields

| Field              | Type                   | Description                                                          |
| ------------------ | ---------------------- | -------------------------------------------------------------------- |
| `repo`             | `str`                  | Full repository name in `owner/repo` format                          |
| `stars`            | `int`                  | Number of GitHub stars (social proof metric)                         |
| `repo_age_days`    | `int`                  | Days since repository creation                                       |
| `audit_risk_level` | `str`                  | Security audit level: `"low"`, `"medium"`, or `"high"`               |
| `trust_score`      | `float`                | Composite score from `0.0` (untrusted) to `1.0` (highly trusted)     |
| `trust_tier`       | `str`                  | Risk classification: `"low_risk"`, `"medium_risk"`, or `"high_risk"` |
| `findings`         | `list[dict[str, Any]]` | List of security findings with severity, message, and evidence       |
| `archived`         | `bool`                 | Whether the GitHub repository is archived                            |

#### Trust Score Calculation

The trust score is calculated using weighted factors:

| Factor          | Weight | Calculation                                                   |
| --------------- | ------ | ------------------------------------------------------------- |
| **Audit Score** | 50%    | `1.0` (low risk), `0.5` (medium), `0.0` (high)                |
| **Star Score**  | 30%    | Sigmoid curve: 0 stars=0.3, 10=0.5, 100=0.7, 1000+=0.9        |
| **Age Score**   | 20%    | Sigmoid curve: \<30 days=0.3, 30-90=0.5, 90-365=0.7, 365+=0.9 |

**Archived repository penalty:**

- Age score reduced by 0.2
- Star score reduced by 0.1

**Trust tier thresholds:**

- `low_risk`: `trust_score >= 0.7` AND `audit_risk_level == "low"`
- `high_risk`: `trust_score < 0.4` OR `audit_risk_level == "high"`
- `medium_risk`: All other cases

#### Methods

##### `to_dict()`

```python
def to_dict(self) -> dict[str, Any]
```

Converts the trust assessment to a dictionary with rounded trust score (3 decimal places).

#### Examples

**Creating and using trust assessment:**

```python
from kagan.core._persona import TrustAssessment

assessment = TrustAssessment(
    repo="owner/persona-repo",
    stars=150,
    repo_age_days=180,
    audit_risk_level="low",
    trust_score=0.75,
    trust_tier="low_risk",
    findings=[],
    archived=False,
)

# Check trust tier before import
if assessment.trust_tier == "low_risk":
    print("Safe to auto-import")
elif assessment.trust_tier == "high_risk":
    print("Requires manual review!")

# Serialize for API response
data = assessment.to_dict()
# {
#     "repo": "owner/persona-repo",
#     "stars": 150,
#     "repo_age_days": 180,
#     "audit_risk_level": "low",
#     "trust_score": 0.75,
#     "trust_tier": "low_risk",
#     "findings": [],
#     "archived": False
# }
```

**Trust score calculation example:**

```python
# Example: New repo with few stars
new_repo = TrustAssessment(
    repo="user/new-personas",
    stars=5,
    repo_age_days=10,
    audit_risk_level="medium",
    trust_score=0.42,  # Lower due to age and audit findings
    trust_tier="medium_risk",
    findings=[{"severity": "medium", "message": "Suspicious tokens in prompt"}],
    archived=False,
)

# Example: Established, popular repo
established = TrustAssessment(
    repo="kagan/official-personas",
    stars=2500,
    repo_age_days=730,
    audit_risk_level="low",
    trust_score=0.91,  # High due to stars, age, and clean audit
    trust_tier="low_risk",
    findings=[],
    archived=False,
)
```

______________________________________________________________________

## Persona Repository Audit

### `persona.audit_repo()`

Audits a remote GitHub repository for persona presets, returning security findings and trust assessment.

#### Signature

```python
async def audit_repo(
    self,
    *,
    repo: str,
    path: str = ".kagan/personas.json",
    ref: str | None = None,
) -> dict[str, Any]
```

#### Parameters

| Parameter | Type          | Default                  | Description                                                   |
| --------- | ------------- | ------------------------ | ------------------------------------------------------------- |
| `repo`    | `str`         | *required*               | Repository in `owner/repo` format                             |
| `path`    | `str`         | `".kagan/personas.json"` | Path to the personas file within the repo                     |
| `ref`     | `str \| None` | `None`                   | Git ref (branch, tag, or SHA). Uses default branch if `None`. |

#### Return Value

Returns a `dict[str, Any]` with the following structure:

```python
{
    "repo": str,  # Repository name (owner/repo)
    "repo_url": str,  # HTML URL to the repository
    "path": str,  # Path to personas file
    "ref": str | None,  # Git ref used
    "archived": bool,  # Whether repo is archived
    "stars": int,  # GitHub star count
    "updated_at": str,  # Last push timestamp (ISO 8601)
    "created_at": str,  # Creation timestamp (ISO 8601)
    "persona_count": int,  # Number of personas in file
    "personas": list[dict],  # Preview of each persona (see below)
    "findings": list[dict],  # Security audit findings
    "audit_risk_level": str,  # "low", "medium", or "high"
    "trust_assessment": dict,  # TrustAssessment as dictionary
    "trust_tier": str,  # "low_risk", "medium_risk", "high_risk"
    "disclaimer": str,  # Safety disclaimer message
}
```

**Persona preview structure:**

```python
{
    "key": str,  # Persona identifier
    "name": str,  # Display name
    "description": str,  # Description
    "prompt_preview": str,  # First 200 chars of prompt (truncated)
    "prompt_length": int,  # Total prompt character count
}
```

**Finding structure:**

```python
{
    "persona": str,  # Persona key where issue was found
    "severity": str,  # "low", "medium", or "high"
    "message": str,  # Description of the issue
    "evidence": list,  # Supporting evidence (tokens found, etc.)
}
```

#### Exceptions

| Exception      | Condition                                                                 |
| -------------- | ------------------------------------------------------------------------- |
| `ValueError`   | Invalid repo format, private repository, unsafe path, or GitHub API error |
| `RuntimeError` | GitHub CLI (`gh`) not installed or not authenticated                      |

#### Audit Findings

The following patterns trigger security findings:

| Pattern                       | Severity | Description                   |
| ----------------------------- | -------- | ----------------------------- |
| `rm -rf`                      | medium   | Destructive command in prompt |
| `curl `, `wget `              | medium   | Network download in prompt    |
| `gh auth token`               | medium   | Token extraction attempt      |
| `password`, `secret`, `token` | medium   | Credential-related keywords   |
| Prompt > 12000 chars          | low      | Unusually long prompt         |

#### Examples

**Basic audit:**

```python
import asyncio
from kagan.core._persona import PersonaPresetOps


async def audit_example():
    # Initialize with settings and audit log
    ops = PersonaPresetOps(settings_ops, audit_log)

    # Audit a public repository
    result = await ops.audit_repo(repo="kagan/personas")

    print(f"Repository: {result['repo']}")
    print(f"Stars: {result['stars']}")
    print(f"Trust tier: {result['trust_tier']}")
    print(f"Trust score: {result['trust_assessment']['trust_score']}")

    if result["findings"]:
        print("\nSecurity findings:")
        for finding in result["findings"]:
            print(f"  - [{finding['severity']}] {finding['message']}")

    return result["trust_tier"] == "low_risk"


asyncio.run(audit_example())
```

**Audit with specific ref and path:**

```python
async def audit_specific_version():
    ops = PersonaPresetOps(settings_ops, audit_log)

    # Audit specific branch
    result = await ops.audit_repo(
        repo="myorg/personas",
        path="custom/path/personas.json",
        ref="develop",  # or tag "v1.0.0" or commit SHA
    )

    trust = result["trust_assessment"]
    print(f"Auditing {result['repo']}@{result['ref']}")
    print(f"Risk level: {result['audit_risk_level']}")
    print(f"Trust score: {trust['trust_score']:.2f}")

    # Check for high-risk content
    if result["audit_risk_level"] == "high":
        print("WARNING: High-risk repository detected!")
        for finding in result["findings"]:
            print(f"  - {finding['persona']}: {finding['message']}")


asyncio.run(audit_specific_version())
```

**Progressive trust workflow:**

```python
async def import_with_trust_check():
    ops = PersonaPresetOps(settings_ops, audit_log)

    # First, audit the repository
    audit = await ops.audit_repo(repo="some-user/personas")

    trust_tier = audit["trust_tier"]
    trust_score = audit["trust_assessment"]["trust_score"]

    # Decide action based on trust tier
    if trust_tier == "low_risk":
        # Safe to auto-import
        result = await ops.import_from_github(repo="some-user/personas", auto_confirm=True)
        print(f"Auto-imported {result['imported']}")

    elif trust_tier == "medium_risk":
        # Show findings to user, ask for confirmation
        print(f"Medium risk (score: {trust_score:.2f})")
        print("Findings:", audit["findings"])
        # Prompt user for confirmation...

    else:  # high_risk
        # Require explicit acknowledgment
        print(f"HIGH RISK (score: {trust_score:.2f})")
        print("Manual review required. Use --acknowledge-risk to proceed.")


asyncio.run(import_with_trust_check())
```

______________________________________________________________________

## Security Considerations

### Runtime Environment

- Always use `build_sanitized_subprocess_environment()` when spawning subprocesses with user-provided data
- The `allow_extra` parameter bypasses all checks — use with caution
- Sensitive patterns are matched case-insensitively

### Git Reference Validation

- Always validate branch/tag names before passing to git operations
- The function delegates to `git check-ref-format` for canonical validation
- Returns `False` for invalid names rather than raising exceptions

### Worktree Path Resolution

- Task IDs must be valid UUIDs — this prevents directory traversal via task identifiers
- The function uses strict allowlist validation (UUID format only)
- Path is resolved and normalized to prevent symlink escapes

### Persona Trust Assessment

- Trust scores are heuristic, not cryptographic guarantees
- Always review source repositories before importing personas
- High star counts do not guarantee safety
- Archived repositories receive trust penalties
- The audit uses pattern matching — false positives/negatives are possible
