"""Tests for MCP agent role-based tool filtering."""

import pytest

from kagan.core.enums import AgentRole
from kagan.server.mcp._policy import ALL_TOOL_NAMES, ROLE_TOOLS, is_tool_allowed
from kagan.server.mcp.server import ServerOptions


@pytest.mark.unit
def test_worker_role_tools() -> None:
    opts = ServerOptions(role=AgentRole.WORKER)
    allowed = {name for name in ALL_TOOL_NAMES if is_tool_allowed(name, opts)}
    assert allowed == {
        "task_get",
        "task_list",
        "task_search",
        "task_events",
        "task_add_note",
        "task_counts",
        "tasks_wait",
        "run_exists",
        "run_create",
        "run_get",
        "run_kill",
        "run_detach",
        "run_summary",
        "settings_get",
        "review_conflicts",
        "plugins_preflight",
        "plugins_preview",
        "session_compact",
        "verify_step",
        "verification_summary",
        "checkpoint_create",
        "checkpoint_list",
        "session_rewind",
        "insight_add",
        "insight_list",
    }


@pytest.mark.unit
def test_reviewer_role_includes_worker_tools() -> None:
    opts = ServerOptions(role=AgentRole.REVIEWER)
    allowed = {name for name in ALL_TOOL_NAMES if is_tool_allowed(name, opts)}
    worker_opts = ServerOptions(role=AgentRole.WORKER)
    worker_allowed = {name for name in ALL_TOOL_NAMES if is_tool_allowed(name, worker_opts)}
    assert worker_allowed < allowed
    assert "review_set_criterion_verdict" in allowed
    assert "review_clear_verdicts" in allowed


@pytest.mark.unit
def test_orchestrator_gets_all_tools() -> None:
    opts = ServerOptions(role=AgentRole.ORCHESTRATOR)
    allowed = {name for name in ALL_TOOL_NAMES if is_tool_allowed(name, opts)}
    assert allowed == ALL_TOOL_NAMES


@pytest.mark.unit
def test_no_role_defaults_to_orchestrator() -> None:
    opts = ServerOptions()
    allowed = {name for name in ALL_TOOL_NAMES if is_tool_allowed(name, opts)}
    assert allowed == ALL_TOOL_NAMES


@pytest.mark.unit
def test_role_hierarchy_is_cumulative() -> None:
    worker = ROLE_TOOLS[AgentRole.WORKER]
    reviewer = ROLE_TOOLS[AgentRole.REVIEWER]
    orchestrator = ROLE_TOOLS[AgentRole.ORCHESTRATOR]
    assert worker < reviewer
    assert reviewer < orchestrator


@pytest.mark.unit
def test_worker_cannot_mutate_tasks() -> None:
    opts = ServerOptions(role=AgentRole.WORKER)
    assert not is_tool_allowed("task_create", opts)
    assert not is_tool_allowed("task_update", opts)
    assert not is_tool_allowed("task_batch_create", opts)
    assert not is_tool_allowed("task_delete", opts)
    assert not is_tool_allowed("run_start", opts)
    assert not is_tool_allowed("run_cancel", opts)
    assert not is_tool_allowed("review_approve", opts)
    assert not is_tool_allowed("review_reject", opts)
    assert not is_tool_allowed("review_merge", opts)
    assert not is_tool_allowed("review_rebase", opts)


@pytest.mark.unit
def test_reviewer_cannot_decide_reviews() -> None:
    opts = ServerOptions(role=AgentRole.REVIEWER)
    assert not is_tool_allowed("review_approve", opts)
    assert not is_tool_allowed("review_reject", opts)
    assert not is_tool_allowed("review_merge", opts)
    assert not is_tool_allowed("review_rebase", opts)
    assert not is_tool_allowed("review_continue_rebase", opts)
    assert not is_tool_allowed("review_abort_rebase", opts)
