"""MCP server command."""

from __future__ import annotations

import click

_VALID_CAPABILITIES = {"viewer", "planner", "pair_worker", "operator", "maintainer"}
_VALID_IDENTITIES = {"kagan", "kagan_admin"}

MCP_PROFILE_PRESETS: dict[str, dict[str, str]] = {
    "security-reviewer": {
        "capability": "viewer",
        "identity": "kagan",
        "description": (
            "Read-only access. Can inspect tasks and flag concerns. Cannot modify or merge."
        ),
    },
    "test-writer": {
        "capability": "pair_worker",
        "identity": "kagan",
        "description": (
            "Can create and update tasks, run agents. Cannot merge or manage projects."
        ),
    },
    "refactoring-agent": {
        "capability": "pair_worker",
        "identity": "kagan",
        "description": (
            "Pair-worker scope. Suitable for bounded refactoring with human review gate."
        ),
    },
    "pair-worker": {
        "capability": "pair_worker",
        "identity": "kagan",
        "description": "Standard human-paired development scope.",
    },
    "orchestrator": {
        "capability": "operator",
        "identity": "kagan_admin",
        "description": (
            "Full task/session/review surface. For orchestrator agents running AUTO pipelines."
        ),
    },
    "maintainer": {
        "capability": "maintainer",
        "identity": "kagan_admin",
        "description": ("Maximum capability. Use for admin-lane orchestrators and CI pipelines."),
    },
}

_PRESET_NAMES = ", ".join(MCP_PROFILE_PRESETS)


@click.command()
@click.option(
    "--readonly",
    is_flag=True,
    help="Expose only read-only coordination tools (for ACP agents)",
)
@click.option(
    "--session-id",
    default=None,
    help="Session ID to bind this MCP server instance to a specific task",
)
@click.option(
    "--capability",
    default=None,
    help="Capability profile for this session (viewer|planner|pair_worker|operator|maintainer)",
)
@click.option(
    "--endpoint",
    default=None,
    help="Core endpoint address to connect to (overrides discovery)",
)
@click.option(
    "--identity",
    default=None,
    help="Session identity lane for policy ceilings (kagan|kagan_admin)",
)
@click.option(
    "--enable-internal-instrumentation",
    is_flag=True,
    default=False,
    help="Enable internal instrumentation diagnostics MCP tool (disabled by default).",
)
@click.option(
    "--preset",
    default=None,
    help=(
        f"Pre-built identity+capability profile. One of: {_PRESET_NAMES}."
        " Overridden by explicit --capability/--identity."
    ),
)
def mcp(
    readonly: bool,
    session_id: str | None,
    capability: str | None,
    endpoint: str | None,
    identity: str | None,
    enable_internal_instrumentation: bool,
    preset: str | None,
) -> None:
    """Run the MCP server (STDIO transport).

    This command is typically invoked by AI agents (Claude Code, OpenCode, etc.)
    to communicate with Kagan via the Model Context Protocol.

    The MCP server uses centralized storage and assumes the current working
    directory is a Kagan-managed project.

    Use --readonly for ACP agents to expose only coordination tools
    (task_list, task_get).
    """
    if preset is not None:
        if preset not in MCP_PROFILE_PRESETS:
            valid = ", ".join(sorted(MCP_PROFILE_PRESETS))
            raise click.BadParameter(f"Invalid preset '{preset}'. Expected one of: {valid}")
        preset_data = MCP_PROFILE_PRESETS[preset]
        if capability is None:
            capability = preset_data["capability"]
        if identity is None:
            identity = preset_data["identity"]

    if capability is not None and capability not in _VALID_CAPABILITIES:
        valid = ", ".join(sorted(_VALID_CAPABILITIES))
        raise click.BadParameter(f"Invalid capability '{capability}'. Expected one of: {valid}")
    if identity is not None and identity not in _VALID_IDENTITIES:
        valid = ", ".join(sorted(_VALID_IDENTITIES))
        raise click.BadParameter(f"Invalid identity '{identity}'. Expected one of: {valid}")

    from kagan.mcp.server import main as mcp_main

    if enable_internal_instrumentation:
        mcp_main(
            readonly=readonly,
            endpoint=endpoint,
            session_id=session_id,
            capability=capability,
            identity=identity,
            enable_internal_instrumentation=True,
        )
        return
    mcp_main(
        readonly=readonly,
        endpoint=endpoint,
        session_id=session_id,
        capability=capability,
        identity=identity,
    )


def _emit_profile_presets() -> None:
    click.echo("Available MCP access profiles:\n")
    for name, data in MCP_PROFILE_PRESETS.items():
        cap = data["capability"]
        ident = data["identity"]
        click.echo(f"  {name}")
        click.echo(f"    {data['description']}")
        click.echo(f"    Equivalent: kagan mcp --capability {cap} --identity {ident}")
        click.echo()


@click.command(name="profiles")
def profiles() -> None:
    """List available MCP access profiles and their equivalent flags."""
    _emit_profile_presets()
