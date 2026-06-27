import difflib
from importlib.metadata import version

import click
from loguru import logger

from kagan.cli._bootstrap import maybe_check_for_updates
from kagan.core.errors import KaganError
from kagan.runtime_env import sanitize_startup_environment as _sanitize_startup_environment

_ISSUES_URL = "https://github.com/kagan-sh/kagan/issues"


def _print_crash_footer() -> None:
    from kagan.core import default_log_path

    log_path = default_log_path()
    click.echo(f"Log file: {log_path}", err=True)
    click.echo(f"Bug report: {_ISSUES_URL}/new", err=True)
    click.echo("Run `kagan doctor` for a system health check.", err=True)


class _CrashException(click.ClickException):
    def show(self, file=None) -> None:
        super().show(file=file)
        _print_crash_footer()


class _CLIGroup(click.Group):
    def list_commands(self, ctx: click.Context) -> list[str]:
        _register_commands()
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        _register_commands()
        return super().get_command(ctx, cmd_name)

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple:
        _register_commands()
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as exc:
            if args:
                cmd_name = args[0]
                matches = difflib.get_close_matches(
                    cmd_name, self.list_commands(ctx), n=3, cutoff=0.6
                )
                if matches:
                    suggestion = ", ".join(f"'{m}'" for m in matches)
                    raise click.UsageError(
                        f"No such command '{cmd_name}'. Did you mean: {suggestion}?"
                    ) from exc
            raise

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except click.ClickException:
            raise
        except click.exceptions.Exit:
            raise
        except click.Abort:
            raise
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            logger.exception("Unhandled CLI exception")
            hint = getattr(exc, "hint", "")
            message = str(exc)
            if hint:
                message = f"{message}\nhint: {hint}"
            raise _CrashException(message) from exc


def _print_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"ᘚᘛ kagan {version('kagan')}")
    ctx.exit()


@click.group(
    cls=_CLIGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
    help="ᘚᘛ Kagan — a supervision layer for AI coding agents.",
    epilog=(
        "\b\n"
        "Common workflows:\n"
        "  kagan          Launch the interactive supervision session\n"
        "  kagan doctor   Check system health\n\n"
        "Full reference: https://docs.kagan.sh/reference/cli/"
    ),
)
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_version,
    help="Show version and exit",
)
@click.option(
    "--skip-update-check",
    is_flag=True,
    hidden=True,
    envvar="KAGAN_SKIP_UPDATE_CHECK",
    help="Skip startup update check",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose stderr logging")
@click.pass_context
def cli(ctx: click.Context, skip_update_check: bool, verbose: bool) -> None:
    from kagan.core import configure_logging

    _sanitize_startup_environment()
    configure_logging(verbose=verbose)

    _register_commands()

    latest = maybe_check_for_updates(skip=skip_update_check)
    if latest:
        click.echo(f"hint: kagan {latest} available. Run `kagan update`.")

    if ctx.invoked_subcommand is None:
        # Bare `kagan` launches the interactive session (canonical entry point),
        # after the doctor preflight.
        _launch_session()


def _launch_session() -> None:
    from pathlib import Path

    from kagan.cli._bootstrap import run_async
    from kagan.cli.doctor import run_doctor_checks
    from kagan.cli.session import run as session_run
    from kagan.core import git, install_asyncio_subprocess_exception_filter
    from kagan.format.doctor import render_preflight

    install_asyncio_subprocess_exception_filter()

    # Preflight renders on ANY non-pass (warn too) so degraded-mode warnings
    # ("gh not found — CI watch off") are visible — not only on a hard fail. The
    # blocking confirm still gates ONLY on a fail; warnings inform and proceed.
    checks = run_doctor_checks()
    fails = [c for c in checks if c.status == "fail"]
    degraded = bool(fails) or any(c.status == "warn" for c in checks)
    if degraded:
        from kagan.format._console import print_themed

        print_themed(render_preflight(checks))

    repo_root = git.repo_root(Path.cwd())
    # A missing manifest is the one fail `kagan init` can fix in place — offer it rather
    # than the generic "continue anyway". init bootstraps git too when cwd isn't a repo,
    # so this fires even without a git repo (init then BLOCKS if the user declines git).
    if [c.name for c in fails] == ["repo manifest"]:
        from kagan.cli.init import run_init

        if not click.confirm("No .kagan/repo.yaml yet. Run setup now?", default=True):
            return  # declined setup — don't drop into a manifestless session
        if run_async(run_init(repo_root, show_preflight=False)) is None:
            return  # setup didn't complete (declined git, etc.) — don't launch
        repo_root = git.repo_root(Path.cwd())  # re-resolve: init may have created the repo
    elif fails and not click.confirm("Continue anyway?", default=False):
        return

    if degraded:
        # The preflight/init phase printed with raw click on the primary screen;
        # wipe it before the full-screen session renders into the litter.
        click.clear()
    run_async(session_run(repo_root=repo_root))


_commands_registered = False


def _register_commands() -> None:
    """One idempotent source of truth — registers the subcommands exactly once."""
    global _commands_registered
    if _commands_registered:
        return
    _commands_registered = True

    from kagan.cli._run import _run
    from kagan.cli.doctor import doctor
    from kagan.cli.init import init
    from kagan.cli.mcp import mcp
    from kagan.cli.new import new
    from kagan.cli.reset import reset
    from kagan.cli.tui import tui
    from kagan.cli.update import update

    for command in (tui, doctor, init, mcp, new, reset, update, _run):
        cli.add_command(command)
