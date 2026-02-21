"""Tests for ACP MCP argument construction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kagan.core.acp.kagan_agent import KaganAgent, _build_mcp_args
from kagan.core.config import AgentConfig


def test_build_mcp_args_unscoped_mutating_uses_admin_lane(monkeypatch) -> None:
    monkeypatch.setattr(
        "kagan.core.ipc.discovery.discover_core_endpoint",
        lambda *args, **kwargs: None,
    )

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


def test_build_mcp_args_unscoped_mutating_honors_custom_external_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        "kagan.core.ipc.discovery.discover_core_endpoint",
        lambda *args, **kwargs: None,
    )

    args = _build_mcp_args(
        task_id="",
        read_only=False,
        external_session_scope_id="orchestrator-20260220",
    )

    assert args == [
        "mcp",
        "--capability",
        "maintainer",
        "--identity",
        "kagan_admin",
        "--session-id",
        "ext:orchestrator-20260220",
    ]


def test_build_mcp_args_task_scope_uses_worker_lane(monkeypatch) -> None:
    monkeypatch.setattr(
        "kagan.core.ipc.discovery.discover_core_endpoint",
        lambda *args, **kwargs: None,
    )

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


@pytest.mark.asyncio
@pytest.mark.windows_ci
async def test_acp_new_session_uses_resolved_kagan_cli_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "kagan.core.ipc.discovery.discover_core_endpoint",
        lambda *args, **kwargs: None,
    )
    monkeypatch.delenv("KAGAN_TASK_ID", raising=False)
    monkeypatch.setattr(
        "kagan.core.acp.kagan_agent.build_kagan_mcp_command_args",
        lambda mcp_args: ("C:/Python312/python.exe", ["-m", "kagan", *mcp_args]),
    )

    agent = KaganAgent(
        tmp_path,
        AgentConfig(
            identity="claude.com",
            name="Claude Code",
            short_name="claude",
            run_command={"*": "npx claude-code-acp"},
        ),
    )

    class _Conn:
        def __init__(self) -> None:
            self.cwd = ""
            self.mcp_servers = []

        async def new_session(self, *, cwd, mcp_servers):
            self.cwd = cwd
            self.mcp_servers = mcp_servers
            return SimpleNamespace(session_id="session-123", modes=None)

    conn = _Conn()
    await agent._acp_new_session(conn)

    assert conn.cwd == str(tmp_path.absolute())
    assert len(conn.mcp_servers) == 1
    mcp_server = conn.mcp_servers[0]
    assert mcp_server.command == "C:/Python312/python.exe"
    assert mcp_server.args[:2] == ["-m", "kagan"]
    assert mcp_server.args[2:] == _build_mcp_args(task_id="", read_only=False)
    assert agent.session_id == "session-123"
