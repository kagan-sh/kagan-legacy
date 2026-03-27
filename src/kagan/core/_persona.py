import asyncio
import base64
import contextlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from kagan.core._prompts import (
    PERSONA_DEFINITIONS_KEY,
    PERSONA_USER_WHITELIST_KEY,
    load_persona_repo_whitelist,
    serialize_persona_definitions,
)
from kagan.runtime_env import build_sanitized_subprocess_environment

if TYPE_CHECKING:
    from kagan.core._audit import AuditLog
    from kagan.core._settings import Settings


@dataclass(frozen=True)
class TrustAssessment:
    """Reputation-based trust assessment for a persona repository."""

    repo: str
    stars: int
    repo_age_days: int
    audit_risk_level: str  # low, medium, high
    trust_score: float  # 0.0 - 1.0
    trust_tier: str  # low_risk, medium_risk, high_risk
    findings: list[dict[str, Any]]
    archived: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "stars": self.stars,
            "repo_age_days": self.repo_age_days,
            "audit_risk_level": self.audit_risk_level,
            "trust_score": round(self.trust_score, 3),
            "trust_tier": self.trust_tier,
            "findings": self.findings,
            "archived": self.archived,
        }


class PersonaPresetOps:
    def __init__(self, settings_ops: "Settings", audit_ops: "AuditLog") -> None:
        self._settings = settings_ops
        self._audit = audit_ops

    async def audit_repo(
        self,
        *,
        repo: str,
        path: str = ".kagan/personas.json",
        ref: str | None = None,
    ) -> dict[str, Any]:
        _validate_repo_slug(repo)
        _validate_repo_path(path)
        await _ensure_gh_ready()
        repo_meta = await _gh_api_json(["repos", repo])
        if bool(repo_meta.get("private")):
            raise ValueError("Persona sharing only supports public repositories")
        file_payload = await _gh_fetch_content(repo=repo, path=path, ref=ref)
        personas = _decode_persona_payload(file_payload)
        findings = _persona_findings(personas)
        audit_risk_level = _risk_level(findings)

        # Build trust assessment
        trust = _calculate_trust_assessment(repo, repo_meta, findings, audit_risk_level)

        return {
            "repo": repo,
            "repo_url": repo_meta.get("html_url"),
            "path": path,
            "ref": ref,
            "archived": bool(repo_meta.get("archived")),
            "stars": int(repo_meta.get("stargazers_count") or 0),
            "updated_at": repo_meta.get("pushed_at"),
            "created_at": repo_meta.get("created_at"),
            "persona_count": len(personas),
            "personas": self._format_persona_preview(personas),
            "findings": findings,
            "audit_risk_level": audit_risk_level,
            "trust_assessment": trust.to_dict(),
            "trust_tier": trust.trust_tier,
            "disclaimer": (
                "Review source repo and prompts before installing. "
                "This audit is heuristic and does not prove safety."
            ),
        }

    async def preview_import(
        self,
        *,
        repo: str,
        path: str = ".kagan/personas.json",
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Preview personas from a repository without importing."""
        _validate_repo_slug(repo)
        _validate_repo_path(path)
        await _ensure_gh_ready()
        repo_meta = await _gh_api_json(["repos", repo])
        if bool(repo_meta.get("private")):
            raise ValueError("Persona sharing only supports public repositories")
        file_payload = await _gh_fetch_content(repo=repo, path=path, ref=ref)
        personas = _decode_persona_payload(file_payload)
        findings = _persona_findings(personas)
        audit_risk_level = _risk_level(findings)
        trust = _calculate_trust_assessment(repo, repo_meta, findings, audit_risk_level)

        return {
            "repo": repo,
            "repo_url": repo_meta.get("html_url"),
            "path": path,
            "ref": ref,
            "stars": int(repo_meta.get("stargazers_count") or 0),
            "archived": bool(repo_meta.get("archived")),
            "persona_count": len(personas),
            "personas": self._format_persona_preview(personas),
            "findings": findings,
            "audit_risk_level": audit_risk_level,
            "trust_assessment": trust.to_dict(),
            "trust_tier": trust.trust_tier,
        }

    def _format_persona_preview(
        self, personas: Mapping[str, Mapping[str, str]]
    ) -> list[dict[str, str]]:
        """Format personas for preview display."""
        result = []
        for key, item in personas.items():
            prompt = item.get("prompt", "")
            preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
            result.append(
                {
                    "key": key,
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "prompt_preview": preview,
                    "prompt_length": len(prompt),
                }
            )
        return result

    async def import_from_github(
        self,
        *,
        repo: str,
        path: str = ".kagan/personas.json",
        ref: str | None = None,
        acknowledge_risk: bool = False,
        merge_mode: str = "merge",
        auto_confirm: bool = False,
    ) -> dict[str, Any]:
        """Import persona presets with progressive trust.

        Args:
            repo: Repository in owner/repo format
            path: Path to personas.json within the repo
            ref: Git ref (branch/tag/sha)
            acknowledge_risk: Required for high-risk imports
            merge_mode: 'merge' or 'replace'
            auto_confirm: Skip confirmation for low-risk imports
        """
        _validate_repo_slug(repo)
        _validate_repo_path(path)
        if merge_mode not in {"merge", "replace"}:
            raise ValueError("merge_mode must be 'merge' or 'replace'")
        await _ensure_gh_ready()

        # Get repo metadata and content
        repo_meta = await _gh_api_json(["repos", repo])
        if bool(repo_meta.get("private")):
            raise ValueError("Persona sharing only supports public repositories")

        payload = await _gh_fetch_content(repo=repo, path=path, ref=ref)
        imported = _decode_persona_payload(payload)
        findings = _persona_findings(imported)
        audit_risk_level = _risk_level(findings)

        # Calculate trust assessment
        trust = _calculate_trust_assessment(repo, repo_meta, findings, audit_risk_level)

        # Progressive trust logic
        if trust.trust_tier == "high_risk" and not acknowledge_risk:
            raise ValueError(
                f"High-risk repository detected (trust score: {trust.trust_score:.2f}). "
                "Use --acknowledge-risk to proceed after reviewing the source."
            )

        # Determine if we should auto-import
        should_auto_import = auto_confirm and trust.trust_tier == "low_risk"

        # For medium/high risk without auto-confirm, we expect external confirmation
        # This is handled by the caller (CLI/MCP)

        # Perform the import
        settings = await self._settings.get()
        current = _load_personas_from_settings(settings)
        merged = dict(imported) if merge_mode == "replace" else {**current, **imported}
        await self._settings.set({PERSONA_DEFINITIONS_KEY: serialize_persona_definitions(merged)})

        await self._audit.record(
            action="persona.import",
            entity_type="persona_preset",
            entity_id=repo,
            detail={
                "repo": repo,
                "path": path,
                "ref": ref,
                "trust_tier": trust.trust_tier,
                "trust_score": trust.trust_score,
                "merge_mode": merge_mode,
                "imported_keys": sorted(imported.keys()),
                "auto_confirmed": should_auto_import,
            },
        )

        result: dict[str, Any] = {
            "repo": repo,
            "repo_url": repo_meta.get("html_url"),
            "path": path,
            "ref": ref,
            "trust_tier": trust.trust_tier,
            "trust_score": trust.trust_score,
            "imported": sorted(imported.keys()),
            "total_personas": len(merged),
            "auto_confirmed": should_auto_import,
            "disclaimer": (
                "Imported from third-party source. Review source repository and persona prompts."
            ),
        }

        if should_auto_import:
            logger.info(
                f"Auto-imported personas from {repo} (low risk, score: {trust.trust_score:.2f})"
            )

        return result

    async def export_to_github(
        self,
        *,
        repo: str,
        path: str = ".kagan/personas.json",
        branch: str | None = None,
        commit_message: str = "chore: publish kagan persona presets",
    ) -> dict[str, Any]:
        _validate_repo_slug(repo)
        _validate_repo_path(path)
        await _ensure_gh_ready()
        repo_meta = await _gh_api_json(["repos", repo])
        if bool(repo_meta.get("private")):
            raise ValueError("Persona sharing requires a public repository")
        settings = await self._settings.get()
        personas = _load_personas_from_settings(settings)
        content = serialize_persona_definitions(personas)
        file_sha: str | None = None
        with contextlib.suppress(ValueError):
            existing = await _gh_fetch_content(
                repo=repo,
                path=path,
                ref=branch or str(repo_meta.get("default_branch") or "main"),
            )
            if isinstance(existing.get("sha"), str):
                file_sha = str(existing["sha"])
        target_branch = branch or str(repo_meta.get("default_branch") or "main")
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": target_branch,
        }
        if file_sha:
            payload["sha"] = file_sha
        await _gh_api_json(["repos", repo, "contents", path], method="PUT", payload=payload)
        await self._audit.record(
            action="persona.export",
            entity_type="persona_preset",
            entity_id=repo,
            detail={"repo": repo, "path": path, "branch": target_branch, "count": len(personas)},
        )
        return {
            "repo": repo,
            "repo_url": repo_meta.get("html_url"),
            "path": path,
            "branch": target_branch,
            "persona_count": len(personas),
            "disclaimer": "Anyone can read this file in a public repository.",
        }

    async def whitelist_list(self) -> dict[str, list[str]]:
        settings = await self._settings.get()
        user_whitelist = sorted(load_persona_repo_whitelist(settings))
        return {
            "registry_whitelist": sorted(_load_registry_whitelist()),
            "user_whitelist": user_whitelist,
        }

    async def whitelist_add(self, repo: str) -> dict[str, list[str]]:
        _validate_repo_slug(repo)
        settings = await self._settings.get()
        items = set(load_persona_repo_whitelist(settings))
        items.add(repo.lower())
        await self._settings.set({PERSONA_USER_WHITELIST_KEY: json.dumps(sorted(items), indent=2)})
        await self._audit.record(
            action="persona.whitelist.add",
            entity_type="persona_whitelist",
            entity_id=repo.lower(),
            detail={"repo": repo.lower()},
        )
        return {"user_whitelist": sorted(items)}

    async def whitelist_remove(self, repo: str) -> dict[str, list[str]]:
        _validate_repo_slug(repo)
        settings = await self._settings.get()
        items = set(load_persona_repo_whitelist(settings))
        items.discard(repo.lower())
        await self._settings.set({PERSONA_USER_WHITELIST_KEY: json.dumps(sorted(items), indent=2)})
        await self._audit.record(
            action="persona.whitelist.remove",
            entity_type="persona_whitelist",
            entity_id=repo.lower(),
            detail={"repo": repo.lower()},
        )
        return {"user_whitelist": sorted(items)}


def _validate_repo_slug(repo: str) -> None:
    parts = repo.split("/", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError("repo must be in owner/repo format")


def _validate_repo_path(path: str) -> None:
    normalized = path.strip().lstrip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise ValueError("path must be a safe repository-relative path")


async def _run_gh_cmd(*args: str) -> tuple[bytes, bytes, int]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return out, err, cast("int", proc.returncode)


async def _ensure_gh_ready() -> None:
    if shutil.which("gh") is None:
        raise ValueError("GitHub CLI (gh) not found on PATH")
    out, _, returncode = await _run_gh_cmd("gh", "auth", "token")
    if returncode != 0 or not out.strip():
        raise ValueError("GitHub CLI not authenticated. Run `gh auth login`.")


async def _gh_api_json(
    segments: list[str],
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    endpoint = "/".join(seg.strip("/") for seg in segments)
    cmd: list[str] = ["gh", "api", endpoint]
    if method != "GET":
        cmd.extend(["-X", method])
    if payload:
        for key, value in payload.items():
            if isinstance(value, bool):
                value = "true" if value else "false"
            cmd.extend(["-f", f"{key}={value}"])
    out, err, returncode = await _run_gh_cmd(*cmd)
    if returncode != 0:
        raise ValueError(err.decode(errors="replace").strip() or "gh api failed")
    try:
        parsed = json.loads(out.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse gh api response: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Expected object response from gh api")
    return parsed


async def _gh_fetch_content(*, repo: str, path: str, ref: str | None) -> dict[str, Any]:
    endpoint = ["repos", repo, "contents", path.strip().lstrip("/")]
    if ref:
        endpoint[-1] = f"{endpoint[-1]}?ref={ref}"
    return await _gh_api_json(endpoint)


def _decode_persona_payload(file_payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    encoded = file_payload.get("content")
    if not isinstance(encoded, str):
        raise ValueError("Expected a file content payload from GitHub")
    raw = base64.b64decode(encoded.encode("ascii"), validate=False).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Persona preset file must be a JSON object")
    result: dict[str, dict[str, str]] = {}
    for key, item in parsed.items():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not name or not prompt:
            continue
        result[str(key)] = {"name": name, "description": description, "prompt": prompt}
    if not result:
        raise ValueError("No valid personas found in preset file")
    return result


def _load_personas_from_settings(settings: Mapping[str, str]) -> dict[str, dict[str, str]]:
    raw = settings.get(PERSONA_DEFINITIONS_KEY, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(k): v
        for k, v in parsed.items()
        if isinstance(v, dict)
        and isinstance(v.get("name"), str)
        and isinstance(v.get("prompt"), str)
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_registry_whitelist() -> set[str]:
    registry_path = _repo_root() / "registry" / "persona_repo_whitelist.json"
    if not registry_path.exists():
        return set()
    try:
        parsed = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item).strip().lower() for item in parsed if str(item).strip()}


def _persona_findings(personas: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    """Audit persona content for security issues using InjectionDetector.

    Checks for prompt injection patterns, suspicious content, and anomalies.
    """
    from kagan.core._security import InjectionDetector

    findings: list[dict[str, Any]] = []
    detector = InjectionDetector()

    for key, item in personas.items():
        prompt = item.get("prompt", "")

        # Use InjectionDetector for sophisticated pattern detection
        result = detector.analyze(prompt)

        if result["risk_level"] == "DANGEROUS":
            findings.append(
                {
                    "persona": key,
                    "severity": "high",
                    "message": "Potential prompt injection patterns detected",
                    "evidence": [f["name"] for f in result["findings"]],
                    "type": "injection",
                }
            )
        elif result["risk_level"] == "SUSPICIOUS":
            findings.append(
                {
                    "persona": key,
                    "severity": "medium",
                    "message": "Suspicious patterns detected in prompt",
                    "evidence": [f["name"] for f in result["findings"]],
                    "type": "suspicious",
                }
            )

        # Also check for suspicious tokens (simple substring matching)
        suspicious_tokens = ["rm -rf", "curl ", "wget ", "gh auth token"]
        hits = [token for token in suspicious_tokens if token in prompt.lower()]
        if hits:
            findings.append(
                {
                    "persona": key,
                    "severity": "medium",
                    "message": "Prompt contains potentially dangerous shell commands",
                    "evidence": hits,
                    "type": "commands",
                }
            )

        # Check for unusually long prompts (might be trying to hide injection)
        if len(prompt) > 12000:
            findings.append(
                {
                    "persona": key,
                    "severity": "low",
                    "message": "Prompt is unusually long (may hide injection)",
                    "evidence": [f"{len(prompt)} characters"],
                    "type": "length",
                }
            )

    return findings


def _risk_level(findings: list[dict[str, Any]]) -> str:
    severities = {str(item.get("severity", "")) for item in findings}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _calculate_repo_age_days(repo_meta: dict[str, Any]) -> int:
    """Calculate repository age in days from created_at timestamp."""
    from datetime import datetime

    created_at = repo_meta.get("created_at", "")
    if not created_at:
        return 0
    try:
        # Parse ISO 8601 format: 2023-01-15T10:30:00Z
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        return (now - created).days
    except (ValueError, TypeError):
        return 0


def _calculate_trust_assessment(
    repo: str,
    repo_meta: dict[str, Any],
    findings: list[dict[str, Any]],
    audit_risk_level: str,
) -> TrustAssessment:
    """Calculate reputation-based trust assessment using simple, transparent rules.

    Trust tiers are determined by simple rules users can understand:
    - HIGH_RISK: High audit severity, or new/unproven repos (<10 stars AND <30 days)
    - LOW_RISK: Clean audit and either established or has community traction
    - MEDIUM_RISK: Everything else (minor findings, moderate traction, etc.)
    """
    stars = int(repo_meta.get("stargazers_count") or 0)
    archived = bool(repo_meta.get("archived"))
    age_days = _calculate_repo_age_days(repo_meta)

    # Determine trust tier with simple, explainable rules
    # Check high-risk first (exceptional case)
    if audit_risk_level == "high":
        trust_tier = "high_risk"
    elif stars < 10 and age_days < 30:
        # New, unproven repositories are high risk
        trust_tier = "high_risk"
    elif audit_risk_level == "low" and (stars >= 50 or age_days >= 90):
        # Clean audit AND established (either stars or age)
        trust_tier = "low_risk"
    elif findings:
        # Has findings but not high severity
        trust_tier = "medium_risk"
    else:
        # Clean audit but not yet established
        trust_tier = "medium_risk"

    # Transparent score based on tier
    trust_score = {"low_risk": 1.0, "medium_risk": 0.5, "high_risk": 0.0}[trust_tier]

    return TrustAssessment(
        repo=repo,
        stars=stars,
        repo_age_days=age_days,
        audit_risk_level=audit_risk_level,
        trust_score=trust_score,
        trust_tier=trust_tier,
        findings=findings,
        archived=archived,
    )
