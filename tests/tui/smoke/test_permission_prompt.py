from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Static

from kagan.tui.keybindings import PERMISSION_PROMPT_BINDINGS
from kagan.tui.ui.widgets.streaming_output import StreamingOutput
from tests.helpers.wait import wait_until

if TYPE_CHECKING:
    from kagan.tui.ui.widgets.permission_prompt import PermissionPrompt


@dataclass(slots=True)
class _FakePermissionOption:
    kind: str
    option_id: str


class _PermissionPromptHarness(App[None]):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(id="chat-input")
            yield StreamingOutput(id="output")


async def _mount_permission_prompt(
    app: _PermissionPromptHarness,
) -> tuple[PermissionPrompt, asyncio.Future]:
    output = app.query_one("#output", StreamingOutput)
    result_future = asyncio.get_running_loop().create_future()
    options = [
        _FakePermissionOption(kind="allow_once", option_id="allow-once-id"),
        _FakePermissionOption(kind="allow_always", option_id="allow-always-id"),
        _FakePermissionOption(kind="reject_once", option_id="deny-id"),
    ]
    prompt = await output.post_permission_request(
        options=options,
        tool_call=SimpleNamespace(title="Test Tool"),
        result_future=result_future,
        timeout=30.0,
    )
    return prompt, result_future


@pytest.mark.asyncio
async def test_permission_prompt_keyboard_controls_work_with_chat_input_present() -> None:
    app = _PermissionPromptHarness()

    async with app.run_test(size=(100, 20)) as pilot:
        chat_input = app.query_one("#chat-input", Input)
        chat_input.focus()
        prompt, result_future = await _mount_permission_prompt(app)

        await wait_until(
            lambda: app.focused is prompt,
            timeout=5.0,
            description="permission prompt to take focus away from chat input",
        )
        assert not list(prompt.query(Button))
        hint = prompt.query_one(".permission-controls", Static)
        assert "Y/Enter allow once" in str(hint.render())

        await pilot.press("y")
        await wait_until(
            lambda: result_future.done(),
            timeout=5.0,
            description="permission prompt to resolve allow-once with y",
        )
        assert result_future.result().id == "allow-once-id"
        assert chat_input.value == ""


def test_permission_prompt_bindings_include_yes_and_deny_aliases() -> None:
    actions_by_key = {binding.key: binding.action for binding in PERMISSION_PROMPT_BINDINGS}
    assert actions_by_key["y"] == "allow_once"
    assert actions_by_key["n"] == "deny"
    assert actions_by_key["d"] == "deny"


@pytest.mark.asyncio
@pytest.mark.parametrize("deny_key", ["n", "d"])
async def test_permission_prompt_deny_hotkeys_do_not_type_into_chat_input(deny_key: str) -> None:
    app = _PermissionPromptHarness()

    async with app.run_test(size=(100, 20)) as pilot:
        chat_input = app.query_one("#chat-input", Input)
        chat_input.focus()
        prompt, result_future = await _mount_permission_prompt(app)

        await wait_until(
            lambda: app.focused is prompt,
            timeout=5.0,
            description="permission prompt to take focus for deny key path",
        )
        await pilot.press(deny_key)
        await wait_until(
            lambda: result_future.done(),
            timeout=5.0,
            description=f"permission prompt to resolve deny with {deny_key}",
        )
        assert result_future.result().id == "deny-id"
        assert chat_input.value == ""
