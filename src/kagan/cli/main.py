"""CLI entry boundary and explicit subcommand routing."""

from __future__ import annotations

from importlib.metadata import version

import click

from kagan.cli.commands.core import core
from kagan.cli.commands.doctor import doctor
from kagan.cli.commands.list_projects import list_cmd
from kagan.cli.commands.mcp import mcp
from kagan.cli.commands.reset import reset
from kagan.cli.commands.tui import tui
from kagan.cli.tools import tools
from kagan.cli.update import update

__version__ = version("kagan")

_ROUTED_COMMANDS: tuple[click.Command, ...] = (
    update,
    tools,
    tui,
    reset,
    list_cmd,
    mcp,
    core,
    doctor,
)


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx: click.Context, version: bool) -> None:
    """AI-powered Kanban TUI for autonomous development workflows."""
    if version:
        click.echo(f"kagan {__version__}")
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        ctx.invoke(tui)


for _command in _ROUTED_COMMANDS:
    cli.add_command(_command)
