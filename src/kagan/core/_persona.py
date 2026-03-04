import asyncio
import base64
import contextlib
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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
        risk_level = _risk_level(findings)
        return {
            "repo": repo,
            "repo_url": repo_meta.get("html_url"),
            "path": path,
            "ref": ref,
            "archived": bool(repo_meta.get("archived")),
            "stars": int(repo_meta.get("stargazers_count") or 0),
            "updated_at": repo_meta.get("pushed_at"),
            "persona_count": len(personas),
            "findings": findings,
            "risk_level": risk_level,
            "disclaimer": (
                "Review source repo and prompts before installing. "
                "This audit is heuristic and does not prove safety."
            ),
        }

    async def import_from_github(
        self,
        *,
        repo: str,
        path: str = ".kagan/personas.json",
        ref: str | None = None,
        allow_untrusted: bool = False,
        acknowledge_risk: bool = False,
        merge_mode: str = "merge",
    ) -> dict[str, Any]:
        _validate_repo_slug(repo)
        _validate_repo_path(path)
        if merge_mode not in {"merge", "replace"}:
            raise ValueError("merge_mode must be 'merge' or 'replace'")
        await _ensure_gh_ready()
        settings = await self._settings.get()
        trusted = await _is_repo_trusted(repo, settings)
        if not trusted and not (allow_untrusted and acknowledge_risk):
            raise ValueError(
                "Repository is not trusted. Add it to whitelist or set allow_untrusted=true "
                "with acknowledge_risk=true after due diligence."
            )
        repo_meta = await _gh_api_json(["repos", repo])
        if bool(repo_meta.get("private")):
            raise ValueError("Persona sharing only supports public repositories")
        payload = await _gh_fetch_content(repo=repo, path=path, ref=ref)
        imported = _decode_persona_payload(payload)
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
                "trusted": trusted,
                "allow_untrusted": allow_untrusted,
                "merge_mode": merge_mode,
                "imported_keys": sorted(imported.keys()),
            },
        )
        return {
            "repo": repo,
            "repo_url": repo_meta.get("html_url"),
            "path": path,
            "ref": ref,
            "trusted": trusted,
            "imported": sorted(imported.keys()),
            "total_personas": len(merged),
            "disclaimer": (
                "Imported from third-party source. Review source repository and persona prompts."
            ),
        }

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


async def _is_repo_trusted(repo: str, settings: Mapping[str, str]) -> bool:
    slug = repo.strip().lower()
    if slug in _load_registry_whitelist():
        return True
    return slug in load_persona_repo_whitelist(dict(settings))


def _persona_findings(personas: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    suspicious = ["rm -rf", "curl ", "wget ", "gh auth token", "password", "secret", "token"]
    for key, item in personas.items():
        prompt = item.get("prompt", "")
        hits = [token for token in suspicious if token in prompt.lower()]
        if hits:
            findings.append(
                {
                    "persona": key,
                    "severity": "medium",
                    "message": "Prompt contains security-sensitive tokens",
                    "evidence": hits,
                }
            )
        if len(prompt) > 12000:
            findings.append(
                {
                    "persona": key,
                    "severity": "low",
                    "message": "Prompt is unusually long",
                    "evidence": [len(prompt)],
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
