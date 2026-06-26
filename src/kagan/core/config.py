"""Per-repo manifest model and loader for `.kagan/repo.yaml`.

The field docstrings on the Pydantic model are the user-facing config reference
(P11): there is no separate config-doc framework.
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from kagan.core.errors import ConfigurationError
from kagan.core.risk import TIERS as _RISK_TIERS

_CONFIG_DIR = ".kagan"
_CONFIG_FILE = "repo.yaml"


class ServiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    command: str
    """Shell command that starts the service."""

    port_env: str | None = None
    """Env var the harness sets to a free port; the harness leases the port and
    injects it (P10). Leave unset for services that do not need a port."""

    env: dict[str, str] = Field(default_factory=dict)
    """Extra environment variables injected into the service process."""

    @field_validator("command")
    @staticmethod
    def _non_empty(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command must not be empty")
        return value


class AgentModels(BaseModel):
    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    builder: str | None = None
    """Model id passed verbatim to this CLI's model flag for the builder run. Unset
    leaves the CLI's own default."""

    reviewer: str | None = None
    """Model id the adversarial validator (lever 2) runs with under this CLI. The
    anti-bias guarantee is the FRESH, SEPARATE spawn, so ``reviewer == builder`` is
    allowed and a smaller same-vendor model (e.g. opus builder, haiku reviewer) is a
    valid one-vendor setup. Unset disables the validator stage for this CLI."""


class AgentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    claude: AgentModels = Field(default_factory=AgentModels)
    codex: AgentModels = Field(default_factory=AgentModels)
    opencode: AgentModels = Field(default_factory=AgentModels)
    kimi: AgentModels = Field(default_factory=AgentModels)

    def for_cli(self, cli: str) -> AgentModels:
        """The model section for ``cli``; an unconfigured/unknown CLI yields an empty
        section (both models None = CLI default, validator disabled)."""
        return getattr(self, cli, _EMPTY_AGENT_MODELS)


_EMPTY_AGENT_MODELS = AgentModels()


class RepoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    project_name: str | None = None
    """Display name for the repo; informational only."""

    base_branch: str = "main"
    """Branch worktrees fork from and ship targets."""

    services: dict[str, ServiceConfig] = Field(default_factory=dict)
    """Named long-running processes the harness starts for a task."""

    checks: dict[str, str] = Field(default_factory=dict)
    """Name -> shell command. Every check is a mirror check the gate runs; the
    gate adds its own universal checks on top of these."""

    security: str | None = None
    """SAST command (semgrep/bandit/CodeQL) the gate runs in the worktree (lever
    3). A non-zero exit becomes a finding: blocking on high-risk scope, advisory
    elsewhere. Unset skips the security gate (the gate records that it skipped)."""

    risk_tiers: dict[str, list[str]] = Field(default_factory=dict)
    """Risk tier -> path globs (lever 4 spine), e.g. {high: [src/auth/**,
    migrations/**], low: [docs/**]}. Intake classifies a task's tier from its
    scope: HIGH if any scope path matches a high glob, LOW only if every path
    matches a low glob, else MEDIUM. Unset leaves every task MEDIUM (today's
    behaviour). Globs use fnmatch, the same idiom scope values are written in.
    Keys must be one of low/medium/high — an unknown key is rejected at load
    (a typo'd tier would otherwise silently route into MEDIUM)."""

    review_rubric: Path = Path(".kagan/review.md")
    """Path (relative to the manifest's own dir) to the repo-specific review
    rubric layered into the review gate."""

    pinned: list[str] = Field(default_factory=list)
    """Branches/paths the agent must not touch."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    """Per-CLI builder/reviewer models, keyed by the agent CLI name (claude, codex,
    opencode, kimi). A task's CLI — chosen at new-task time — indexes this section;
    its `builder`/`reviewer` are passed verbatim to that CLI's model flag. Because the
    model lives under its CLI's key, a cross-vendor mismatch is unrepresentable: kagan
    does no model-name translation. Write each CLI's own model id (claude resolves its
    native aliases ``opus``/``sonnet``/``haiku`` itself; opencode wants
    ``opencode/claude-*``; codex/kimi want their vendor-native ids). An unconfigured
    CLI uses its own default model. An unknown CLI key is rejected at load."""

    max_concurrent_agents: int = 2
    """Hard cap on agents in flight at once (lever 5). The harness refuses to
    start a new run while this many tasks are RUNNING/VALIDATING — the research's
    parallel-agent cliff after 3 (DESIGN L181). Anti-slot-machine friction, not a
    team metric: it gates generation, never observed."""

    approve_cooldown_seconds: int = 60
    """Mandatory wait after a task lands in REVIEW before approve unlocks (lever
    5). Forces a real read instead of a regenerate-and-rubber-stamp loop. Derived
    at render time from the RUNNING/VALIDATING -> REVIEW event timestamp; never
    written into the committable ledger."""

    agent_timeout_seconds: int = 1800
    """Wall-clock cap on a single agent run (builder, intake, or validator) before
    kagan stops it (F1 bounded execution / circuit breaker). Generous by default (30
    min) so a legitimate long run is never sabotaged; a timed-out builder still has
    its partial diff harvested and lands in REVIEW with a blocking finding, and a
    re-run resumes in the same worktree. Set 0 to disable the cap entirely."""

    high_risk_approvers: int = 2
    """Distinct git identities a HIGH-risk task needs before approve flips it to
    READY (lever 6 cross-team). Low/medium need 1. The bar lives in
    Harness.approve_task, not can_approve; cross-team distinctness needs two
    configured git identities (DESIGN §3.7)."""

    debt_threshold: int | None = None
    """Structural-debt budget (lever 9). When more than this many prior tasks have
    rewritten files under a scope, intake bumps that scope's risk tier UP one level
    (low->medium->high) so the rotting area routes into heavier review. ESCALATION
    ONLY — never a block, never a self-serve override. Unset (None) disables it, so
    the repo behaves exactly like today."""

    @field_validator("risk_tiers")
    @staticmethod
    def _known_tiers(value: dict[str, list[str]]) -> dict[str, list[str]]:
        unknown = sorted(set(value) - set(_RISK_TIERS))
        if unknown:
            raise ValueError(f"unknown risk tier(s) {unknown}; valid tiers are {list(_RISK_TIERS)}")
        return value


def find_repo_root(start: Path | str | None = None) -> Path | None:
    start = Path(start or os.getcwd()).resolve()
    for path in [start, *start.parents]:
        if (path / _CONFIG_DIR / _CONFIG_FILE).is_file():
            return path
    return None


def load_repo_config(repo_root: Path | str) -> RepoConfig:
    manifest_dir = Path(repo_root) / _CONFIG_DIR
    path = manifest_dir / _CONFIG_FILE
    if not path.is_file():
        raise ConfigurationError(context="repo manifest", detail=f"{path} not found")
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            context="repo manifest", detail=f"{path}: invalid YAML: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(
            context="repo manifest",
            detail=f"{path}: expected a top-level mapping, got {type(raw).__name__}",
        )
    try:
        cfg = RepoConfig.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigurationError(context="repo manifest", detail=f"{path}: {details}") from exc
    # P11: resolve a relative rubric path against the manifest's own dir.
    if not cfg.review_rubric.is_absolute():
        cfg.review_rubric = (manifest_dir.parent / cfg.review_rubric).resolve()
    return cfg


def load_review_rubric(repo_root: Path | str) -> str:
    path = load_repo_config(repo_root).review_rubric
    if not path.is_file():
        raise ConfigurationError(context="review rubric", detail=f"{path} not found")
    return path.read_text()
