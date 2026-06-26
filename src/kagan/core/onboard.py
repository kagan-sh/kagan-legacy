"""Onboarding logic for `kagan init` (Phase 14) — pure, no prompt-toolkit.

The agent PROPOSES a manifest (read-only, via `agent.launch_manifest_draft`); this
module parses that proposal, scans each proposed command for obviously-dangerous
shapes BEFORE any human approves it, holds the deterministic floor templates for the
no-agent case, and renders the human-approved fields to validated `.kagan/repo.yaml`.

The trust boundary is the human gate in the CLI, not this module: nothing here runs a
command. `flag_dangerous` only nudges; `render_manifest_yaml` validates through
``RepoConfig`` so an init-written manifest can never be one the loader would reject.
"""

import re
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import yaml

from kagan.core.config import RepoConfig
from kagan.core.errors import ConfigurationError
from kagan.runtime_env import build_sanitized_subprocess_environment

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.core.models import ReportMessage

# Deterministic risk-lint. The ONE place a deterministic scan is correct: it reads the
# command STRING, not the repo's framework — so it never rots. Order matters only for
# which single reason surfaces first; every pattern is a "make the human look twice" nudge.
_DANGER_PATTERNS: tuple[tuple[str, str], ...] = (
    (r":\s*\(\s*\)\s*\{", "fork bomb"),
    (r"\brm\s+-[a-z]*[rf]", "deletes files (rm -r/-f)"),
    (r"\brm\b[^\n]*--(?:recursive|force)", "deletes files (rm --recursive/--force)"),
    (r"\bfind\b[^\n]*-delete\b", "bulk deletes files (find -delete)"),
    (r"\bchmod\b[^\n]*777", "world-writable permissions (chmod 777)"),
    (r"\b(?:sudo|doas)\b", "runs with elevated privileges"),
    (r"\bmkfs\b", "formats a filesystem (mkfs)"),
    (r"\bdd\s+if=", "raw disk write (dd)"),
    (r"\|\s*(?:sh|bash|zsh)\b", "pipes content into a shell"),
    (r"\bgit\s+push\b", "pushes to a remote (git push)"),
    (r"\b(?:curl|wget)\b", "makes network requests (curl/wget)"),
    (r"\b(?:ssh|scp|nc|telnet)\b", "opens a remote network connection"),
    (r">\s*/(?:dev|etc|usr|bin|boot|sys|proc)\b", "writes to a system path"),
)


def flag_dangerous(command: str) -> str | None:
    """Return a short reason if the command matches a dangerous shape, else None.

    Not a sandbox and not a guarantee — a nudge that forces an extra confirm in the
    walk. A human who approves past it gets what they approved (the residual risk)."""
    for pattern, reason in _DANGER_PATTERNS:
        if re.search(pattern, command):
            return reason
    return None


@dataclass(frozen=True, slots=True)
class ProposedCheck:
    name: str
    command: str
    provenance: str = (
        "invented"  # ci|precommit|scripts|makefile|pyproject|lockfile|instructions|invented|edited
    )
    source: str = ""


@dataclass(slots=True)
class ManifestDraft:
    base_branch: str = "main"
    checks: list[ProposedCheck] = field(default_factory=list)
    risk_tiers: dict[str, list[str]] = field(default_factory=dict)
    services: dict[str, dict] = field(default_factory=dict)
    security: str | None = None
    builder: str | None = None
    reviewer: str | None = None


def parse_manifest_report(reports: list[ReportMessage]) -> ManifestDraft | None:
    """Pull the agent's `manifest` envelope (the last one wins) into a ManifestDraft.

    Returns None when the agent reported no manifest — the caller falls to the
    deterministic skeleton. Tolerant of a partial/odd payload: every field is
    defaulted and bad-shaped entries are dropped rather than raising, because a
    flaky draft must degrade to the floor, not crash onboarding (rule 12)."""
    payload: dict | None = None
    for msg in reports:
        if msg.type == "manifest" and isinstance(msg.payload, dict):
            payload = msg.payload
    if payload is None:
        return None
    return _draft_from_payload(payload)


def _draft_from_payload(payload: dict) -> ManifestDraft:
    # Sanitize at parse so a parsed draft is ALWAYS loader-valid: an unknown risk tier,
    # an extra/malformed service field, or a non-dict sibling must never crash the write
    # AFTER the human's walk (rule 12 — a flaky draft degrades, it doesn't strand work).
    from kagan.core.config import ServiceConfig
    from kagan.core.risk import TIERS as _KNOWN_TIERS

    checks: list[ProposedCheck] = []
    seen: set[str] = set()
    for raw in payload.get("checks") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        command = str(raw.get("command", "")).strip()
        if not name or not command or name in seen:  # first wins — no silent overwrite
            continue
        seen.add(name)
        checks.append(
            ProposedCheck(
                name=name,
                command=command,
                provenance=str(raw.get("provenance", "invented")).strip() or "invented",
                source=str(raw.get("source", "")).strip(),
            )
        )

    raw_tiers = payload.get("risk_tiers")
    risk_tiers: dict[str, list[str]] = {}
    if isinstance(raw_tiers, dict):
        for tier, globs in raw_tiers.items():
            if tier in _KNOWN_TIERS and isinstance(globs, list):
                risk_tiers[tier] = [str(g) for g in globs]

    raw_services = payload.get("services")
    services: dict[str, dict] = {}
    if isinstance(raw_services, dict):
        for sname, spec in raw_services.items():
            if not isinstance(spec, dict):
                continue
            try:
                ServiceConfig.model_validate(spec)  # drop a service the loader would reject
            except Exception:
                continue
            services[str(sname)] = spec

    def _str_or_none(value: object) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    return ManifestDraft(
        base_branch=str(payload.get("base_branch") or "main"),
        checks=checks,
        risk_tiers=risk_tiers,
        services=services,
        security=_str_or_none(payload.get("security")),
        builder=_str_or_none(payload.get("builder")),
        reviewer=_str_or_none(payload.get("reviewer")),
    )


