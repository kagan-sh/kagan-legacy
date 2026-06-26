"""Skeleton smoke: the MCP server is created over stdio with exactly the report tools."""

import pytest

from kagan.mcp.server import ServerOptions, create_server


@pytest.mark.mcp
@pytest.mark.smoke
async def test_server_registers_exactly_the_report_tools(tmp_path) -> None:
    # MCP-SRV-02/04 + SEC-02: only report tools exist, so anything else (a push/merge
    # tool, an unknown tool) is rejected by construction. report_findings (lever 2) is
    # a report tool — it lands findings the human still adjudicates, never pushes/merges.
    server = create_server(ServerOptions(data_dir=str(tmp_path / "kagan.db")))
    assert server.name == "kagan"
    names = {t.name for t in await server.list_tools()}
    assert names == {
        "report_intake_decisions",
        "report_needs_you",
        "report_smoke_tests",
        "report_drift",
        "report_findings",
        "report_done",
    }
