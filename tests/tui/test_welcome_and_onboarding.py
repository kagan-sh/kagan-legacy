import pytest
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo
from textual.widgets import Input

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def test_launch_shows_welcome_with_project_list(board_with_task: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "welcome-screen"
        assert app.screen.query_one("#project-list") is not None


async def test_enter_on_welcome_opens_kanban(board_with_task: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_enter_on_empty_welcome_creates_project_from_cwd(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui import KaganApp

    monkeypatch.chdir(tmp_path)

    app = KaganApp(db_path=tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "welcome-screen"

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert app.screen.id == "kanban-screen"
        projects = await app.core.projects.list()
        assert len(projects) == 1
        assert projects[0].name == tmp_path.name


async def test_dismissed_cwd_banner_updates_enter_hint_and_action(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.hint_bar import KeybindingHint

    monkeypatch.chdir(tmp_path)

    app = KaganApp(db_path=tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "welcome-screen"

        await pilot.press("escape")
        await pilot.pause()

        hint_widget = app.screen.query_one("#welcome-hint", KeybindingHint)
        assert "new project" in hint_widget.hints

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen.id == "setup-flow"


async def test_enter_prefers_cwd_banner_create_over_recent_project(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.hint_bar import KeybindingHint

    driver = await KaganDriver.boot(tmp_path)
    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    await driver.create_project("Project A", repo_path=str(repo_a))

    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    monkeypatch.chdir(repo_b)

    app = KaganApp(db_path=tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "welcome-screen"

        hint_widget = app.screen.query_one("#welcome-hint", KeybindingHint)
        assert "create" in hint_widget.hints

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert app.screen.id == "kanban-screen"
        assert app.project is not None
        assert app.project.name == "repo-b"

        project_for_b = await app.core.projects.find_by_repo(str(repo_b.resolve()))
        assert project_for_b is not None

    await driver.teardown()


async def test_returning_to_welcome_refreshes_project_list_after_cwd_create(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import OptionList

    from kagan.tui import KaganApp

    driver = await KaganDriver.boot(tmp_path)
    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    await driver.create_project("Project A", repo_path=str(repo_a))

    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    monkeypatch.chdir(repo_b)

    app = KaganApp(db_path=tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.id == "welcome-screen"

        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert app.screen.id == "kanban-screen"

        await app.action_open_project_selector()
        await pilot.pause()
        await pilot.pause()
        assert app.screen.id == "welcome-screen"

        project_list = app.screen.query_one("#project-list", OptionList)
        assert project_list.option_count == 2

    await driver.teardown()


async def test_new_project_from_welcome_creates_project_and_opens_kanban(tmp_path) -> None:
    from kagan.tui import KaganApp

    driver = await KaganDriver.boot(tmp_path)
    repo_path = driver.tmp_path / "sample-repo"
    repo_path.mkdir()

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        assert app.screen.id == "setup-flow"
        app.screen.query_one("#new-project-name", Input).value = "New Project"
        app.screen.query_one("#new-project-repo-path", Input).value = str(repo_path)

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen.id == "kanban-screen"

        projects = await app.core.projects.list()
        created = next((project for project in projects if project.name == "New Project"), None)
        assert created is not None

        repos = await app.core.projects.repos(created.id)
        assert len(repos) == 1
        assert repos[0].path == str(repo_path.resolve())
        assert (repo_path / ".git").exists()

    await driver.teardown()


async def test_new_project_from_welcome_links_existing_repo(tmp_path) -> None:
    from kagan.tui import KaganApp

    driver = await KaganDriver.boot(tmp_path)
    repo_path = driver.tmp_path / "existing-repo"
    await make_git_repo(repo_path)

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        assert app.screen.id == "setup-flow"
        app.screen.query_one("#new-project-name", Input).value = "Linked Project"
        app.screen.query_one("#new-project-repo-path", Input).value = str(repo_path)

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen.id == "kanban-screen"

        projects = await app.core.projects.list()
        created = next((project for project in projects if project.name == "Linked Project"), None)
        assert created is not None

        repos = await app.core.projects.repos(created.id)
        assert len(repos) == 1
        assert repos[0].path == str(repo_path.resolve())

    await driver.teardown()
