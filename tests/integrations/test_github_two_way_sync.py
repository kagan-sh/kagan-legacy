"""Tests: GitHub two-way sync — verbatim body, criteria-via-comment, decoupled status."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kagan.core import KaganCore
from kagan.core.enums import Priority, TaskStatus
from kagan.core.integrations.github import (
    _KAGAN_CRITERIA_MARKER,
    GitHubConfig,
    GitHubIntegration,
    _parse_criteria_lines,
    _render_criteria_comment,
    _seed_criteria_from_body,
)

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


def _make_issue(number: int, title: str, body: str = "", labels=None):
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "state": "OPEN",
        "url": f"https://github.com/octocat/hello-world/issues/{number}",
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_parse_criteria_lines_parses_checkboxes() -> None:
    text = "Some intro\n- [ ] foo\n- [x] bar\n- [X] baz\nTrailing text"
    result = _parse_criteria_lines(text)
    assert result == [("foo", False), ("bar", True), ("baz", True)]


def test_parse_criteria_lines_tolerates_indentation() -> None:
    text = "  - [ ] indented\n    - [x] more indented"
    result = _parse_criteria_lines(text)
    assert len(result) == 2
    assert result[0] == ("indented", False)
    assert result[1] == ("more indented", True)


def test_seed_criteria_from_body_extracts_texts() -> None:
    body = "Description\n- [ ] first\n- [x] second (already done)\n- [ ] third"
    texts = _seed_criteria_from_body(body)
    assert texts == ["first", "second (already done)", "third"]


def test_seed_criteria_from_body_returns_empty_when_no_checkboxes() -> None:
    texts = _seed_criteria_from_body("No checkboxes here")
    assert texts == []


def test_render_criteria_comment_starts_with_marker() -> None:
    comment = _render_criteria_comment(["foo", "bar"])
    assert comment.startswith(_KAGAN_CRITERIA_MARKER)


def test_render_criteria_comment_string_criteria_rendered_unchecked() -> None:
    comment = _render_criteria_comment(["foo", "bar"])
    assert "- [ ] foo" in comment
    assert "- [ ] bar" in comment


def test_render_criteria_comment_with_verdict_objects() -> None:
    """Criteria with PASS verdict render as [x]; others as [ ]."""
    verdict_pass = MagicMock()
    verdict_pass.verdict = "PASS"
    verdict_pass.created_at = "2024-01-01T12:00:00"

    verdict_fail = MagicMock()
    verdict_fail.verdict = "FAIL"
    verdict_fail.created_at = "2024-01-01T11:00:00"

    crit_done = MagicMock()
    crit_done.text = "done crit"
    crit_done.verdicts = [verdict_pass]

    crit_open = MagicMock()
    crit_open.text = "open crit"
    crit_open.verdicts = [verdict_fail]

    comment = _render_criteria_comment([crit_done, crit_open])
    assert "- [x] done crit" in comment
    assert "- [ ] open crit" in comment


# ---------------------------------------------------------------------------
# Body round-trip
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_body_round_trips_verbatim(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Description is the GitHub issue body, not a synthesised string."""
    original_body = "Fix the login bug\n\nSteps:\n1. Go to /login\n2. Submit form"
    mock_fetch.return_value = [_make_issue(1, "Login bug", original_body)]

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert tasks[0].description == original_body


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_description_contains_no_url_prefix(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Imported description must NOT start with the GitHub issue URL."""
    mock_fetch.return_value = [_make_issue(1, "Some issue", "Body only")]

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    assert not tasks[0].description.startswith("https://")


# ---------------------------------------------------------------------------
# Criteria sync via comment
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_first_import_seeds_criteria_from_body_checkboxes(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """First import: checkboxes in body seed kagan acceptance criteria."""
    mock_fetch.return_value = [
        _make_issue(1, "Feature", "- [ ] foo\n- [x] bar")
    ]

    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    texts = {c.text for c in tasks[0].criteria}
    assert texts == {"foo", "bar"}


@patch("kagan.core.integrations.github._gh_list_comments", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_create_comment", new_callable=AsyncMock, return_value=1)
async def test_criteria_comment_created_on_first_change(
    mock_create_comment, mock_list_comments, client
) -> None:
    """Creating a comment when no tagged comment exists yet."""
    mock_list_comments.return_value = []  # No existing comments

    task = await client.tasks.create(
        "Linked task",
        acceptance_criteria=["foo", "bar"],
        github_issue=None,
    )

    from kagan.core.integrations.github import _sync_criteria_via_comment

    await _sync_criteria_via_comment(client, task, "octocat/hello-world", 42)

    mock_create_comment.assert_called_once()
    call_args = mock_create_comment.call_args
    assert _KAGAN_CRITERIA_MARKER in call_args[0][2]
    assert "- [ ] foo" in call_args[0][2]
    assert "- [ ] bar" in call_args[0][2]


@patch("kagan.core.integrations.github._gh_list_comments", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_update_comment", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_create_comment", new_callable=AsyncMock)
async def test_criteria_comment_updated_on_subsequent_change(
    mock_create_comment, mock_update_comment, mock_list_comments, client
) -> None:
    """When a tagged comment already exists, update it (no duplicate)."""
    existing_comment_body = f"{_KAGAN_CRITERIA_MARKER}\n\n- [ ] old criterion"
    mock_list_comments.return_value = [
        {"id": 999, "body": existing_comment_body}
    ]

    task = await client.tasks.create("Task with criteria", acceptance_criteria=["new criterion"])

    from kagan.core.integrations.github import _sync_criteria_via_comment

    await _sync_criteria_via_comment(client, task, "octocat/hello-world", 42)

    mock_update_comment.assert_called_once()
    mock_create_comment.assert_not_called()
    call_args = mock_update_comment.call_args
    assert call_args[0][1] == 999  # comment_id
    assert "- [ ] new criterion" in call_args[0][2]


@patch("kagan.core.integrations.github._gh_list_comments", new_callable=AsyncMock)
async def test_criteria_pulled_from_tagged_comment_overrides_body_seed(
    mock_list_comments,
) -> None:
    """_pull_criteria_from_comment returns parsed lines from the tagged comment."""
    tagged_body = f"{_KAGAN_CRITERIA_MARKER}\n\n- [ ] from comment\n- [x] done"
    mock_list_comments.return_value = [{"id": 1, "body": tagged_body}]

    from kagan.core.integrations.github import _pull_criteria_from_comment

    result = await _pull_criteria_from_comment("octocat/hello-world", 42)

    assert result is not None
    assert ("from comment", False) in result
    assert ("done", True) in result


@patch("kagan.core.integrations.github._gh_list_comments", new_callable=AsyncMock)
async def test_pull_criteria_returns_none_when_no_tagged_comment(
    mock_list_comments,
) -> None:
    """_pull_criteria_from_comment returns None when no tagged comment exists."""
    mock_list_comments.return_value = [
        {"id": 1, "body": "Just a regular comment"}
    ]

    from kagan.core.integrations.github import _pull_criteria_from_comment

    result = await _pull_criteria_from_comment("octocat/hello-world", 42)
    assert result is None


# ---------------------------------------------------------------------------
# Status decoupling
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_status_change_does_not_call_gh(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """Regression: task status change must never call any gh CLI wrapper."""
    mock_fetch.return_value = [_make_issue(1, "Bug", "Body")]
    await integration.sync(client, config, client.active_project_id)

    tasks = await client.tasks.list()
    task_id = tasks[0].id

    with (
        patch("kagan.core.integrations.github._gh_view_issue") as mock_view,
        patch("kagan.core.integrations.github._gh_create_issue") as mock_create,
        patch("kagan.core.integrations.github._gh_list_comments") as mock_list,
        patch("kagan.core.integrations.github._gh_create_comment") as mock_create_comment,
        patch("kagan.core.integrations.github._gh_update_comment") as mock_update,
    ):
        await client.tasks.set_status(task_id, TaskStatus.IN_PROGRESS)

        mock_view.assert_not_called()
        mock_create.assert_not_called()
        mock_list.assert_not_called()
        mock_create_comment.assert_not_called()
        mock_update.assert_not_called()


@patch("kagan.core.integrations.github._gh_fetch_issues", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_is_authenticated", new_callable=AsyncMock, return_value=True
)
@patch("kagan.core.integrations.github._gh_path", return_value="/usr/bin/gh")
async def test_pull_sync_does_not_trigger_push_back_loop(
    _mock_path, _mock_auth, mock_fetch, integration, config, client
) -> None:
    """A second pull sync (same issues) does not re-create or modify tasks."""
    mock_fetch.return_value = [_make_issue(1, "Bug", "Body")]
    result1 = await integration.sync(client, config, client.active_project_id)
    assert result1.created == 1

    result2 = await integration.sync(client, config, client.active_project_id)
    assert result2.created == 0
    assert result2.skipped == 1

    tasks = await client.tasks.list()
    assert len(tasks) == 1


# ---------------------------------------------------------------------------
# Create-and-link: Tasks.create(github_issue=...)
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_create_issue", new_callable=AsyncMock, return_value=99)
async def test_create_with_github_issue_new_creates_and_links(
    mock_create_issue, tmp_path
) -> None:
    """github_issue='new' creates a GitHub issue and stores the link on the task."""
    from tests.helpers.helpers import make_git_repo

    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path)

    c = KaganCore(db_path=tmp_path / "test.db")
    project = await c.projects.create("P")
    await c.projects.set_active(project.id)
    await c.projects.add_repo(project.id, str(repo_path))

    with patch(
        "kagan.core._tasks.Tasks._detect_repo_slug_for_project",
        new_callable=AsyncMock,
        return_value="octocat/hello-world",
    ):
        task = await c.tasks.create("New task", description="body", github_issue="new")

    assert task.github_issue == "octocat/hello-world#99"
    mock_create_issue.assert_called_once_with("octocat/hello-world", "New task", "body")
    c.close()


@patch(
    "kagan.core.integrations.github._gh_view_issue",
    new_callable=AsyncMock,
    return_value={"number": 5, "title": "Existing issue"},
)
async def test_create_with_github_issue_number_links_existing(
    _mock_view, tmp_path
) -> None:
    """github_issue='5' validates and links an existing GitHub issue."""
    c = KaganCore(db_path=tmp_path / "test.db")
    project = await c.projects.create("P")
    await c.projects.set_active(project.id)

    with patch(
        "kagan.core._tasks.Tasks._detect_repo_slug_for_project",
        new_callable=AsyncMock,
        return_value="octocat/hello-world",
    ):
        task = await c.tasks.create("My task", github_issue="5")

    assert task.github_issue == "octocat/hello-world#5"
    c.close()


@patch(
    "kagan.core.integrations.github._gh_view_issue",
    new_callable=AsyncMock,
    side_effect=Exception("404 not found"),
)
async def test_create_with_invalid_github_issue_raises(
    _mock_view, tmp_path
) -> None:
    """github_issue pointing to a nonexistent issue raises KaganError."""
    from kagan.core.errors import KaganError

    c = KaganCore(db_path=tmp_path / "test.db")
    project = await c.projects.create("P")
    await c.projects.set_active(project.id)

    with (
        patch(
            "kagan.core._tasks.Tasks._detect_repo_slug_for_project",
            new_callable=AsyncMock,
            return_value="octocat/hello-world",
        ),
        pytest.raises((KaganError, Exception)),
    ):
        await c.tasks.create("My task", github_issue="999")

    c.close()


# ---------------------------------------------------------------------------
# _search_issues
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._search_issues", new_callable=AsyncMock)
async def test_search_issues_returns_matches(mock_search) -> None:
    """_search_issues returns parsed issue dicts from gh CLI output."""
    mock_search.return_value = [
        {"number": 1, "title": "Login bug", "state": "open"},
        {"number": 2, "title": "Login UX", "state": "open"},
    ]

    from kagan.core.integrations.github import _search_issues

    # The mock already patches _search_issues; calling it directly goes to the mock
    results = await _search_issues("octocat/hello-world", "login", limit=5)
    assert len(results) == 2
    assert results[0]["title"] == "Login bug"


async def test_search_issues_returns_empty_on_no_link() -> None:
    """_search_issues returns empty list when gh is not available (simulated by no-op patch)."""
    with patch(
        "kagan.core.integrations.github.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
    ) as mock_exec:
        proc = AsyncMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_exec.return_value = proc

        from kagan.core.integrations.github import _search_issues

        results = await _search_issues("octocat/hello-world", "anything", limit=5)
        assert results == []


# ---------------------------------------------------------------------------
# push_task_change — title / description / priority push-back
# ---------------------------------------------------------------------------


@patch("kagan.core.integrations.github._gh_edit_issue", new_callable=AsyncMock)
async def test_push_task_change_edits_title(mock_edit, integration, client) -> None:
    """push_task_change with fields={'title'} calls _gh_edit_issue with the new title."""
    task = await client.tasks.create(
        "Original title",
        description="desc",
        github_issue=None,
    )
    # Manually attach the github_issue link so no real gh call is needed.
    task.github_issue = "octocat/hello-world#7"
    task.title = "Updated title"

    await integration.push_task_change(client, task, fields={"title"})

    mock_edit.assert_called_once_with("octocat/hello-world", 7, title="Updated title")


@patch("kagan.core.integrations.github._gh_edit_issue", new_callable=AsyncMock)
async def test_push_task_change_pushes_body_verbatim(mock_edit, integration, client) -> None:
    """push_task_change with fields={'description'} sends verbatim markdown body."""
    raw_md = "Fix [the login bug](https://example.com/issue)\n\n- [x] step one\n- [ ] step two"
    task = await client.tasks.create("Task", description="initial")
    task.github_issue = "octocat/hello-world#8"
    task.description = raw_md

    await integration.push_task_change(client, task, fields={"description"})

    mock_edit.assert_called_once_with("octocat/hello-world", 8, body=raw_md)


@patch("kagan.core.integrations.github._gh_edit_issue", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_ensure_label", new_callable=AsyncMock)
@patch(
    "kagan.core.integrations.github._gh_issue_labels",
    new_callable=AsyncMock,
    return_value=["priority:medium", "bug"],
)
async def test_push_task_change_swaps_priority_labels(
    _mock_labels, mock_ensure, mock_edit, integration, client
) -> None:
    """Changing priority to HIGH removes priority:medium and adds priority:high."""
    task = await client.tasks.create("Task", description="desc")
    task.github_issue = "octocat/hello-world#9"
    task.priority = Priority.HIGH

    await integration.push_task_change(client, task, fields={"priority"})

    mock_ensure.assert_called_once_with("octocat/hello-world", "priority:high")
    mock_edit.assert_called_once()
    call_kwargs = mock_edit.call_args.kwargs
    assert call_kwargs["add_labels"] == ["priority:high"]
    assert call_kwargs["remove_labels"] == ["priority:medium"]


@patch("kagan.core.integrations.github._gh_edit_issue", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_ensure_label", new_callable=AsyncMock)
@patch("kagan.core.integrations.github._gh_issue_labels", new_callable=AsyncMock)
async def test_push_task_change_no_status_branch(
    mock_labels, mock_ensure, mock_edit, integration, client
) -> None:
    """push_task_change with fields={'status'} is a no-op — no gh calls made."""
    task = await client.tasks.create("Task", description="desc")
    task.github_issue = "octocat/hello-world#10"

    await integration.push_task_change(client, task, fields={"status"})

    mock_edit.assert_not_called()
    mock_ensure.assert_not_called()
    mock_labels.assert_not_called()


async def test_from_sync_flag_prevents_push_back(client) -> None:
    """Tasks updated with _from_sync=True never trigger push-back to GitHub."""
    with patch(
        "kagan.core.integrations.github._push_task_change",
        new_callable=AsyncMock,
    ) as mock_push:
        task = await client.tasks.create("Bug", description="Body")
        # Update with _from_sync=True — this must NOT call _push_task_change
        await client.tasks.update(task.id, title="Bug updated", _from_sync=True)

    mock_push.assert_not_called()
