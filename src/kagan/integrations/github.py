import asyncio
from pathlib import Path
from urllib.parse import urlparse

from kagan.core import KaganCore, PreflightCheckResult
from kagan.plugins import ImportResult, PluginManager
from kagan.plugins._github import GitHubImportConfig
from kagan.runtime_env import build_sanitized_subprocess_environment

GITHUB_IMPORT_STATES = frozenset({"open", "closed", "all"})


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


def parse_github_repo_slug_from_remote_url(remote_url: str) -> str | None:
    value = remote_url.strip()
    if not value:
        return None

    path = ""
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
    else:
        parsed = urlparse(value)
        host = parsed.netloc.lower()
        if host.endswith("github.com"):
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


async def github_preflight_checks(client: KaganCore) -> list[PreflightCheckResult]:
    manager = PluginManager(client)
    await manager.load()
    if "github" not in manager.available:
        raise ValueError("GitHub import is unavailable in this installation.")
    return manager.get("github").preflight()


async def sync_github_issues(
    client: KaganCore,
    *,
    project_id: str,
    repo_slug: str,
    state: str = "open",
    import_label: str | None = None,
) -> ImportResult:
    normalized_state = normalize_github_state(state)
    canonical_repo = canonical_repo_slug(repo_slug)
    owner, repo = canonical_repo.split("/", 1)

    manager = PluginManager(client)
    await manager.load()
    if "github" not in manager.available:
        raise ValueError("GitHub import is unavailable in this installation.")

    import_plugin = manager.get_import("github")
    import_plugin.configure(
        GitHubImportConfig(
            owner=owner,
            repo=repo,
            state=normalized_state,
            import_label=import_label,
        )
    )
    return await manager.sync("github", project_id=project_id)
