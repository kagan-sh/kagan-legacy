"""Tests: GitHub integration — label mapping, idempotent sync, verbatim body, preflight."""

import json
import sys

import pytest

import kagan.core.integrations.github  # noqa: F401  (side-effect: registers module in sys.modules)
from kagan.core import KaganCore, Priority
from kagan.core.integrations.github import (
    GitHubConfig,
    GitHubIntegration,
    canonical_repo_slug,
    format_github_setup_message,
    github_blocking_checks,
    normalize_github_state,
    parse_github_repo_slug_from_remote_url,
)
from tests.helpers.github_cli_fake import make_fake_gh_bin
from tests.helpers.helpers import make_git_repo

_gh_module = sys.modules["kagan.core.integrations.github"]

pytestmark = [pytest.mark.integrations]


# ---------------------------------------------------------------------------
# Sync config
# ---------------------------------------------------------------------------


def test_sync_config_settings_key(config: GitHubConfig) -> None:
    """Settings key uses owner/repo slug with integration. prefix."""
    assert config.settings_key() == "integration.github.octocat/hello-world.sync_map"


def test_sync_config_repo_slug(config: GitHubConfig) -> None:
    """repo_slug joins owner and repo."""
    assert config.repo_slug == "octocat/hello-world"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("octocat/hello-world", "octocat/hello-world"),
        ("  octocat/hello-world  ", "octocat/hello-world"),
    ],
)
def test_canonical_repo_slug_accepts_valid_values(raw: str, expected: str) -> None:
    assert canonical_repo_slug(raw) == expected


@pytest.mark.parametrize("raw", ["octocat", "octo cat/hello", "/hello", "octocat/"])
def test_canonical_repo_slug_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        canonical_repo_slug(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("open", "open"), ("CLOSED", "closed"), (" All ", "all")],
)
def test_normalize_github_state(raw: str, expected: str) -> None:
    assert normalize_github_state(raw) == expected


def test_normalize_github_state_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        normalize_github_state("pending")


@pytest.mark.parametrize(
    ("remote_url", "expected"),
    [
        ("https://github.com/octocat/hello-world.git", "octocat/hello-world"),
        ("https://github.com/octocat/hello-world", "octocat/hello-world"),
        ("git@github.com:octocat/hello-world.git", "octocat/hello-world"),
        ("ssh://git@github.com/octocat/hello-world.git", "octocat/hello-world"),
        ("ssh://git@ssh.github.com:443/octocat/hello-world.git", "octocat/hello-world"),
    ],
)
def test_parse_github_repo_slug_from_remote_url(remote_url: str, expected: str) -> None:
    assert parse_github_repo_slug_from_remote_url(remote_url) == expected


@pytest.mark.parametrize(
    "remote_url",
    [
        "",
        "https://gitlab.com/octocat/hello-world.git",
        "https://evilgithub.com/octocat/hello-world.git",
        "https://github.com.evil.com/octocat/hello-world.git",
        "https://github.com@evil.com/octocat/hello-world.git",
        "git@github.com:octocat/hello/world.git",
        "github.com/octocat/hello-world",
    ],
)
def test_parse_github_repo_slug_from_remote_url_returns_none_for_unsupported(
    remote_url: str,
) -> None:
    assert parse_github_repo_slug_from_remote_url(remote_url) is None


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def test_preflight_warns_gh_missing(monkeypatch, integration: GitHubIntegration) -> None:
    """Preflight warns when gh CLI is not installed."""
    monkeypatch.setattr(_gh_module, "_gh_path", lambda: None)
    checks = integration.preflight()
    assert any(c.name == "gh_cli" and c.status.value == "warn" for c in checks)
    assert any("https://cli.github.com" in c.fix_hint for c in checks)


def test_preflight_passes_when_gh_authed(
    tmp_path, monkeypatch, integration: GitHubIntegration
) -> None:
    """Preflight passes when gh is installed and authenticated (real subprocess)."""
    make_fake_gh_bin(tmp_path, monkeypatch)
    checks = integration.preflight()
    gh_cli = next(c for c in checks if c.name == "gh_cli")
    assert gh_cli.status.value == "pass"


