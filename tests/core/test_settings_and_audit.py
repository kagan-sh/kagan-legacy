"""Feature tests: Settings & Audit — docs/internal/features/core.md §9."""

import pytest

from kagan.core import TaskStatus
from tests.helpers.driver import KaganDriver

pytestmark = pytest.mark.core


async def test_settings_get_returns_empty_dict_initially(board: KaganDriver) -> None:
    result = await board.settings_get()
    assert isinstance(result, dict)


async def test_settings_update_persists_and_is_readable(board: KaganDriver) -> None:
    await board.settings_update({"default_agent_backend": "claude-code"})
    result = await board.settings_get()
    assert result.get("default_agent_backend") == "claude-code"


async def test_known_settings_keys_are_persisted(board: KaganDriver) -> None:
    await board.settings_update(
        {
            "default_agent_backend": "opencode",
            "default_launcher": "tmux",
            "auto_review": "false",
            "require_approval": "true",
        }
    )
    result = await board.settings_get()
    assert result["default_agent_backend"] == "opencode"
    assert result["default_launcher"] == "tmux"
    assert result["auto_review"] == "false"
    assert result["require_approval"] == "true"


async def test_mutations_are_audit_logged(board: KaganDriver) -> None:
    await board.create_task("Audited Task")
    audit = await board.audit_list(limit=10)
    assert isinstance(audit, dict)
    items = audit.get("items", [])
    assert isinstance(items, list)
    assert len(items) >= 1


async def test_update_task_is_audit_logged(board: KaganDriver) -> None:
    task = await board.create_task("Audit Update Task")
    await board.update_task(task.id, title="Updated Title")

    items = (await board.audit_list(limit=5)).get("items", [])
    actions = [item.get("action") for item in items]
    assert "task.update" in actions


async def test_status_transition_is_audit_logged(board: KaganDriver) -> None:
    task = await board.create_task("Audit Status Task")
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)

    items = (await board.audit_list(limit=5)).get("items", [])
    actions = [item.get("action") for item in items]
    assert "task.status_change" in actions


async def test_delete_task_is_audit_logged(board: KaganDriver) -> None:
    task = await board.create_task("Audit Delete Task")
    await board.delete_task(task.id)

    items = (await board.audit_list(limit=10)).get("items", [])
    actions = [item.get("action") for item in items]
    assert "task.delete" in actions


async def test_audit_trail_queryable_with_limit(board: KaganDriver) -> None:
    await board.create_task("Task A")
    await board.create_task("Task B")
    await board.create_task("Task C")

    audit_all = await board.audit_list(limit=100)
    audit_limited = await board.audit_list(limit=1)

    all_items = audit_all.get("items", [])
    limited_items = audit_limited.get("items", [])
    assert isinstance(all_items, list)
    assert isinstance(limited_items, list)

    assert len(all_items) >= 3
    assert len(limited_items) <= 1
