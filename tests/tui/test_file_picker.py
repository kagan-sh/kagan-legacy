from pathlib import Path

import pytest
from tests.helpers.driver import KaganDriver
from textual.screen import Screen
from textual.widgets import Input, Static

from kagan.tui import KaganApp
from kagan.tui.widgets.chat import ChatPanel

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


def _write_repo_files(repo_path: Path) -> None:
    (repo_path / "src").mkdir(parents=True, exist_ok=True)
    (repo_path / "src" / "keep.py").write_text("print('keep')\n", encoding="utf-8")
    (repo_path / "src" / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
    (repo_path / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")


class _ChatHostScreen(Screen):
    def compose(self):
        yield ChatPanel()

    def on_chat_panel_file_picker_requested(self, event: ChatPanel.FilePickerRequested) -> None:
        panel = self.query_one(ChatPanel)
        self.app.push_screen(
            panel.create_file_picker_modal(initial_query=event.initial_query),
            callback=panel.handle_file_picker_selected,
        )


class _FilePickerTestApp(KaganApp):
    CSS_PATH = []

    async def _route_startup(self) -> None:
        self.push_screen(_ChatHostScreen())


async def test_chat_file_picker_inserts_selected_relative_path_into_input(
    tmp_path: Path,
) -> None:
    driver = await KaganDriver.boot(tmp_path)
    repo_path = tmp_path / "repo"
    _write_repo_files(repo_path)
    project_id = await driver.create_project("File Picker Project", repo_path=repo_path)

    app = _FilePickerTestApp(db_path=driver.tmp_path / "kagan.db")
    project = await app.core.projects.get(project_id)
    await app.activate_project(project)
    await app.core.settings.set(
        {
            "open_last_project_on_startup": "true",
            "ui.last_project_id": project_id,
        }
    )

    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, _ChatHostScreen)

            panel = app.screen.query_one("#chat-panel", ChatPanel)
            panel.action_open_file_picker("keep")
            await pilot.pause()

            from kagan.tui.screens.file_picker import FilePickerModal

            assert isinstance(app.screen, FilePickerModal)
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, _ChatHostScreen)
            input_widget = app.screen.query_one("#chat-overlay-input", Input)
            assert input_widget.value == "src/keep.py "
    finally:
        await driver.teardown()


async def test_chat_file_picker_skips_gitignored_files(tmp_path: Path) -> None:
    driver = await KaganDriver.boot(tmp_path)
    repo_path = tmp_path / "repo"
    _write_repo_files(repo_path)
    project_id = await driver.create_project("File Picker Project", repo_path=repo_path)

    app = _FilePickerTestApp(db_path=driver.tmp_path / "kagan.db")
    project = await app.core.projects.get(project_id)
    await app.activate_project(project)
    await app.core.settings.set(
        {
            "open_last_project_on_startup": "true",
            "ui.last_project_id": project_id,
        }
    )

    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, _ChatHostScreen)

            panel = app.screen.query_one("#chat-panel", ChatPanel)
            panel.action_open_file_picker("ignored")
            await pilot.pause()

            from kagan.tui.screens.file_picker import FilePickerModal

            assert isinstance(app.screen, FilePickerModal)
            empty_state = app.screen.query_one("#file-picker-empty", Static)
            count = app.screen.query_one("#file-picker-match-count", Static)
            assert empty_state.display is True
            assert "No matching files." in str(count.render())
    finally:
        await driver.teardown()
