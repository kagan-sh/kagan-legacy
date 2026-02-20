"""Tests for ACP MCP argument construction."""

from __future__ import annotations

from kagan.core.acp.kagan_agent import _build_mcp_args


def test_build_mcp_args_unscoped_mutating_uses_admin_lane(monkeypatch) -> None:
    monkeypatch.setattr("kagan.core.ipc.discovery.discover_core_endpoint", lambda: None)

    args = _build_mcp_args(task_id="", read_only=False)

    assert args == [
        "mcp",
        "--capability",
        "maintainer",
        "--identity",
        "kagan_admin",
        "--session-id",
        "ext:orchestrator",
    ]


def test_build_mcp_args_task_scope_uses_worker_lane(monkeypatch) -> None:
    monkeypatch.setattr("kagan.core.ipc.discovery.discover_core_endpoint", lambda: None)

    args = _build_mcp_args(task_id="abc123", read_only=False)

    assert args == [
        "mcp",
        "--capability",
        "pair_worker",
        "--identity",
        "kagan",
        "--session-id",
        "task:abc123",
    ]
