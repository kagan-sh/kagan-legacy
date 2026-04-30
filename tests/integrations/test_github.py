"""Tests: GitHub integration — label mapping, idempotent sync, verbatim body, preflight."""

import json
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from kagan.core import KaganCore, Priority
from kagan.core.integrations.github import (
    GitHubConfig,
    GitHubIntegration,
    GitHubIssue,
    _extract_label_names,
    _map_labels,
    canonical_repo_slug,
    format_github_setup_message,
    github_blocking_checks,
    normalize_github_state,
    parse_github_repo_slug_from_remote_url,
)
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.integrations]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    c = KaganCore(db_path=tmp_path / "test.db")
    project = await c.projects.create("Test Project")
    await c.projects.set_active(project.id)
    yield c
    c.close()


@pytest.fixture
def config():
    return GitHubConfig(owner="octocat", repo="hello-world")


@pytest.fixture
def integration():
    return GitHubIntegration()


# ---------------------------------------------------------------------------
# Label mapping (pure functions — fast, no I/O)
# ---------------------------------------------------------------------------


def test_extract_label_names_from_gh_format() -> None:
    """Labels are extracted from nested gh JSON format."""
    issue: GitHubIssue = {"labels": [{"name": "bug"}, {"name": "priority:high"}]}
    assert _extract_label_names(issue) == ["bug", "priority:high"]


def test_extract_label_names_handles_empty() -> None:
    """Empty or missing labels return empty list."""
    assert _extract_label_names({}) == []
    assert _extract_label_names({"labels": []}) == []
    assert _extract_label_names(cast("GitHubIssue", {"labels": None})) == []


def test_map_labels_priority() -> None:
    """Priority labels map to Priority enum values."""
    priority, remaining = _map_labels(["priority:high", "bug"])
    assert priority == Priority.HIGH
    assert remaining == ["bug"]


def test_map_labels_unknown_labels_pass_through() -> None:
    priority, remaining = _map_labels(["kagan:detached", "enhancement"])
    assert priority == Priority.MEDIUM
    assert remaining == ["kagan:detached", "enhancement"]


def test_map_labels_combined() -> None:
    priority, remaining = _map_labels(["priority:critical", "kagan:attached", "frontend", "bug"])
    assert priority == Priority.CRITICAL
    assert remaining == ["kagan:attached", "frontend", "bug"]


def test_map_labels_case_insensitive() -> None:
    """Label matching is case-insensitive."""
    priority, _ = _map_labels(["Priority:HIGH"])
    assert priority == Priority.HIGH


def test_map_labels_defaults_when_no_mapped_labels() -> None:
    priority, remaining = _map_labels(["bug", "documentation"])
    assert priority == Priority.MEDIUM
    assert remaining == ["bug", "documentation"]


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


@patch("kagan.core.integrations.github._gh_path", return_value=None)
def test_preflight_warns_gh_missing(_mock_path, integration: GitHubIntegration) -> None:
    """Preflight warns when gh CLI is not installed."""
    checks = integration.preflight()
    assert any(c.name == "gh_cli" and c.status.value == "warn" for c in checks)
    assert any("https://cli.github.com" in c.fix_hint for c in checks)


