import difflib
import importlib
from importlib.metadata import version

import click
from loguru import logger

from kagan.cli._bootstrap import maybe_check_for_updates
from kagan.core.errors import KaganError
from kagan.runtime_env import sanitize_startup_environment as _sanitize_startup_environment

_RICH_CLICK_MODULE: object | None = None
_RICH_GROUP_BASE: type[click.Group] = click.Group
try:
    _RICH_CLICK_MODULE = importlib.import_module("rich_click")
    _RICH_GROUP_BASE = getattr(_RICH_CLICK_MODULE, "RichGroup", click.Group)
except ModuleNotFoundError:
    _RICH_CLICK_MODULE = None


def _configure_rich_click() -> None:
    if _RICH_CLICK_MODULE is None:
        return
    settings = getattr(_RICH_CLICK_MODULE, "rich_click", None)
    if settings is None:
        return
    settings.GROUP_ARGUMENTS_OPTIONS = True
    settings.FOOTER_TEXT = "Documentation: https://docs.kagan.sh/reference/cli/"


def _option_switches(command: click.Command, ctx: click.Context) -> list[str]:
    switches: list[str] = []
    for param in command.get_params(ctx):
        if not isinstance(param, click.Option) or param.hidden:
            continue
        long_names = [name for name in param.opts if name.startswith("--")]
        if long_names:
            switches.append(long_names[0])
        elif param.opts:
            switches.append(param.opts[0])
    return switches


def _sync_rich_click_groups(root_group: click.Group) -> None:
    if _RICH_CLICK_MODULE is None:
        return
    settings = getattr(_RICH_CLICK_MODULE, "rich_click", None)
    if settings is None:
        return
    context = click.Context(root_group)
    root_options = _option_switches(root_group, context)
    command_names = [name for name, command in root_group.commands.items() if not command.hidden]

    root_names = {"kagan", "kg", "cli", root_group.name or ""}
    root_names.discard("")
    for root_name in root_names:
        settings.OPTION_GROUPS[root_name] = [{"name": "Options", "options": root_options}]
        settings.COMMAND_GROUPS[root_name] = [{"name": "Commands", "commands": command_names}]

    for command_name, command in root_group.commands.items():
        switches = _option_switches(command, context)
        if switches:
            settings.OPTION_GROUPS[command_name] = [{"name": "Options", "options": switches}]


_configure_rich_click()

_ISSUES_URL = "https://github.com/kagan-sh/kagan/issues"


def _print_crash_footer() -> None:
    from kagan.core._logging import default_log_path

    log_path = default_log_path()
    click.echo(f"Log file: {log_path}", err=True)
    click.echo(f"Bug report: {_ISSUES_URL}/new", err=True)


class _CrashException(click.ClickException):
    def show(self, file=None) -> None:
        super().show(file=file)
        _print_crash_footer()


_CLIGroupBase: type[click.Group] = _RICH_GROUP_BASE


class _CLIGroup(_CLIGroupBase):
    _commands_registered: bool = False

    def _ensure_commands_registered(self) -> None:
        if not self._commands_registered:
            _register_commands()
            self._commands_registered = True

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._ensure_commands_registered()
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        self._ensure_commands_registered()
        return super().get_command(ctx, cmd_name)

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple:
        self._ensure_commands_registered()
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
    help="ᘚᘛ Kagan — one orchestration layer to rule them all.",
    epilog=(
        "Common workflows:\n"
        "  kagan                     Launch the Kanban TUI\n"
        "  kagan chat 'fix the bug'  Single-shot agent prompt\n"
        "  kagan web                 Open the web dashboard\n"
        "  kagan doctor              Check system health\n\n"
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
    from kagan.core._logging import configure_logging

    _sanitize_startup_environment()
    configure_logging(verbose=verbose)

    _register_commands()

    latest = maybe_check_for_updates(skip=skip_update_check)
    if latest:
        click.echo(f"hint: kagan {latest} available. Run `kagan update`.")

    if ctx.invoked_subcommand is None:
        import sys

        if sys.stdout.isatty():
            click.echo("ᘚᘛ Kagan — launching TUI. Run 'kagan --help' for all commands.")
        tui_cmd = cli.commands.get("tui")
        if tui_cmd is None:
            raise click.ClickException("TUI command not available")
        ctx.invoke(tui_cmd)


def _plugins_cli_enabled() -> bool:
    import os

    value = os.environ.get("KAGAN_ENABLE_PLUGIN_CLI", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _register_commands() -> None:
    _sanitize_startup_environment()
    if getattr(cli, "_commands_registered", False):
        return

    from kagan.cli.chat import chat
    from kagan.cli.doctor import doctor
    from kagan.cli.imports import import_cmd
    from kagan.cli.list_projects import list_projects
    from kagan.cli.mcp import mcp
    from kagan.cli.plugins import plugins
    from kagan.cli.reset import reset
    from kagan.cli.serve import serve
    from kagan.cli.tools import tools
    from kagan.cli.tui import tui
    from kagan.cli.update import update
    from kagan.cli.web import web

    cli.add_command(tui)
    cli.add_command(chat)
    cli.add_command(doctor)
    cli.add_command(import_cmd)
    cli.add_command(list_projects)
    cli.add_command(mcp)
    cli.add_command(serve)
    cli.add_command(reset)
    cli.add_command(update)
    cli.add_command(tools)
    cli.add_command(web)
    if _plugins_cli_enabled():
        cli.add_command(plugins)

    _sync_rich_click_groups(cli)
    cli._commands_registered = True
