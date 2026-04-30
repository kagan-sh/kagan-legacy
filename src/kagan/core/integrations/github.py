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

Body round-trip policy: ``task.description = issue.body`` verbatim, both
directions.  No URL prefix, no ``[label]`` tags in the description.

Acceptance-criteria sync: on first import, ``- [ ]`` / ``- [x]`` lines in the
issue body are seeded as criteria.  On subsequent pulls and whenever criteria
change in kagan, a tagged comment (marked with ``_KAGAN_CRITERIA_MARKER``) is
upserted on the issue so the checklist stays in sync.

Status is fully decoupled: kagan task status changes never touch the GitHub
issue; GitHub issue state changes never touch the task.

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
import re
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

_GH_JSON_FIELDS = "number,title,body,labels,state,url,updatedAt"

_KAGAN_CRITERIA_MARKER: Final[str] = "<!-- kagan:acceptance-criteria -->"

_CRITERIA_LINE_RE = re.compile(r"^\s*- \[([xX ])\] (.+)$")


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
    target_repo_id: str | None = None

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
    updatedAt: str


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
        raise ValueError("Repository must use owner/repo format (for example octocat/hello-world)")
    owner, name = value.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name or " " in owner or " " in name:
        raise ValueError("Repository must use owner/repo format (for example octocat/hello-world)")
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


