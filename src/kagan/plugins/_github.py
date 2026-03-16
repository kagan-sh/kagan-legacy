"""kagan.plugins._github — GitHub Issues import plugin.

Imports open issues from a GitHub repository into a kagan project as tasks.
Uses the ``gh`` CLI for authentication and API access — no token management
needed. Label conventions on the GitHub side auto-map to kagan task properties:

    priority:critical  →  Priority.CRITICAL
    priority:high      →  Priority.HIGH
    priority:medium    →  Priority.MEDIUM
    priority:low       →  Priority.LOW
    kagan:auto         →  WorkMode.AUTO
    kagan:pair         →  WorkMode.PAIR

Sync is idempotent: a mapping of issue numbers → task IDs is persisted in
the kagan settings table. Re-running sync skips already-imported issues.
"""

import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Final, TypedDict

from loguru import logger

from kagan.core import CheckStatus, KaganCore, PreflightCheckResult
from kagan.core.enums import Priority, WorkMode
from kagan.core.errors import KaganError, NotFoundError
from kagan.plugins import ImporterPlugin, ImportResult, PluginError, PluginSyncError
from kagan.runtime_env import build_sanitized_subprocess_environment


class GitHubIssue(TypedDict, total=False):
    number: int
    title: str
    body: str | None
    labels: list[dict[str, Any]]
    state: str
    url: str


# Label prefix → (task field, mapping)
_PRIORITY_LABELS: Final[dict[str, Priority]] = {
    "priority:critical": Priority.CRITICAL,
    "priority:high": Priority.HIGH,
    "priority:medium": Priority.MEDIUM,
    "priority:low": Priority.LOW,
}

_MODE_LABELS: dict[str, WorkMode] = {
    "kagan:auto": WorkMode.AUTO,
    "kagan:pair": WorkMode.PAIR,
}

_GH_JSON_FIELDS = "number,title,body,labels,state,url"


@dataclass(frozen=True)
class GitHubImportConfig:
    """Configuration for a single GitHub import sync."""

    owner: str
    repo: str
    state: str = "open"
    import_label: str | None = None

    @property
    def repo_slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    def settings_key(self) -> str:
        return f"plugin.github.{self.repo_slug}.sync_map"


def _gh_path() -> str | None:
    return shutil.which("gh")


async def _gh_is_authenticated() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            "auth",
            "token",
            env=build_sanitized_subprocess_environment(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return proc.returncode == 0 and bool(stdout.strip())
    except (OSError, FileNotFoundError):
        return False


async def _gh_fetch_issues(config: GitHubImportConfig) -> list[GitHubIssue]:
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
        "100",
    ]
    if config.import_label:
        cmd.extend(["--label", config.import_label])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise PluginSyncError(f"gh issue list failed: {err}")

    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PluginSyncError(f"Failed to parse gh output: {exc}") from exc

    if not isinstance(data, list):
        raise PluginSyncError(f"Expected JSON array from gh, got {type(data).__name__}")

    return data


def _extract_label_names(issue: GitHubIssue) -> list[str]:
    raw = issue.get("labels") or []
    return [lbl["name"] for lbl in raw if isinstance(lbl, dict) and "name" in lbl]


def _map_labels(label_names: list[str]) -> tuple[Priority, WorkMode, list[str]]:
    priority = Priority.MEDIUM
    mode = WorkMode.AUTO
    remaining: list[str] = []

    for name in label_names:
        lower = name.lower()
        if lower in _PRIORITY_LABELS:
            priority = _PRIORITY_LABELS[lower]
        elif lower in _MODE_LABELS:
            mode = _MODE_LABELS[lower]
        else:
            remaining.append(name)

    return priority, mode, remaining


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


class GitHubImporter(ImporterPlugin):
    """Import GitHub issues into kagan as tasks."""

    def __init__(self, config: GitHubImportConfig | None = None) -> None:
        self._config: GitHubImportConfig | None = config
        self._client: KaganCore | None = None

    @property
    def name(self) -> str:
        return "github"

    async def setup(self, client: KaganCore) -> None:
        self._client = client

    async def teardown(self) -> None:
        self._client = None

    def configure(self, config: object) -> None:
        if not isinstance(config, GitHubImportConfig):
            msg = f"Expected GitHubImportConfig, got {type(config).__name__}"
            raise TypeError(msg)
        if not config.owner or not config.repo:
            raise PluginError("configure() requires owner and repo")
        self._config = config

    def preflight(self) -> list[PreflightCheckResult]:
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
                ["gh", "auth", "token"],
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

    async def sync(self, project_id: str) -> ImportResult:
        if self._client is None:
            raise PluginError("Plugin not set up — call setup() first")
        if self._config is None:
            raise PluginError("Plugin not configured — call configure() first")

        client = self._client
        config = self._config

        if _gh_path() is None:
            raise PluginError("GitHub CLI (gh) not found. Install → https://cli.github.com")
        if not await _gh_is_authenticated():
            raise PluginError("GitHub CLI not authenticated. Run → gh auth login")

        issues = await _gh_fetch_issues(config)
        logger.info(
            "GitHub sync: fetched {} issues from {}",
            len(issues),
            config.repo_slug,
        )

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
                    client,
                    project_id,
                    number,
                    issue,
                    sync_map,
                    result,
                )
            except (PluginError, KaganError) as exc:
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
        priority, mode, extra_labels = _map_labels(label_names)
        description = _build_description(issue, extra_labels)

        task = await client.tasks.create(
            title,
            description=description,
            priority=priority,
            execution_mode=mode,
        )
        sync_map[number] = task.id
        return ImportResult(
            created=result.created + 1,
            updated=result.updated,
            skipped=result.skipped,
            errors=result.errors,
        )


__all__ = [
    "GitHubImportConfig",
    "GitHubImporter",
]
