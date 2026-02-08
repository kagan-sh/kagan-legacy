"""MCP server command."""

from __future__ import annotations

import click


@click.command()
@click.option(
    "--readonly",
    is_flag=True,
    help="Expose only read-only coordination tools (for ACP agents)",
)
def mcp(readonly: bool) -> None:
    """Run the MCP server (STDIO transport).

    This command is typically invoked by AI agents (Claude Code, OpenCode, etc.)
    to communicate with Kagan via the Model Context Protocol.

    The MCP server uses centralized storage and assumes the current working
    directory is a Kagan-managed project.

    Use --readonly for ACP agents to expose only coordination tools
    (get_parallel_tasks, get_task).
    """
    from kagan.mcp.server import main as mcp_main

    mcp_main(readonly=readonly)
