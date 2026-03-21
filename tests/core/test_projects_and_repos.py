"""Feature tests: Projects & Repos — docs/internal/features/core.md §2."""

import pytest

from kagan.core.errors import SessionError
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo

pytestmark = pytest.mark.core


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    yield driver
    await driver.teardown()


async def test_create_project_appears_in_list(board: KaganDriver) -> None:
    project_id = await board.create_project("Alpha Project")
    projects = await board.list_projects()
    assert any(p.id == project_id for p in projects)
    assert any(p.name == "Alpha Project" for p in projects)


async def test_link_repo_to_project_by_path(board: KaganDriver, tmp_path) -> None:
    repo_path = tmp_path / "my-repo"
    await make_git_repo(repo_path)
    project_id = await board.create_project("Repo Project")
    repo_id = await board.add_repo(repo_path)
    repos = await board.get_project_repos(project_id)
    assert any(r.id == repo_id for r in repos)
    assert any(str(repo_path) in r.path for r in repos)


async def test_add_repo_auto_initializes_git_by_default(board: KaganDriver, tmp_path) -> None:
    repo_path = tmp_path / "plain-folder"
    project_id = await board.create_project("Auto Init Project")

    assert not (repo_path / ".git").exists()
    repo_id = await board.add_repo(repo_path)

    repos = await board.get_project_repos(project_id)
    assert any(r.id == repo_id for r in repos)
    assert (repo_path / ".git").exists()


async def test_add_repo_requires_git_when_auto_init_disabled(board: KaganDriver, tmp_path) -> None:
    repo_path = tmp_path / "manual-folder"
    await board.create_project("Manual Init Project")
    await board.settings_update({"auto_init_git_repo": "false"})

    with pytest.raises(SessionError):
        await board.add_repo(repo_path)


async def test_add_repo_uses_default_base_branch_setting(board: KaganDriver, tmp_path) -> None:
    repo_path = tmp_path / "trunk-folder"
    project_id = await board.create_project("Branch Default Project")
    await board.settings_update({"default_base_branch": "trunk"})

    await board.add_repo(repo_path)
    repos = await board.get_project_repos(project_id)
    assert repos[0].default_branch == "trunk"


async def test_add_repo_same_path_is_idempotent_for_same_project(
    board: KaganDriver, tmp_path
) -> None:
    repo_path = tmp_path / "idempotent-repo"
    await make_git_repo(repo_path)
    project_id = await board.create_project("Idempotent Repo Project")

    first_repo_id = await board.add_repo(repo_path)
    second_repo_id = await board.add_repo(repo_path)

    assert first_repo_id == second_repo_id
    repos = await board.get_project_repos(project_id)
    assert len(repos) == 1


async def test_add_repo_same_path_across_projects_raises_session_error(
    board: KaganDriver, tmp_path
) -> None:
    repo_path = tmp_path / "shared-repo"
    await make_git_repo(repo_path)

    await board.create_project("Project One")
    await board.add_repo(repo_path)
    await board.create_project("Project Two")

    with pytest.raises(SessionError, match="already linked"):
        await board.add_repo(repo_path)


async def test_create_project_with_duplicate_repo_path_rolls_back_new_project(
    board: KaganDriver, tmp_path
) -> None:
    repo_path = tmp_path / "duplicate-create-repo"
    await make_git_repo(repo_path)

    await board.create_project("Primary Project", repo_path=str(repo_path))
    projects_before = await board.list_projects()

    with pytest.raises(SessionError, match="already linked"):
        await board.create_project("Conflicting Project", repo_path=str(repo_path))

    projects_after = await board.list_projects()
    assert len(projects_after) == len(projects_before)
    assert all(project.name != "Conflicting Project" for project in projects_after)


async def test_set_active_project_scopes_task_ops(board: KaganDriver) -> None:
    pid_a = await board.create_project("Project A")
    pid_b = await board.create_project("Project B")

    await board.open_project(pid_a)
    task_a = await board.create_task("Task in A")

    await board.open_project(pid_b)
    task_b = await board.create_task("Task in B")

    assert task_a.project_id == pid_a
    assert task_b.project_id == pid_b

    tasks_in_b = await board.list_tasks()
    task_ids = {t.id for t in tasks_in_b}
    assert task_b.id in task_ids
    assert task_a.id not in task_ids


async def test_find_project_by_name(board: KaganDriver) -> None:
    await board.create_project("Findable Project")
    project = await board.get_project(
        next(p.id for p in await board.list_projects() if p.name == "Findable Project")
    )
    assert project is not None
    assert project.name == "Findable Project"


async def test_find_project_by_repo_path(board: KaganDriver, tmp_path) -> None:
    repo_path = tmp_path / "linked-repo"
    await make_git_repo(repo_path)
    await board.create_project("Repo-Linked Project")
    await board.add_repo(repo_path)

    found = await board.find_project_by_repo_path(repo_path)
    assert found is not None
    assert found.name == "Repo-Linked Project"


async def test_find_project_by_repo_path_normalizes_query_path(
    board: KaganDriver, tmp_path
) -> None:
    repo_path = tmp_path / "linked-repo-normalized"
    await make_git_repo(repo_path)
    await board.create_project("Normalized Lookup Project")
    await board.add_repo(repo_path)

    found = await board.find_project_by_repo_path(f"{repo_path}/.")
    assert found is not None
    assert found.name == "Normalized Lookup Project"


async def test_delete_project_removes_it_from_list(board: KaganDriver) -> None:
    project_id = await board.create_project("Doomed Project")
    await board.delete_project(project_id)
    projects = await board.list_projects()
    assert not any(p.id == project_id for p in projects)


async def test_delete_project_cascades_tasks(board: KaganDriver) -> None:
    project_id = await board.create_project("Cascade Project")
    await board.create_task("Task to be deleted")
    tasks_before = await board.list_tasks()
    assert len(tasks_before) >= 1

    await board.delete_project(project_id)

    await board.create_project("Fresh Project")
    tasks_after = await board.list_tasks()
    assert all(t.project_id != project_id for t in tasks_after)


async def test_delete_active_project_clears_scope(board: KaganDriver) -> None:
    project_id = await board.create_project("Active Project")
    await board.delete_project(project_id)

    with pytest.raises(SessionError):
        await board.create_task("Should fail without active project")