def test_github_blocking_checks_filters_non_pass_statuses() -> None:
    from kagan.core import CheckStatus, PreflightCheckResult

    checks = [
        PreflightCheckResult(name="gh_cli", status=CheckStatus.PASS, message="ok", fix_hint=""),
        PreflightCheckResult(
            name="gh_auth",
            status=CheckStatus.WARN,
            message="not authenticated",
            fix_hint="Run gh auth login",
        ),
    ]
    blocked = github_blocking_checks(checks)

    assert len(blocked) == 1
    assert blocked[0].name == "gh_auth"


def test_format_github_setup_message_shows_fix_steps_for_blockers() -> None:
    from kagan.core import CheckStatus, PreflightCheckResult

    checks = [
        PreflightCheckResult(
            name="gh_auth",
            status=CheckStatus.WARN,
            message="GitHub CLI not authenticated",
            fix_hint="Run gh auth login",
        )
    ]

    message = format_github_setup_message(checks)

    assert "GitHub setup is required before import" in message
    assert "GitHub CLI not authenticated" in message
    assert "Run gh auth login" in message


# ---------------------------------------------------------------------------
# Helpers for issue dicts
# ---------------------------------------------------------------------------


def _make_gh_issues(*issues):
    """Build a list of issue dicts in gh CLI JSON format."""
    result = []
    for num, title, labels in issues:
        result.append(
            {
                "number": num,
                "title": title,
                "body": f"Body for #{num}",
                "labels": [{"name": lbl} for lbl in labels],
                "state": "OPEN",
                "url": f"https://github.com/octocat/hello-world/issues/{num}",
            }
        )
    return result


# ---------------------------------------------------------------------------
# New design: verbatim body
# ---------------------------------------------------------------------------


