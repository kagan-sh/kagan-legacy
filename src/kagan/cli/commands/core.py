"""Core process management commands."""

from __future__ import annotations

import os
import signal
import sys

import click

from kagan.core.paths import get_core_runtime_dir
from kagan.core.services.runtime import (
    cleanup_stale_runtime_files,
    discover_running_pid_fallback,
)


@click.group()
def core() -> None:
    """Manage the Kagan core process."""


def _print_endpoint_details(endpoint, *, include_runtime: bool = False) -> None:
    """Print endpoint details in a consistent format."""
    click.echo(f"  Transport: {endpoint.transport}")
    click.echo(f"  Address:   {endpoint.address}")
    if endpoint.port is not None:
        click.echo(f"  Port:      {endpoint.port}")
    if endpoint.pid is not None:
        click.echo(f"  PID:       {endpoint.pid}")
    if include_runtime:
        click.echo(f"  Runtime:   {get_core_runtime_dir()}")


@core.command()
@click.option(
    "--foreground",
    is_flag=True,
    help="Run core in foreground (blocks until stopped).",
)
def start(foreground: bool) -> None:
    """Start the core process if it is not running."""
    from kagan.core.ipc.discovery import discover_core_endpoint
    from kagan.core.services.runtime import ensure_core_running_sync, launch_core_subprocess

    endpoint = discover_core_endpoint()
    if endpoint is not None:
        click.secho("Core is already running.", fg="green", bold=True)
        _print_endpoint_details(endpoint)
        return

    if foreground:
        raise SystemExit(launch_core_subprocess())

    endpoint = ensure_core_running_sync()
    click.secho("Core started.", fg="green", bold=True)
    _print_endpoint_details(endpoint, include_runtime=True)


@core.command()
def status() -> None:
    """Show the status of the running core process."""
    from kagan.core.ipc.discovery import discover_core_endpoint

    endpoint = discover_core_endpoint()
    if endpoint is None:
        fallback_pid = discover_running_pid_fallback()
        if fallback_pid is not None:
            click.secho("Core process is running, but runtime metadata is incomplete.", fg="yellow")
            click.echo(f"  PID:       {fallback_pid}")
            click.echo(f"  Runtime:   {get_core_runtime_dir()}")
            click.echo("  Hint:      run `kagan core stop` then `kagan core start`")
            sys.exit(2)
        click.secho("Core is not running.", fg="yellow")
        sys.exit(1)

    click.secho("Core is running.", fg="green", bold=True)
    _print_endpoint_details(endpoint, include_runtime=True)


@core.command()
def stop() -> None:
    """Stop the running core process."""
    from kagan.core.ipc.discovery import discover_core_endpoint

    endpoint = discover_core_endpoint()
    pid = endpoint.pid if endpoint is not None else None
    if pid is None:
        pid = discover_running_pid_fallback()
    if pid is None:
        click.secho("Core is not running.", fg="yellow")
        sys.exit(1)

    click.echo(f"Stopping core process (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        click.secho("Stop signal sent.", fg="green")
    except ProcessLookupError:
        click.secho("Process already stopped.", fg="yellow")
        # Clean up stale runtime files
        cleanup_stale_runtime_files()
    except PermissionError:
        click.secho(f"Permission denied to stop PID {pid}.", fg="red")
        sys.exit(1)