@patch("kagan.core.integrations.github.subprocess")
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
def test_preflight_passes_when_gh_authed(
    _mock_path, mock_subprocess, integration: GitHubIntegration
) -> None:
    """Preflight passes when gh is installed and authenticated."""
    mock_subprocess.run.return_value.returncode = 0
    mock_subprocess.run.return_value.stdout = "gho_fake_token"
    mock_subprocess.TimeoutExpired = TimeoutError

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


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_import_stores_body_verbatim(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Imported task description equals the GitHub issue body exactly."""
    body_text = "Fix the login bug\n\nSteps to reproduce:\n1. Go to /login\n2. Click Submit"
    mock_fetch.return_value = [
        {
            "number": 1,
            "title": "Login bug",
            "body": body_text,
            "labels": [],
            "state": "OPEN",
            "url": "https://github.com/octocat/hello-world/issues/1",
        }
    ]

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert len(tasks) == 1
    assert tasks[0].description == body_text


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_first_import_seeds_criteria_from_body_checkboxes(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """First import seeds acceptance criteria from - [ ] / - [x] lines in body."""
    mock_fetch.return_value = [
        {
            "number": 1,
            "title": "Feature with checkboxes",
            "body": "Acceptance criteria:\n- [ ] foo\n- [x] bar\n- [ ] baz",
            "labels": [],
            "state": "OPEN",
            "url": "https://github.com/octocat/hello-world/issues/1",
        }
    ]

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert len(tasks) == 1
    criteria_texts = [c.text for c in tasks[0].criteria]
    assert set(criteria_texts) == {"foo", "bar", "baz"}


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_import_sets_github_issue_field_to_canonical_form(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Imported task has github_issue set to '<owner>/<repo>#<number>'."""
    mock_fetch.return_value = _make_gh_issues((42, "Some issue", []))

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert len(tasks) == 1
    assert tasks[0].github_issue == "octocat/hello-world#42"


# ---------------------------------------------------------------------------
# Idempotent sync (with mocked gh CLI)
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_creates_tasks_from_issues(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """First sync creates tasks for each GitHub issue."""
    mock_fetch.return_value = _make_gh_issues(
        (1, "Bug report", ["bug", "priority:high"]),
        (2, "Feature request", ["enhancement"]),
    )

    result = await integration.sync(client, config, client.active_project_id)
    assert result.created == 2
    assert result.skipped == 0

    tasks = await client.tasks.list()
    titles = {t.title for t in tasks}
    assert "Bug report" in titles
    assert "Feature request" in titles

    # Verify label mapping
    bug_task = next(t for t in tasks if t.title == "Bug report")
    assert bug_task.priority == Priority.HIGH


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_assigns_imported_tasks_to_selected_repo(
    _mock_path, _mock_auth, mock_fetch, integration, config, client, tmp_path
) -> None:
    """Imported issues stay visible when the board is filtered to the selected repo."""
    repo_path = tmp_path / "selected-repo"
    await make_git_repo(repo_path)
    project_id = client.active_project_id
    assert project_id is not None
    repo = await client.projects.add_repo(project_id, str(repo_path))
    await client.settings.set({f"ui.selected_repo.{project_id}": repo.id})
    mock_fetch.return_value = _make_gh_issues((1, "Repo-scoped bug", ["bug"]))

    result = await integration.sync(client, config, project_id)

    assert result.created == 1
    tasks = await client.tasks.list(repo_id=repo.id)
    assert len(tasks) == 1
    assert tasks[0].title == "Repo-scoped bug"


@patch("kagan.core.integrations.github._pull_criteria_from_comment", new_callable=AsyncMock, return_value=None)
@patch("kagan.core.integrations.github._gh_view_issue", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_is_idempotent(
    _mock_path, _mock_auth, mock_fetch, mock_view, _mock_pull_criteria, integration, config, client
) -> None:
    """Running sync twice with same issues creates tasks only once."""
    issues = _make_gh_issues((1, "Bug report", ["bug"]))
    mock_fetch.return_value = issues
    mock_view.return_value = {
        "number": 1,
        "title": "Bug report",
        "body": "Body for #1",
        "labels": [{"name": "bug"}],
        "state": "OPEN",
    }

    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 0
    assert result2.skipped == 1

    tasks = await client.tasks.list()
    assert len(tasks) == 1


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_reimports_deleted_tasks(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """If a synced task is deleted, re-sync re-creates it."""
    issues = _make_gh_issues((1, "Bug report", ["bug"]))
    mock_fetch.return_value = issues

    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    tasks = await client.tasks.list()
    await client.tasks.delete(tasks[0].id)

    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 1
    assert result2.skipped == 0


@patch("kagan.core.integrations.github._pull_criteria_from_comment", new_callable=AsyncMock, return_value=None)
@patch("kagan.core.integrations.github._gh_view_issue", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_incremental_new_issues(
    _mock_path, _mock_auth, mock_fetch, mock_view, _mock_pull_criteria, integration, config, client
) -> None:
    """Sync picks up new issues while skipping already-imported ones."""
    mock_fetch.return_value = _make_gh_issues((1, "First", []))
    mock_view.return_value = {
        "number": 1,
        "title": "First",
        "body": "Body for #1",
        "labels": [],
        "state": "OPEN",
    }
    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    mock_fetch.return_value = _make_gh_issues((1, "First", []), (2, "Second", []))
    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 1
    assert result2.skipped == 1

    tasks = await client.tasks.list()
    assert len(tasks) == 2


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_persists_map_in_settings(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Sync map is persisted in settings and survives reinstantiation."""
    mock_fetch.return_value = _make_gh_issues((42, "Important fix", []))
    await integration.sync(client, config, client.active_project_id)

    settings = await client.settings.get()
    key = config.settings_key()
    assert key in settings
    sync_map = json.loads(settings[key])
    assert "42" in sync_map


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_sync_with_issue_numbers_imports_only_selected(
    _mock_path, _mock_auth, mock_fetch, integration, client
) -> None:
    """Sync with issue_numbers only imports matching issues."""
    mock_fetch.return_value = _make_gh_issues(
        (1, "Bug", []),
        (2, "Feature", []),
        (3, "Docs", []),
    )
    config = GitHubConfig(owner="octocat", repo="hello-world", issue_numbers=(1, 3))
    result = await integration.sync(client, config, client.active_project_id)
    assert result.created == 2
    tasks = await client.tasks.list()
    assert {t.title for t in tasks} == {"Bug", "Docs"}


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_preview_returns_items_without_importing(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Preview returns ExternalItem list without creating tasks."""
    mock_fetch.return_value = _make_gh_issues(
        (1, "Bug report", ["bug"]),
        (2, "Feature", ["enhancement"]),
    )
    items = await integration.preview(client, config, client.active_project_id)
    assert len(items) == 2
    assert items[0].extra["number"] == 1
    assert items[0].already_synced is False
    tasks = await client.tasks.list()
    assert len(tasks) == 0


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_preview_marks_synced_items(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Preview marks previously synced issues."""
    issues = _make_gh_issues((1, "Bug", []))
    mock_fetch.return_value = issues
    await integration.sync(client, config, client.active_project_id)

    mock_fetch.return_value = _make_gh_issues((1, "Bug", []), (2, "New", []))
    items = await integration.preview(client, config, client.active_project_id)
    assert items[0].already_synced is True
    assert items[1].already_synced is False


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_path", return_value=None)
async def test_sync_raises_when_gh_missing(_mock_path, integration, config, client) -> None:
    """sync() raises KaganError when gh CLI is not installed."""
    from kagan.core.errors import KaganError

    with pytest.raises(KaganError, match=r"gh.*not found"):
        await integration.sync(client, config, client.active_project_id)


@patch("kagan.core.integrations.github._gh_path", return_value=None)
async def test_preview_raises_when_gh_missing(_mock_path, integration, config, client) -> None:
    """preview() raises KaganError when gh CLI is not installed."""
    from kagan.core.errors import KaganError

    with pytest.raises(KaganError, match=r"gh.*not found"):
        await integration.preview(client, config, client.active_project_id)
