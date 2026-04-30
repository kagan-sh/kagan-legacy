"""kagan.core.integrations.github — GitHub Issues integration.

Imports open (or closed / all) issues from a GitHub repository into a kagan
project as tasks.  Uses the ``gh`` CLI for auth — no token management needed.

Label conventions on the GitHub side auto-map to kagan task priorities:

    priority:critical  →  Priority.CRITICAL
    priority:high      →  Priority.HIGH
    priority:medium    →  Priority.MEDIUM
    priority:low       →  Priority.LOW

Sync is idempotent: a mapping of issue numbers → task IDs is persisted in
the kagan settings table.  Re-running sync skips already-imported issues.

Design choice: ``github`` (the module-level singleton) is instantiated once
without a client reference; it receives the client only at call time. The
class is testable: tests can pass a mock client to each method directly.

The module exports a singleton ``github = GitHubIntegration()`` so callers
can write ``from kagan.core.integrations import github`` and use it directly,
or import the class for testing.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, TypedDict
from urllib.parse import urlparse

from loguru import logger

from kagan.core import CheckStatus, KaganCore, PreflightCheckResult
from kagan.core._subprocess import resolve_spawn_command
from kagan.core.enums import Priority
from kagan.core.errors import KaganError, NotFoundError
from kagan.core.integrations._base import ExternalItem, ImportResult
from kagan.runtime_env import build_sanitized_subprocess_environment

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_IMPORT_STATES: frozenset[str] = frozenset({"open", "closed", "all"})

_PRIORITY_LABELS: Final[dict[str, Priority]] = {
    "priority:critical": Priority.CRITICAL,
    "priority:high": Priority.HIGH,
    "priority:medium": Priority.MEDIUM,
    "priority:low": Priority.LOW,
}

_GH_JSON_FIELDS = "number,title,body,labels,state,url"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitHubConfig:
    """Configuration for a single GitHub import sync."""

    owner: str
    repo: str
    state: str = "open"
    labels: tuple[str, ...] = ()
    limit: int = 100
    issue_numbers: tuple[int, ...] = ()

    @property
    def repo_slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    def settings_key(self) -> str:
        return f"integration.github.{self.repo_slug}.sync_map"


# ---------------------------------------------------------------------------
# TypedDicts for raw gh CLI output
# ---------------------------------------------------------------------------


class GitHubIssue(TypedDict, total=False):
    number: int
    title: str
    body: str | None
    labels: list[dict[str, Any]]
    state: str
    url: str


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def normalize_github_state(state: str) -> str:
    normalized = state.strip().lower()
    if normalized not in GITHUB_IMPORT_STATES:
        supported = ", ".join(sorted(GITHUB_IMPORT_STATES))
        raise ValueError(f"Issue state must be one of: {supported}")
    return normalized


def canonical_repo_slug(repo_slug: str) -> str:
    value = repo_slug.strip()
    if "/" not in value:
        raise ValueError(
            "Repository must use owner/repo format (for example octocat/hello-world)"
        )
    owner, name = value.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name or " " in owner or " " in name:
        raise ValueError(
            "Repository must use owner/repo format (for example octocat/hello-world)"
        )
    return f"{owner}/{name}"


def _is_allowed_github_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.strip().lower().rstrip(".")
    return normalized == "github.com" or normalized.endswith(".github.com")


def parse_github_repo_slug_from_remote_url(remote_url: str) -> str | None:
    value = remote_url.strip()
    if not value:
        return None

    path = ""
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
    else:
        parsed = urlparse(value)
        if _is_allowed_github_host(parsed.hostname):
            path = parsed.path.lstrip("/")

    if not path:
        return None

    normalized_path = path.removesuffix(".git").strip("/")
    parts = [segment for segment in normalized_path.split("/") if segment]
    if len(parts) != 2:
        return None

    owner, repo = parts
    try:
        return canonical_repo_slug(f"{owner}/{repo}")
    except ValueError:
        return None


async def detect_github_repo_slug_from_origin(repo_path: str | Path) -> str | None:
    repo = Path(repo_path)
    proc = await asyncio.create_subprocess_exec(
        "git",
        "remote",
        "get-url",
        "origin",
        cwd=repo,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    remote_url = stdout.decode(errors="replace").strip()
    return parse_github_repo_slug_from_remote_url(remote_url)


def github_blocking_checks(checks: list[PreflightCheckResult]) -> list[PreflightCheckResult]:
    return [check for check in checks if check.status.value != "pass"]


def format_github_setup_message(checks: list[PreflightCheckResult]) -> str:
    blocked = github_blocking_checks(checks)
    if not blocked:
        return "GitHub setup looks good. Enter a repository and continue."

    lines: list[str] = ["GitHub setup is required before import:"]
    for check in blocked:
        lines.append(f"- {check.message}")
        if check.fix_hint:
            lines.append(f"  Fix: {check.fix_hint}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Low-level gh CLI wrappers (module-level, testable via patch)
# ---------------------------------------------------------------------------


def _gh_path() -> str | None:
    return shutil.which("gh")


async def _gh_is_authenticated() -> bool:
    try:
        resolved = resolve_spawn_command("gh", "auth", "token")
        proc = await asyncio.create_subprocess_exec(
            *resolved,
            env=build_sanitized_subprocess_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return proc.returncode == 0 and bool(stdout.strip())
    except (OSError, FileNotFoundError):
        return False


async def _gh_fetch_issues(config: GitHubConfig) -> list[GitHubIssue]:
    cmd: list[str] = [
        "gh",
        "issue",
        "list",
        "--repo",
        config.repo_slug,
        "--state",
        config.state,
        "--json",
        _GH_JSON_FIELDS,
        "--limit",
        str(config.limit),
    ]
    for lbl in config.labels:
        cmd.extend(["--label", lbl])

    resolved = resolve_spawn_command(cmd[0], *cmd[1:])
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh issue list failed: {err}")

    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise KaganError(f"Failed to parse gh output: {exc}") from exc

    if not isinstance(data, list):
        raise KaganError(f"Expected JSON array from gh, got {type(data).__name__}")

    return data


# ---------------------------------------------------------------------------
# Pure helper functions (label parsing, description building)
# ---------------------------------------------------------------------------


def _extract_label_names(issue: GitHubIssue) -> list[str]:
    raw = issue.get("labels") or []
    return [lbl["name"] for lbl in raw if isinstance(lbl, dict) and "name" in lbl]


def _map_labels(label_names: list[str]) -> tuple[Priority, list[str]]:
    priority = Priority.MEDIUM
    remaining: list[str] = []
    for name in label_names:
        lower = name.lower()
        if lower in _PRIORITY_LABELS:
            priority = _PRIORITY_LABELS[lower]
        else:
            remaining.append(name)
    return priority, remaining


def _build_description(issue: GitHubIssue, extra_labels: list[str]) -> str:
    parts: list[str] = []

    if url := issue.get("url"):
        parts.append(url)

    if extra_labels:
        tags = " ".join(f"[{lbl}]" for lbl in extra_labels)
        parts.append(tags)

    body = (issue.get("body") or "").strip()
    if body:
        parts.append(body)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Sync-map persistence helpers
# ---------------------------------------------------------------------------


async def _load_sync_map(client: KaganCore, key: str) -> dict[str, str]:
    settings = await client.settings.get()
    raw = settings.get(key, "{}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def _save_sync_map(client: KaganCore, key: str, sync_map: dict[str, str]) -> None:
    await client.settings.set({key: json.dumps(sync_map, separators=(",", ":"))})


# ---------------------------------------------------------------------------
# GitHubIntegration class
# ---------------------------------------------------------------------------


class GitHubIntegration:
    """GitHub Issues integration implementing the Integration protocol.

    The class is instantiated once (as the module-level ``github`` singleton)
    and receives the ``KaganCore`` client and ``GitHubConfig`` at call time.
    This avoids any lifecycle (setup/teardown) machinery.

    Usage::

        from kagan.core.integrations import github

        result = await github.sync(client, config, project_id)
        items   = await github.preview(client, config, project_id)
        checks  = github.preflight()
    """

    id: str = "github"

    # -- Preflight ----------------------------------------------------------

    def preflight(self) -> list[PreflightCheckResult]:
        """Return health checks for gh CLI availability and auth."""
        checks: list[PreflightCheckResult] = []
        gh = _gh_path()
        if gh is None:
            checks.append(
                PreflightCheckResult(
                    name="gh_cli",
                    status=CheckStatus.WARN,
                    message="GitHub CLI (gh) not found on PATH",
                    fix_hint="Install → https://cli.github.com",
                )
            )
            return checks

        checks.append(
            PreflightCheckResult(
                name="gh_cli",
                status=CheckStatus.PASS,
                message=f"gh found at {gh}",
                fix_hint="",
            )
        )

        try:
            result = subprocess.run(
                resolve_spawn_command("gh", "auth", "token"),
                capture_output=True,
                text=True,
                timeout=5,
                env=build_sanitized_subprocess_environment(),
            )
            if result.returncode == 0 and result.stdout.strip():
                checks.append(
                    PreflightCheckResult(
                        name="gh_auth",
                        status=CheckStatus.PASS,
                        message="gh authenticated",
                        fix_hint="",
                    )
                )
            else:
                checks.append(
                    PreflightCheckResult(
                        name="gh_auth",
                        status=CheckStatus.WARN,
                        message="GitHub CLI not authenticated",
                        fix_hint="Run → gh auth login",
                    )
                )
        except (OSError, subprocess.TimeoutExpired):
            checks.append(
                PreflightCheckResult(
                    name="gh_auth",
                    status=CheckStatus.WARN,
                    message="Could not verify gh authentication",
                    fix_hint="Run → gh auth login",
                )
            )

        return checks

    # -- Internal helpers ---------------------------------------------------

    async def _fetch_issues(
        self, config: GitHubConfig
    ) -> list[GitHubIssue]:
        """Validate prerequisites and fetch issues from GitHub."""
        if _gh_path() is None:
            raise KaganError("GitHub CLI (gh) not found. Install → https://cli.github.com")
        if not await _gh_is_authenticated():
            raise KaganError("GitHub CLI not authenticated. Run → gh auth login")

        issues = await _gh_fetch_issues(config)
        logger.info(
            "GitHub fetch: {} issues from {}",
            len(issues),
            config.repo_slug,
        )

        if config.issue_numbers:
            allowed = set(config.issue_numbers)
            issues = [i for i in issues if i.get("number") in allowed]

        return issues

    async def _sync_single_issue(
        self,
        client: KaganCore,
        project_id: str,
        number: str,
        issue: GitHubIssue,
        sync_map: dict[str, str],
        result: ImportResult,
    ) -> ImportResult:
        title = (issue.get("title") or "").strip()

        if number in sync_map:
            task_id = sync_map[number]
            try:
                await client.tasks.get(task_id)
                return ImportResult(
                    created=result.created,
                    updated=result.updated,
                    skipped=result.skipped + 1,
                    errors=result.errors,
                )
            except NotFoundError:
                logger.debug("Task {} for issue #{} was deleted, re-importing", task_id, number)

        label_names = _extract_label_names(issue)
        priority, extra_labels = _map_labels(label_names)
        description = _build_description(issue, extra_labels)

        task = await client.tasks.create(
            title,
            description=description,
            priority=priority,
        )
        sync_map[number] = task.id
        return ImportResult(
            created=result.created + 1,
            updated=result.updated,
            skipped=result.skipped,
            errors=result.errors,
        )

    # -- Public API ---------------------------------------------------------

    async def sync(
        self,
        client: KaganCore,
        config: GitHubConfig,
        project_id: str,
    ) -> ImportResult:
        """Pull GitHub issues into the given project.  Idempotent."""
        issues = await self._fetch_issues(config)
        settings_key = config.settings_key()
        sync_map = await _load_sync_map(client, settings_key)
        result = ImportResult()

        for issue in issues:
            number = str(issue.get("number", ""))
            title = (issue.get("title") or "").strip()
            if not number or not title:
                result = result.with_error(f"Issue missing number or title: {issue}")
                continue

            try:
                result = await self._sync_single_issue(
                    client, project_id, number, issue, sync_map, result
                )
            except KaganError as exc:
                result = result.with_error(f"Issue #{number}: {exc}")
                logger.opt(exception=True).warning("Failed to sync issue #{}", number)

        await _save_sync_map(client, settings_key, sync_map)
        logger.info(
            "GitHub sync complete: created={} skipped={} errors={}",
            result.created,
            result.skipped,
            len(result.errors),
        )
        return result

    async def preview(
        self,
        client: KaganCore,
        config: GitHubConfig,
        project_id: str,
    ) -> list[ExternalItem]:
        """Fetch issues matching config and return preview without importing."""
        issues = await self._fetch_issues(config)
        sync_map = await _load_sync_map(client, config.settings_key())

        items: list[ExternalItem] = []
        for issue in issues:
            number = issue.get("number")
            title = (issue.get("title") or "").strip()
            if not number or not title:
                continue
            label_names = _extract_label_names(issue)
            items.append(
                ExternalItem(
                    id=str(number),
                    title=title,
                    url=issue.get("url", ""),
                    state=issue.get("state", "open"),
                    labels=tuple(label_names),
                    already_synced=str(number) in sync_map,
                    # Keep raw number for consumers that need it
                    extra={"number": number},
                )
            )
        return items


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

github = GitHubIntegration()


# ---------------------------------------------------------------------------
# Convenience wrappers (used by TUI, CLI, server routes)
# ---------------------------------------------------------------------------


async def github_preflight_checks(client: KaganCore) -> list[PreflightCheckResult]:
    """Return preflight checks for the GitHub integration."""
    return github.preflight()


async def sync_github_issues(
    client: KaganCore,
    *,
    project_id: str,
    repo_slug: str,
    state: str = "open",
    labels: list[str] | None = None,
    limit: int = 100,
    issue_numbers: list[int] | None = None,
) -> ImportResult:
    """Convenience wrapper: build config and call github.sync()."""
    normalized_state = normalize_github_state(state)
    canonical = canonical_repo_slug(repo_slug)
    owner, repo = canonical.split("/", 1)
    config = GitHubConfig(
        owner=owner,
        repo=repo,
        state=normalized_state,
        labels=tuple(labels or ()),
        limit=limit,
        issue_numbers=tuple(issue_numbers or ()),
    )
    return await github.sync(client, config, project_id)


async def preview_github_issues(
    client: KaganCore,
    *,
    project_id: str,
    repo_slug: str,
    state: str = "open",
    labels: list[str] | None = None,
    limit: int = 100,
    issue_numbers: list[int] | None = None,
) -> list[ExternalItem]:
    """Convenience wrapper: build config and call github.preview()."""
    normalized_state = normalize_github_state(state)
    canonical = canonical_repo_slug(repo_slug)
    owner, repo = canonical.split("/", 1)
    config = GitHubConfig(
        owner=owner,
        repo=repo,
        state=normalized_state,
        labels=tuple(labels or ()),
        limit=limit,
        issue_numbers=tuple(issue_numbers or ()),
    )
    return await github.preview(client, config, project_id)


__all__ = [
    "GITHUB_IMPORT_STATES",
    "GitHubConfig",
    "GitHubIntegration",
    "GitHubIssue",
    "canonical_repo_slug",
    "detect_github_repo_slug_from_origin",
    "format_github_setup_message",
    "github",
    "github_blocking_checks",
    "github_preflight_checks",
    "normalize_github_state",
    "parse_github_repo_slug_from_remote_url",
    "preview_github_issues",
    "sync_github_issues",
]