async def test_import_stores_body_verbatim(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """Imported task description equals the GitHub issue body exactly."""
    body_text = "Fix the login bug\n\nSteps to reproduce:\n1. Go to /login\n2. Click Submit"

    async def _fake_fetch(_config):
        return [
            {
                "number": 1,
                "title": "Login bug",
                "body": body_text,
                "labels": [],
                "state": "OPEN",
                "url": "https://github.com/octocat/hello-world/issues/1",
            }
        ]

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert len(tasks) == 1
    assert tasks[0].description == body_text


async def test_first_import_seeds_criteria_from_body_checkboxes(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """First import seeds acceptance criteria from - [ ] / - [x] lines in body."""

    async def _fake_fetch(_config):
        return [
            {
                "number": 1,
                "title": "Feature with checkboxes",
                "body": "Acceptance criteria:\n- [ ] foo\n- [x] bar\n- [ ] baz",
                "labels": [],
                "state": "OPEN",
                "url": "https://github.com/octocat/hello-world/issues/1",
            }
        ]

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert len(tasks) == 1
    criteria_texts = [c.text for c in tasks[0].criteria]
    assert set(criteria_texts) == {"foo", "bar", "baz"}


async def test_import_sets_github_issue_field_to_canonical_form(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """Imported task has github_issue set to '<owner>/<repo>#<number>'."""

    async def _fake_fetch(_config):
        return _make_gh_issues((42, "Some issue", []))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert len(tasks) == 1
    assert tasks[0].github_issue == "octocat/hello-world#42"


# ---------------------------------------------------------------------------
# Idempotent sync
# ---------------------------------------------------------------------------


async def test_sync_creates_tasks_from_issues(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """First sync creates tasks for each GitHub issue."""

    async def _fake_fetch(_config):
        return _make_gh_issues(
            (1, "Bug report", ["bug", "priority:high"]),
            (2, "Feature request", ["enhancement"]),
        )

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    result = await integration.sync(client, config, client.active_project_id)
    assert result.created == 2
    assert result.skipped == 0

    tasks = await client.tasks.list()
    titles = {t.title for t in tasks}
    assert "Bug report" in titles
    assert "Feature request" in titles

    bug_task = next(t for t in tasks if t.title == "Bug report")
    assert bug_task.priority == Priority.HIGH


async def test_sync_assigns_imported_tasks_to_selected_repo(
    authed_gh, monkeypatch, integration, config, client, tmp_path
) -> None:
    """Imported issues stay visible when the board is filtered to the selected repo."""
    repo_path = tmp_path / "selected-repo"
    await make_git_repo(repo_path)
    project_id = client.active_project_id
    assert project_id is not None
    repo = await client.projects.add_repo(project_id, str(repo_path))
    await client.settings.set({f"ui.selected_repo.{project_id}": repo.id})

    async def _fake_fetch(_config):
        return _make_gh_issues((1, "Repo-scoped bug", ["bug"]))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    result = await integration.sync(client, config, project_id)

    assert result.created == 1
    tasks = await client.tasks.list(repo_id=repo.id)
    assert len(tasks) == 1
    assert tasks[0].title == "Repo-scoped bug"


async def test_sync_is_idempotent(authed_gh, monkeypatch, integration, config, client) -> None:
    """Running sync twice with same issues creates tasks only once."""
    issues = _make_gh_issues((1, "Bug report", ["bug"]))
    view_data = {
        "number": 1,
        "title": "Bug report",
        "body": "Body for #1",
        "labels": [{"name": "bug"}],
        "state": "OPEN",
    }

    async def _fake_fetch(_config):
        return issues

    async def _fake_view(repo_slug, number):
        return view_data

    async def _no_criteria(repo_slug, number):
        return None

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)
    monkeypatch.setattr(_gh_module, "_gh_view_issue", _fake_view)
    monkeypatch.setattr(_gh_module, "_pull_criteria_from_comment", _no_criteria)

    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 0
    assert result2.skipped == 1

    tasks = await client.tasks.list()
    assert len(tasks) == 1


async def test_sync_reimports_deleted_tasks(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """If a synced task is deleted, re-sync re-creates it."""

    async def _fake_fetch(_config):
        return _make_gh_issues((1, "Bug report", ["bug"]))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    tasks = await client.tasks.list()
    await client.tasks.delete(tasks[0].id)

    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 1
    assert result2.skipped == 0


async def test_sync_incremental_new_issues(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """Sync picks up new issues while skipping already-imported ones."""
    view_data = {
        "number": 1,
        "title": "First",
        "body": "Body for #1",
        "labels": [],
        "state": "OPEN",
    }

    async def _fake_fetch_first(_config):
        return _make_gh_issues((1, "First", []))

    async def _fake_view(repo_slug, number):
        return view_data

    async def _no_criteria(repo_slug, number):
        return None

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch_first)
    monkeypatch.setattr(_gh_module, "_gh_view_issue", _fake_view)
    monkeypatch.setattr(_gh_module, "_pull_criteria_from_comment", _no_criteria)

    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    async def _fake_fetch_second(_config):
        return _make_gh_issues((1, "First", []), (2, "Second", []))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch_second)

    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 1
    assert result2.skipped == 1

    tasks = await client.tasks.list()
    assert len(tasks) == 2


async def test_sync_persists_map_in_settings(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """Sync map is persisted in settings and survives reinstantiation."""

    async def _fake_fetch(_config):
        return _make_gh_issues((42, "Important fix", []))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    await integration.sync(client, config, client.active_project_id)

    settings = await client.settings.get()
    key = config.settings_key()
    assert key in settings
    sync_map = json.loads(settings[key])
    assert "42" in sync_map


async def test_sync_with_issue_numbers_imports_only_selected(
    authed_gh, monkeypatch, integration, client
) -> None:
    """Sync with issue_numbers only imports matching issues."""

    async def _fake_fetch(_config):
        return _make_gh_issues(
            (1, "Bug", []),
            (2, "Feature", []),
            (3, "Docs", []),
        )

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    config = GitHubConfig(owner="octocat", repo="hello-world", issue_numbers=(1, 3))
    result = await integration.sync(client, config, client.active_project_id)
    assert result.created == 2
    tasks = await client.tasks.list()
    assert {t.title for t in tasks} == {"Bug", "Docs"}


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


async def test_preview_returns_items_without_importing(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """Preview returns ExternalItem list without creating tasks."""

    async def _fake_fetch(_config):
        return _make_gh_issues(
            (1, "Bug report", ["bug"]),
            (2, "Feature", ["enhancement"]),
        )

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    items = await integration.preview(client, config, client.active_project_id)
    assert len(items) == 2
    assert items[0].extra["number"] == 1
    assert items[0].already_synced is False
    tasks = await client.tasks.list()
    assert len(tasks) == 0


async def test_preview_marks_synced_items(
    authed_gh, monkeypatch, integration, config, client
) -> None:
    """Preview marks previously synced issues."""

    async def _fake_fetch_first(_config):
        return _make_gh_issues((1, "Bug", []))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch_first)
    await integration.sync(client, config, client.active_project_id)

    async def _fake_fetch_second(_config):
        return _make_gh_issues((1, "Bug", []), (2, "New", []))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch_second)
    items = await integration.preview(client, config, client.active_project_id)
    assert items[0].already_synced is True
    assert items[1].already_synced is False


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


async def test_sync_raises_when_gh_missing(monkeypatch, integration, config, client) -> None:
    """sync() raises KaganError when gh CLI is not installed."""
    from kagan.core.errors import KaganError

    monkeypatch.setattr(_gh_module, "_gh_path", lambda: None)

    with pytest.raises(KaganError, match=r"gh.*not found"):
        await integration.sync(client, config, client.active_project_id)


async def test_preview_raises_when_gh_missing(monkeypatch, integration, config, client) -> None:
    """preview() raises KaganError when gh CLI is not installed."""
    from kagan.core.errors import KaganError

    monkeypatch.setattr(_gh_module, "_gh_path", lambda: None)

    with pytest.raises(KaganError, match=r"gh.*not found"):
        await integration.preview(client, config, client.active_project_id)


async def test_sync_raises_when_no_repo_attached(
    authed_gh, monkeypatch, integration, config, tmp_path
) -> None:
    """sync() raises KaganError when project has no repositories attached."""
    from kagan.core.errors import KaganError

    async def _fake_fetch(_config):
        return _make_gh_issues((1, "Bug report", ["bug"]))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    client = KaganCore(db_path=tmp_path / "no_repo_test.db")
    project = await client.projects.create("No Repo Project")
    await client.projects.set_active(project.id)

    try:
        with pytest.raises(KaganError, match=r"No repositories attached"):
            await integration.sync(client, config, project.id)
    finally:
        client.close()


async def test_sync_raises_when_multiple_repos_and_none_selected(
    authed_gh, monkeypatch, integration, config, tmp_path
) -> None:
    """sync() raises KaganError when project has multiple repos but none is selected."""
    from kagan.core.errors import KaganError

    async def _fake_fetch(_config):
        return _make_gh_issues((1, "Bug report", ["bug"]))

    monkeypatch.setattr(_gh_module, "_gh_fetch_issues", _fake_fetch)

    client = KaganCore(db_path=tmp_path / "multi_repo_test.db")
    project = await client.projects.create("Multi Repo Project")
    await client.projects.set_active(project.id)

    repo1_path = tmp_path / "repo1"
    repo2_path = tmp_path / "repo2"
    await make_git_repo(repo1_path)
    await make_git_repo(repo2_path)
    await client.projects.add_repo(project.id, str(repo1_path))
    await client.projects.add_repo(project.id, str(repo2_path))

    try:
        with pytest.raises(KaganError, match=r"Multiple repositories attached"):
            await integration.sync(client, config, project.id)
    finally:
        client.close()