async def _gh_view_issue(repo_slug: str, number: int) -> dict[str, Any]:
    """Fetch a single issue from GitHub using gh CLI.

    Returns a dict with keys: number, title, body, labels, state, url, updatedAt.
    Raises KaganError on failure.
    """
    fields = "number,title,body,labels,state,url,updatedAt"
    resolved = resolve_spawn_command(
        "gh", "issue", "view", str(number), "--repo", repo_slug, "--json", fields
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh issue view failed for {repo_slug}#{number}: {err}")
    try:
        return json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise KaganError(f"Failed to parse gh issue view output: {exc}") from exc


async def _gh_list_comments(repo_slug: str, number: int) -> list[dict[str, Any]]:
    """List comments on a GitHub issue using gh API.

    Returns a list of comment dicts (id, body, user, created_at, updated_at).
    """
    resolved = resolve_spawn_command("gh", "api", f"repos/{repo_slug}/issues/{number}/comments")
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh api comments failed for {repo_slug}#{number}: {err}")
    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise KaganError(f"Failed to parse gh api comments output: {exc}") from exc
    return data if isinstance(data, list) else []


async def _gh_create_comment(repo_slug: str, number: int, body: str) -> int:
    """Create a comment on a GitHub issue and return its comment id.

    Parses the comment URL printed by ``gh issue comment`` to extract the id.
    Raises KaganError on failure.
    """
    resolved = resolve_spawn_command(
        "gh", "issue", "comment", str(number), "--repo", repo_slug, "--body", body
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh issue comment failed for {repo_slug}#{number}: {err}")
    # gh prints the comment URL, e.g.:
    # https://github.com/owner/repo/issues/42#issuecomment-123456789
    url = stdout.decode("utf-8").strip()
    match = re.search(r"issuecomment-(\d+)", url)
    if match:
        return int(match.group(1))
    # Fallback: we created successfully but couldn't parse id
    return 0


async def _gh_update_comment(repo_slug: str, comment_id: int, body: str) -> None:
    """Update an existing comment on a GitHub issue via gh API PATCH.

    Raises KaganError on failure.
    """
    resolved = resolve_spawn_command(
        "gh",
        "api",
        "-X",
        "PATCH",
        f"repos/{repo_slug}/issues/comments/{comment_id}",
        "-f",
        f"body={body}",
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh api PATCH comment {comment_id} failed: {err}")


async def _gh_create_issue(repo_slug: str, title: str, body: str) -> int:
    """Create a new GitHub issue and return its issue number.

    Parses the issue URL printed by ``gh issue create``.
    Raises KaganError on failure.
    """
    resolved = resolve_spawn_command(
        "gh",
        "issue",
        "create",
        "--repo",
        repo_slug,
        "--title",
        title,
        "--body",
        body,
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh issue create failed for {repo_slug}: {err}")
    url = stdout.decode("utf-8").strip()
    # URL format: https://github.com/owner/repo/issues/42
    match = re.search(r"/issues/(\d+)$", url)
    if not match:
        raise KaganError(f"Could not parse issue number from gh output: {url!r}")
    return int(match.group(1))


async def _gh_edit_issue(
    repo_slug: str,
    number: int,
    *,
    title: str | None = None,
    body: str | None = None,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> None:
    """Edit a GitHub issue title, body, and/or labels via gh CLI.

    Skips the call entirely when no arguments are set.
    Raises KaganError on failure.
    """
    cmd: list[str] = ["gh", "issue", "edit", str(number), "--repo", repo_slug]
    if title is not None:
        cmd.extend(["--title", title])
    if body is not None:
        cmd.extend(["--body", body])
    for lbl in add_labels or []:
        cmd.extend(["--add-label", lbl])
    for lbl in remove_labels or []:
        cmd.extend(["--remove-label", lbl])

    # Nothing to do — all args were None/empty
    if len(cmd) == 6:  # only "gh issue edit <n> --repo <slug>"
        return

    resolved = resolve_spawn_command(cmd[0], *cmd[1:])
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh issue edit failed for {repo_slug}#{number}: {err}")


async def _gh_ensure_label(repo_slug: str, name: str) -> None:
    """Create a label in the repo, or update it if it already exists (--force).

    Colors are chosen by a fixed palette keyed on the label name.
    Raises KaganError on failure.
    """
    _LABEL_COLORS: dict[str, str] = {
        "priority:critical": "B60205",
        "priority:high": "D93F0B",
        "priority:medium": "FBCA04",
        "priority:low": "0E8A16",
    }
    color = _LABEL_COLORS.get(name, "EDEDED")
    resolved = resolve_spawn_command(
        "gh",
        "label",
        "create",
        name,
        "--repo",
        repo_slug,
        "--color",
        color,
        "--force",
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise KaganError(f"gh label create failed for {repo_slug} / {name!r}: {err}")


async def _gh_issue_labels(repo_slug: str, number: int) -> list[str]:
    """Return the label names currently applied to a GitHub issue.

    Returns an empty list on any failure (best-effort).
    """
    resolved = resolve_spawn_command(
        "gh",
        "issue",
        "view",
        str(number),
        "--repo",
        repo_slug,
        "--json",
        "labels",
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return []
    labels = data.get("labels") or []
    return [lbl["name"] for lbl in labels if isinstance(lbl, dict) and "name" in lbl]


async def _search_issues(repo_slug: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search GitHub issues in a repo by text query.

    Returns a list of dicts with keys: number, title, state.
    Returns empty list on any failure (best-effort).
    """
    resolved = resolve_spawn_command(
        "gh",
        "issue",
        "list",
        "--repo",
        repo_slug,
        "--search",
        query,
        "--limit",
        str(limit),
        "--json",
        "number,title,state",
    )
    proc = await asyncio.create_subprocess_exec(
        *resolved,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Criteria helpers
# ---------------------------------------------------------------------------


def _render_criteria_comment(criteria: list[Any]) -> str:
    """Build a tagged comment body from a list of criterion objects.

    Each criterion may be a string (text, considered unchecked) or an object
    with ``.text`` and ``.verdicts`` attributes.  A criterion is checked if the
    latest verdict on it is "pass".

    Accessing the ``verdicts`` relationship on a detached ORM instance raises
    ``sqlalchemy.exc.DetachedInstanceError`` — we treat that as no verdicts.
    """
    lines: list[str] = [_KAGAN_CRITERIA_MARKER, ""]
    for crit in criteria:
        if isinstance(crit, str):
            lines.append(f"- [ ] {crit}")
            continue
        text = getattr(crit, "text", str(crit))
        is_done = False
        try:
            verdicts = list(getattr(crit, "verdicts", []) or [])
            if verdicts:
                latest = sorted(verdicts, key=lambda v: getattr(v, "created_at", ""), reverse=True)
                top_verdict = getattr(latest[0], "verdict", "").upper()
                is_done = top_verdict == "PASS"
        except Exception:
            pass
        box = "x" if is_done else " "
        lines.append(f"- [{box}] {text}")
    return "\n".join(lines)


def _parse_criteria_lines(text: str) -> list[tuple[str, bool]]:
    """Parse ``- [ ] text`` / ``- [x] text`` lines from a block of text.

    Returns ``[(text, done)]`` for each matching line.
    """
    results: list[tuple[str, bool]] = []
    for line in text.splitlines():
        m = _CRITERIA_LINE_RE.match(line)
        if m:
            done = m.group(1).lower() == "x"
            results.append((m.group(2).strip(), done))
    return results


def _seed_criteria_from_body(body: str) -> list[str]:
    """Return criterion texts from ``- [ ]`` / ``- [x]`` lines in an issue body.

    Used only on first import as a one-time bootstrap.  Returns text only
    (done-state is irrelevant for seeding).
    """
    parsed = _parse_criteria_lines(body)
    return [text for text, _done in parsed]


async def _sync_criteria_via_comment(
    client: KaganCore,
    task: Any,
    repo_slug: str,
    number: int,
) -> None:
    """Upsert the tagged criteria comment on a GitHub issue (fire-and-forget).

    Finds the tagged comment, updates it if present; creates one if not.
    All failures are logged at WARNING and never re-raised.
    """
    try:
        criteria = list(task.criteria) if hasattr(task, "criteria") else []
        new_body = _render_criteria_comment(criteria)
        comments = await _gh_list_comments(repo_slug, number)
        tagged = next(
            (
                c
                for c in comments
                if isinstance(c.get("body"), str) and c["body"].startswith(_KAGAN_CRITERIA_MARKER)
            ),
            None,
        )
        if tagged is not None:
            comment_id = tagged.get("id")
            if comment_id:
                await _gh_update_comment(repo_slug, int(comment_id), new_body)
        else:
            await _gh_create_comment(repo_slug, number, new_body)
    except Exception as exc:
        logger.warning("Failed to sync criteria comment for {}#{}: {}", repo_slug, number, exc)


async def _pull_criteria_from_comment(repo_slug: str, number: int) -> list[tuple[str, bool]] | None:
    """Find the tagged criteria comment and parse its lines.

    Returns ``[(text, done)]`` if a tagged comment exists, else ``None``.
    """
    try:
        comments = await _gh_list_comments(repo_slug, number)
    except KaganError:
        return None
    tagged = next(
        (
            c
            for c in comments
            if isinstance(c.get("body"), str) and c["body"].startswith(_KAGAN_CRITERIA_MARKER)
        ),
        None,
    )
    if tagged is None:
        return None
    return _parse_criteria_lines(tagged["body"])


# ---------------------------------------------------------------------------
# Pure helper functions (label parsing)
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


async def _resolve_task_repo_id(
    client: KaganCore,
    project_id: str,
    configured_repo_id: str | None,
) -> str:
    """Pick the repo_id that imported tasks should belong to.

    Raises:
        KaganError: If no repo_id can be determined (no repos attached to
            the project, or multiple repos with none selected).
    """
    if configured_repo_id:
        return configured_repo_id

    try:
        repos = await client.projects.repos(project_id)
    except KaganError as exc:
        raise KaganError(
            "Failed to resolve repository for import. Attach a repository to the project first."
        ) from exc

    if not repos:
        raise KaganError(
            "No repositories attached to this project. "
            "Attach a repository before importing GitHub issues."
        )

    settings = await client.settings.get()
    selected_repo_id = settings.get(f"ui.selected_repo.{project_id}")
    if selected_repo_id and any(repo.id == selected_repo_id for repo in repos):
        return selected_repo_id

    if len(repos) == 1:
        return repos[0].id

    repo_paths = ", ".join(r.path for r in repos)
    raise KaganError(
        f"Multiple repositories attached to this project ({repo_paths}). "
        "Select a repository in the TUI/web UI before importing, or pass target_repo_id explicitly."
    )


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
        items = await github.preview(client, config, project_id)
        checks = github.preflight()
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

    async def _fetch_issues(self, config: GitHubConfig) -> list[GitHubIssue]:
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
        number: str,
        issue: GitHubIssue,
        sync_map: dict[str, str],
        result: ImportResult,
        repo_id: str | None,
        repo_slug: str,
    ) -> ImportResult:
        title = (issue.get("title") or "").strip()
        body = (issue.get("body") or "").strip()
        github_issue_link = f"{repo_slug}#{number}"

        if number in sync_map:
            task_id = sync_map[number]
            try:
                existing = await client.tasks.get(task_id)
            except NotFoundError:
                logger.debug("Task {} for issue #{} was deleted, re-importing", task_id, number)
            else:
                return await self._refresh_existing_task(
                    client,
                    existing,
                    task_id,
                    number,
                    repo_slug,
                    github_issue_link,
                    result,
                )

        label_names = _extract_label_names(issue)
        priority, _extra_labels = _map_labels(label_names)

        # Seed acceptance criteria from body checkboxes on first import
        seeded_criteria = _seed_criteria_from_body(body)

        task = await client.tasks.create(
            title,
            _from_sync=True,
            description=body,
            priority=priority,
            repo_id=repo_id,
            acceptance_criteria=seeded_criteria or None,
            github_issue=github_issue_link,
        )
        sync_map[number] = task.id
        return ImportResult(
            created=result.created + 1,
            updated=result.updated,
            skipped=result.skipped,
            errors=result.errors,
        )

    async def _refresh_existing_task(
        self,
        client: KaganCore,
        existing: Any,
        task_id: str,
        number: str,
        repo_slug: str,
        github_issue_link: str,
        result: ImportResult,
    ) -> ImportResult:
        """Pull canonical GitHub state for one already-imported issue and apply
        any field-level changes to the kagan task.

        Uses _gh_view_issue for the authoritative single-issue data.  Always
        passes _from_sync=True to every tasks.update call so the update does
        not trigger push-back to GitHub.  Status is never touched.
        """
        gh_issue = await _gh_view_issue(repo_slug, int(number))
        gh_title = (gh_issue.get("title") or "").strip()
        gh_body = (gh_issue.get("body") or "").strip()
        label_names = [
            lbl["name"]
            for lbl in (gh_issue.get("labels") or [])
            if isinstance(lbl, dict) and "name" in lbl
        ]
        gh_priority, _extra = _map_labels(label_names)

        update_kwargs: dict[str, Any] = {}

        if gh_title and gh_title != (existing.title or "").strip():
            update_kwargs["title"] = gh_title
        if gh_body != (existing.description or "").strip():
            update_kwargs["description"] = gh_body
        if gh_priority != existing.priority:
            update_kwargs["priority"] = gh_priority

        # Pull criteria from tagged comment; if present, they are canonical
        pulled = await _pull_criteria_from_comment(repo_slug, int(number))
        if pulled is not None:
            update_kwargs["acceptance_criteria"] = [text for text, _done in pulled]

        if not update_kwargs:
            logger.debug("GitHub pull: issue #{} unchanged, skipping task {}", number, task_id)
            return ImportResult(
                created=result.created,
                updated=result.updated,
                skipped=result.skipped + 1,
                errors=result.errors,
            )

        await client.tasks.update(task_id, _from_sync=True, **update_kwargs)
        logger.debug(
            "GitHub pull: updated task {} from issue #{} fields={}",
            task_id,
            number,
            set(update_kwargs.keys()),
        )
        return ImportResult(
            created=result.created,
            updated=result.updated + 1,
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
        repo_id = await _resolve_task_repo_id(client, project_id, config.target_repo_id)
        result = ImportResult()

        for issue in issues:
            number = str(issue.get("number", ""))
            title = (issue.get("title") or "").strip()
            if not number or not title:
                result = result.with_error(f"Issue missing number or title: {issue}")
                continue

            try:
                result = await self._sync_single_issue(
                    client, number, issue, sync_map, result, repo_id, config.repo_slug
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

    async def push_task_change(
        self,
        client: KaganCore,
        task: Any,
        *,
        fields: set[str],
    ) -> None:
        """Push title / priority / description changes on a linked task back to GitHub.

        Only the fields listed in *fields* are pushed.  Status is intentionally
        excluded — call sites must never include it.  Failures are logged at
        WARNING and never re-raised so the caller is unaffected.
        """
        github_issue: str | None = getattr(task, "github_issue", None)
        if not github_issue or "#" not in github_issue:
            return

        push_fields = fields & {"title", "description", "priority"}
        if not push_fields:
            return

        slug, number_str = github_issue.rsplit("#", 1)
        try:
            number = int(number_str)
        except ValueError:
            logger.warning("push_task_change: malformed github_issue link {!r}", github_issue)
            return

        _PRIORITY_LABEL_NAMES: dict[int, str] = {
            Priority.CRITICAL: "priority:critical",
            Priority.HIGH: "priority:high",
            Priority.MEDIUM: "priority:medium",
            Priority.LOW: "priority:low",
        }
        _ALL_PRIORITY_LABELS: frozenset[str] = frozenset(_PRIORITY_LABEL_NAMES.values())

        try:
            if "title" in push_fields:
                await _gh_edit_issue(slug, number, title=task.title)

            if "description" in push_fields:
                await _gh_edit_issue(slug, number, body=task.description or "")

            if "priority" in push_fields:
                new_label = _PRIORITY_LABEL_NAMES.get(task.priority)
                if new_label is not None:
                    current_labels = await _gh_issue_labels(slug, number)
                    add_labels = [new_label] if new_label not in current_labels else []
                    remove_labels = [
                        lbl
                        for lbl in current_labels
                        if lbl in _ALL_PRIORITY_LABELS and lbl != new_label
                    ]
                    await _gh_ensure_label(slug, new_label)
                    if add_labels or remove_labels:
                        await _gh_edit_issue(
                            slug, number, add_labels=add_labels, remove_labels=remove_labels
                        )
        except Exception as exc:
            logger.warning(
                "push_task_change failed for {}#{} fields={}: {}",
                slug,
                number,
                push_fields,
                exc,
            )

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

# Lazy-import alias used by _tasks.py for fire-and-forget push-back.
_push_task_change = github.push_task_change


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
    "_KAGAN_CRITERIA_MARKER",
    "GitHubConfig",
    "GitHubIntegration",
    "GitHubIssue",
    "_gh_create_comment",
    "_gh_create_issue",
    "_gh_edit_issue",
    "_gh_ensure_label",
    "_gh_issue_labels",
    "_gh_list_comments",
    "_gh_update_comment",
    "_gh_view_issue",
    "_parse_criteria_lines",
    "_pull_criteria_from_comment",
    "_push_task_change",
    "_render_criteria_comment",
    "_search_issues",
    "_seed_criteria_from_body",
    "_sync_criteria_via_comment",
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
