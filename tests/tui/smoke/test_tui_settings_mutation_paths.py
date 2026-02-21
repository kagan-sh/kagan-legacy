from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.core.builtin_agents import get_builtin_agent
from kagan.core.config import KaganConfig
from kagan.tui.app import KaganApp
from kagan.tui.ui.screens.kanban.session_controller import KanbanSessionController
from kagan.tui.ui.screens.welcome import WelcomeScreen


@pytest.mark.asyncio
async def test_kagan_app_persist_settings_updates_applies_local_config(tmp_path) -> None:
    app = KaganApp(
        db_path=str(tmp_path / "kagan.db"),
        config_path=str(tmp_path / "config.toml"),
    )
    update_settings = AsyncMock(
        return_value=(True, "Settings updated", {"general.auto_review": False}, {})
    )
    app._ctx = SimpleNamespace(
        api=SimpleNamespace(update_settings=update_settings),
        config=app.config,
    )

    success, message = await app.persist_settings_updates({"general.auto_review": False})

    assert success is True
    assert message == "Settings updated"
    assert app.config.general.auto_review is False
    assert app._ctx.config is app.config
    update_settings.assert_awaited_once_with({"general.auto_review": False})


class _WelcomeScreenForPreferenceTest(WelcomeScreen):
    def __init__(self, kagan_app: object) -> None:
        super().__init__()
        self._kagan_app = kagan_app

    @property
    def kagan_app(self) -> object:
        return self._kagan_app


@pytest.mark.asyncio
async def test_welcome_auto_review_persists_through_settings_api() -> None:
    persist = AsyncMock(return_value=(True, "Settings updated"))
    screen = _WelcomeScreenForPreferenceTest(
        SimpleNamespace(persist_settings_updates=persist),
    )

    await screen._persist_auto_review_preference(True)

    persist.assert_awaited_once_with({"general.auto_review": True})


@pytest.mark.asyncio
async def test_session_controller_skip_future_uses_settings_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    persist = AsyncMock(return_value=(True, "Settings updated"))
    apply_updates = MagicMock()

    screen = SimpleNamespace(
        kagan_app=SimpleNamespace(
            config=SimpleNamespace(ui=SimpleNamespace(skip_pair_instructions=False)),
            persist_settings_updates=persist,
            apply_settings_updates=apply_updates,
            config_path=tmp_path / "config.toml",
        ),
        run_worker=lambda awaitable, **kwargs: awaitable.close(),
        app=SimpleNamespace(),
    )
    controller = KanbanSessionController(screen=screen)  # type: ignore[arg-type]
    monkeypatch.setattr(
        "kagan.tui.ui.screens.kanban.session_controller.await_screen_result",
        AsyncMock(return_value="skip_future"),
    )
    monkeypatch.setattr(controller, "do_open_pair_session", AsyncMock())

    result = await controller._show_pair_instructions_if_needed(
        task=SimpleNamespace(id="task-1", title="PAIR"),
        workspace_path=tmp_path,
        terminal_backend="tmux",
    )

    assert result is True
    apply_updates.assert_called_once_with({"ui.skip_pair_instructions": True})


@pytest.mark.asyncio
async def test_session_controller_global_agent_persists_through_settings_api() -> None:
    builtin = get_builtin_agent("opencode")
    assert builtin is not None

    config = KaganConfig()
    config.agents["opencode"] = builtin.config.model_copy(deep=True)
    persist = AsyncMock(return_value=(True, "Settings updated"))
    update_agent = MagicMock()
    notify = MagicMock()
    screen = SimpleNamespace(
        kagan_app=SimpleNamespace(
            config=config,
            persist_settings_updates=persist,
            config_path=SimpleNamespace(),
        ),
        header=SimpleNamespace(update_agent_from_config=update_agent),
        notify=notify,
        ctx=SimpleNamespace(config=config),
    )
    controller = KanbanSessionController(screen=screen)  # type: ignore[arg-type]

    await controller.apply_global_agent_selection("opencode")

    persist.assert_awaited_once_with({"general.default_worker_agent": "opencode"})
    update_agent.assert_called_once_with(config)
    notify.assert_called_once_with("Global agent set to: opencode", severity="information")


@pytest.mark.asyncio
async def test_session_controller_save_pair_instructions_uses_settings_api() -> None:
    persist = AsyncMock(return_value=(True, "Settings updated"))
    notify = MagicMock()
    screen = SimpleNamespace(
        kagan_app=SimpleNamespace(persist_settings_updates=persist),
        notify=notify,
    )
    controller = KanbanSessionController(screen=screen)  # type: ignore[arg-type]

    await controller.save_pair_instructions_preference(skip=True)

    persist.assert_awaited_once_with({"ui.skip_pair_instructions": True})
    notify.assert_not_called()