def render_manifest_yaml(config: dict) -> str:
    """Validate the assembled config through RepoConfig, then dump it to YAML.

    Validating first (rule 8) means `kagan init` can never write a manifest the
    loader would reject — the gate is structural, not a comment in a prompt. Dumps
    the plain dict (not the model) so paths stay relative strings, not resolved."""
    cleaned = {k: v for k, v in config.items() if v not in (None, {}, [], "")}
    try:
        RepoConfig.model_validate(cleaned)
    except Exception as exc:  # pydantic ValidationError or value errors from validators
        raise ConfigurationError(context="init manifest", detail=str(exc)) from exc
    header = "# .kagan/repo.yaml — generated by `kagan init`; edit freely by hand.\n"
    body = yaml.safe_dump(cleaned, sort_keys=False, default_flow_style=False)
    return header + body


def skeleton_manifest() -> str:
    """The deterministic floor: a valid, mostly-commented manifest for the no-agent
    case. Parses to a valid RepoConfig (only project_name/base_branch are live)."""
    return (
        "# .kagan/repo.yaml — generated by `kagan init`. Fill in your own commands.\n"
        "base_branch: main\n"
        "\n"
        "# checks: name -> shell command. The gate runs each on every review.\n"
        "# checks:\n"
        "#   build: <your build command>\n"
        "#   lint: <your lint command>\n"
        "#   test: <your test command>\n"
        "\n"
        "# risk_tiers route ceremony by scope. high = validator + comprehension + 2nd\n"
        "# approver; low skips them. Unset leaves every task medium.\n"
        "# risk_tiers:\n"
        "#   low: [docs/**]\n"
        "#   high: [src/auth/**, migrations/**]\n"
        "\n"
        "# reviewer: model for the adversarial validator (a 2nd opinion on the diff).\n"
        "# Unset DISABLES that stage. A different size of the same vendor is fine.\n"
        "# reviewer: <model>\n"
        "# builder: <model>\n"
    )


def recommended_gitignore() -> str:
    """Project-agnostic defaults — OS/editor cruft, env/secrets, logs, and kagan's own
    operational state (the committable subset stays tracked)."""
    return (
        "# OS\n.DS_Store\nThumbs.db\n"
        "# Editor\n.vscode/\n.idea/\n*.swp\n"
        "# Environment / secrets\n.env\n.env.*\n"
        "# Logs\n*.log\n"
        "# kagan operational state (committable subset stays tracked)\n"
        ".kagan/state/\n.kagan_worktrees/\n"
    )


def init_git_repo(root: Path) -> bool:
    """`git init` + a recommended `.gitignore` + an initial commit. Returns True only on
    a repo with a commit (kagan needs a HEAD: per-task worktrees fork from it).

    A bootstrap identity is used for THIS commit only when none is configured, so a
    fresh machine isn't dead-ended. Safe if `.git` already exists (skips init)."""
    env = build_sanitized_subprocess_environment()

    def _git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    try:
        if _git("rev-parse", "--git-dir").returncode != 0 and _git("init").returncode != 0:
            return False
        gitignore = root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(recommended_gitignore(), encoding="utf-8")
        _git("add", "-A")
        msg = "chore: initialize repository (kagan init)"
        res = _git("commit", "-m", msg)
        if res.returncode != 0:
            blob = (res.stderr + res.stdout).lower()
            if any(s in blob for s in ("user.email", "user.name", "tell me who you are")):
                res = _git(
                    "-c", "user.name=kagan", "-c", "user.email=kagan@localhost", "commit", "-m", msg
                )
        return res.returncode == 0
    except OSError, subprocess.SubprocessError:
        return False


def starter_rubric() -> str:
    """A minimal review rubric so the gate has something to layer in on day one."""
    return (
        "# Review rubric\n\n"
        "What a reviewer must confirm before approving a change in this repo. Edit to "
        "fit the project — this is a starting point.\n\n"
        "- The change does what the task asked, and nothing out of scope.\n"
        "- Every declared check passes; failures are understood, not waved through.\n"
        "- New behaviour is covered by a test that fails without the change.\n"
        "- No secrets, credentials, or tokens added to the tree.\n"
        "- Errors are handled where they can actually occur; no silent except-pass.\n"
        "- The human can explain, in their own words, why the change is correct.\n"
    )


__all__ = [
    "ManifestDraft",
    "ProposedCheck",
    "flag_dangerous",
    "init_git_repo",
    "parse_manifest_report",
    "recommended_gitignore",
    "render_manifest_yaml",
    "skeleton_manifest",
    "starter_rubric",
]
